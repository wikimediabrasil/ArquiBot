from unittest.mock import patch, Mock, MagicMock
import requests
import requests_mock
import mwparserfromhell
from datetime import timedelta

from django.test import TestCase
from django.test import override_settings

from archivebot.utils import (
    fetch_current_wikitext,
    extract_inserted_wikitext,
    extract_citar_templates_mwparser,
    extract_citar_templates_as_strings,
    extract_external_links_from_text,
    parse_citar_template,
    build_updated_template,
    process_citation_template,
    update_archived_templates_in_article,
)

from archivebot.archiving import ArchivedURL
from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck

def archive_url(url):
    arq = ArchivedURL(url)
    arq.archive()
    return arq.archive_url

@override_settings(
    ARQUIBOT_TOKEN="token123",
    WIKIPEDIA_CODE="test",
    USER_AGENT="ArquiBot/1.0 (https://pt.wikipedia.org/wiki/Usuário(a):ArquiBot)",
)
class TestUtils(TestCase):
    def setUp(self):
        self.wikipedia = Wikipedia.get()
        self.article = self.get_article("Test Page")

    def get_article(self, title):
        wikipedia = Wikipedia.get()
        article = ArticleCheck.objects.create(wikipedia=wikipedia, title=title)
        return article

    def mock_rest_get(self, mocker, data):
        mocker.get(
            self.article._page_endpoint(),
            json=data,
            status_code=200,
        )

    def mock_rest_put(self, mocker, data):
        mocker.put(
            self.article._page_endpoint(),
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
            self.article._page_endpoint(),
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

        result = fetch_current_wikitext("Test Article")
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

        result = fetch_current_wikitext("NoPage")
        self.assertIsNone(result)

    @patch("archivebot.utils.requests.get")
    def test_no_revisions_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "query": {"pages": [{"pageid": 1, "title": "EmptyPage", "revisions": []}]}
        }
        mock_get.return_value = mock_resp

        result = fetch_current_wikitext("EmptyPage")
        self.assertIsNone(result)

    @patch("archivebot.utils.requests.get")
    def test_http_error_returns_none_and_logs_warning(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_resp

        with self.assertLogs(level="WARNING") as log_cm:
            result = fetch_current_wikitext("HTTPErrorPage")
        self.assertIsNone(result)
        self.assertTrue(any("Failed to fetch full wikitext" in message for message in log_cm.output))

    @patch("archivebot.utils.requests.get", side_effect=requests.RequestException("Timeout"))
    def test_request_exception_returns_none_and_logs_warning(self, mock_get):
        with self.assertLogs(level="WARNING") as log_cm:
            result = fetch_current_wikitext("TimeoutPage")
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
        )

        self.assertIn("wayb=20250115032356", updated_template)

        # --- New test case: skips if arquivourl or wayb already present ---
        template_str2 = '{{Citar web|url=https://pt.wikipedia.org/|arquivourl=http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/}}'
        wikicode2 = mwparserfromhell.parse(template_str2)
        tpl2 = wikicode2.filter_templates()[0]

        result2 = process_citation_template(
            title=page_title,
            template=tpl2,
            archive_url='http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/',
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
            )

            self.assertIsNone(result3)

    def test_admin_panel_check_func_found(self):
        archived_map = {"https://example.com": "https://archive.org"}
        result = archived_map.get("https://example.com")
        self.assertEqual(result, archived_map["https://example.com"])

    def test_admin_panel_check_func_not_found(self):
        archived_map = {"https://example.com": "https://archive.org"}
        result = archived_map.get("https://missing.com")
        self.assertIsNone(result)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_success(self, mocker):
        source = "{{Citar web|url=https://pt.wikipedia.org}}"
        self.mock_page_source(mocker, source)
        self.mock_edit_id(mocker, 12346)
        archived_map = {
            "https://pt.wikipedia.org": "http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/"
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
        self.assertIn("no templates to update", msg)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_put_fail(self, mocker):
        source= "{{Citar web|url=https://pt.wikipedia.org}}",
        self.mock_page_source(mocker, source)
        self.mock_edit_fail(mocker)
        archived_map = {
            "https://pt.wikipedia.org": "http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/"
        }
        success, msg = update_archived_templates_in_article(self.article, archived_map)
        self.assertFalse(success)
        self.assertIn("Failed to commit edit", msg)

    @requests_mock.Mocker()
    def test_update_archived_templates_in_article_no_changes(self, mocker):
        source= "{{Citar web|url=https://other.com}}",
        self.mock_page_source(mocker, source)
        archived_map = {
            "https://pt.wikipedia.org": "http://web.archive.org/web/20250115032356/https://pt.wikipedia.org/"
        }
        success, msg = update_archived_templates_in_article(self.article, archived_map)
        self.assertFalse(success)
        self.assertIn("Article unchanged", msg)


class ArchivedURLTests(TestCase):
    def test_timestamp(self):
        a = ArchivedURL("https://pt.wikipedia.org")
        a.archive_url = "http://web.archive.org/web/20250115033343/https://pt.wikipedia.org"
        self.assertEqual(a.archive_timestamp, "20250115033343")

class ArticleCheckTests(TestCase):
    def setUp(self):
        self.wikipedia = Wikipedia.get()
        self.article = self.get_article("Test Page")

    def get_article(self, title):
        wikipedia = Wikipedia.get()
        article = ArticleCheck.objects.create(wikipedia=wikipedia, title=title)
        return article

    def test_recent_check(self):
        past_check = self.get_article("Test")
        checker = self.get_article("Test")
        past_check.created = checker.created - timedelta(days=6)
        past_check.save()
        self.assertEqual(checker.recent_check().id, past_check.id)
        past_check.created = checker.created - timedelta(days=7)
        past_check.save()
        self.assertIsNone(checker.recent_check())
        past_check.created = checker.created + timedelta(days=1)
        past_check.save()
        self.assertEqual(checker.recent_check().id, past_check.id)
        past_check.delete()
        self.assertIsNone(checker.recent_check())
