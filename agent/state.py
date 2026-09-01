"""Stato runtime condiviso, in memoria (utente singolo): la "vista live".

Per ogni sessione tiene:
  - l'ultimo frame (data URL) e quando è arrivato;
  - le rilevazioni correnti: etichetta, confidenza, riquadro normalizzato 0..1;
  - i volti riconosciuti;
  - la descrizione della scena (dal VLM, aggiornata in background) e la sua età;
  - gli eventi recenti (cosa è comparso/sparito, chi è stato riconosciuto).

Nulla viene scritto su disco.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from .labels import label_it

_lock = threading.Lock()
_frames: dict[str, str] = {}
_updated: dict[str, float] = {}
_seq: dict[str, int] = {}
_objects: dict[str, list[str]] = {}          # etichette (con duplicati, per contare)
_detections: dict[str, list[dict]] = {}      # {label, score, box:[x,y,w,h] normalizzato}
_faces: dict[str, list[str]] = {}
_scene: dict[str, tuple[str, float]] = {}    # (testo, timestamp)
_scene_error: dict[str, str] = {}
_events: dict[str, deque] = {}
_prev_set: dict[str, frozenset] = {}         # insieme all'aggiornamento precedente
_logged_set: dict[str, frozenset] = {}       # ultimo insieme registrato negli eventi


def _ev(session: str) -> deque:
    return _events.setdefault(session, deque(maxlen=40))


def add_event(session: str, text: str) -> None:
    with _lock:
        _ev(session).append((time.time(), text))


def _track_changes(session: str, labels: list[str]) -> None:
    """Registra "in vista" / "non più in vista" solo per cambi stabili (2 aggiornamenti)."""
    s = frozenset(labels)
    prev = _prev_set.get(session)
    _prev_set[session] = s
    if prev is None or s != prev:
        return  # aspetta che il cambiamento sia stabile
    logged = _logged_set.get(session, frozenset())
    if s == logged:
        return
    now = time.time()
    appeared = sorted(label_it(x) for x in (s - logged))
    gone = sorted(label_it(x) for x in (logged - s))
    if appeared:
        _ev(session).append((now, "in vista: " + ", ".join(appeared)))
    if gone:
        _ev(session).append((now, "non più in vista: " + ", ".join(gone)))
    _logged_set[session] = s


def set_frame(
    session: str,
    data_url: str | None,
    objects: list[str] | None = None,
    detections: list[dict] | None = None,
) -> None:
    with _lock:
        if data_url:
            _frames[session] = data_url
            _updated[session] = time.time()
            _seq[session] = _seq.get(session, 0) + 1
        else:
            if session in _frames:
                _ev(session).append((time.time(), "camera spenta"))
            for d in (_frames, _updated, _objects, _detections, _faces, _prev_set, _logged_set):
                d.pop(session, None)
            return
        if detections is not None:
            _detections[session] = [
                {
                    "label": str(d.get("label", "")),
                    "score": float(d.get("score", 0) or 0),
                    "box": [float(v) for v in (d.get("box") or [0, 0, 0, 0])][:4],
                }
                for d in detections
            ]
            if objects is None:
                objects = [d["label"] for d in _detections[session]]
        if objects is not None:
            _objects[session] = list(objects)
            _track_changes(session, list(objects))


def get_frame(session: str) -> str | None:
    with _lock:
        return _frames.get(session)


def frame_seq(session: str) -> int:
    with _lock:
        return _seq.get(session, 0)


def get_objects(session: str) -> list[str]:
    with _lock:
        return list(_objects.get(session, []))


def get_detections(session: str) -> list[dict]:
    with _lock:
        return [dict(d) for d in _detections.get(session, [])]


def set_faces(session: str, names: list[str] | None) -> None:
    with _lock:
        _faces[session] = list(names or [])


def get_faces(session: str) -> list[str]:
    with _lock:
        return list(_faces.get(session, []))


def set_scene(session: str, text: str) -> None:
    with _lock:
        _scene[session] = (text, time.time())
        _scene_error.pop(session, None)


def set_scene_error(session: str, err: str) -> None:
    with _lock:
        _scene_error[session] = err


def get_scene(session: str) -> tuple[str, float] | None:
    """(testo, età in secondi) o None."""
    with _lock:
        item = _scene.get(session)
    return (item[0], time.time() - item[1]) if item else None


def get_scene_error(session: str) -> str | None:
    with _lock:
        return _scene_error.get(session)


def get_events(session: str, n: int = 6) -> list[tuple[float, str]]:
    with _lock:
        return list(_ev(session))[-n:]


def frame_age(session: str) -> float | None:
    """Secondi trascorsi dall'ultimo frame, o None se non c'è."""
    with _lock:
        ts = _updated.get(session)
    return (time.time() - ts) if ts else None


def active_sessions(within: float = 30.0) -> list[str]:
    now = time.time()
    with _lock:
        return [s for s, ts in _updated.items() if (now - ts) <= within]
