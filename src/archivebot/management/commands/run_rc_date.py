from datetime import datetime
from django.core.management.base import BaseCommand
from archivebot.utils import run_rc_date


class Command(BaseCommand):
    help = "Run the archive bot on a Recent Changes UTC date"

    def add_arguments(self, parser):
        parser.add_argument(
            "date",
            type=str,
            help="Date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--stop-at-edit-count",
            type=int,
            default=None,
            help="Stop after this many edits",
        )

    def handle(self, *args, **options):
        date_str = options["date"]
        stop_at_edit_count = self.stop_at_edit_count(options["stop_at_edit_count"])
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        run_rc_date(date, stop_at_edit_count=stop_at_edit_count)

    def stop_at_edit_count(self, stop_at_edit_coun_str: str = None):
        try:
            value = int(stop_at_edit_coun_str)
            if value >= 1:
                return value
        except (ValueError, TypeError):
            pass
        return None
