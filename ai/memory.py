import queue
import threading

from logger import logger


class Memory:

    def __init__(self, storage):
        self.filename = "facts.json"
        self.storage = storage
        self.facts = {}
        self.queue = queue.Queue()

        self._load()

        self.thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="memory",
        )
        self.thread.start()

    def _load(self):
        try:
            self.facts = self.storage.load_json(self.filename)
            logger.info(
                f"Loaded {len(self.facts)} facts"
            )
        except FileNotFoundError:
            logger.info(
                "Memory file not found, starting with empty memory"
            )
            self.facts = {}
        except Exception as e:
            logger.exception(
                f"Failed to load memory: {e}"
            )
            self.facts = {}

    def stop(self):

        self.queue.join()
        self.queue.put(None)
        self.thread.join()

    def update(self, new_facts):
        if new_facts:
            self.queue.put(new_facts)

    def _worker(self):
        while True:
            new_facts = self.queue.get()
            if new_facts is None:
                self.queue.task_done()
                return

            changed = False

            for key, value in new_facts.items():
                if self.facts.get(key) != value:
                    self.facts[key] = value
                    changed = True

            if changed:
                try:
                    self.storage.save_json(self.filename, self.facts)
                    logger.info("Memory saved")
                except Exception:
                    logger.exception("Failed to save memory")

            self.queue.task_done()
