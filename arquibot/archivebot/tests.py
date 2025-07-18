import unittest
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime
import requests
import mwparserfromhell

from archivebot.utils import (
    get_recent_changes_with_diff,
    extract_inserted_text_from_diff,
    extract_citar_templates_mwparser,
    extract_citar_templates_as_strings,
    extract_external_links_from_text,
    is_url_alive,
    archive_url,
    parse_citar_template,
    build_updated_template,
    process_citation_template,
    run_archive_bot
)

class TestUtils(unittest.TestCase):

    def test_extract_inserted_text_from_diff(self):
        html = '<div><ins class="diffchange">This is new content.</ins></div>'
        result = extract_inserted_text_from_diff(html)
        self.assertIn("This is new content.", result)

    def test_extract_citar_templates_mwparser(self):
        text = '{{Citar web|url=https://example.org}} and {{Outro|name=value}}'
        result = extract_citar_templates_mwparser(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name.strip(), "Citar web")

    def test_extract_citar_templates_as_strings(self):
        text = '{{Citar web|url=https://example.org}} and {{Outro|name=value}}'
        result = extract_citar_templates_as_strings(text)
        self.assertEqual(result, ['{{Citar web|url=https://example.org}}'])

    def test_parse_citar_template(self):
        tpl = mwparserfromhell.parse("{{Citar web|url=https://example.org|title=Example}}").filter_templates()[0]
        parsed = parse_citar_template(tpl)
        self.assertEqual(parsed["url"], "https://example.org")
        self.assertEqual(parsed["title"], "Example")

    def test_build_updated_template(self):
        fields = {
            "url": "https://example.org",
            "arquivourl": "https://web.archive.org/save/https://example.org",
            "arquivodata": "2023-01-01",
        }
        result = build_updated_template("Citar web", fields)
        self.assertIn("url=https://example.org", result)
        self.assertIn("arquivourl=https://web.archive.org/save/https://example.org", result)

    def test_extract_external_links_from_text(self):
        text = 'Some text with https://example.org and another https://site.com/page'
        result = extract_external_links_from_text(text)
        self.assertIn("https://example.org", result)
        self.assertIn("https://site.com/page", result)

    @patch("archivebot.utils.requests.head")
    def test_is_url_alive_success(self, mock_head):
        mock_head.return_value.status_code = 200
        self.assertTrue(is_url_alive("https://example.org"))

    @patch("archivebot.utils.requests.head")
    def test_is_url_alive_fail(self, mock_head):
        mock_head.side_effect = requests.RequestException()
        self.assertFalse(is_url_alive("https://example.org"))

    @patch("archivebot.utils.requests.get")
    @patch("archivebot.utils.WaybackMachineSaveAPI.save")
    def test_archive_url_success_and_fallback(self, mock_save, mock_get):
        mock_instance = Mock()
        mock_instance.archive_url = "https://web.archive.org/web/20230701/https://example.org"
        mock_save.return_value = None
        with patch("archivebot.utils.WaybackMachineSaveAPI", return_value=mock_instance):
            result = archive_url("https://example.org")
            self.assertTrue(result.startswith("https://web.archive.org/web"))

    @patch("archivebot.utils.ArchivedCitation")
    def test_process_citation_template(self, mock_model):
        mock_create = mock_model.objects.create

        template_str = '{{Citar web|url=https://example.org}}'
        page_title = "Test Page"

        # Parse the string and get the template object
        wikicode = mwparserfromhell.parse(template_str)
        tpl = wikicode.filter_templates()[0]

        updated_template = process_citation_template(
            title=page_title,
            template=tpl,
            archive_url='https://web.archive.org/example',
            archive_date=datetime.strptime('2025-07-17', "%Y-%m-%d").date(),
            url_is_dead=True
        )

        self.assertIn("arquivourl=https://web.archive.org/example", updated_template)
        self.assertIn("arquivodata=2025-07-17", updated_template)
        self.assertIn("urlmorta=sim", updated_template)

        mock_create.assert_called_once_with(
            article_title='Test Page',
            original_template='{{Citar web|url=https://example.org}}',
            updated_template=updated_template,
            url='https://example.org',
            arquivourl='https://web.archive.org/example',
            arquivodata=datetime.strptime('2025-07-17', "%Y-%m-%d").date(),
            urlmorta=True
        )

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
        self.assertEqual(result[0]['diff'], "+This is a test revision.")

    @patch("archivebot.utils.ArchiveLog.objects.create")
    @patch("archivebot.utils.is_url_alive")
    @patch("archivebot.utils.archive_url")
    @patch("archivebot.utils.get_recent_changes_with_diff")
    @patch("archivebot.utils.logging.info")
    def test_run_archive_bot(
        self, mock_recent, mock_archive, mock_alive, mock_stats, mock_log
    ):
        mock_alive.return_value = True
        mock_archive.return_value = "https://web.archive.org/web/20230701/https://example.org"
        mock_recent.return_value = [{
            "title": "Test Page",
            "diff": '<ins class="diffchange">{{Citar web|url=https://example.org}}</ins>'
        }]

        run_archive_bot()
        self.assertTrue(mock_log.called, "ArchiveLog.objects.create was not called")
        self.assertTrue(mock_stats.called, "update_stats was not called")
