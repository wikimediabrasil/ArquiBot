import time
import logging
from datetime import timedelta
from datetime import UTC

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from archivebot.utils import run_rc_date
from archivebot.models import ArticleCheck, Wikipedia

logger = logging.getLogger("arquibot")


class Command(BaseCommand):
    help = "Run daily the archive bot on yesterday's (UTC) Recent Changes"
    HOURS = 24

    def add_arguments(self, parser):
        parser.add_argument(
            "--stop-at-edit-count",
            type=int,
            default=10,
            help="Stop after this many edits (default: 10)",
        )

    def handle(self, *args, **options):
        stop_at_edit_count = self.stop_at_edit_count(options["stop_at_edit_count"])
        while True:
            self.now = now()
            yesterday = self.yesterday()
            if not self.reached_edit_count_today(stop_at_edit_count):
                try:
                    run_rc_date(yesterday, stop_at_edit_count=stop_at_edit_count)
                except Exception as e:
                    logger.error(f"error for {yesterday} Recent Changes: {e}")
            self.wait_until_tomorrow()

    def yesterday(self):
        today_utc = self.now.astimezone(UTC).date()
        return today_utc - timedelta(days=1)

    def reached_edit_count_today(self, edit_count):
        wikipedia = Wikipedia.get()
        today = self.now.astimezone(UTC).date()
        edits_today = (
            ArticleCheck.objects.filter(
                wikipedia=wikipedia,
                created__date=today,
            )
            .exclude(edit_id__isnull=True)
            .count()
        )
        logger.info(f"reached {edits_today}/{edit_count} edits today...")
        return edits_today >= edit_count

    def wait_until_tomorrow(self):
        next_day_6am = (self.now + timedelta(days=1)).replace(hour=6)
        wait_sec = (next_day_6am - now()).total_seconds()
        if wait_sec > 0:
            wait_hours = wait_sec / 3600
            logger.info(f"sleeping for {wait_hours:.3f} hours until '{next_day_6am}'...")
            time.sleep(wait_sec)
        else:
            logger.info(f"already reached '{next_day_6am}', not waiting...")

    def stop_at_edit_count(self, stop_at_edit_coun_str: str = None):
        try:
            value = int(stop_at_edit_coun_str)
            if value >= 1:
                return value
        except (ValueError, TypeError):
            pass
        return None
