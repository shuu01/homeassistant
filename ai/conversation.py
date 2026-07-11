from collections import deque
from queue import Queue
import threading

from logger import logger


class Conversation:

    def __init__(self, storage, max_messages=20):
        self.filename = "messages.json"
        self.storage = storage
        self.messages = deque(maxlen=max_messages)
        self.queue = Queue()

        self._load()

        self.thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="conversation",
        )
        self.thread.start()

    def stop(self):

        self.queue.join()
        self.queue.put(None)
        self.thread.join()

    def _load(self):

        try:
            messages = self.storage.load_json(self.filename)
            self.messages.extend(messages)

            logger.info(
                "Loaded %d messages.",
                len(self.messages),
            )
        except Exception as e:
            logger.warning(
                "Unable to load conversation: %s",
                e,
            )

    def _worker(self):

        while True:

            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                return
            role, text = item
            self.messages.append(
                {
                    "role": role,
                    "text": text,
                }
            )

            self.storage.save_json(
                self.filename,
                list(self.messages)
            )

            self.queue.task_done()

    def add(self, role, text):
        self.queue.put(
            (role, text)
        )

    def clear(self):
        self.messages.clear()
        self.storage.save_json(self.filename, [])
