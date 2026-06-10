import logging

from django.db import models
from django.db.models import Count
from django.db.models import UniqueConstraint
from django.utils.timezone import now

from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck


logger = logging.getLogger("arquibot")


class Timestamp(models.Model):
    datetime = models.DateTimeField(unique=True)

    def __str__(self):
        return f"[{self.datetime}] timestamp"

    class Meta:
        ordering = ("-datetime",)


class StatisticsManager(models.Manager):
    """Custom manager for AllTimeStatistics."""

    def process_statistics(self, timestamp=None):
        """
        Process and update statistics for all Wikipedias.
        """
        if timestamp is None:
            timestamp, _ = Timestamp.objects.get_or_create(datetime=now())
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
