import json
import requests
import logging
from urllib.parse import quote
from django.conf import settings

from archivebot.models import ArticleCheck
from archivebot.recent_changes import Diff

logger = logging.getLogger("arquibot")


class WikipediaClient:
    HEADERS = {
        "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
        "User-Agent": settings.USER_AGENT,
        "Content-Type": "application/json",
    }


class WikipediaDiffRestClient(WikipediaClient):
    def __init__(self, diff: Diff):
        self.diff = diff

    def endpoint(self):
        base = self.diff.wikipedia.rest_api()
        return (
            base
            + "/revision/"
            + str(self.diff.old_revision_id)
            + "/compare/"
            + str(self.diff.new_revision_id)
        )

    def diff_changes(self):
        logger.debug(
            f"[{self.diff.title}] {self.diff.old_revision_id} ->"
            f" {self.diff.new_revision_id} obtaining diff change..."
        )
        response = requests.get(
            self.endpoint(),
            headers=self.HEADERS,
        )
        response.raise_for_status()
        return response.json()

    def diff_inserted_wikitext(self):
        changes = self.diff_changes()["diff"]
        inserted = []
        for change in changes:
            allowed_types = [1, 3, 5]
            if change.get("type") in allowed_types:
                if change.get("text"):
                    inserted.append(change["text"])
        return "\n".join(inserted)


class WikipediaRestClient(WikipediaClient):
    def __init__(self, article: ArticleCheck):
        self.article = article

    def endpoint(self):
        # `/` is a path delimiter but it needs to be a path argument
        # so we need to escape it manually
        base = self.article.wikipedia.rest_api()
        return base + "/page/" + quote(self.article.title).replace("/", "%2F")

    def edit(self, new_source: str, comment: str, latest_id: str):
        logger.debug(f"[{self.article}] sending edit request...")
        payload = {
            "source": new_source,
            "comment": comment,
            "latest": {"id": latest_id},
        }
        response = requests.put(
            self.endpoint(),
            headers=self.HEADERS,
            data=json.dumps(payload),
        )
        response.raise_for_status()
        return response.json()

    def page_data(self):
        logger.debug(f"[{self.article}] obtaining page data...")
        response = requests.get(
            self.endpoint(),
            headers=self.HEADERS,
        )
        response.raise_for_status()
        return response.json()

    def source(self):
        return self.page_data().get("source", "")
