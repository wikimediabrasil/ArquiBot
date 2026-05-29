from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now

from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck

from .models import Statistics


class StatisticsManagerTestCase(TestCase):
    def setUp(self):
        Wikipedia.objects.all().delete()
        self.wiki_pt, _ = Wikipedia.objects.get_or_create(code="pt")
        self.wiki_es, _ = Wikipedia.objects.get_or_create(code="es")
        self.now = now()

        self.article_pt_ok_1 = ArticleCheck.objects.create(
            wikipedia=self.wiki_pt,
            edit_id=12345,
            title="OK 1",
        )
        self.article_pt_ok_2 = ArticleCheck.objects.create(
            wikipedia=self.wiki_pt,
            edit_id=23456,
            title="OK 2",
        )
        self.article_pt_noedit = ArticleCheck.objects.create(
            wikipedia=self.wiki_pt,
            edit_id=None,
            title="No edits",
        )
        self.article_pt_future = ArticleCheck.objects.create(
            wikipedia=self.wiki_pt,
            edit_id=67890,
            title="Future edit",
        )
        ArticleCheck.objects.filter(id=self.article_pt_future.id).update(
            # workaround for auto_now=True
            modified=self.now + timedelta(days=1)
        )
        self.article_es = ArticleCheck.objects.create(
            wikipedia=self.wiki_es,
            edit_id=11111,
            title="ES OK",
        )

        self.url_pt_archived = UrlCheck.objects.create(
            article=self.article_pt_ok_1,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )
        self.url_pt_ok_2_archived_1 = UrlCheck.objects.create(
            article=self.article_pt_ok_2,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )
        self.url_pt_ok_2_archived_2 = UrlCheck.objects.create(
            article=self.article_pt_ok_2,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )
        self.url_pt_pending = UrlCheck.objects.create(
            article=self.article_pt_ok_1,
        )
        self.url_pt_no_edit = UrlCheck.objects.create(
            article=self.article_pt_noedit,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )
        self.url_pt_future = UrlCheck.objects.create(
            article=self.article_pt_future,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )
        self.url_es_archived = UrlCheck.objects.create(
            article=self.article_es,
            status=UrlCheck.ArchiveStatus.ARCHIVED,
        )

        self.PT_EDITS = 2
        self.PT_URLS = 3
        self.ES_EDITS = 1
        self.ES_URLS = 1

    def test_process_statistics_creates_statistics(self):
        self.assertFalse(Statistics.objects.exists())
        Statistics.objects.process_statistics()
        self.assertEqual(Statistics.objects.count(), 2)
        self.assertTrue(Statistics.objects.filter(wikipedia=self.wiki_pt).exists())
        self.assertTrue(Statistics.objects.filter(wikipedia=self.wiki_es).exists())

    def test_process_statistics_counts_edits(self):
        Statistics.objects.process_statistics()
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        stats_es = Statistics.objects.get(wikipedia=self.wiki_es)
        self.assertEqual(stats_pt.edits, self.PT_EDITS)
        self.assertEqual(stats_pt.urls_archived, self.PT_URLS)
        self.assertEqual(stats_es.edits, self.ES_EDITS)
        self.assertEqual(stats_es.urls_archived, self.ES_URLS)

    def test_process_statistics_updates_existing_statistics(self):
        stats_pt = Statistics.objects.create(
            wikipedia=self.wiki_pt, edits=0, urls_archived=0
        )
        stats_es = Statistics.objects.create(
            wikipedia=self.wiki_es, edits=0, urls_archived=0
        )
        self.assertEqual(Statistics.objects.count(), 2)
        Statistics.objects.process_statistics()
        stats_pt.refresh_from_db()
        stats_es.refresh_from_db()
        self.assertEqual(stats_pt.edits, self.PT_EDITS)
        self.assertEqual(stats_pt.urls_archived, self.PT_URLS)
        self.assertEqual(stats_es.edits, self.ES_EDITS)
        self.assertEqual(stats_es.urls_archived, self.ES_URLS)

    def test_process_statistics_timestamp_is_set(self):
        before = now()
        Statistics.objects.process_statistics()
        after = now()
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        self.assertGreaterEqual(stats_pt.timestamp, before)
        self.assertLessEqual(stats_pt.timestamp, after)

    def test_process_statistics_empty_wikipedia(self):
        Wikipedia.objects.all().delete()
        Statistics.objects.all().delete()
        Statistics.objects.process_statistics()
        self.assertEqual(Statistics.objects.count(), 0)
