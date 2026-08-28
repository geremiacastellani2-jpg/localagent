"""Stato runtime condiviso, in memoria (utente singolo).

Tiene l'ultimo frame inviato dalla UI web per ogni sessione, così lo strumento
di vista può "guardare" senza aprire lui stesso la camera. I frame non vengono
mai scritti su disco.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_latest_frames: dict[str, str] = {}  # session -> data URL (jpeg base64)


def set_frame(session: str, data_url: str | None) -> None:
    with _lock:
        if data_url:
            _latest_frames[session] = data_url
        else:
            _latest_frames.pop(session, None)


def get_frame(session: str) -> str | None:
    with _lock:
        return _latest_frames.get(session)
