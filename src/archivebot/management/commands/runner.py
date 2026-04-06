import time
import logging
from datetime import timedelta
from datetime import UTC

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from archivebot.utils import run_rc_date

logger = logging.getLogger("arquibot")


class Command(BaseCommand):
    help = "Run daily the archive bot on yesterday's (UTC) Recent Changes"
    HOURS = 24
    EDIT_COUNT = 10

    def handle(self, *args, **options):
        while True:
            self.now = now()
            yesterday = self.yesterday()
            try:
                edit_count = run_rc_date(yesterday, stop_at_edit_count=self.EDIT_COUNT)
            except Exception as e:
                logger.error(f"error for {yesterday} Recent Changes: {e}")
                edit_count = 0
            if self.no_more_edits(edit_count):
                logger.info("no more edits to be made...")
                self.wait_until_tomorrow()
            else:
                logger.info(f"made {edit_count} edits, continuing...")

    def yesterday(self):
        today_utc = self.now.astimezone(UTC).date()
        return today_utc - timedelta(days=1)

    def no_more_edits(self, edit_count):
        return edit_count is None or edit_count <= 0

    def wait_until_tomorrow(self):
        next_day_6am = (self.now + timedelta(days=1)).replace(hour=6)
        wait_sec = (next_day_6am - now()).total_seconds()
        if wait_sec > 0:
            wait_hours = wait_sec / 3600
            logger.info(f"waiting {wait_hours:.3f} hours until '{next_day_6am}'...")
            time.sleep(wait_sec)
        else:
            logger.info(f"already reached '{next_day_6am}', not waiting...")
