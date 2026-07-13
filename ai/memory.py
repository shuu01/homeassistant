from logger import logger

class Memory:

    def __init__(self, storage):
        self.filename = "facts.json"
        self.storage = storage
        self.facts = {}

        self._load()

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

    def update(self, new_facts):

        if not new_facts:
            return

        changed = False

        for key, value in new_facts.items():
            current = self.facts.get(key, [])
            if not isinstance(current, list):
                current = [current]
            if not isinstance(value, list):
                value = [value]

            merged = list(dict.fromkeys(current + value))

            if merged != current:
                self.facts[key] = merged
                changed = True

        if changed:
            try:
                self.storage.save_json(self.filename, self.facts)
                logger.info("Memory saved")
            except Exception:
                logger.exception("Failed to save memory")
