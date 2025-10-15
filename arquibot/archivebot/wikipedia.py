import json
import requests
from urllib.parse import quote
from django.conf import settings


class WikipediaClient:
    HEADERS = {
        "Authorization": f"Bearer {settings.ARQUIBOT_TOKEN}",
        "User-Agent": settings.USER_AGENT,
        "Content-Type": "application/json",
    }


class WikipediaRestClient(WikipediaClient):
    BASE = settings.WIKIPEDIA_URL + "/w/rest.php/v1"

    def __init__(self, title):
        self.title = title

    def endpoint(self):
        # `/` is a path delimiter but it needs to be a path argument
        # so we need to escape it manually
        return self.BASE + "/page/" + quote(self.title).replace("/", "%2F")

    def edit(self, new_source: str, comment: str, latest_id: str):
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
