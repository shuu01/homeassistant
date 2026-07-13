import json
import os

import requests
import threading
from queue import Queue, Empty


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
        self._lock = threading.Lock()

        # filename -> python object
        self._cache = {}

        # filename -> serialized json string
        self._dirty = set()

        self._queue = Queue()
        self._stop = threading.Event()

        self._load_gist()

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="gist-storage",
        )
        self._thread.start()

    def _load_gist(self):

        response = requests.get(
            self.url,
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        gist = response.json()

        for filename, file in gist["files"].items():

            content = file["content"]

            if not content.strip():
                self._cache[filename] = {}
                continue

            try:
                self._cache[filename] = json.loads(content)
            except Exception:
                self._cache[filename] = {}

    def load_json(self, filename, default=None):
        if default is None:
            default = {}

        with self._lock:
            return self._cache.get(filename, default)

    def save_json(self, filename, data):
        with self._lock:

            self._cache[filename] = data
            self._dirty.add(filename)

        # wake worker (duplicates are harmless)
        self._queue.put(None)

    def _worker(self):

        while not self._stop.is_set():

            try:
                self._queue.get(timeout=1)
            except Empty:
                pass

            try:
                self._flush()
            except Exception:
                logger.exception("Failed to flush gist")

    def _flush(self):

        with self._lock:

            if not self._dirty:
                return

            payload = {
                "files": {
                    filename: {
                        "content": json.dumps(
                            self._cache[filename],
                            indent=2,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    }
                    for filename in self._dirty
                }
            }

            self._dirty.clear()

        try:

            response = requests.patch(
                self.url,
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            response.raise_for_status()

        except Exception:

            # restore dirty set so next flush retries
            with self._lock:
                self._dirty.update(payload["files"].keys())

            raise

    def stop(self):

        self._stop.set()
        self._queue.put(None)
        self._thread.join()
