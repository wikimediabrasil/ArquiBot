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
            if not self.yesterday_already_checked():
                try:
                    run_rc_date(yesterday, stop_at_edit_count=stop_at_edit_count)
                except Exception as e:
                    logger.error(f"error for {yesterday} Recent Changes: {e}")
            self.wait_until_tomorrow()

    def yesterday(self):
        today_utc = self.now.astimezone(UTC).date()
        return today_utc - timedelta(days=1)

    def yesterday_already_checked(self):
        wikipedia = Wikipedia.get()
        return ArticleCheck.objects.filter(
            wikipedia=wikipedia, created__date=self.yesterday()
        ).exists()

    def wait_until_tomorrow(self):
        tomorrow_6am = (self.now + timedelta(days=1)).replace(hours=6)
        wait_sec = (tomorrow_6am - self.now).total_seconds()
        wait_hours = wait_sec / 3600
        logger.info(f"sleeping for {wait_hours:.3f}... hours")
        time.sleep(wait_sec)

    def stop_at_edit_count(self, stop_at_edit_coun_str: str = None):
        try:
            value = int(stop_at_edit_coun_str)
            if value >= 1:
                return value
        except (ValueError, TypeError):
            pass
        return None
