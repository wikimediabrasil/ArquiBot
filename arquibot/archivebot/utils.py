import requests
import logging
import traceback
from bs4 import BeautifulSoup
from django.utils.timezone import now
from datetime import timedelta
from waybackpy import WaybackMachineSaveAPI
import mwparserfromhell
from .models import ArchiveLog, BotRunStats, ArchivedCitation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('archivebot.log', encoding='utf-8'),
        logging.StreamHandler()  # logs to console
    ]
)

def fetch_wikitext_for_title(title):
    """Fetch full wikitext content of a given page title from test.wikipedia.org."""
    TEST_WIKI_API = "https://test.wikipedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content",
        "rvslots": "main",
        "formatversion": 2,
    }
    try:
        response = requests.get(TEST_WIKI_API, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", [])
        if pages and "revisions" in pages[0]:
            return pages[0]["revisions"][0]["slots"]["main"]["content"]
        else:
            logging.warning(f"No revisions found for page: {title}")
            return None
    except Exception as e:
        logging.error(f"Failed to fetch wikitext for {title}: {e}")
        return None
    
def extract_inserted_text_from_diff(diff_html):
    """Parse diff HTML and extract inserted text."""
    if not diff_html:
        return ""
    soup = BeautifulSoup(diff_html, "html.parser")
    inserted_texts = [ins.get_text() for ins in soup.find_all("ins")]
    return "\n".join(inserted_texts)

def extract_citar_templates_mwparser(wikitext):
    """Use mwparserfromhell to extract all citar templates"""
    wikicode = mwparserfromhell.parse(wikitext)
    return [
        template for template in wikicode.filter_templates()
        if template.name.strip().lower().startswith("citar ")
    ]

def is_url_alive(url, timeout=1):
    """Checks if a URL is dead or alive"""
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

    # time.sleep()

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

"""def run_archive_bot():
    logging.info("Archive Bot started.")
    recent_changes = get_recent_changes_with_diff(grclimit=50, last_hours=2)

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
        wikicode = mwparserfromhell.parse(inserted_content)
        citar_templates = extract_citar_templates_mwparser(inserted_content)

        # Extract and deduplicate all URLs from citar templates
        url_to_templates = {}
        for tmpl in citar_templates:
            if tmpl.has("url"):
                url = str(tmpl.get("url").value).strip()
                if url:
                    url_to_templates.setdefault(url, []).append(tmpl)

        processed_urls = set()

        for url, templates in url_to_templates.items():
            if url.lower().startswith((
                "http://web.archive.org", 
                "https://web.archive.org", 
                "https://doi.org", 
                "http://doi.org", 
                "https://dx.doi.org"
                )):
                logging.info(f"Skipping DOI or archived URL: {url}")
                continue

            if url in processed_urls:
                continue  # skip duplicate
            processed_urls.add(url)
            total_urls += 1

            # Skip templates that already have arquivourl
            templates_to_process = [
                tmpl for tmpl in templates
                if not tmpl.has("arquivourl") and not tmpl.has("wayb")
            ]

            if not templates_to_process:
                logging.info(f"All templates for {url} in {title} already archived.")
                continue

            # Archive the URL
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

            if archived:
                archived_count += 1
                logging.info(f"Archived URL added to template: {url}")

            # Log archive result
            status = "archived" if archived else "skipped"
            message = archive_link if archived else "No citation updated"
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

    # Save bot run stats
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
        logging.info(f"BotRunStats saved: Articles: {len(unique_articles)}, URLs checked: {total_urls}, URLs archived: {archived_count}, Edits made: {real_edits_made}")
    except Exception as e:
        logging.error(f"Failed to save BotRunStats: {e}")

    logging.info("Archive Bot finished.")"""


def run_archive_bot():
    title = "User:Nayohmeee"
    logging.info(f"Running archive bot manually on static page: {title}")

    wikitext = fetch_wikitext_for_title(title)
    if not wikitext:
        logging.warning(f"No wikitext found for {title}")
        return

    citar_templates = extract_citar_templates_mwparser(wikitext)

    if not citar_templates:
        logging.info(f"No citar templates found in {title}")
        return

    url_to_templates = {}
    for tmpl in citar_templates:
        if tmpl.has("url"):
            url = str(tmpl.get("url").value).strip()
            if url:
                url_to_templates.setdefault(url, []).append(tmpl)

    processed_urls = set()
    total_urls = 0
    archived_count = 0

    for url, templates in url_to_templates.items():
        if url.lower().startswith((
            "http://web.archive.org",
            "https://web.archive.org",
            "https://doi.org",
            "http://doi.org",
            "https://dx.doi.org"
        )):
            logging.info(f"Skipping DOI or archived URL: {url}")
            continue

        if url in processed_urls:
            continue
        processed_urls.add(url)
        total_urls += 1

        templates_to_process = [
            tmpl for tmpl in templates
            if not tmpl.has("arquivourl") and not tmpl.has("wayb")
        ]

        if not templates_to_process:
            logging.info(f"All templates for {url} in {title} already archived.")
            continue

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

        if archived:
            archived_count += 1
            logging.info(f"Archived URL added to template: {url}")

        # Log archive result
        status = "archived" if archived else "skipped"
        message = archive_link if archived else "No citation updated"
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

    # Save bot run stats
    try:
        BotRunStats.objects.update_or_create(
            run_date=now(),
            defaults={
                'articles_scanned': 1,
                'urls_checked': total_urls,
                'urls_archived': archived_count,
                'edits_made': 1 if total_urls > 0 else 0,
            }
        )
        logging.info(f"BotRunStats saved: Articles: 1, URLs checked: {total_urls}, URLs archived: {archived_count}")
    except Exception as e:
        logging.error(f"Failed to save BotRunStats: {e}")

    logging.info("Archive Bot finished.")
