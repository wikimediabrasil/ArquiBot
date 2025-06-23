import os
import requests
import re
import logging
from datetime import timedelta, timezone
from django.utils.timezone import now

from waybackpy import WaybackMachineSaveAPI
from .models import ArchiveLog, BotRunStats

# Setup logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_path = os.path.join(BASE_DIR, 'archivebot.log')

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
)

WIKIPEDIA_API_URL = "https://pt.wikipedia.org/w/api.php"

def get_recent_changes(last_hours=24):
    """Fetch recent changes on ptwiki in the past N hours."""
    rcend = now().astimezone(timezone.utc)
    rcstart = rcend - timedelta(hours=last_hours)

    logging.info(f"Fetching changes from {rcstart} to {rcend}")

    params = {
        "action": "query",
        "format": "json",
        "list": "recentchanges",
        "rcnamespace": 0,
        "rctype": "edit|new",
        "rcprop": "title|ids|timestamp",
        "rcstart": rcstart.isoformat(),
        "rcend": rcend.isoformat(),
    }

    titles = set()
    rccontinue = None

    while True:
        if rccontinue:
            params['rccontinue'] = rccontinue

        response = requests.get(WIKIPEDIA_API_URL, params=params)
        data = response.json()

        changes = data.get("query", {}).get("recentchanges", [])
        for item in changes:
            titles.add(item["title"])

        if "continue" in data:
            rccontinue = data["continue"]["rccontinue"]
        else:
            break

    logging.info(f"Number of articles fetched: {len(titles)}")
    if not titles:
        logging.warning("No recent changes found. Try using a wider time range or checking API status.")

    return list(titles)

def get_article_content(title):
    """Fetch full wikitext content of a Wikipedia article."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "rvprop": "content",
        "titles": title,
    }
    response = requests.get(WIKIPEDIA_API_URL, params=params)
    pages = response.json().get("query", {}).get("pages", {})
    return next(iter(pages.values())).get("revisions", [{}])[0].get("*", "")

def extract_citar_web_urls(text):
    """Extract only URLs inside {{citar web}} templates using regex."""
    return re.findall(r'\{\{[Cc]itar\s+web[^\}]*?url\s*=\s*(https?://[^\|\s\}]+)', text)

def is_url_alive(url, timeout=10):
    """Check if a URL is alive by sending a HEAD request."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False

def archive_url(url):
    """Archive a URL using the Wayback Machine."""
    try:
        save_api = WaybackMachineSaveAPI(
            url,
            user_agent="ptwiki-archivebot/1.0 (https://pt.wikipedia.org/wiki/User:YourBotUsername)"
        )
        archive = save_api.save()
        logging.info(f"Archived: {url} → {archive.archive_url}")
        return archive.archive_url
    except Exception as e:
        logging.error(f"Failed to archive {url}: {e}")
        return None

def run_archive_bot():
    """Main archive bot runner for ptwiki using {{citar web}}."""
    logging.info("Bot started.")
    titles = get_recent_changes(last_hours=24 * 7)  # Scan past 7 days for testing

    unique_articles = set()
    total_urls = 0
    archived_count = 0

    for title in titles:
        logging.info(f"Checking article: {title}")
        content = get_article_content(title)
        urls = extract_citar_web_urls(content)

        if not urls:
            logging.info(f"No citar web URLs found in: {title}")
            continue

        unique_articles.add(title)

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
                logging.warning(f"Could not save log to DB: {e}")

    # Save daily summary to BotRunStats
    today = now().date()
    if total_urls > 0:
        try:
            BotRunStats.objects.update_or_create(
                run_date=today,
                defaults={
                    'articles_scanned': len(unique_articles),
                    'urls_checked': total_urls,
                    'urls_archived': archived_count,
                    'edits_made': len(unique_articles)
                }
            )
            logging.info("BotRunStats updated.")
        except Exception as e:
            logging.warning(f"Failed to update BotRunStats: {e}")

    logging.info("Bot finished.")
