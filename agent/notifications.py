"""Coda di notifiche proattive.

Lo scheduler e la percezione ci scrivono ("⏰ promemoria", "👤 è arrivato X",
"☀️ rassegna del mattino"); la UI web fa polling su /notifications e le mostra.
In memoria: sono messaggi effimeri, non vanno persistiti.
"""

from __future__ import annotations

import itertools
import threading
import time

_lock = threading.Lock()
_items: list[dict] = []
_counter = itertools.count(1)
_MAX = 200


def push(text: str, kind: str = "info") -> int:
    with _lock:
        item = {"id": next(_counter), "text": text, "kind": kind, "ts": time.time()}
        _items.append(item)
        if len(_items) > _MAX:
            del _items[:-_MAX]
        return item["id"]


def since(cursor: int) -> list[dict]:
    with _lock:
        return [dict(i) for i in _items if i["id"] > cursor]


def latest_id() -> int:
    with _lock:
        return _items[-1]["id"] if _items else 0
