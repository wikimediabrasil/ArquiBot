import logging
import requests

from django.conf import settings
from waybackpy import WaybackMachineSaveAPI

logger = logging.getLogger("arquibot")

class ArchivedURL:
    """
    URL archiver in Wayback Machine.
    """

    WAYBACK_PY_MAX_TRIES = 3
    USER_AGENT = settings.USER_AGENT

    def __init__(self, url: str):
        self.url = url
        self.archive_url = None

    @classmethod
    def already_archived(cls, url: str, archive_url: str):
        arch = cls(url)
        arch.archive_url = archive_url
        return arch

    def archive(self):
        logger.info(f"Attempting to archive URL: {self.url}")

        try:
            save_api = WaybackMachineSaveAPI(
                self.url,
                self.USER_AGENT,
                self.WAYBACK_PY_MAX_TRIES,
            )
            archive = save_api.save()
            if hasattr(archive, "archive_url") and archive.archive_url:
                logger.info(f"Archived via WaybackPy: {self.url} → {archive.archive_url}")
                self.archive_url = archive.archive_url
            else:
                logger.warning(f"WaybackPy returned no archive_url for {self.url}")
        except Exception as e:
            logger.error(f"WaybackPy failed for {self.url}: {e}")

        try:
            logger.info(f"Trying fallback Wayback availability API for: {self.url}")
            availability_resp = requests.get("https://archive.org/wayback/available", params={"url": self.url}, timeout=30)
            data = availability_resp.json()
            snapshot = data.get("archived_snapshots", {}).get("closest", {})
            if snapshot.get("available"):
                archive_url = snapshot.get("url")
                logger.info(f"Found existing archive: {self.url} → {archive_url}")
                self.archive_url = archive_url
            else:
                logger.warning(f"No archive found for: {self.url}")
        except Exception as e:
            logger.error(f"Exception in fallback availability API for {self.url}: {e}")

    @property
    def is_archived(self):
        return bool(self.archive_url) and "web.archive.org/web/" in self.archive_url

    @property
    def archive_timestamp(self):
        if self.archive_url:
            timestamp_and_rest = self.archive_url.split("web.archive.org/web/")[1]
            return timestamp_and_rest.split("/")[0]
