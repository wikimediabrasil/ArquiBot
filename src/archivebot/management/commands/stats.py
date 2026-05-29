from django.core.management.base import BaseCommand
from stats.models import Statistics


class Command(BaseCommand):
    help = "Process statistics"

    def handle(self, *args, **options):
        Statistics.objects.process_statistics()
