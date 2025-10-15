from django.core.management.base import BaseCommand
from archivebot.utils import run_article


class Command(BaseCommand):
    help = "Run the archive bot every N hours (default: 24 hours)"

    def add_arguments(self, parser):
        parser.add_argument(
            "article",
            type=str,
            help="Article page title",
        )

    def handle(self, *args, **options):
        page_title = options["article"]
        run_article(page_title)
