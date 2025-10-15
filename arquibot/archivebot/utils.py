import requests
import logging as logginglib
import traceback
import json
import mwparserfromhell
from bs4 import BeautifulSoup
from django.utils.timezone import now
from datetime import timedelta
from waybackpy import WaybackMachineSaveAPI
from urllib.parse import quote
from django.conf import settings
from .models import BotRunStats, ArchivedCitation

SKIPPED_URL_PREFIXES = settings.SKIPPED_URL_PREFIXES
LAST_HOURS = settings.LAST_HOURS
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
USER_AGENT = settings.USER_AGENT
WIKIPEDIA_URL = settings.WIKIPEDIA_URL
ARQUIBOT_TOKEN = settings.ARQUIBOT_TOKEN

ACTION_API = WIKIPEDIA_URL + "/w/api.php"
REST_API = WIKIPEDIA_URL + "/w/rest.php/v1"

logging = logginglib.getLogger("arquibot")

HEADERS = {
    "Authorization": f"Bearer {ARQUIBOT_TOKEN}",
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
}
WAYBACK_PY_MAX_TRIES = 3


def get_recent_changes_with_diff(last_hours=LAST_HOURS):
    """Fetch recent changes with diffs using generator=recentchanges, rvdiffto=prev and grccontinue."""
    end_time = now().astimezone()
    start_time = end_time - timedelta(hours=last_hours)

    params = {
        "action": "query",
        "format": "json",
        "generator": "recentchanges",
        "grcnamespace": 0,
        "grclimit": "max",
        "grcshow": "!bot",
        "grcstart": end_time.isoformat(),
        "grcend": start_time.isoformat(),
        "prop": "revisions",
        "rvprop": "ids|timestamp|user|comment|content",
        "rvdiffto": "prev",
    }

    all_pages = {}

    while True:
        response = requests.get(ACTION_API, params=params, headers=HEADERS)
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        all_pages.update(pages)  # merge new batch into results

        # Handle continuation
        if "continue" in data:
            params.update(data["continue"])  # adds "grccontinue"
        else:
            break

    return all_pages.values()

def fetch_current_wikitext_ptwiki(title: str, api_url: str = ACTION_API, timeout: int=REQUEST_TIMEOUT) -> str | None:
    # Fetch full current wikitext for an article from wikipedia.org.
    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "formatversion": 2,
        "titles": title,
    }
    try:
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None
        revs = pages[0].get("revisions", [])
        if not revs:
            return None
        return revs[0]["slots"]["main"]["content"]
    except Exception as e:
        logging.warning(f"Failed to fetch full wikitext for '{title}': {e}")
        return None

def extract_inserted_wikitext(diff_html, revision=None, full_wikitext=None):
    """
    Extract inserted wikitext from a diff HTML.
    Falls back to the full revision content or full page content if no <ins> tags are found.
    Always returns a string.
    """
    # Try extracting inserted content from diff <ins> tags
    if diff_html:
        soup = BeautifulSoup(diff_html, "html.parser")
        inserted_texts = [ins.get_text() for ins in soup.find_all("ins")]
        if inserted_texts:
            return "\n".join(inserted_texts)

    # Fallback to revision content
    if revision:
        content = ""
        if "slots" in revision and "main" in revision["slots"]:
            content = revision["slots"]["main"].get("*") or ""
        elif "content" in revision:
            content = revision["content"] or ""
        return content

    # Final fallback: full wikitext passed explicitly
    if full_wikitext:
        return full_wikitext

    # Nothing found → return empty string
    return ""

def extract_citar_templates_mwparser(wikitext):
    """Use mwparserfromhell to extract all citar templates"""
    wikicode = mwparserfromhell.parse(wikitext)
    return [
        template for template in wikicode.filter_templates()
        if template.name.strip().lower().startswith("citar ")
    ]

def is_url_alive(url, timeout: int=REQUEST_TIMEOUT):
    """Checks if a URL is alive (2xx or 3xx status)."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        logging.info(f"Checked URL {url}, status code: {response.status_code}")
        return response.status_code < 400
    except requests.RequestException as e:
        logging.warning(f"URL check failed for {url}: {str(e)}")
        return False

def archive_url(url):
    """Try to archive a URL once, with detailed logging."""
    logging.info(f"Attempting to archive URL: {url}")

    try:
        save_api = WaybackMachineSaveAPI(
            url,
            USER_AGENT,
            WAYBACK_PY_MAX_TRIES,
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
        availability_resp = requests.get("https://archive.org/wayback/available", params={"url": url}, timeout=30)
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

def extract_citar_templates_as_strings(text):
    """
    Extract all full {{citar ...}} templates (as strings) from wikitext.
    Case-insensitive and supports all known citar templates using mwparserfromhell.
    """
    wikicode = mwparserfromhell.parse(text)
    templates = []
    for template in wikicode.filter_templates():
        name = template.name.strip().lower()
        if name.startswith("citar "):
            templates.append(str(template))  # convert full template back to string
    return templates

def parse_citar_template(template):
    """Extract fields from a mwparserfromhell.Template as a dictionary (case-insensitive keys)."""
    fields = {}
    for param in template.params:
        key = str(param.name).strip().lower()
        val = str(param.value).strip()
        fields[key] = val
    return fields

def build_updated_template(template_name, fields):
    """Rebuild a citation template string from its name and fields."""
    parts = [f'{{{{{template_name}']
    for k, v in fields.items():
        parts.append(f'{k}={v}')
    parts.append('}}')
    return '|'.join(parts)

def process_citation_template(title, template, archive_url, archive_date, url_is_dead=False):
    """Process the citation template"""
    logging.info(f"Processing template for article: {title}")

    param_names = [param.name.strip().lower() for param in template.params]
    if 'arquivourl' in param_names or 'wayb' in param_names:
        logging.info(f"Skipping {title}: Template already has arquivourl or wayb")
        return None

    if not template.has("url") or not template.get("url").value.strip():
        logging.warning(f"Skipping ArchivedCitation for {title}: Missing or empty 'url'")
        return None

    original_template = str(template)
    template.add("arquivourl", archive_url)
    template.add("arquivodata", archive_date.strftime("%Y-%m-%d"))

    if url_is_dead:
        template.add("urlmorta", "sim")
    else:
        if template.has("urlmorta"):
            template.remove("urlmorta")

    updated = str(template)

    try:
        ArchivedCitation.objects.create(
            article_title=title,
            original_template=original_template,
            updated_template=updated,
            url=template.get("url").value.strip(),
            arquivourl=archive_url,
            arquivodata=archive_date,
            urlmorta=url_is_dead
        )
        logging.info(f"Saved ArchivedCitation for {title}")
    except Exception as e:
        logging.warning(f"Failed to save ArchivedCitation for {title}: {e}")
        logging.debug(traceback.format_exc())

    return updated

def extract_external_links_from_text(text):
    """Extract external URLs from plain text using mwparserfromhell external link filter."""
    wikicode = mwparserfromhell.parse(text)
    urls = set()

    # Extract URLs from external links [[...]]
    for ext_link in wikicode.filter_external_links():
        url = str(ext_link.url).strip()
        if url:
            urls.add(url)

    return list(urls)

def admin_panel_check_func(url: str, archived_url_map: dict) -> str | None:
    """
    Check if the given URL has an archived template in the local admin panel data.

    Args:
        url (str): The original URL to check.
        archived_url_map (dict): A dictionary mapping original URLs to archived template strings.

    Returns:
        str or None: The archived template string if found, else None.
    """
    return archived_url_map.get(url)

def get_page_data(title: str):
    try:
        resp = requests.get(REST_API + "/page/" + quote(title).replace("/", "%2F"), headers=HEADERS)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error(f"Failed to fetch article '{title}': {e}")
        raise e

def update_archived_templates_in_article(title: str, archived_url_map: dict, edit_comment: str = "Update archived URLs via bot"):
    """
    Fetch the Wikipedia page, replace citation templates with archived versions where available,
    and commit the updated wikitext back to the wiki.

    Args:
        title (str): Wikipedia page title to edit (e.g. "User:YourBot/sandbox").
        archived_url_map (dict): Map original URLs to archived template strings.
        edit_comment (str): Edit summary/comment.

    Returns:
        tuple: (success: bool, message: str)
    """
    if not hasattr(archived_url_map, "values") or not archived_url_map.values():
        return False, "No templates to update"

    page_data = get_page_data(title)
    wikitext = page_data.get("source", "")
    latest_id = page_data.get("latest", {}).get("id")
    if not wikitext or not latest_id:
        return False, "Failed to get wikitext or revision ID."

    # Step 2: Parse wikitext with mwparserfromhell
    wikicode = mwparserfromhell.parse(wikitext)
    templates = wikicode.filter_templates()
    changed = False

    # Step 3: Iterate over citation templates and replace if archived version exists
    for template in templates:
        if not template.name.lower().startswith("citar "):
            continue

        if not template.has("url"):
            continue

        url = str(template.get("url").value).strip()

        archived_template_str = admin_panel_check_func(url, archived_url_map)
        if archived_template_str:
            # Replace the whole template with the archived one
            try:
                new_template = mwparserfromhell.parse(archived_template_str).filter_templates()[0]
                wikicode.replace(template, new_template)
                changed = True
            except Exception as e:
                # Log parsing errors but continue
                logging.error(f"Error parsing archived template for URL {url}: {e}")

    if not changed:
        return False, "No archived templates were applied. Article unchanged."

    # Step 4: Commit updated wikitext back to Wikipedia
    payload = {
        "source": str(wikicode),
        "comment": edit_comment,
        "latest": {"id": latest_id}
    }

    try:
        put_resp = requests.put(REST_API + "/page/" + title.replace(" ", "_"), headers=HEADERS, data=json.dumps(payload))
        put_resp.raise_for_status()
        return True, f"Successfully updated archived templates in '{title}'."
    except Exception as e:
        return False, f"Failed to commit edit: {e}"


def run_article(title):
    logging.info("Archive Bot started.")
    logging.info(f"running on one page: {title}")
    page_data = get_page_data(title)
    wikitext = page_data.get("source", "")
    archived_url_map = archived_url_map_from_wikitext({}, wikitext, title)
    success, msg = update_archived_templates_in_article(title, archived_url_map)
    logging.info(f"Article update result for {title}: {msg}")


def archived_url_map_from_wikitext(initial_archived_url_map, wikitext, title):
    archived_url_map = initial_archived_url_map

    citar_templates = extract_citar_templates_mwparser(wikitext)

    # Map URLs to templates
    url_to_templates = {}
    for tmpl in citar_templates:
        if tmpl.has("url"):
            url = str(tmpl.get("url").value).strip()
            if url:
                url_to_templates.setdefault(url, []).append(tmpl)

    processed_urls = set()

    for url, templates in url_to_templates.items():
        if any([url.lower().startswith(prefix) for prefix in SKIPPED_URL_PREFIXES]):
            logging.info(f"Skipping DOI or archived URL: {url}")
            continue

        if url in processed_urls:
            continue
        processed_urls.add(url)

        # Skip templates already archived in DB
        templates_to_process = [
            tmpl for tmpl in templates
            if url not in archived_url_map and not tmpl.has("arquivourl") and not tmpl.has("wayb")
        ]

        if not templates_to_process:
            logging.info(f"{url} in {title} already archived.")
            continue

        # Archive the URL if not in DB
        archive_link = archived_url_map.get(url)
        if not archive_link:
            archive_link = archive_url(url)
        url_is_dead = not is_url_alive(url)

        if not archive_link:
            logging.info(f"Archiving failed for {url}")
            continue

        archived = False
        for tmpl in templates_to_process:
            updated = process_citation_template(
                title=title,
                template=tmpl,
                archive_url=archive_link,
                archive_date=now().date(),
                url_is_dead=url_is_dead
            )
            if updated:
                archived = True
                archived_url_map[url] = str(updated)

        if archived:
            logging.info(f"Archived URL added to template: {url}")

        return archived_url_map


def run_archive_bot(interval_hours: int = 168):
    logging.info("Archive Bot started.")

    # Fetch recent changes
    recent_changes = get_recent_changes_with_diff(last_hours=interval_hours) # recent_changes = get_recent_changes_with_diff(grclimit=50, last_hours=interval_hours)

    if not recent_changes:
        logging.info("No recent changes found.")
        return

    logging.info(f"Found {len(recent_changes)} recent changes to process.")

    # Preload all archived URLs from the DB
    archived_url_map = {
        entry.url: entry.updated_template
        for entry in ArchivedCitation.objects.all()
    }
    logging.info(f"Loaded {len(archived_url_map)} archived URLs from database.")

    unique_articles = set()
    total_urls = 0
    archived_count = 0
    real_edits_made = 0

    for page in recent_changes:
        title = page.get("title")
        revisions = page.get("revisions", [])
        if not title or not revisions:
            logging.warning(f"Skipping {title or 'Unknown'}: missing revision content")
            continue

        rev = revisions[0]
        diff_html = rev.get("diff", {}).get("*", "")
        rev_content = rev.get("content")  # Full wikitext if available

        # Extract inserted wikitext, fallback to full revision content
        content_to_scan = extract_inserted_wikitext(diff_html) or rev_content
        if not content_to_scan or not content_to_scan.strip():
            # Last resort: fetch current wikitext from wiki
            content_to_scan = fetch_current_wikitext_ptwiki(title) or ""
            if not content_to_scan.strip():
                logging.info(f"Skipping {title}: no content to scan")
                continue

        unique_articles.add(title)
        real_edits_made += 1

        archived_url_map = archived_url_map_from_wikitext(archived_url_map, content_to_scan, title)

        # Push updates to Wikipedia using preloaded archived_url_map
        success, msg = update_archived_templates_in_article(title, archived_url_map)
        if success:
            real_edits_made += 1
        logging.info(f"Article update result for {title}: {msg}")

    # Save bot stats
    try:
        BotRunStats.objects.update_or_create(
            run_date=now(),
            defaults={
                "articles_scanned": len(unique_articles),
                "urls_checked": total_urls,
                "urls_archived": archived_count,
                "edits_made": real_edits_made,
            }
        )
        logging.info(f"BotRunStats saved: Articles: {len(unique_articles)}, URLs checked: {total_urls}, URLs archived: {archived_count}, Edits made: {real_edits_made}")
    except Exception as e:
        logging.error(f"Failed to save BotRunStats: {e}")

    logging.info("Archive Bot finished.")
