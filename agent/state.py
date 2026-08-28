"""Stato runtime condiviso, in memoria (utente singolo).

Per ogni sessione tiene:
  - l'ultimo frame inviato dalla UI (aggiornato in continuo: è il feed "live");
  - l'elenco degli oggetti rilevati in tempo reale nel browser (vista live).

Nulla di tutto ciò viene scritto su disco.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_frames: dict[str, str] = {}           # session -> data URL (jpeg base64)
_objects: dict[str, list[str]] = {}    # session -> etichette oggetti correnti
_faces: dict[str, list[str]] = {}      # session -> nomi volti riconosciuti
_updated: dict[str, float] = {}        # session -> timestamp ultimo frame


def set_frame(session: str, data_url: str | None, objects: list[str] | None = None) -> None:
    with _lock:
        if data_url:
            _frames[session] = data_url
            _updated[session] = time.time()
        else:
            _frames.pop(session, None)
            _updated.pop(session, None)
        if objects is not None:
            _objects[session] = objects


def get_frame(session: str) -> str | None:
    with _lock:
        return _frames.get(session)


def get_objects(session: str) -> list[str]:
    with _lock:
        return list(_objects.get(session, []))


def set_faces(session: str, names: list[str] | None) -> None:
    with _lock:
        _faces[session] = list(names or [])


def get_faces(session: str) -> list[str]:
    with _lock:
        return list(_faces.get(session, []))


def frame_age(session: str) -> float | None:
    """Secondi trascorsi dall'ultimo frame, o None se non c'è."""
    with _lock:
        ts = _updated.get(session)
    return (time.time() - ts) if ts else None
