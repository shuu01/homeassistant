import os
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

class ServiceClient:
    def __init__(self, base_url, name=""):
        self.base_url = base_url.rstrip("/")
        self._token = None
        self._expires = 0
        self.name = name

        self.cloud_run = os.getenv("CLOUD_RUN") == "1"

def _headers(self):
    if not self.cloud_run:
        return {}

    if time.time() > self._expires:
        self._token = id_token.fetch_id_token(
            Request(),
            self.base_url,
        )
        self._expires = time.time() + 3000   # refresh ~every 50 min

    return {
        "Authorization": f"Bearer {self._token}"
    }

    def post(self, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())

        return requests.post(
            f"{self.base_url}{path}",
            headers=headers,
            **kwargs,
        )

    def get(self, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())

        return requests.get(
            f"{self.base_url}{path}",
            headers=headers,
            **kwargs,
        )
