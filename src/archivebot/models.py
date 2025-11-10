import logging
import json
from typing import List
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import requests
from django.db import models
from django.conf import settings
from django.utils.translation import pgettext_lazy

logger = logging.getLogger("arquibot")

HEADERS = {
    "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
    "User-Agent": settings.USER_AGENT,
    "Content-Type": "application/json",
}


class Wikipedia(models.Model):
    code = models.CharField(max_length=32, help_text="'pt', 'test', etc")

    def __str__(self):
        return self.code + " wikipedia"

    @staticmethod
    def get() -> "Wikipedia":
        wikipedia, _ = Wikipedia.objects.get_or_create(code=settings.WIKIPEDIA_CODE)
        return wikipedia

    def url(self):
        return f"https://{self.code}.wikipedia.org"

    def action_api(self):
        return self.url() + "/w/api.php"

    def rest_api(self):
        return self.url() + "/w/rest.php/v1"

    def headers(self):
        return {
            "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
            "User-Agent": settings.USER_AGENT,
            "Content-Type": "application/json",
        }



class ArticleCheck(models.Model):
    wikipedia = models.ForeignKey(Wikipedia, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)

    diff_new_id = models.PositiveIntegerField(blank=True, null=True)
    diff_old_id = models.PositiveIntegerField(blank=True, null=True)

    edit_id = models.PositiveIntegerField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        suffix = ""
        if self.diff_new_id and self.diff_old_id:
            suffix = f" | {self.diff_old_id} -> {self.diff_new_id}"
        return f"[{self.title}{suffix}]"

    def url(self):
        return self.wikipedia.url() + "/wiki/" + self.title

    def edit_url(self):
        if self.edit_id:
            return f"{self.wikipedia.url()}/w/index.php?title={self.title}&diff=prev&oldid={self.edit_id}"

    # ------------
    # Diff methods
    # ------------

    @staticmethod
    def create_from_recent_changes_diffs(diffs: List["Diff"]) -> List["ArticleCheck"]:
        articles = []
        for diff in diffs:
            article = ArticleCheck.objects.create(
                wikipedia=diff.wikipedia,
                title=diff.title,
                diff_new_id=diff.new_revision_id,
                diff_old_id=diff.old_revision_id,
            )
            articles.append(article)
        return articles

    @property
    def has_diff(self):
        return self.diff_new_id and self.diff_old_id

    def _request_diff_compare(self) -> dict:
        endpoint = (
            self.wikipedia.rest_api()
            + "/revision/"
            + str(self.diff_old_id)
            + "/compare/"
            + str(self.diff_new_id)
        )
        response = requests.get(endpoint, headers=self.wikipedia.headers())
        response.raise_for_status()
        return response.json()

    def diff_inserted_wikitext(self):
        if not (self.diff_new_id and self.diff_old_id):
            raise ValueError(f"{self} no diff ids")
        logger.debug(f"{self} obtaining diff change...")
        data = self._request_diff_compare()
        changes = data["diff"]
        inserted = []
        for change in changes:
            allowed_types = [1, 3, 5]
            if change.get("type") in allowed_types:
                if change.get("text"):
                    inserted.append(change["text"])
        return "\n".join(inserted)

    # ----------------
    # Page interaction
    # ----------------

    def _page_endpoint(self):
        # `/` is a path delimiter but it needs to be a path argument
        # so we need to escape it manually
        base = self.wikipedia.rest_api()
        return base + "/page/" + quote(self.title).replace("/", "%2F")

    def page_data(self):
        logger.debug(f"{self} obtaining page data...")
        response = requests.get(
            self._page_endpoint(),
            headers=self.wikipedia.headers(),
        )
        response.raise_for_status()
        return response.json()

    def source(self):
        return self.page_data().get("source", "")

    def _request_edit(self, new_source: str, comment: str, latest_id: str):
        logger.debug(f"{self} sending edit request...")
        payload = {
            "source": new_source,
            "comment": comment,
            "latest": {"id": latest_id},
        }
        response = requests.put(
            self._page_endpoint(),
            headers=self.wikipedia.headers(),
            data=json.dumps(payload),
        )
        response.raise_for_status()
        return response.json()

    def edit_and_save(self, new_source: str, comment: str, latest_id: str):
        data = self._request_edit(new_source, comment, latest_id)
        self.edit_id = data.get("latest", {}).get("id")
        self.save()


class UrlCheck(models.Model):
    article = models.ForeignKey(
        ArticleCheck,
        on_delete=models.CASCADE,
        related_name="urls",
    )
    url = models.URLField()

    class ArchiveStatus(models.TextChoices):
        RUNNING = (
            "running",
            pgettext_lazy("url-status-running", "check running"),
        )
        ARCHIVED = (
            "archived",
            pgettext_lazy("url-status-archived", "successful archive"),
        )
        FAILED = (
            "failed",
            pgettext_lazy("url-status-failed", "archive failed"),
        )
        IGNORED_PERMALINK = (
            "ignored_permalink",
            pgettext_lazy("url-status-ignored-permalink", "Permalink ignored"),
        )
        IGNORED_ARCHIVED = (
            "ignored_archived",
            pgettext_lazy("url-status-ignored-archived", "URL already archived"),
        )

    status = models.CharField(
        max_length=32,
        blank=True,
        choices=ArchiveStatus.choices,
        default=ArchiveStatus.RUNNING,
    )
    archive_url = models.URLField(blank=True, null=True)
    is_url_dead = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def set_ignored_permalink(self):
        self.status = self.ArchiveStatus.IGNORED_PERMALINK
        self.save()

    def set_ignored_archived(self):
        self.status = self.ArchiveStatus.IGNORED_ARCHIVED
        self.save()

    def set_failed(self, is_url_dead: bool):
        self.is_url_dead = is_url_dead
        self.status = self.ArchiveStatus.FAILED
        self.save()

    def set_archived(self, archive_url: str, is_url_dead: bool):
        self.archive_url = archive_url
        self.is_url_dead = is_url_dead
        self.status = self.ArchiveStatus.ARCHIVED
        self.save()


@dataclass
class Diff:
    title: str
    page_id: int
    old_revision_id: int
    new_revision_id: int
    wikipedia: Wikipedia

    @classmethod
    def from_rc_edit(cls, rc_edit, wikipedia: Wikipedia):
        return cls(
            title=rc_edit["title"],
            page_id=rc_edit["pageid"],
            old_revision_id=rc_edit["old_revid"],
            new_revision_id=rc_edit["revid"],
            wikipedia=wikipedia,
        )

    def combine(self, other: "Diff"):
        if other.new_revision_id > self.new_revision_id:
            self.new_revision_id = other.new_revision_id
        if other.old_revision_id < self.old_revision_id:
            self.old_revision_id = other.old_revision_id


class RecentChanges:
    def __init__(self, start_time: datetime, end_time: datetime, wikipedia: Wikipedia):
        self.start_time = start_time
        self.end_time = end_time
        self.wikipedia = wikipedia

    def load(self):
        params = {
            "action": "query",
            "format": "json",
            "list": "recentchanges",
            "rcnamespace": 0,
            "rclimit": "max",
            "rcshow": "!bot",
            "rctype": "edit",
            "rcstart": self.end_time.isoformat(),
            "rcend": self.start_time.isoformat(),
            "rcprop": "title|ids|timestamp",
        }

        all_edits = []

        while True:
            response = requests.get(
                self.wikipedia.action_api(), params=params, headers=HEADERS
            )
            response.raise_for_status()
            data = response.json()

            edits = data.get("query", {}).get("recentchanges", [])
            all_edits.extend(edits)

            # Handle continuation
            if "continue" in data:
                params.update(data["continue"])
            else:
                break

        self.all_edits = all_edits

    def combined_diffs(self) -> List[Diff]:
        result = {}
        for rc_edit in self.all_edits:
            diff = Diff.from_rc_edit(rc_edit, self.wikipedia)
            result.setdefault(diff.page_id, diff)
            result[diff.page_id].combine(diff)
        return result.values()
