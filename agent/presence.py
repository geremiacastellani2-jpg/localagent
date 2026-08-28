"""Tracciamento presenze — chi è davanti alla camera.

Il riconoscimento dei volti avviene nel browser (face-api.js) e i nomi
riconosciuti arrivano al server. Qui teniamo l'ultimo avvistamento di ciascuno e
distinguiamo un "arrivo" (riappare dopo un'assenza) dalla presenza continua, così
le notifiche non si ripetono a ogni frame.
"""

from __future__ import annotations

import threading
import time

from .config import settings

_lock = threading.Lock()
_last_seen: dict[str, float] = {}


def update(names: list[str]) -> list[str]:
    """Registra i volti visti ora; ritorna quelli appena *arrivati*."""
    now = time.time()
    gap = settings.presence_arrival_gap_seconds
    arrivals = []
    with _lock:
        for n in names:
            if not n or n.lower() in {"unknown", "sconosciuto"}:
                continue
            prev = _last_seen.get(n)
            if prev is None or (now - prev) > gap:
                arrivals.append(n)
            _last_seen[n] = now
    return arrivals


def present(within: float = 10.0) -> list[str]:
    """Chi è stato visto negli ultimi `within` secondi."""
    now = time.time()
    with _lock:
        return [n for n, ts in _last_seen.items() if (now - ts) <= within]
