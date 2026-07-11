import json
import os

import requests


class GistStorage:

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.gist_id = os.getenv("GIST_ID")

        self.url = f"https://api.github.com/gists/{self.gist_id}"

        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def load_json(self, filename, default=None):
        if default is None:
            default = {}

        response = requests.get(
            self.url,
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        gist = response.json()

        if filename not in gist["files"]:
            return default

        content = gist["files"][filename]["content"]

        if not content.strip():
            return default

        return json.loads(content)

    def save_json(self, filename, data):
        payload = {
            "files": {
                filename: {
                    "content": json.dumps(
                        data,
                        indent=2,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                }
            }
        }

        response = requests.patch(
            self.url,
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
