"""Tutte le informazioni della camera, in forma leggibile (per il modello) e JSON
(per la UI e per altri agenti via /vision).

Le posizioni sono dal punto di vista dell'utente: l'anteprima è specchiata, quindi
l'asse orizzontale viene ribaltato rispetto al frame grezzo.
"""

from __future__ import annotations

import time
from collections import Counter

from . import state
from .labels import label_it


def position_words(box: list[float]) -> str:
    """'in basso a sinistra, da vicino' — da un riquadro normalizzato [x,y,w,h]."""
    x, y, w, h = (list(box) + [0, 0, 0, 0])[:4]
    cx = 1.0 - (x + w / 2)  # specchio: come lo vede l'utente
    cy = y + h / 2
    horiz = "a sinistra" if cx < 0.35 else ("a destra" if cx > 0.65 else "al centro")
    vert = "in alto" if cy < 0.3 else ("in basso" if cy > 0.7 else "")
    area = max(0.0, w) * max(0.0, h)
    dist = "da vicino" if area > 0.28 else ("da lontano" if area < 0.03 else "")
    where = f"{vert} {horiz}".strip()
    return f"{where}, {dist}" if dist else where


def describe_detections(dets: list[dict]) -> str:
    """'persona (al centro, da vicino), tazza (in basso a sinistra)'."""
    if not dets:
        return ""
    parts = []
    for d in sorted(dets, key=lambda d: -(d.get("score") or 0))[:12]:
        parts.append(f"{label_it(d.get('label', ''))} ({position_words(d.get('box') or [])})")
    return ", ".join(parts)


def count_objects(labels: list[str]) -> str:
    counted = Counter(label_it(x) for x in labels)
    return ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counted.items())


def _fmt_time(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def report_lines(session: str) -> list[str]:
    """Righe per lo "Stato attuale" nel system prompt."""
    age = state.frame_age(session)
    if age is None or age > 20:
        lines = ["- Camera: spenta (nessuna vista disponibile)"]
    else:
        dets = state.get_detections(session)
        objs = state.get_objects(session)
        seen = describe_detections(dets) if dets else count_objects(objs)
        faces = state.get_faces(session)
        line = f"- Camera: ATTIVA (frame di {int(age)}s fa)"
        line += f" — in vista: {seen}" if seen else " — nessun oggetto riconosciuto al momento"
        if faces:
            line += f"; persone riconosciute: {', '.join(sorted(set(faces)))}"
        lines = [line]
        scene = state.get_scene(session)
        if scene:
            text, sage = scene
            lines.append(f"- Scena (descritta {int(sage)}s fa): {text}")
    events = state.get_events(session, n=5)
    if events:
        lines.append(
            "- Eventi camera recenti: "
            + " · ".join(f"{_fmt_time(ts)} {txt}" for ts, txt in events)
        )
    return lines


def report_text(session: str) -> str:
    """Report completo per lo strumento current_view."""
    age = state.frame_age(session)
    if age is None:
        return "La camera non è attiva: non sto vedendo niente in questo momento."
    fresh = "in tempo reale" if age < 5 else f"ultimo frame {int(age)}s fa"
    dets = state.get_detections(session)
    objs = state.get_objects(session)
    out = [f"Camera attiva ({fresh})."]
    seen = describe_detections(dets) if dets else count_objects(objs)
    out.append(f"In vista: {seen}." if seen else "Nessun oggetto riconosciuto al momento.")
    faces = state.get_faces(session)
    if faces:
        out.append("Persone riconosciute: " + ", ".join(sorted(set(faces))) + ".")
    scene = state.get_scene(session)
    if scene:
        out.append(f"Scena (descritta {int(scene[1])}s fa): {scene[0]}")
    err = state.get_scene_error(session)
    if err and not scene:
        out.append(f"(descrizione automatica non disponibile: {err})")
    events = state.get_events(session, n=6)
    if events:
        out.append("Eventi recenti: " + " · ".join(f"{_fmt_time(ts)} {txt}" for ts, txt in events))
    out.append("Per una descrizione fresca e dettagliata usa `look`.")
    return "\n".join(out)


def json_report(session: str) -> dict:
    """Tutte le informazioni della camera, per la UI e per altri agenti."""
    age = state.frame_age(session)
    dets = state.get_detections(session)
    scene = state.get_scene(session)
    return {
        "active": age is not None and age <= 20,
        "frame_age": None if age is None else round(age, 1),
        "detections": [
            {
                "label": d["label"],
                "label_it": label_it(d["label"]),
                "score": d["score"],
                "box": d["box"],
                "position": position_words(d["box"]),
            }
            for d in dets
        ],
        "objects": dict(Counter(label_it(x) for x in state.get_objects(session))),
        "faces": sorted(set(state.get_faces(session))),
        "scene": None if not scene else {"text": scene[0], "age": round(scene[1], 1)},
        "scene_error": state.get_scene_error(session),
        "events": [{"time": _fmt_time(ts), "text": txt} for ts, txt in state.get_events(session, n=10)],
    }
