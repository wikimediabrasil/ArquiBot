from django.core.management.base import BaseCommand, CommandError
from archivebot.utils import run_archive_bot
import time
import logging


class Command(BaseCommand):
    help = "Run the archive bot every N hours (default: 24 hours)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=168,  # default now is 168(1 week) hours
            help="Interval in hours between bot runs (default: 24)"
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval <= 0:
            raise CommandError("Interval must be greater than 0")

        logging.info(f"Starting archive bot. Running every {interval} hour(s).")

        while True:
            try:
                self.stdout.write(self.style.SUCCESS("Running archive bot cycle..."))

                # === Run your archive bot here ===
                run_archive_bot(interval)

                logging.info("Bot cycle completed successfully.")

            except Exception as e:
                logging.error(f"Error while running bot: {e}")
                self.stderr.write(self.style.ERROR(f"Error: {e}"))

            logging.info(f"Sleeping for {interval} hour(s)...")
            time.sleep(interval * 3600)  # Convert hours to seconds
