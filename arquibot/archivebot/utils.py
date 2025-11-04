import logging
from typing import List
from datetime import time
from datetime import datetime
from datetime import date
from datetime import timedelta

import requests
import mwparserfromhell
from django.utils.timezone import now
from django.utils.timezone import make_aware
from django.conf import settings
from bs4 import BeautifulSoup

from archivebot.archiving import ArchivedURL
from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck
from archivebot.models import RecentChanges
from archivebot.models import Diff

SKIPPED_URL_PREFIXES = settings.SKIPPED_URL_PREFIXES
LAST_HOURS = settings.LAST_HOURS
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
USER_AGENT = settings.USER_AGENT
ARQUIBOT_TOKEN = settings.ARQUIBOT_TOKEN

logger = logging.getLogger("arquibot")

HEADERS = {
    "Authorization": f"Bearer {ARQUIBOT_TOKEN}",
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
}


def get_recent_changes_with_diff(last_hours=LAST_HOURS):
    """Fetch recent changes with diffs using generator=recentchanges, rvdiffto=prev and grccontinue."""
    end_time = now().astimezone()
    start_time = end_time - timedelta(hours=last_hours)
    return get_recent_changes_from_start_end_time(start_time, end_time)


def get_recent_changes_from_dates(start_date: date, end_date: date):
    start_time = make_aware(datetime.combine(start_date, time.min))
    end_time = make_aware(datetime.combine(end_date, time.max))
    return get_recent_changes_from_start_end_time(start_time, end_time)


def get_recent_changes_from_start_end_time(start_time: datetime, end_time: datetime) -> List[Diff]:
    rc = RecentChanges(start_time, end_time, wikipedia=Wikipedia.get())
    rc.load()
    return rc.combined_diffs()

def fetch_current_wikitext(title: str, timeout: int=REQUEST_TIMEOUT) -> str | None:
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
    wikipedia = Wikipedia.get()
    try:
        r = requests.get(wikipedia.action_api(), params=params, headers=HEADERS, timeout=timeout)
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
        logger.warning(f"Failed to fetch full wikitext for '{title}': {e}")
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
    result = [
        template for template in wikicode.filter_templates()
        if template.name.strip().lower().startswith("citar ")
    ]
    return result

def has_citar_templates_mwparser(wikitext):
    """Checks if wikitext has citar templates with URLs"""
    templates = extract_citar_templates_mwparser(wikitext)
    return any(template.has("url") for template in templates )

def is_url_alive(url, timeout: int=REQUEST_TIMEOUT):
    """Checks if a URL is alive (2xx or 3xx status)."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        logger.info(f"Checked URL {url}, status code: {response.status_code}")
        # we are ignoring 401, 402 and 403
        return response.status_code < 404
    except requests.RequestException as e:
        logger.warning(f"URL check failed for {url}: {str(e)}")
        return False

def archive_url(url):
    arq = ArchivedURL(url)
    arq.archive()
    return arq.archive_url

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

def process_citation_template(title, template, archive_url, url_is_dead=False):
    """Process the citation template"""
    logger.info(f"Processing template for article: {title} with archive url {archive_url}")

    param_names = [param.name.strip().lower() for param in template.params]
    if 'arquivourl' in param_names or 'wayb' in param_names:
        logger.info(f"Skipping {title}: Template already has arquivourl or wayb")
        return None

    if not template.has("url") or not template.get("url").value.strip():
        logger.warning(f"Skipping ArchivedCitation for {title}: Missing or empty 'url'")
        return None

    url = template.get("url").value.strip()
    arq = ArchivedURL.already_archived(url, archive_url)
    timestamp = arq.archive_timestamp

    template.add("wayb", timestamp)

    if url_is_dead:
        template.add("urlmorta", "sim")
    else:
        if template.has("urlmorta"):
            template.remove("urlmorta")

    updated = str(template)
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

def update_archived_templates_in_article(article: ArticleCheck, archived_url_map: dict):
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
        return False, "no templates to update"

    page_data = article.page_data()
    wikitext = page_data.get("source", "")
    latest_id = page_data.get("latest", {}).get("id")
    if not wikitext or not latest_id:
        logger.error(f"page_data={page_data}")
        return False, "failed to get wikitext or revision ID."

    # Step 2: Parse wikitext with mwparserfromhell
    wikicode = mwparserfromhell.parse(wikitext)
    templates = wikicode.filter_templates()
    changed = False

    urls_archived = set()

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
                urls_archived.add(url)
            except Exception as e:
                # Log parsing errors but continue
                logger.error(f"Error parsing archived template for URL {url}: {e}")

    if not changed:
        return False, "No archived templates were applied. Article unchanged."

    # Step 4: Commit updated wikitext back to Wikipedia
    count = len(urls_archived)
    word = "URLs" if count > 1 else "URL"
    comment = f"Arquivamento de {count} {word}"

    try:
        article.edit_and_save(new_source=str(wikicode), comment=comment, latest_id=latest_id)
        return True, f"{article} Successfully updated archived templates in."
    except Exception as e:
        return False, f"Failed to commit edit: {e}"


def run_article(title):
    logger.info("Archive Bot started.")
    logger.info(f"running on one page: {title}")
    wikipedia = Wikipedia.get()
    article: ArticleCheck = ArticleCheck.objects.create(
        wikipedia=wikipedia,
        title=title,
    )
    wikitext = article.source()
    archived_url_map = archived_url_map_from_wikitext({}, wikitext, article)
    success, msg = update_archived_templates_in_article(article, archived_url_map)
    logger.info(f"Article update result for '{title}': {msg}")


def archived_url_map_from_wikitext(initial_archived_url_map, wikitext, article: ArticleCheck):
    archived_url_map = initial_archived_url_map
    if not archived_url_map:
        archived_url_map = {}

    citar_templates = extract_citar_templates_mwparser(wikitext)
    logger.debug(f"{article} citar templates extracted ({len(citar_templates)}): {citar_templates}")

    # Map URLs to templates
    url_to_templates = {}
    for tmpl in citar_templates:
        if tmpl.has("url"):
            url = str(tmpl.get("url").value).strip()
            if url:
                url_to_templates.setdefault(url, []).append(tmpl)

    processed_urls = set()
    for url, templates in url_to_templates.items():
        logger.debug(f"url={url}, template count={len(templates)}")
        for template in templates:
            logger.debug(f"url={url}, template={template}")

    title = article.title

    for url, templates in url_to_templates.items():
        check: UrlCheck = UrlCheck.objects.create(
            article=article,
            url=url,
        )
        if any([url.lower().startswith(prefix) for prefix in SKIPPED_URL_PREFIXES]):
            logger.info(f"Skipping DOI or archived URL: {url}")
            check.set_ignored_permalink()
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
            logger.debug(f"url={url} in [{title}] already archived.")
            check.set_ignored_archived()
            continue

        # Archive the URL if not in DB
        archive_link = archived_url_map.get(url)
        if not archive_link:
            archive_link = archive_url(url)
        url_is_dead = not is_url_alive(url)

        if not archive_link:
            logger.info(f"Archiving failed for {url}")
            check.set_failed(url_is_dead)
            continue

        archived = False
        for tmpl in templates_to_process:
            updated = process_citation_template(
                title=title,
                template=tmpl,
                archive_url=archive_link,
                url_is_dead=url_is_dead
            )
            if updated:
                archived = True
                check.set_archived(archive_link,url_is_dead)
                archived_url_map[url] = str(updated)

        if archived:
            logger.info(f"Archived URL added to template: {url}")

    return archived_url_map


def run_archive_bot(interval_hours: int = 168):
    recent_changes = get_recent_changes_with_diff(last_hours=interval_hours) # recent_changes = get_recent_changes_with_diff(grclimit=50, last_hours=interval_hours)
    run_on_recent_changes(recent_changes)


def run_rc_date(date):
    recent_changes = get_recent_changes_from_dates(date, date)
    run_on_recent_changes(recent_changes)


def run_on_recent_changes(diffs: List[Diff]):
    logger.info("Archive Bot started.")

    if not diffs:
        logger.info("No recent changes found.")
        return

    logger.info(f"Found {len(diffs)} diffs to process.")

    archived_url_map = {}
    articles = ArticleCheck.create_from_recent_changes_diffs(diffs)

    for article in articles:
        inserted_wikitext = article.diff_inserted_wikitext()

        if not has_citar_templates_mwparser(inserted_wikitext):
            inserted_wikitext = inserted_wikitext.replace("\n", "\\n")
            logger.debug(f"{article} skipping: no citation templates in diff")
            continue

        logger.info(f"{article} has citar templates in diff")
        wikitext = article.source()

        archived_url_map = archived_url_map_from_wikitext(archived_url_map, wikitext, article)
        success, msg = update_archived_templates_in_article(article, archived_url_map)
        logger.info(f"{article} result: {msg}")

    logger.info("Archive Bot finished.")
