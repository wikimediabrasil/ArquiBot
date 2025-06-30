import requests
import re
import logging
import time
from bs4 import BeautifulSoup
from django.utils.timezone import now
from datetime import timedelta
from waybackpy import WaybackMachineSaveAPI
from .models import ArchiveLog, BotRunStats

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('archivebot.log', encoding='utf-8'),
        logging.StreamHandler()  # logs to console
    ]
)

WIKIPEDIA_API_URL = "https://pt.wikipedia.org/w/api.php"

def get_recent_changes_with_diff(grclimit=10, last_hours=1):
    """Fetch recent changes with diffs using generator=recentchanges and rvdiffto=prev."""
    end_time = now().astimezone()
    start_time = end_time - timedelta(hours=last_hours)

    params = {
        "action": "query",
        "format": "json",
        "generator": "recentchanges",
        "grcnamespace": 0,
        "grclimit": grclimit,
        "grcshow": "!bot",
        "grcstart": end_time.isoformat(),
        "grcend": start_time.isoformat(),
        "prop": "revisions",
        "rvprop": "ids|timestamp|user|comment|content",
        "rvdiffto": "prev",
    }

    response = requests.get(WIKIPEDIA_API_URL, params=params)
    data = response.json()
    pages = data.get("query", {}).get("pages", {})
    return pages.values()

def extract_inserted_text_from_diff(diff_html):
    """Parse diff HTML and extract inserted text."""
    if not diff_html:
        return ""
    soup = BeautifulSoup(diff_html, "html.parser")
    inserted_texts = [ins.get_text() for ins in soup.find_all("ins")]
    return "\n".join(inserted_texts)

def extract_citar_web_urls(text):
    """Extract URLs from citar web templates in inserted text."""
    pattern = re.compile(r'\{\{[Cc]itar\s+web.*?\|.*?[Uu][Rr][Ll]\s*=\s*(https?://[^\|\}\s]+)', re.DOTALL)
    return [match.group(1) for match in pattern.finditer(text)]

def is_url_alive(url, timeout=10):
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        logging.info(f"Checked URL {url}, status code: {response.status_code}")
        return response.status_code == 200
    except requests.RequestException as e:
        logging.warning(f"URL check failed for {url}: {e}")
        return False

def archive_url(url):
    """Try to archive a URL once, with detailed logging."""
    logging.info(f"Attempting to archive URL: {url}")

    time.sleep(1) # Wait 1 second before archiving to avoid overwhelming Wayback server

    try:
        save_api = WaybackMachineSaveAPI(
            url,
            user_agent="ptwiki-archivebot/1.0 (https://pt.wikipedia.org/wiki/User:YourBotUsername)"
        )
        archive = save_api.save()
        if hasattr(archive, "archive_url") and archive.archive_url:
            logging.info(f"Archived via WaybackPy: {url} → {archive.archive_url}")
            return archive.archive_url
        else:
            logging.warning(f"WaybackPy returned no archive_url for {url}")
    except Exception as e:
        logging.error(f"WaybackPy failed for {url}: {e}")

    # Fallback to check if URL already archived
    try:
        logging.info(f"Trying fallback Wayback availability API for: {url}")
        availability_resp = requests.get("https://archive.org/wayback/available", params={"url": url}, timeout=15)
        data = availability_resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available"):
            archive_url = snapshot.get("url")
            logging.info(f"Found existing archive: {url} → {archive_url}")
            return archive_url
        else:
            logging.warning(f"No archive found for: {url}")
    except Exception as e:
        logging.error(f"Exception in fallback availability API for {url}: {e}")

    return None

def run_archive_bot():
    logging.info("Archive Bot started.")

    recent_changes = get_recent_changes_with_diff(grclimit=50, last_hours=1)

    unique_articles = set()
    total_urls = 0
    archived_count = 0
    real_edits_made = 0

    for page in recent_changes:
        title = page.get("title")
        revisions = page.get("revisions", [])
        if not title or not revisions:
            continue

        unique_articles.add(title)

        rev = revisions[0]
        diff_html = rev.get("diff", {}).get("*", "")
        inserted_content = extract_inserted_text_from_diff(diff_html)

        if not inserted_content.strip():
            logging.info(f"No inserted content in {title}")
            continue

        real_edits_made += 1

        urls = extract_citar_web_urls(inserted_content)
        if not urls:
            logging.info(f"No citar web URLs found in inserted content for {title}")
            continue

        for url in urls:
            total_urls += 1
            if is_url_alive(url):
                archive_link = archive_url(url)
                status = "archived" if archive_link else "failed"
                message = archive_link or "Archiving failed"
                if archive_link:
                    archived_count += 1
            else:
                archive_link = None
                status = "skipped"
                message = "Dead link — not archived"

            try:
                ArchiveLog.objects.create(
                    url=url,
                    article_title=title,
                    status=status,
                    message=message,
                    timestamp=now()
                )
            except Exception as e:
                logging.warning(f"Failed to save ArchiveLog for {url} ({title}): {e}")

    try:
        BotRunStats.objects.update_or_create(
            run_date=now(),
            defaults={
                'articles_scanned': len(unique_articles),
                'urls_checked': total_urls,
                'urls_archived': archived_count,
                'edits_made': real_edits_made,
            }
        )
        logging.info(f"BotRunStats saved: Articles: {len(unique_articles)}, URLs checked: {total_urls}, URLs archived: {archived_count}, Real edits: {real_edits_made}")
    except Exception as e:
        logging.error(f"Failed to save BotRunStats: {e}")

    logging.info("Archive Bot finished.")
