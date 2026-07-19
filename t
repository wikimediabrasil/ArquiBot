[1mdiff --git a/src/archivebot/management/commands/runner.py b/src/archivebot/management/commands/runner.py[m
[1mindex 364045e..d29bbcc 100644[m
[1m--- a/src/archivebot/management/commands/runner.py[m
[1m+++ b/src/archivebot/management/commands/runner.py[m
[36m@@ -51,4 +51,4 @@[m [mclass Command(BaseCommand):[m
             logger.info(f"already reached '{next_day_6am}', not waiting...")[m
 [m
     def stats(self):[m
[31m-        Statistics.objects.process_statistics()[m
[32m+[m[32m        Statistics.objects.process_yesterday()[m
[1mdiff --git a/src/archivebot/management/commands/stats.py b/src/archivebot/management/commands/stats.py[m
[1mindex 741b279..3f88b48 100644[m
[1m--- a/src/archivebot/management/commands/stats.py[m
[1m+++ b/src/archivebot/management/commands/stats.py[m
[36m@@ -5,5 +5,16 @@[m [mfrom stats.models import Statistics[m
 class Command(BaseCommand):[m
     help = "Process statistics"[m
 [m
[32m+[m[32m    def add_arguments(self, parser):[m
[32m+[m[32m        parser.add_argument([m
[32m+[m[32m            "--yesterday",[m
[32m+[m[32m            action="store_true",[m
[32m+[m[32m            default=False,[m
[32m+[m[32m        )[m
[32m+[m
     def handle(self, *args, **options):[m
[31m-        Statistics.objects.process_statistics()[m
[32m+[m[32m        yesterday = options["yesterday"][m
[32m+[m[32m        if yesterday:[m
[32m+[m[32m            Statistics.objects.process_yesterday()[m
[32m+[m[32m        else:[m
[32m+[m[32m            Statistics.objects.process_statistics()[m
[1mdiff --git a/src/archivebot/templates/layout.html b/src/archivebot/templates/layout.html[m
[1mindex ffc47cd..0ad36cd 100644[m
[1m--- a/src/archivebot/templates/layout.html[m
[1m+++ b/src/archivebot/templates/layout.html[m
[36m@@ -19,7 +19,9 @@[m
   </div>[m
   <h1>ArquiBot</h1>[m
   <p style="text-align: center;">[m
[31m-    <a href="{% url 'home' %}">home</a> | <a href="{% url 'logs' %}">logs</a>[m
[32m+[m[32m    <a href="{% url 'home' %}">home</a> |[m
[32m+[m[32m    <a href="{% url 'stats' %}">stats</a> |[m
[32m+[m[32m    <a href="{% url 'logs' %}">logs</a>[m
   </p>[m
 [m
   {% block content %}[m
[1mdiff --git a/src/archivebot/templates/stats.html b/src/archivebot/templates/stats.html[m
[1mindex 14be6d5..27ae2bc 100644[m
[1m--- a/src/archivebot/templates/stats.html[m
[1m+++ b/src/archivebot/templates/stats.html[m
[36m@@ -4,13 +4,16 @@[m
 [m
 {% block content %}[m
 [m
[31m-{% if timestamp %}[m
 <h2>Global statistics</h2>[m
[31m-<p style="text-align: center; font-size: 0.9em;">[m
[31m-  {{ timestamp.datetime }}[m
[31m-  (<a href="{% url 'stats' id=timestamp.id %}">link</a>)[m
[31m-</p>[m
[32m+[m[32m{% if date_fmt %}[m
[32m+[m[32m<form method="get">[m
[32m+[m[32m<label for="date-filter">Filter by date (UTC):</label>[m
[32m+[m[32m<input type="date" name="date" id="date-filter" value="{{ date_fmt }}" onchange="this.form.submit()">[m
[32m+[m[32m</form>[m
[32m+[m[32m<p style="text-align: center; font-size: 0.9em;"> {{ timestamp.datetime }} </p>[m
[32m+[m[32m{% endif %}[m
 [m
[32m+[m[32m{% if statistics %}[m
 <table>[m
   <thead>[m
     <tr>[m
[36m@@ -29,6 +32,8 @@[m
     {% endfor %}[m
   </tbody>[m
 </table>[m
[32m+[m[32m{% else %}[m
[32m+[m[32m<h3 style="text-align: center;">Statistics not found</h3>[m
 {% endif %}[m
 [m
 {% endblock content %}[m
[1mdiff --git a/src/archivebot/urls.py b/src/archivebot/urls.py[m
[1mindex 1022fbc..7b1216f 100644[m
[1m--- a/src/archivebot/urls.py[m
[1m+++ b/src/archivebot/urls.py[m
[36m@@ -5,5 +5,5 @@[m [mfrom . import views[m
 urlpatterns = [[m
     path('logs/', views.logs, name='logs'),[m
     path('', views.home, name='home'),[m
[31m-    path('stats/<int:id>/', views.stats, name='stats'),[m
[32m+[m[32m    path('stats/', views.stats, name='stats'),[m
 ][m
[1mdiff --git a/src/archivebot/views.py b/src/archivebot/views.py[m
[1mindex c8a3c5d..db0478d 100644[m
[1m--- a/src/archivebot/views.py[m
[1m+++ b/src/archivebot/views.py[m
[36m@@ -11,15 +11,6 @@[m [mfrom stats.models import Statistics[m
 from stats.models import Timestamp[m
 [m
 [m
[31m-def _stats_data(timestamp):[m
[31m-    statistics = ([m
[31m-        Statistics.objects.filter(timestamp=timestamp)[m
[31m-        .exclude(edits=0)[m
[31m-        .exclude(wikipedia__code="test")[m
[31m-    )[m
[31m-    return {[m
[31m-        "statistics": statistics,[m
[31m-        "timestamp": timestamp,[m
 def home(request):[m
     wikipedias = Wikipedia.objects.exclude(code="test").all()[m
     data = {[m
[36m@@ -28,11 +19,25 @@[m [mdef home(request):[m
     return render(request, "home.html", data)[m
 [m
 [m
[32m+[m[32mdef stats(request):[m
[32m+[m[32m    request_date = request.GET.get("date")[m
[32m+[m[32m    date = None[m
[32m+[m[32m    if request_date:[m
[32m+[m[32m        date = datetime.strptime(request_date, "%Y-%m-%d")[m
[32m+[m[32m        timestamp = Timestamp.objects.of_date(date)[m
[32m+[m[32m    else:[m
[32m+[m[32m        timestamp = Timestamp.objects.order_by("-datetime").first()[m
[32m+[m[32m        if timestamp:[m
[32m+[m[32m            date = timestamp.date[m
 [m
[31m-def stats(request, id):[m
[31m-    timestamp = Timestamp.objects.get(id=id)[m
[31m-    data = _stats_data(timestamp)[m
[31m-    return render(request, "stats.html", data)[m
[32m+[m[32m    statistics = Statistics.objects.of_timestamp(timestamp)[m
[32m+[m[32m    data = {[m
[32m+[m[32m        "timestamp": timestamp,[m
[32m+[m[32m        "statistics": statistics,[m
[32m+[m[32m        "date_fmt": date.strftime("%Y-%m-%d") if date else None,[m
[32m+[m[32m    }[m
[32m+[m[32m    status = 404 if timestamp is None else 200[m
[32m+[m[32m    return render(request, "stats.html", data, status=status)[m
 [m
 [m
 def logs(request):[m
[1mdiff --git a/src/stats/models.py b/src/stats/models.py[m
[1mindex 88691cc..1a48a81 100644[m
[1m--- a/src/stats/models.py[m
[1m+++ b/src/stats/models.py[m
[36m@@ -1,9 +1,14 @@[m
 import logging[m
[32m+[m[32mfrom datetime import time[m
[32m+[m[32mfrom datetime import datetime[m
[32m+[m[32mfrom datetime import timedelta[m
[32m+[m[32mfrom datetime import UTC[m
 [m
 from django.db import models[m
 from django.db.models import Count[m
 from django.db.models import UniqueConstraint[m
 from django.utils.timezone import now[m
[32m+[m[32mfrom django.utils import timezone[m
 [m
 from archivebot.models import Wikipedia[m
 from archivebot.models import ArticleCheck[m
[36m@@ -13,25 +18,62 @@[m [mfrom archivebot.models import UrlCheck[m
 logger = logging.getLogger("arquibot")[m
 [m
 [m
[32m+[m[32mclass TimestampManager(models.Manager):[m
[32m+[m[32m    def yesterday_23_59_utc(self):[m
[32m+[m[32m        today_utc = now().astimezone(UTC).date()[m
[32m+[m[32m        yesterday = today_utc - timedelta(days=1)[m
[32m+[m[32m        dt = timezone.make_aware(datetime.combine(yesterday, time.max))[m
[32m+[m[32m        timestamp, _ = self.get_or_create(datetime=dt)[m
[32m+[m[32m        return timestamp[m
[32m+[m
[32m+[m[32m    def of_date_fmt(self, date_fmt):[m
[32m+[m[32m        date = datetime.strptime(date_fmt, "%Y-%m-%d")[m
[32m+[m[32m        return self.of_date(date)[m
[32m+[m
[32m+[m[32m    def of_date(self, date):[m
[32m+[m[32m        return ([m
[32m+[m[32m            Timestamp.objects.filter([m
[32m+[m[32m                datetime__date=date,[m
[32m+[m[32m            )[m
[32m+[m[32m            .order_by("-datetime")[m
[32m+[m[32m            .first()[m
[32m+[m[32m        )[m
[32m+[m
[32m+[m
 class Timestamp(models.Model):[m
[32m+[m[32m    objects = TimestampManager()[m
[32m+[m
     datetime = models.DateTimeField(unique=True)[m
 [m
     def __str__(self):[m
         return f"[{self.datetime}] timestamp"[m
 [m
[32m+[m[32m    @property[m
[32m+[m[32m    def date(self):[m
[32m+[m[32m        return self.datetime.date()[m
[32m+[m
[32m+[m[32m    @property[m
[32m+[m[32m    def date_fmt(self):[m
[32m+[m[32m        return self.date.strftime("%Y-%m-%d")[m
[32m+[m
     class Meta:[m
         ordering = ("-datetime",)[m
 [m
 [m
 class StatisticsManager(models.Manager):[m
[31m-    """Custom manager for AllTimeStatistics."""[m
[31m-[m
     def process_statistics(self, timestamp=None):[m
[32m+[m[32m        if timestamp is None:[m
[32m+[m[32m            timestamp, _ = Timestamp.objects.get_or_create(datetime=now())[m
[32m+[m[32m        return self.process_at(timestamp)[m
[32m+[m
[32m+[m[32m    def process_yesterday(self):[m
[32m+[m[32m        timestamp = Timestamp.objects.yesterday_23_59_utc()[m
[32m+[m[32m        return self.process_at(timestamp)[m
[32m+[m
[32m+[m[32m    def process_at(self, timestamp):[m
         """[m
         Process and update statistics for all Wikipedias.[m
         """[m
[31m-        if timestamp is None:[m
[31m-            timestamp, _ = Timestamp.objects.get_or_create(datetime=now())[m
         logger.info(f"processing statistics: {timestamp}...")[m
         for wikipedia in Wikipedia.objects.all():[m
             logger.debug(f"stats: [{wikipedia}]...")[m
[36m@@ -60,6 +102,13 @@[m [mclass StatisticsManager(models.Manager):[m
 [m
             stats.save()[m
 [m
[32m+[m[32m    def of_timestamp(self, timestamp: Timestamp):[m
[32m+[m[32m        return ([m
[32m+[m[32m            Statistics.objects.filter(timestamp=timestamp)[m
[32m+[m[32m            .exclude(edits=0)[m
[32m+[m[32m            .exclude(wikipedia__code="test")[m
[32m+[m[32m        )[m
[32m+[m
 [m
 class Statistics(models.Model):[m
     objects = StatisticsManager()[m
[1mdiff --git a/src/stats/tests.py b/src/stats/tests.py[m
[1mindex df226a0..cb0b670 100644[m
[1m--- a/src/stats/tests.py[m
[1m+++ b/src/stats/tests.py[m
[36m@@ -157,13 +157,20 @@[m [mclass StatisticsManagerTestCase(TestCase):[m
         stats_es = Statistics.objects.get(wikipedia=self.wiki_es, timestamp=ts)[m
         self.check(stats_pt, stats_es)[m
 [m
[31m-    def test_process_statistics_timestamp_is_set(self):[m
[31m-        before = now()[m
[31m-        Statistics.objects.process_statistics()[m
[32m+[m[32m    def test_process_statistics_timestamp_yesterday(self):[m
[32m+[m[32m        before = now() - timedelta(days=1)[m
[32m+[m[32m        Statistics.objects.process_yesterday()[m
         after = now()[m
         stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)[m
[32m+[m[32m        stats_es = Statistics.objects.get(wikipedia=self.wiki_es)[m
         self.assertGreaterEqual(stats_pt.timestamp.datetime, before)[m
         self.assertLessEqual(stats_pt.timestamp.datetime, after)[m
[32m+[m[32m        self.assertEqual(stats_pt.edits, 1)[m
[32m+[m[32m        self.assertEqual(stats_pt.articles, 1)[m
[32m+[m[32m        self.assertEqual(stats_pt.urls_archived, 1)[m
[32m+[m[32m        self.assertEqual(stats_es.edits, 0)[m
[32m+[m[32m        self.assertEqual(stats_es.articles, 0)[m
[32m+[m[32m        self.assertEqual(stats_es.urls_archived, 0)[m
 [m
     def test_process_statistics_empty_wikipedia(self):[m
         Wikipedia.objects.all().delete()[m
[36m@@ -171,10 +178,10 @@[m [mclass StatisticsManagerTestCase(TestCase):[m
         self.assertEqual(Statistics.objects.count(), 0)[m
 [m
     def test_home_view_includes_valid_statistics(self):[m
[31m-        Statistics.objects.process_statistics()[m
[32m+[m[32m        Statistics.objects.process_statistics(timestamp=self.timestamp)[m
         stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)[m
         stats_es = Statistics.objects.get(wikipedia=self.wiki_es)[m
[31m-        response = self.client.get(reverse("home"))[m
[32m+[m[32m        response = self.client.get(reverse("stats"))[m
         self.assertEqual(response.status_code, 200)[m
         statistics = response.context["statistics"][m
         self.assertEqual(statistics.count(), 2)[m
[36m@@ -187,18 +194,16 @@[m [mclass StatisticsManagerTestCase(TestCase):[m
 [m
     def test_home_view_empty(self):[m
         Timestamp.objects.all().delete()[m
[31m-        response = self.client.get(reverse("home"))[m
[31m-        self.assertEqual(response.status_code, 200)[m
[31m-        self.assertNotIn("statistics", response.context)[m
[31m-        self.assertNotIn("timestamp", response.context)[m
[31m-        self.assertNotIn("Global statistics", response.text)[m
[32m+[m[32m        response = self.client.get(reverse("stats"))[m
[32m+[m[32m        self.assertEqual(response.status_code, 404)[m
[32m+[m[32m        self.assertIn("not found", response.text)[m
 [m
     def test_stats_view(self):[m
         ts = self.timestamp[m
         Statistics.objects.process_statistics(timestamp=ts)[m
         stats_pt = Statistics.objects.get(wikipedia=self.wiki_pt)[m
         stats_es = Statistics.objects.get(wikipedia=self.wiki_es)[m
[31m-        response = self.client.get(reverse("stats", args=[ts.id]))[m
[32m+[m[32m        response = self.client.get(reverse("stats", query={"date": stats_pt.timestamp.date_fmt}))[m
         self.assertEqual(response.status_code, 200)[m
         statistics = response.context["statistics"][m
         self.assertEqual(statistics.count(), 2)[m
