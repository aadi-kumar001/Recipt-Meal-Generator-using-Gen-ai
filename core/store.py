"""Recipe database and a tiny JSON feedback store."""
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_recipes(path=None):
    with open(path or DATA / "recipes.json", encoding="utf-8") as fh:
        return json.load(fh)


class FeedbackStore:
    """Stores ratings (1-5) per recipe id. Safe for simple multi-thread use."""

    def __init__(self, path=None):
        self.path = Path(path) if path else DATA / "feedback.json"
        self._lock = threading.Lock()
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    def add(self, recipe_id: str, rating: int):
        if not 1 <= rating <= 5:
            raise ValueError("rating must be 1-5")
        with self._lock:
            self._data.setdefault(recipe_id, []).append(rating)
            self._data[recipe_id] = self._data[recipe_id][-50:]
            try:
                self.path.write_text(json.dumps(self._data), encoding="utf-8")
            except OSError:
                pass  # read-only filesystem: keep in memory only

    def average(self, recipe_id: str):
        ratings = self._data.get(recipe_id)
        return sum(ratings) / len(ratings) if ratings else None
