from typing import List
from datetime import datetime
from dataclasses import dataclass

import requests
from django.conf import settings

from archivebot.models import Wikipedia

HEADERS = {
    "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
    "User-Agent": settings.USER_AGENT,
    "Content-Type": "application/json",
}


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
