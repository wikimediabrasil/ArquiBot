import os
import requests
import re
import logging
import time
from datetime import timedelta, timezone
from django.utils.timezone import now
from urllib.parse import quote
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
        "rcstart": rcend.isoformat(),
        "rcend": rcstart.isoformat(),
        "rclimit": "max",
    }

    changes = []
    rccontinue = None

    while True:
        if rccontinue:
            params['rccontinue'] = rccontinue

        response = requests.get(WIKIPEDIA_API_URL, params=params)
        logging.info(f"Recentchanges API URL: {response.url}")
        data = response.json()

        changes.extend(data.get("query", {}).get("recentchanges", []))

        if "continue" in data:
            rccontinue = data["continue"].get("rccontinue")
        else:
            break

    logging.info(f"Total recent changes fetched: {len(changes)}")
    return changes


def get_articles_with_full_revision_info(titles):
    """
    Fetch detailed revision info (including slots->main content) for multiple titles.
    Returns the raw API response JSON as-is.
    """
    if not titles:
        return {}

    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "revisions",
        "rvslots": "main",
        "rvprop": "ids|timestamp|user|comment|content",
        "titles": "|".join(titles),
    }
    response = requests.get(WIKIPEDIA_API_URL, params=params)
    logging.info(f"Revisions API URL: {response.url}")
    return response.json()


def extract_citar_web_urls(text):
    """Extract URLs only from {{citar web ... url=...}} templates."""
    return re.findall(r'\{\{[Cc]itar\s+web[^\}]*?url\s*=\s*(https?://[^\|\s\}]+)', text)


def is_url_alive(url, timeout=10):
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def archive_url(url):
    logging.info(f"Attempting to archive URL: {url}")

    if not is_url_alive(url):
        logging.warning(f"Skipping dead or unreachable URL: {url}")
        return None

    time.sleep(1)  # avoid hammering Wayback Machine

    try:
        save_api = WaybackMachineSaveAPI(
            url,
            user_agent="ptwiki-archivebot/1.0 (https://pt.wikipedia.org/wiki/User:YourBotUsername)"
        )
        archive = save_api.save()
        logging.info(f"Archived with waybackpy: {url} → {archive.archive_url}")
        return archive.archive_url
    except Exception as e:
        logging.error(f"Waybackpy archiving failed for {url}: {e}")

    # Fallback to direct HTTP GET on archive.org save endpoint
    try:
        fallback_url = "https://web.archive.org/save/" + quote(url, safe="")
        headers = {
            "User-Agent": "ptwiki-archivebot/1.0 (https://pt.wikipedia.org/wiki/User:YourBotUsername)"
        }
        fallback_response = requests.get(fallback_url, headers=headers, timeout=15)
        if fallback_response.status_code in [200, 302]:
            logging.info(f"Fallback archived: {url} → {fallback_url}")
            return fallback_url
        else:
            logging.warning(f"Fallback archiving failed for {url} with status {fallback_response.status_code}")
    except Exception as e:
        logging.error(f"Exception during fallback archiving for {url}: {e}")

    return None


def run_archive_bot():
    logging.info("Archive Bot started.")
    changes = get_recent_changes(last_hours=24 * 7)

    # Gather unique titles from recent changes
    titles = list({change["title"] for change in changes})

    batch_size = 50  # max titles per API request
    unique_articles = set()
    total_urls = 0
    archived_count = 0

    for i in range(0, len(titles), batch_size):
        batch = titles[i:i + batch_size]
        rev_data = get_articles_with_full_revision_info(batch)
        pages = rev_data.get("query", {}).get("pages", [])

        for page in pages:
            title = page.get("title")
            unique_articles.add(title)

            revisions = page.get("revisions", [])
            if not revisions:
                logging.info(f"No revisions found for {title}")
                continue

            # Get latest revision content
            content = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            urls = extract_citar_web_urls(content)

            if not urls:
                logging.info(f"No citar web URLs found in latest revision of {title}")
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
                    logging.warning(f"Failed to save ArchiveLog: {e}")

    # Update BotRunStats
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

    logging.info("Archive Bot finished.")
