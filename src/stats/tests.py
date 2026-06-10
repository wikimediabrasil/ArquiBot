from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now
from django.core.management import call_command
from django.urls import reverse

from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck

from .models import Statistics
from .models import Timestamp


class StatisticsManagerTestCase(TestCase):
    def setUp(self):
        Wikipedia.objects.all().delete()
        self.wiki_pt, _ = Wikipedia.objects.get_or_create(code="pt")
        self.wiki_es, _ = Wikipedia.objects.get_or_create(code="es")

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
        self.article_pt_ok_2_other_edit = ArticleCheck.objects.create(
            wikipedia=self.wiki_pt,
            edit_id=34567,
            title="OK 2",
        )
        ArticleCheck.objects.filter(id=self.article_pt_ok_2_other_edit.id).update(
            # workaround for auto_now=True
            modified=now() - timedelta(days=10)
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
            modified=now() + timedelta(days=1)
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
        self.url_pt_ok_2_other_edit = UrlCheck.objects.create(
            article=self.article_pt_ok_2_other_edit,
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

        self.timestamp = Timestamp.objects.create(datetime=now())

        self.PT_EDITS = 3
        self.PT_ARTICLES = 2
        self.PT_URLS = 4
        self.ES_EDITS = 1
        self.ES_ARTICLES = 1
        self.ES_URLS = 1

    def check(self, stats_pt, stats_es):
        self.assertEqual(stats_pt.edits, self.PT_EDITS)
        self.assertEqual(stats_pt.articles, self.PT_ARTICLES)
        self.assertEqual(stats_pt.urls_archived, self.PT_URLS)
        self.assertEqual(stats_es.edits, self.ES_EDITS)
        self.assertEqual(stats_es.articles, self.ES_ARTICLES)
        self.assertEqual(stats_es.urls_archived, self.ES_URLS)

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
        self.check(stats_pt, stats_es)

    def test_process_statistics_command(self):
        call_command("stats")
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        stats_es = Statistics.objects.get(wikipedia=self.wiki_es)
        self.check(stats_pt, stats_es)

    def test_process_statistics_updates_existing_statistics(self):
        ts = self.timestamp
        stats_pt = Statistics.objects.create(
            wikipedia=self.wiki_pt, edits=0, urls_archived=0, timestamp=ts
        )
        stats_es = Statistics.objects.create(
            wikipedia=self.wiki_es, edits=0, urls_archived=0, timestamp=ts
        )
        self.assertEqual(Statistics.objects.count(), 2)
        Statistics.objects.process_statistics(timestamp=ts)
        self.assertEqual(Statistics.objects.count(), 2)
        stats_pt.refresh_from_db()
        stats_es.refresh_from_db()
        self.check(stats_pt, stats_es)

    def test_process_statistics_creates_new_statistics(self):
        ts = self.timestamp
        stats_pt = Statistics.objects.create(
            wikipedia=self.wiki_pt, edits=0, urls_archived=0, timestamp=ts
        )
        stats_es = Statistics.objects.create(
            wikipedia=self.wiki_es, edits=0, urls_archived=0, timestamp=ts
        )
        self.assertEqual(Statistics.objects.count(), 2)
        ts = Timestamp.objects.create(datetime=now() + timedelta(minutes=5))
        Statistics.objects.process_statistics(timestamp=ts)
        self.assertEqual(Statistics.objects.count(), 4)
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt, timestamp=ts)
        stats_es = Statistics.objects.get(wikipedia=self.wiki_es, timestamp=ts)
        self.check(stats_pt, stats_es)

    def test_process_statistics_timestamp_is_set(self):
        before = now()
        Statistics.objects.process_statistics()
        after = now()
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        self.assertGreaterEqual(stats_pt.timestamp.datetime, before)
        self.assertLessEqual(stats_pt.timestamp.datetime, after)

    def test_process_statistics_empty_wikipedia(self):
        Wikipedia.objects.all().delete()
        Statistics.objects.process_statistics()
        self.assertEqual(Statistics.objects.count(), 0)

    def test_home_view_includes_valid_statistics(self):
        Statistics.objects.process_statistics()
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        stats_es = Statistics.objects.get(wikipedia=self.wiki_es)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        statistics = response.context["statistics"]
        self.assertEqual(statistics.count(), 2)
        self.assertIn(stats_pt, statistics)
        self.assertIn(stats_es, statistics)
        timestamp = response.context["timestamp"]
        self.assertEqual(timestamp, stats_pt.timestamp)
        self.assertIn("Global statistics", response.text)
        self.assertIn("contribs", response.text)

    def test_home_view_empty(self):
        Timestamp.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("statistics", response.context)
        self.assertNotIn("timestamp", response.context)
        self.assertNotIn("Global statistics", response.text)

    def test_stats_view(self):
        ts = self.timestamp
        Statistics.objects.process_statistics(timestamp=ts)
        stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)
        stats_es = Statistics.objects.get(wikipedia=self.wiki_es)
        response = self.client.get(reverse("stats", args=[ts.id]))
        self.assertEqual(response.status_code, 200)
        statistics = response.context["statistics"]
        self.assertEqual(statistics.count(), 2)
        self.assertIn(stats_pt, statistics)
        self.assertIn(stats_es, statistics)
        self.assertEqual(ts, response.context["timestamp"])
        self.assertIn("Global statistics", response.text)
        self.assertIn("contribs", response.text)
