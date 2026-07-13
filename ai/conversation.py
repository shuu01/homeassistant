from collections import deque
from logger import logger
import time


class Conversation:
    CONVERSATION_TTL = 60 * 60  # 1 hour

    def __init__(self, storage, max_messages=20):
        self.filename = "messages.json"
        self.storage = storage
        self.messages = deque(maxlen=max_messages)

        self._load()

    def _load(self):

        try:
            messages = self.storage.load_json(self.filename)
            self.messages.extend(messages)

            logger.info(f"Loaded {len(self.messages)} messages.")
        except Exception as e:
            logger.warning(
                f"Failed to load messages: {e}"
            )

    def add(self, role, text):

        self.messages.append(
            {
                "role": role,
                "text": text,
                "timestamp": time.time(),
            }
        )

        self.storage.save_json(
            self.filename,
            list(self.messages)
        )

    def clear(self):
        self.messages.clear()
        self.storage.save_json(self.filename, [])

    def recent_messages(self):
        cutoff = time.time() - CONVERSATION_TTL

        return [
            {
                "role": m["role"],
                "text": m["text"],
            }
            for m in self.messages
            if m.get("timestamp", 0) >= cutoff
        ]
