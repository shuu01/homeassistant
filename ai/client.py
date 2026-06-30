import os
import requests
import time
from google.auth.transport.requests import Request
from google.oauth2 import id_token

import logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

class Service:
    def __init__(self, name, base_url):
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

    def wait_until_ready(self):
        while True:
            try:
                response = self.get("/health", timeout=2)
                response.raise_for_status()
                logger.info(f"{self.name} ready")
                return
            except Exception as e:
                logger.error(e)
                logger.info(f"Waiting for {self.name}...")
                time.sleep(5)

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
