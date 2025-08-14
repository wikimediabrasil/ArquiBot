from django.core.management.base import BaseCommand
from archivebot.utils import run_archive_bot
from django.conf import settings

headers = {
    "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
    "User-Agent": "Arquibot/1.0 (naomi.ibeh69@gmail.com)"
}

class Command(BaseCommand):
    help = "Run the ptwiki archive bot"

    def handle(self, *args, **kwargs):
        run_archive_bot()
