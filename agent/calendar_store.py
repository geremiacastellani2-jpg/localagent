"""Calendario — archivio locale (fonte di verità).

Gli eventi vivono qui, in SQLite. La sincronizzazione con un server CalDAV
(iCloud, Google, Fastmail…) è un livello sopra (vedi caldav_sync.py): se non è
configurata, il calendario funziona comunque in locale.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from .db import connect

ISO = "%Y-%m-%dT%H:%M:%S"


def normalize_dt(value: str, all_day: bool = False) -> str:
    """Porta una stringa data/ora al formato ISO canonico usato nel DB.

    Accetta ISO 8601 ('2026-08-29', '2026-08-29 15:00', '2026-08-29T15:00:00').
    Solleva ValueError se non interpretabile.
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("data/ora mancante")
    dt = datetime.fromisoformat(s)
    if all_day:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.strftime(ISO)


def now_iso() -> str:
    return datetime.now().strftime(ISO)


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "uid": r["uid"],
        "title": r["title"],
        "start_at": r["start_at"],
        "end_at": r["end_at"],
        "all_day": bool(r["all_day"]),
        "location": r["location"] or "",
        "notes": r["notes"] or "",
        "caldav_href": r["caldav_href"],
    }


def add_event(
    title: str,
    start_at: str,
    end_at: str | None = None,
    all_day: bool = False,
    location: str = "",
    notes: str = "",
    uid: str | None = None,
    caldav_href: str | None = None,
) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("titolo mancante")
    start_norm = normalize_dt(start_at, all_day)
    end_norm = normalize_dt(end_at, all_day) if end_at else None
    uid = uid or f"{uuid.uuid4()}@maggiordomo.local"

    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO events (uid, title, start_at, end_at, all_day, location, notes, caldav_href) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, title, start_norm, end_norm, int(all_day), location, notes, caldav_href),
        )
        conn.commit()
        return get_event(cur.lastrowid)  # type: ignore[return-value]
    finally:
        conn.close()


def get_event(event_id: int) -> dict | None:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _row_to_dict(r) if r else None
    finally:
        conn.close()


def list_events(start: str, end: str) -> list[dict]:
    """Eventi con inizio in [start, end)."""
    s = normalize_dt(start)
    e = normalize_dt(end)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE start_at >= ? AND start_at < ? ORDER BY start_at ASC",
            (s, e),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def upcoming(limit: int = 10, from_dt: str | None = None) -> list[dict]:
    frm = normalize_dt(from_dt) if from_dt else now_iso()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE start_at >= ? ORDER BY start_at ASC LIMIT ?",
            (frm, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_event(event_id: int, **fields) -> dict | None:
    allowed = {"title", "start_at", "end_at", "all_day", "location", "notes", "caldav_href"}
    sets, params = [], []
    all_day = bool(fields.get("all_day", False))
    for key, val in fields.items():
        if key not in allowed or val is None:
            continue
        if key in {"start_at", "end_at"}:
            val = normalize_dt(val, all_day)
        if key == "all_day":
            val = int(bool(val))
        sets.append(f"{key} = ?")
        params.append(val)
    if not sets:
        return get_event(event_id)
    params.append(event_id)
    conn = connect()
    try:
        conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()
    return get_event(event_id)


def delete_event(event_id: int) -> dict | None:
    """Elimina e restituisce l'evento cancellato (per la pulizia su CalDAV)."""
    ev = get_event(event_id)
    if not ev:
        return None
    conn = connect()
    try:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
    finally:
        conn.close()
    return ev


def upsert_by_uid(
    uid: str,
    title: str,
    start_at: str,
    end_at: str | None,
    all_day: bool,
    location: str,
    notes: str,
    caldav_href: str | None,
) -> str:
    """Inserisce o aggiorna un evento identificato dall'UID (usato dalla pull CalDAV).

    Ritorna 'insert' o 'update'.
    """
    start_norm = normalize_dt(start_at, all_day)
    end_norm = normalize_dt(end_at, all_day) if end_at else None
    conn = connect()
    try:
        existing = conn.execute("SELECT id FROM events WHERE uid = ?", (uid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE events SET title=?, start_at=?, end_at=?, all_day=?, location=?, notes=?, "
                "caldav_href=? WHERE uid=?",
                (title, start_norm, end_norm, int(all_day), location, notes, caldav_href, uid),
            )
            conn.commit()
            return "update"
        conn.execute(
            "INSERT INTO events (uid, title, start_at, end_at, all_day, location, notes, caldav_href) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, title, start_norm, end_norm, int(all_day), location, notes, caldav_href),
        )
        conn.commit()
        return "insert"
    finally:
        conn.close()


def format_event(ev: dict) -> str:
    """Riga leggibile per l'agente."""
    start = datetime.strptime(ev["start_at"], ISO)
    if ev["all_day"]:
        when = start.strftime("%a %d %b") + " (tutto il giorno)"
    else:
        when = start.strftime("%a %d %b %H:%M")
        if ev["end_at"]:
            end = datetime.strptime(ev["end_at"], ISO)
            when += "–" + end.strftime("%H:%M" if end.date() == start.date() else "%d %b %H:%M")
    line = f"#{ev['id']} {when} · {ev['title']}"
    if ev["location"]:
        line += f" @ {ev['location']}"
    return line


def day_bounds(day_iso: str) -> tuple[str, str]:
    """Da una data ('2026-08-29') ai limiti [inizio, inizio+1giorno)."""
    d = datetime.fromisoformat(day_iso).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.strftime(ISO), (d + timedelta(days=1)).strftime(ISO)
