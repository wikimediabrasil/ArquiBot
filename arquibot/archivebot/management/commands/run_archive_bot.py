from django.core.management.base import BaseCommand
from archivebot.utils import run_archive_bot

class Command(BaseCommand):
    help = "Run the ptwiki archive bot"

    def handle(self, *args, **kwargs):
        run_archive_bot()
