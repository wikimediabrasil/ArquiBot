from unittest.mock import patch, Mock, MagicMock
import requests
import requests_mock
import mwparserfromhell

from django.test import TestCase
from django.test import override_settings

from archivebot.utils import (
    get_recent_changes_with_diff,
    fetch_current_wikitext_ptwiki,
    extract_inserted_wikitext,
    extract_citar_templates_mwparser,
    extract_citar_templates_as_strings,
    extract_external_links_from_text,
    is_url_alive,
    archive_url,
    parse_citar_template,
    build_updated_template,
    process_citation_template,
    admin_panel_check_func,
    update_archived_templates_in_article,
    run_archive_bot
)

from archivebot.archiving import ArchivedURL
from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.wikipedia import WikipediaRestClient

@override_settings(
    ARQUIBOT_TOKEN="token123",
    WIKIPEDIA_CODE="test",
    USER_AGENT="ArquiBot/1.0 (https://pt.wikipedia.org/wiki/Usuário(a):ArquiBot)",
)
class TestUtils(TestCase):
    def setUp(self):
        self.wikipedia = Wikipedia.get()
        self.article = self.get_article("Test Page")
        self.rest_client = WikipediaRestClient(self.article)

    def get_article(self, title):
        wikipedia = Wikipedia.get()
        article = ArticleCheck.objects.create(wikipedia=wikipedia, title=title)
        return article

    def mock_rest_get(self, mocker, data):
        mocker.get(
            self.rest_client.endpoint(),
            json=data,
            status_code=200,
        )

    def mock_rest_put(self, mocker, data):
        mocker.put(
            self.rest_client.endpoint(),
            json=data,
            status_code=200,
        )

    def mock_page_source(self, mocker, source):
        data = {
            "source": source,
            "latest": {"id": 123},
        }
        self.mock_rest_get(mocker, data)

    def mock_edit_id(self, mocker, edit_id):
        self.mock_rest_put(mocker, {"latest": {"id": edit_id}})

    def mock_edit_fail(self, mocker):
        mocker.put(
            self.rest_client.endpoint(),
            json={"message": "edit failed"},
            status_code=400,
        )

    #  fetch_current_wikitext_ptwiki tests
    @patch("archivebot.utils.requests.get")
    def test_successful_fetch(self, mock_get):
        # Mock JSON response with one page and one revision
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "query": {
                "pages": [
                    {
                        "pageid": 123,
                        "title": "Test Article",
                        "revisions": [
                            {
                                "slots": {
                                    "main": {
                                        "content": "Full wikitext content here"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_resp

        result = fetch_current_wikitext_ptwiki("Test Article")
        self.assertEqual(result, "Full wikitext content here")
        mock_get.assert_called_once()
        called_params = mock_get.call_args[1]["params"]
        self.assertEqual(called_params["titles"], "Test Article")

    @patch("archivebot.utils.requests.get")
    def test_no_pages_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"query": {"pages": []}}
        mock_get.return_value = mock_resp

        result = fetch_current_wikitext_ptwiki("NoPage")
        self.assertIsNone(result)

    @patch("archivebot.utils.requests.get")
    def test_no_revisions_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "query": {"pages": [{"pageid": 1, "title": "EmptyPage", "revisions": []}]}
        }
        mock_get.return_value = mock_resp

        result = fetch_current_wikitext_ptwiki("EmptyPage")
        self.assertIsNone(result)

    @patch("archivebot.utils.requests.get")
    def test_http_error_returns_none_and_logs_warning(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_resp

        with self.assertLogs(level="WARNING") as log_cm:
            result = fetch_current_wikitext_ptwiki("HTTPErrorPage")
        self.assertIsNone(result)
        self.assertTrue(any("Failed to fetch full wikitext" in message for message in log_cm.output))

    @patch("archivebot.utils.requests.get", side_effect=requests.RequestException("Timeout"))
    def test_request_exception_returns_none_and_logs_warning(self, mock_get):
        with self.assertLogs(level="WARNING") as log_cm:
            result = fetch_current_wikitext_ptwiki("TimeoutPage")
        self.assertIsNone(result)
        self.assertTrue(any("Failed to fetch full wikitext" in message for message in log_cm.output))

    # extract_inserted_wikitext tests
    def test_extract_inserted_wikitext(self):
        html = '<div><ins class="diffchange">This is new content.</ins></div>'
        result = extract_inserted_wikitext(html)
        self.assertIn("This is new content.", result)

    def test_extract_inserted_wikitext_from_diff_with_none(self):
        result = extract_inserted_wikitext(None)
        self.assertEqual(result, "")

    def test_extract_inserted_wikitext_from_diff_with_empty_string(self):
        result = extract_inserted_wikitext("")
        self.assertEqual(result, "")

    def test_fetch_revision_content_with_slots(self):
    # revision with slots -> should pull from slots.main["*"]
        revision = {
            "slots": {
                "main": {
                    "*": "slot-based content"
                }
            }
        }
        result = extract_inserted_wikitext(None, revision)
        assert result == "slot-based content"


    def test_fetch_revision_content_with_content_key(self):
        # revision with legacy "content" -> should pull from content
        revision = {
            "content": "legacy content"
        }
        result = extract_inserted_wikitext(None, revision)
        assert result == "legacy content"


    def test_fetch_revision_content_with_empty_content(self):
        # revision with empty slots and content
        revision = {
            "slots": {"main": {"*": ""}},
            "content": ""
        }
        result = extract_inserted_wikitext(None, revision)
        assert result == ""

    def test_fetch_revision_content_with_missing_keys(self):
        # revision missing both slots and content
        revision = {}
        result = extract_inserted_wikitext(None, revision)
        assert result == ""  # or None, depending on your 

    # extract_citar_templates tests
    def test_extract_citar_templates_mwparser(self):
        text = '{{Citar web|url=https://example.org}} and {{Outro|name=value}}'
        result = extract_citar_templates_mwparser(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name.strip(), "Citar web")

    def test_extract_citar_templates_as_strings(self):
        text = '{{Citar web|url=https://example.org}} and {{Outro|name=value}}'
        result = extract_citar_templates_as_strings(text)
        self.assertEqual(result, ['{{Citar web|url=https://example.org}}'])

    # parse_citar_template and build_updated_template tests
    def test_parse_citar_template(self):
        tpl = mwparserfromhell.parse("{{Citar web|url=https://example.org|title=Example}}").filter_templates()[0]
        parsed = parse_citar_template(tpl)
        self.assertEqual(parsed["url"], "https://example.org")
        self.assertEqual(parsed["title"], "Example")

    # build_updated_template tests
    def test_build_updated_template(self):
        fields = {
            "url": "https://example.org",
            "wayb": "20250115032356",
        }
        result = build_updated_template("Citar web", fields)
        self.assertIn("url=https://example.org", result)
        self.assertIn("wayb=20250115032356", result)

    # extract_external_links_from_text tests
    def test_extract_external_links_from_text(self):
        text = 'Some text with https://example.org and another https://site.com/page'
        result = extract_external_links_from_text(text)
        self.assertIn("https://example.org", result)
        self.assertIn("https://site.com/page", result)

    # is_url_alive and archive_url tests
    @patch("archivebot.utils.requests.head")
    def test_is_url_alive_success(self, mock_head):
        mock_head.return_value.status_code = 200
        self.assertTrue(is_url_alive("https://example.org"))

    @patch("archivebot.utils.requests.head")
    def test_is_url_alive_fail(self, mock_head):
        mock_head.side_effect = requests.RequestException()
        self.assertFalse(is_url_alive("https://example.org"))

    # archive_url tests
    @patch("archivebot.utils.requests.get")
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save")
    def test_archive_url_success_and_fallback(self, mock_save, mock_get):
        # Original success test: WaybackPy returns archive_url
        mock_instance = Mock()
        mock_instance.archive_url = "https://web.archive.org/web/20230701/https://example.org"
        mock_save.return_value = None
        with patch("archivebot.archiving.WaybackMachineSaveAPI", return_value=mock_instance):
            result = archive_url("https://example.org")
            self.assertTrue(result.startswith("https://web.archive.org/web"))

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save")
    def test_archive_url_none_and_no_available(self, mock_save, mock_get):
        mock_save.return_value = None
        mock_get.side_effect = requests.RequestException()
        result = archive_url("https://noarchive.com")
        self.assertIsNone(result)

    @patch("archivebot.archiving.WaybackMachineSaveAPI")
    def test_archive_url_waybackpy_returns_no_archive_url(self, mock_wayback_class):
        # Setup mock instance with archive_url as None
        mock_instance = Mock()
        mock_instance.archive_url = None
        mock_instance.save.return_value = mock_instance  # save() returns the mock instance itself

        mock_wayback_class.return_value = mock_instance

        with self.assertLogs(level="WARNING") as log_cm:
            result = archive_url("https://noarchiveurl.test")

        self.assertIsNone(result)
        self.assertTrue(any("WaybackPy returned no archive_url" in message for message in log_cm.output))

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save", side_effect=Exception("WaybackPy error"))
    def test_archive_url_waybackpy_exception(self, mock_save, mock_get):
        # WaybackPy raises exception → fallback triggered
        mock_get.return_value.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "url": "http://web.archive.org/web/20250815214522/http://brokenlink.com/"
                }
            }
        }
        result = archive_url("https://brokenlink.com")
        self.assertEqual(result, "http://web.archive.org/web/20250815214522/http://brokenlink.com/")

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save", side_effect=Exception("Force fallback"))
    def test_archive_url_fallback_success(self, mock_save, mock_get):
        # Fallback returns available snapshot
        mock_get.return_value.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "url": "https://web.archive.org/web/20220101/https://fallback.com"
                }
            }
        }
        result = archive_url("https://fallback.com")
        self.assertEqual(result, "https://web.archive.org/web/20220101/https://fallback.com")

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save", side_effect=Exception("Force fallback"))
    def test_archive_url_fallback_no_archive_found(self, mock_save, mock_get):
        # Fallback returns no available archive
        mock_get.return_value.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": False
                }
            }
        }
        result = archive_url("https://notarchived.com")
        self.assertIsNone(result)

    @patch("archivebot.utils.requests.get", side_effect=Exception("Fallback API error"))
    @patch("archivebot.archiving.WaybackMachineSaveAPI.save", side_effect=Exception("Force fallback"))
    def test_archive_url_fallback_exception(self, mock_save, mock_get):
        # Fallback API itself fails
        result = archive_url("https://error.com")
        self.assertIsNone(result)

    # process_citation_template tests
    def test_process_citation_template(self):
        # --- Existing test: normal processing ---
        template_str = '{{Citar web|url=https://pt.wikipedia.org/}}'
        page_title = "Test Page"

        wikicode = mwparserfromhell.parse(template_str)
        tpl = wikicode.filter_templates()[0]

        updated_template = process_citation_template(
            title=page_title,
            template=tpl,
            archive_url='http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/',
            url_is_dead=True
        )

        self.assertIn("wayb=20250115032356", updated_template)
        self.assertIn("urlmorta=sim", updated_template)

        # --- New test case: skips if arquivourl or wayb already present ---
        template_str2 = '{{Citar web|url=https://pt.wikipedia.org/|arquivourl=http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/}}'
        wikicode2 = mwparserfromhell.parse(template_str2)
        tpl2 = wikicode2.filter_templates()[0]

        result2 = process_citation_template(
            title=page_title,
            template=tpl2,
            archive_url='http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/',
            url_is_dead=False
        )

        self.assertIsNone(result2)

        # --- New test case: skips if no url or empty url ---
        for template_str3 in ['{{Citar web|title=Example}}', '{{Citar web|url=  }}']:
            wikicode3 = mwparserfromhell.parse(template_str3)
            tpl3 = wikicode3.filter_templates()[0]

            result3 = process_citation_template(
                title=page_title,
                template=tpl3,
                archive_url='http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/',
                url_is_dead=False
            )

            self.assertIsNone(result3)

        # --- New test: url_is_dead is False AND urlmorta exists, so it should be removed ---
        template_str4 = '{{Citar web|url=https://example.org|urlmorta=sim}}'
        wikicode4 = mwparserfromhell.parse(template_str4)
        tpl4 = wikicode4.filter_templates()[0]

        updated_template4 = process_citation_template(
            title=page_title,
            template=tpl4,
            archive_url='http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/',
            url_is_dead=False
        )

        self.assertNotIn("urlmorta=", updated_template4)  # urlmorta should be removed

    # get_recent_changes_with_diff tests
    @patch('archivebot.utils.requests.get')
    def test_get_recent_changes_with_diff(self, mock_get):
        mock_get.return_value = MagicMock()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "query": {
                "pages": {
                    "12345": {
                        "title": "Test Page",
                        "revisions": [
                            {
                                "diff": {
                                    "*": "+This is a test revision."
                                },
                                "slots": {
                                    "main": {
                                        "*": "Full page content"
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        result = list(get_recent_changes_with_diff())
        self.assertTrue(len(result) >= 1)
        self.assertIn("Test Page", result[0]['title'])
        self.assertEqual(result[0]["revisions"][0]['diff']["*"], "+This is a test revision.")

    # run archive_bot tests
    @patch("archivebot.utils.requests.get")
    @patch("archivebot.utils.is_url_alive")
    @patch("archivebot.utils.archive_url")
    @patch("archivebot.utils.get_recent_changes_with_diff")
    @patch("archivebot.utils.logger.info")
    @patch("archivebot.utils.process_citation_template")
    @patch("archivebot.utils.extract_inserted_wikitext")
    def test_run_archive_bot(
        self,
        mock_extract_diff,
        mock_process_citation,
        mock_log_info,
        mock_recent_changes,
        mock_archive_url,
        mock_is_alive,
        mock_get,
    ):
        # Setup diverse recent_changes input to cover all branches:
        mock_recent_changes.return_value = [
            {"title": None, "revisions": []},  # No title/revisions: skipped
            {"title": "EmptyDiff", "revisions": [{"diff": {"*": "<div></div>"}}]},  # Empty inserted content
            {"title": "DOIPage", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://doi.org/example}}</ins>'}}]},  # DOI skipped
            {"title": "DupPage1", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://dup.com}}</ins>'}}]},  # Duplicate URLs
            {"title": "DupPage2", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://dup.com}}</ins>'}}]},
            {"title": "ArchivedPage", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://archived.com|arquivourl=https://archive.org}}</ins>'}}]},  # Already archived
            {"title": "FailArchivePage", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://failarchive.com}}</ins>'}}]},  # Archive fails
            {"title": "NormalPage", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://normal.com}}</ins>'}}]},  # Normal success
        ]

        def extract_diff_side_effect(diff_html):
            if diff_html.startswith("<ins>") and diff_html.endswith("</ins>"):
                return diff_html[5:-6]
            return ""

        mock_extract_diff.side_effect = extract_diff_side_effect

        # Helper to create template mocks with different attributes
        def make_template_mock(url, has_keys=None):
            has_keys = has_keys or ["url"]
            mock = MagicMock()
            mock.has.side_effect = lambda k: k in has_keys
            mock.get.return_value.value.strip.return_value = url
            return mock

        # Archive URL returns None for failarchive, else returns archive URL
        def archive_url_side_effect(url):
            if url == "https://failarchive.com":
                return None
            return f"https://web.archive.org/web/20230701/{url}"

        mock_archive_url.side_effect = archive_url_side_effect

        # URL alive check: failarchive dead, others alive
        mock_is_alive.side_effect = lambda url: url != "https://failarchive.com"

        # process_citation_template returns True only for "https://normal.com"
        def process_citation_side_effect(title, template, archive_url, url_is_dead):
            url = template.get("url").value.strip()
            return url == "https://normal.com"

        mock_process_citation.side_effect = process_citation_side_effect

        def archive_log_side_effect(*args, **kwargs):
            if kwargs.get("url") == "https://failarchive.com":
                raise Exception("DB save fail")
            return MagicMock()

        mock_get.return_value.json.return_value = {
            "source": "{{Citar web|url=https://example.com}}",
            "latest": {"id": 12345}
        }

        # Run the function
        run_archive_bot()

        # Assert key logs called for major branches
        mock_log_info.assert_any_call("Archive Bot started.")
        mock_log_info.assert_any_call("Archive Bot finished.")
        mock_log_info.assert_any_call("Skipping EmptyDiff: no content to scan")
        mock_log_info.assert_any_call("Skipping DOI or archived URL: https://doi.org/example")
        mock_log_info.assert_any_call("Archiving failed for https://failarchive.com")
        mock_log_info.assert_any_call("Archived URL added to template: https://normal.com")

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.utils.logger.warning")
    @patch("archivebot.utils.is_url_alive")
    @patch("archivebot.utils.archive_url")
    @patch("archivebot.utils.get_recent_changes_with_diff")
    @patch("archivebot.utils.extract_inserted_wikitext")
    @patch("archivebot.utils.extract_citar_templates_mwparser")
    def test_archive_log_create_exception_logs_warning(
        self,
        mock_extract_citar,
        mock_extract_diff,
        mock_recent_changes,
        mock_archive_url,
        mock_is_alive,
        mock_log_warn,
        mock_get,
    ):
        mock_recent_changes.return_value = [
            {"title": "TestPage", "revisions": [{"diff": {"*": '<ins>{{Citar web|url=https://failarchive.com}}</ins>'}}]},
        ]
        mock_get.return_value.json.return_value = {
            "source": "{{Citar web|url=https://failarchive.com}}",
            "latest": {"id": 12345}
        }

        mock_archive_url.return_value = "http://web.archive.org/web/20250115033343/https://pt.wikipedia.org"
        mock_is_alive.return_value = True
        mock_extract_diff.return_value = '<ins>{{Citar web|url=https://failarchive.com}}</ins>'
        mock_extract_citar.return_value = [
            MagicMock(has=lambda k: k == "url", get=MagicMock(return_value=MagicMock(value=MagicMock(strip=MagicMock(return_value="https://failarchive.com")))))
        ]

        # Run the function
        run_archive_bot()

    def test_admin_panel_check_func_found(self):
        archived_map = {"https://example.com": "{{Citar web|url=https://example.com|arquivourl=https://archive.org}}"}
        result = admin_panel_check_func("https://example.com", archived_map)
        self.assertEqual(result, archived_map["https://example.com"])

    def test_admin_panel_check_func_not_found(self):
        archived_map = {"https://example.com": "archived template"}
        result = admin_panel_check_func("https://missing.com", archived_map)
        self.assertIsNone(result)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_success(self, mocker):
        source = "{{Citar web|url=https://example.com}}"
        self.mock_page_source(mocker, source)
        self.mock_edit_id(mocker, 12346)
        archived_map = {
            "https://example.com": "{{Citar web|url=https://example.com|arquivourl=https://archive.org}}"
        }
        success, msg = update_archived_templates_in_article(self.article, archived_map)
        self.article.refresh_from_db()
        self.assertEqual(self.article.edit_id, 12346)
        self.assertTrue(success)
        self.assertIn("Successfully updated", msg)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_get_fail(self, mocker):
        self.mock_page_source(mocker, "")
        success, msg = update_archived_templates_in_article(self.article, {})
        self.assertFalse(success)
        self.assertIn("No templates to update", msg)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_put_fail(self, mocker):
        source= "{{Citar web|url=https://example.com}}",
        self.mock_page_source(mocker, source)
        self.mock_edit_fail(mocker)
        archived_map = {
            "https://example.com": "{{Citar web|url=https://example.com|arquivourl=https://archive.org}}"
        }
        success, msg = update_archived_templates_in_article(self.article, archived_map)
        self.assertFalse(success)
        self.assertIn("Failed to commit edit", msg)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_no_changes(self, mocker):
        source= "{{Citar web|url=https://other.com}}",
        self.mock_page_source(mocker, source)
        archived_map = {
            "https://example.com": "{{Citar web|url=https://example.com|arquivourl=https://archive.org}}"
        }
        success, msg = update_archived_templates_in_article(self.article, archived_map)
        self.assertFalse(success)
        self.assertIn("Article unchanged", msg)


class ArchivedURLTests(TestCase):
    def test_timestamp(self):
        a = ArchivedURL("https://pt.wikipedia.org")
        a.archive_url = "http://web.archive.org/web/20250115033343/https://pt.wikipedia.org"
        self.assertEqual(a.archive_timestamp, "20250115033343")
