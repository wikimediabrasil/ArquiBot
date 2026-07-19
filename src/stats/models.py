import logging
from datetime import time
from datetime import datetime
from datetime import timedelta
from datetime import UTC

from django.db import models
from django.db.models import Count
from django.db.models import UniqueConstraint
from django.utils.timezone import now
from django.utils import timezone

from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck


logger = logging.getLogger("arquibot")


class TimestampManager(models.Manager):
    def yesterday_23_59_utc(self):
        today_utc = now().astimezone(UTC).date()
        yesterday = today_utc - timedelta(days=1)
        dt = timezone.make_aware(datetime.combine(yesterday, time.max))
        timestamp, _ = self.get_or_create(datetime=dt)
        return timestamp

    def of_date_fmt(self, date_fmt):
        date = datetime.strptime(date_fmt, "%Y-%m-%d")
        return self.of_date(date)

    def of_date(self, date):
        return (
            Timestamp.objects.filter(
                datetime__date=date,
            )
            .order_by("-datetime")
            .first()
        )


class Timestamp(models.Model):
    objects = TimestampManager()

    datetime = models.DateTimeField(unique=True)

    def __str__(self):
        return f"[{self.datetime}] timestamp"

    @property
    def date(self):
        return self.datetime.date()

    @property
    def date_fmt(self):
        return self.date.strftime("%Y-%m-%d")

    class Meta:
        ordering = ("-datetime",)


class StatisticsManager(models.Manager):
    def process_statistics(self, timestamp=None):
        if timestamp is None:
            timestamp, _ = Timestamp.objects.get_or_create(datetime=now())
        return self.process_at(timestamp)

    def process_yesterday(self):
        timestamp = Timestamp.objects.yesterday_23_59_utc()
        return self.process_at(timestamp)

    def process_at(self, timestamp):
        """
        Process and update statistics for all Wikipedias.
        """
        logger.info(f"processing statistics: {timestamp}...")
        for wikipedia in Wikipedia.objects.all():
            logger.debug(f"stats: [{wikipedia}]...")
            stats, _ = self.get_or_create(
                timestamp=timestamp,
                wikipedia=wikipedia,
            )

            query = ArticleCheck.objects.filter(
                wikipedia=wikipedia,
                edit_id__isnull=False,
                modified__lte=timestamp.datetime,
            )
            stats.edits = query.count()

            stats.articles = query.aggregate(
                articles=Count("title", distinct=True),
            )["articles"]

            stats.urls_archived = UrlCheck.objects.filter(
                article__wikipedia=wikipedia,
                article__edit_id__isnull=False,
                article__modified__lte=timestamp.datetime,
                status=UrlCheck.ArchiveStatus.ARCHIVED,
            ).count()

            stats.save()

    def of_timestamp(self, timestamp: Timestamp):
        return (
            Statistics.objects.filter(timestamp=timestamp)
            .exclude(edits=0)
            .exclude(wikipedia__code="test")
        )


class Statistics(models.Model):
    objects = StatisticsManager()

    timestamp = models.ForeignKey(Timestamp, on_delete=models.CASCADE)
    wikipedia = models.ForeignKey(Wikipedia, on_delete=models.CASCADE)

    edits = models.PositiveIntegerField(
        default=0,
        help_text="Total number of edits",
    )
    articles = models.PositiveIntegerField(
        default=0,
        help_text="Total number of articles edited",
    )
    urls_archived = models.PositiveIntegerField(
        default=0,
        help_text="Total number of URLs archived",
    )

    def __str__(self):
        return f"[{self.wikipedia.code}] stats at {self.timestamp}"

    class Meta:
        ordering = ("timestamp", "-edits")
        constraints = [
            UniqueConstraint(
                fields=("wikipedia", "timestamp"),
                name="unique_wikipedia_timestamp",
            ),
        ]
        verbose_name_plural = "Statistics"
