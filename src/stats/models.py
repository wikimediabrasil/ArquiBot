import logging

from django.db import models
from django.utils.timezone import now

from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck


logger = logging.getLogger("arquibot")


class StatisticsManager(models.Manager):
    """Custom manager for AllTimeStatistics."""

    def process_statistics(self, point_in_time=None):
        """
        Process and update statistics for all Wikipedias.
        """
        for wikipedia in Wikipedia.objects.all():
            logger.info(f"{wikipedia} stats...")
            point_in_time = now() if point_in_time is None else point_in_time
            stats, created = self.get_or_create(wikipedia=wikipedia)

            query = ArticleCheck.objects.filter(
                wikipedia=wikipedia,
                edit_id__isnull=False,
                modified__lte=point_in_time,
            )
            for a in query:
                logger.info(f"{a} {a.edit_id} - {a.modified}")
            stats.edits = query.count()

            stats.urls_archived = UrlCheck.objects.filter(
                article__wikipedia=wikipedia,
                article__edit_id__isnull=False,
                article__modified__lte=point_in_time,
                status=UrlCheck.ArchiveStatus.ARCHIVED,
            ).count()

            stats.timestamp = point_in_time

            stats.save()


class Statistics(models.Model):
    objects = StatisticsManager()

    wikipedia = models.OneToOneField(Wikipedia, on_delete=models.CASCADE)

    edits = models.PositiveIntegerField(
        default=0,
        help_text="Total number of edits",
    )
    urls_archived = models.PositiveIntegerField(
        default=0,
        help_text="Total number of URLs archived",
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.wikipedia.code}] stats at {self.timestamp}"

    class Meta:
        ordering = ("-edits", "-urls_archived")
