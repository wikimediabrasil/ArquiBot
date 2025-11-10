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

    def handle(self, *args, **options):
        date_str = options["date"]
        date = datetime.strptime(date_str, "%Y-%m-%d")
        run_rc_date(date)
