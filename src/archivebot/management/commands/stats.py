from django.core.management.base import BaseCommand
from stats.models import Statistics


class Command(BaseCommand):
    help = "Process statistics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yesterday",
            action="store_true",
            default=False,
        )

    def handle(self, *args, **options):
        yesterday = options["yesterday"]
        if yesterday:
            Statistics.objects.process_yesterday()
        else:
            Statistics.objects.process_statistics()
