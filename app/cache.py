"""
Small in-process caches.

Nothing here needs to be Redis for a 24h hackathon prototype: the demo
dataset is 100 patients / ~15MB and the DuckDB file is read-only, so a
plain LRU dict is enough and keeps the "patient data never leaves this
process" story intact (no external cache service to reason about).

What gets cached:
  - Reconstructed Timeline objects, keyed by subject_id. This is the
    expensive part of a request (a dozen+ joined queries across
    admissions/transfers/labs/meds/procedures/ICU stays/chartevents),
    and it's identical for a given patient on every subsequent request
    -- both for GET /timeline and for the "timeline" intent in /ask.
  - Concept dictionaries (d_labitems / d_items) are handled separately
    in app/ai/concepts.py: they're global and loaded once at startup,
    not per-patient, so they don't need LRU eviction at all.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from app.models import Timeline


class LRUCache:
    def __init__(self, max_size: int = 64):
        self.max_size = max_size
        self._data: "OrderedDict[int, Timeline]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: int) -> Timeline | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def set(self, key: int, value: Timeline) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            if len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


from app.config import TIMELINE_CACHE_SIZE  # noqa: E402

timeline_cache = LRUCache(max_size=TIMELINE_CACHE_SIZE)