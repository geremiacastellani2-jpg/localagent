"""Sincronizzazione CalDAV: rispecchia il calendario locale su un server remoto.

Interoperabile con iCloud, Google, Fastmail, Radicale… Se le librerie `caldav`
e `icalendar` non sono installate, o se il CalDAV non è configurato, tutte le
funzioni degradano con grazia: il calendario continua a funzionare in locale.

Modello di sync (semplice, adatto a utente singolo):
  - push_event / delete_remote  → scrivono la modifica locale sul server
  - pull(start, end)            → legge gli eventi remoti in una finestra
Un merge bidirezionale con risoluzione dei conflitti è materiale per una fase
successiva; qui il locale è la fonte di verità per ciò che crei tu.
"""

from __future__ import annotations

from datetime import datetime

from .calendar_store import ISO
from .config import settings

try:  # dipendenze opzionali
    import caldav  # type: ignore
    from icalendar import Calendar, Event  # type: ignore

    _AVAILABLE = True
except Exception:  # pragma: no cover - dipende dall'ambiente
    _AVAILABLE = False


class CalDavUnavailable(RuntimeError):
    pass


def available() -> bool:
    return _AVAILABLE and settings.caldav_configured()


def status() -> str:
    if not _AVAILABLE:
        return "CalDAV non installato (pip install caldav icalendar) — calendario solo locale."
    if not settings.caldav_configured():
        return "CalDAV non configurato (CALDAV_URL/USERNAME/PASSWORD) — calendario solo locale."
    return "CalDAV configurato."


def _principal_calendar():
    client = caldav.DAVClient(
        url=settings.caldav_url,
        username=settings.caldav_username,
        password=settings.caldav_password,
    )
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise CalDavUnavailable("Nessun calendario trovato sul server CalDAV.")
    if settings.caldav_calendar:
        for cal in calendars:
            name = str(getattr(cal, "name", "") or "")
            if name == settings.caldav_calendar:
                return cal
    return calendars[0]


def _to_dt(value: str) -> datetime:
    return datetime.strptime(value, ISO)


def push_event(ev: dict) -> str | None:
    """Crea/aggiorna l'evento sul server. Ritorna l'href remoto, o None se non attivo."""
    if not available():
        return None
    cal = _principal_calendar()
    vcal = Calendar()
    vcal.add("prodid", "-//Maggiordomo Locale//IT")
    vcal.add("version", "2.0")
    vevent = Event()
    vevent.add("uid", ev["uid"])
    vevent.add("summary", ev["title"])
    if ev["all_day"]:
        vevent.add("dtstart", _to_dt(ev["start_at"]).date())
    else:
        vevent.add("dtstart", _to_dt(ev["start_at"]))
        if ev.get("end_at"):
            vevent.add("dtend", _to_dt(ev["end_at"]))
    if ev.get("location"):
        vevent.add("location", ev["location"])
    if ev.get("notes"):
        vevent.add("description", ev["notes"])
    vcal.add_component(vevent)

    obj = cal.save_event(vcal.to_ical().decode("utf-8"))
    return str(getattr(obj, "url", "") or "") or None


def delete_remote(href: str | None) -> None:
    if not available() or not href:
        return
    client = caldav.DAVClient(
        url=settings.caldav_url,
        username=settings.caldav_username,
        password=settings.caldav_password,
    )
    try:
        client.object_by_url(href).delete()
    except Exception:
        pass  # se non c'è più, va bene lo stesso


def pull(start: str, end: str) -> list[dict]:
    """Legge gli eventi remoti nella finestra [start, end) come dict normalizzabili."""
    if not available():
        raise CalDavUnavailable(status())
    cal = _principal_calendar()
    results = cal.date_search(start=_to_dt(start), end=_to_dt(end))

    events: list[dict] = []
    for obj in results:
        try:
            comp = Calendar.from_ical(obj.data)
        except Exception:
            continue
        for sub in comp.walk("VEVENT"):
            dtstart = sub.get("dtstart")
            if dtstart is None:
                continue
            start_val = dtstart.dt
            all_day = not isinstance(start_val, datetime)
            dtend = sub.get("dtend")
            end_val = dtend.dt if dtend is not None else None
            events.append(
                {
                    "uid": str(sub.get("uid")),
                    "title": str(sub.get("summary") or "(senza titolo)"),
                    "start_at": _fmt(start_val),
                    "end_at": _fmt(end_val) if end_val is not None else None,
                    "all_day": all_day,
                    "location": str(sub.get("location") or ""),
                    "notes": str(sub.get("description") or ""),
                    "caldav_href": str(getattr(obj, "url", "") or "") or None,
                }
            )
    return events


def _fmt(value) -> str:
    if isinstance(value, datetime):
        return value.strftime(ISO)
    # date pura (all-day)
    return datetime(value.year, value.month, value.day).strftime(ISO)
