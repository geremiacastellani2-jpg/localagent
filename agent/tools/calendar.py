"""Strumenti calendario: creano/leggono eventi in locale e li rispecchiano su CalDAV.

Le date vanno passate in ISO 8601 (es. '2026-08-29T15:00'). Il modello deve prima
chiamare `get_current_time` per risolvere riferimenti relativi tipo "domani".
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import calendar_store as cal
from .. import caldav_sync
from .base import Tool, obj


def _try_push(event: dict) -> str:
    """Rispecchia su CalDAV se attivo; ritorna una nota da appendere al risultato."""
    if not caldav_sync.available():
        return ""
    try:
        href = caldav_sync.push_event(event)
        if href:
            cal.update_event(event["id"], caldav_href=href)
        return " (sincronizzato su CalDAV)"
    except Exception as exc:  # noqa: BLE001
        return f" (salvato in locale; sync CalDAV fallita: {exc})"


def _add_event(args: dict, _ctx: dict) -> str:
    try:
        event = cal.add_event(
            title=args.get("title", ""),
            start_at=args.get("start_at", ""),
            end_at=args.get("end_at"),
            all_day=bool(args.get("all_day", False)),
            location=args.get("location", "") or "",
            notes=args.get("notes", "") or "",
        )
    except ValueError as exc:
        return f"[errore] {exc}"
    note = _try_push(event)
    return "Evento creato: " + cal.format_event(event) + note


def _list_events(args: dict, _ctx: dict) -> str:
    date = (args.get("date") or "").strip()
    start = (args.get("start") or "").strip()
    end = (args.get("end") or "").strip()
    try:
        if start and end:
            events = cal.list_events(start, end)
            header = f"Eventi dal {start} al {end}:"
        else:
            day = date or datetime.now().strftime("%Y-%m-%d")
            s, e = cal.day_bounds(day)
            events = cal.list_events(s, e)
            header = f"Agenda del {day}:"
    except ValueError as exc:
        return f"[errore] data non valida: {exc}"
    if not events:
        return header + "\nNessun evento."
    return header + "\n" + "\n".join(cal.format_event(ev) for ev in events)


def _upcoming(args: dict, _ctx: dict) -> str:
    limit = int(args.get("limit") or 5)
    events = cal.upcoming(limit=limit)
    if not events:
        return "Nessun evento in programma."
    return "Prossimi eventi:\n" + "\n".join(cal.format_event(ev) for ev in events)


def _move_event(args: dict, _ctx: dict) -> str:
    eid = args.get("id")
    if eid is None or not args.get("start_at"):
        return "[errore] servono 'id' e nuovo 'start_at'"
    ev = cal.get_event(int(eid))
    if not ev:
        return f"Nessun evento #{eid}."
    try:
        updated = cal.update_event(
            int(eid),
            start_at=args.get("start_at"),
            end_at=args.get("end_at"),
            all_day=ev["all_day"],
        )
    except ValueError as exc:
        return f"[errore] {exc}"
    note = _try_push(updated) if updated else ""
    return "Evento spostato: " + cal.format_event(updated) + note  # type: ignore[arg-type]


def _delete_event(args: dict, _ctx: dict) -> str:
    eid = args.get("id")
    if eid is None:
        return "[errore] id mancante"
    ev = cal.delete_event(int(eid))
    if not ev:
        return f"Nessun evento #{eid}."
    if caldav_sync.available():
        caldav_sync.delete_remote(ev.get("caldav_href"))
    return f"Eliminato evento #{eid}: {ev['title']}"


def _sync(args: dict, _ctx: dict) -> str:
    if not caldav_sync.available():
        return caldav_sync.status()
    back = int(args.get("days_back") or 7)
    fwd = int(args.get("days_forward") or 30)
    now = datetime.now()
    start = (now - timedelta(days=back)).strftime(cal.ISO)
    end = (now + timedelta(days=fwd)).strftime(cal.ISO)
    try:
        remote = caldav_sync.pull(start, end)
    except Exception as exc:  # noqa: BLE001
        return f"[errore] pull CalDAV fallita: {exc}"
    ins = upd = 0
    for r in remote:
        action = cal.upsert_by_uid(
            uid=r["uid"], title=r["title"], start_at=r["start_at"], end_at=r["end_at"],
            all_day=r["all_day"], location=r["location"], notes=r["notes"], caldav_href=r["caldav_href"],
        )
        ins += action == "insert"
        upd += action == "update"
    return f"Sincronizzati {len(remote)} eventi da CalDAV ({ins} nuovi, {upd} aggiornati)."


TOOLS = [
    Tool(
        name="add_event",
        description="Crea un evento in calendario. Date in ISO 8601 (es. 2026-08-29T15:00).",
        parameters=obj(
            {
                "title": {"type": "string"},
                "start_at": {"type": "string", "description": "Inizio in ISO 8601."},
                "end_at": {"type": "string", "description": "Fine in ISO 8601 (facoltativo)."},
                "all_day": {"type": "boolean", "description": "Evento di tutto il giorno."},
                "location": {"type": "string"},
                "notes": {"type": "string"},
            },
            required=["title", "start_at"],
        ),
        run=_add_event,
    ),
    Tool(
        name="list_events",
        description="Mostra gli eventi di un giorno (default: oggi) o di un intervallo start/end.",
        parameters=obj(
            {
                "date": {"type": "string", "description": "Giorno singolo, ISO 'YYYY-MM-DD'."},
                "start": {"type": "string", "description": "Inizio intervallo ISO."},
                "end": {"type": "string", "description": "Fine intervallo ISO."},
            }
        ),
        run=_list_events,
    ),
    Tool(
        name="upcoming_events",
        description="Elenca i prossimi eventi a partire da adesso.",
        parameters=obj({"limit": {"type": "integer"}}),
        run=_upcoming,
    ),
    Tool(
        name="move_event",
        description="Sposta un evento a un nuovo orario di inizio (e fine, facoltativa).",
        parameters=obj(
            {
                "id": {"type": "integer"},
                "start_at": {"type": "string", "description": "Nuovo inizio ISO 8601."},
                "end_at": {"type": "string", "description": "Nuova fine ISO 8601 (facoltativa)."},
            },
            required=["id", "start_at"],
        ),
        run=_move_event,
    ),
    Tool(
        name="delete_event",
        description="Elimina un evento dato il suo id.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_delete_event,
    ),
    Tool(
        name="sync_calendar",
        description="Sincronizza gli eventi dal server CalDAV nell'archivio locale.",
        parameters=obj(
            {
                "days_back": {"type": "integer", "description": "Giorni passati da leggere (default 7)."},
                "days_forward": {"type": "integer", "description": "Giorni futuri da leggere (default 30)."},
            }
        ),
        run=_sync,
    ),
]
