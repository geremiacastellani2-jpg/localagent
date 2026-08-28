"""Smoke test delle parti non-LLM: DB, strumenti, registro, import del server.

Non chiama modelli (non serve chiave/Ollama). Verifica che il codice regga.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# usa un DB temporaneo isolato
tmp = Path(tempfile.mkdtemp()) / "smoke.db"
import os

os.environ["DB_PATH"] = str(tmp)

from agent.db import init_db  # noqa: E402
from agent.tools import build_registry  # noqa: E402
from agent.tools.notes import _add_note, _list_notes  # noqa: E402
from agent.tools.memory import _remember, _recall  # noqa: E402
from agent.state import set_frame, get_frame  # noqa: E402

ok = True


def check(name: str, cond: bool) -> None:
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


init_db()

# note
print(_add_note({"text": "comprare il latte", "tags": "casa"}, {}))
listing = _list_notes({}, {})
check("nota presente nell'elenco", "comprare il latte" in listing)

# memoria
print(_remember({"subject": "utente", "fact": "beve caffè amaro"}, {}))
recall = _recall({"query": "caffè"}, {})
check("fatto richiamato", "caffè" in recall)
# idempotenza
again = _remember({"subject": "utente", "fact": "beve caffè amaro"}, {})
check("remember idempotente", "Già in memoria" in again)

# calendario
from agent.tools.calendar import _add_event, _list_events, _upcoming, _move_event, _delete_event  # noqa: E402
from agent import caldav_sync  # noqa: E402

res = _add_event(
    {"title": "Dentista", "start_at": "2026-08-29T15:00", "end_at": "2026-08-29T15:30", "location": "Centro"},
    {},
)
check("evento creato", "Dentista" in res)
day = _list_events({"date": "2026-08-29"}, {})
check("evento nell'agenda del giorno", "Dentista" in day)
empty = _list_events({"date": "2030-01-01"}, {})
check("giorno vuoto gestito", "Nessun evento" in empty)
up = _upcoming({"limit": 5}, {})
check("prossimi eventi elencati", "Dentista" in up)
moved = _move_event({"id": 1, "start_at": "2026-08-29T16:00"}, {})
check("evento spostato", "16:00" in moved)
deleted = _delete_event({"id": 1}, {})
check("evento eliminato", "Eliminato" in deleted)
check("CalDAV non configurato in test", not caldav_sync.available())

# registro
reg = build_registry()
names = {t["function"]["name"] for t in reg.schemas()}
expected = {"add_note", "list_notes", "delete_note", "add_reminder", "list_reminders",
            "complete_reminder", "remember_fact", "recall", "forget_fact", "look", "get_current_time",
            "add_event", "list_events", "upcoming_events", "move_event", "delete_event", "sync_calendar"}
check("tutti gli strumenti registrati", expected <= names)

# registro: strumento sconosciuto non esplode
check("strumento sconosciuto gestito", reg.run("nope", "{}", {}).startswith("[errore]"))

# stato frame
set_frame("s1", "data:image/jpeg;base64,AAAA")
check("frame memorizzato", get_frame("s1") == "data:image/jpeg;base64,AAAA")
set_frame("s1", None)
check("frame ripulito", get_frame("s1") is None)

# import del server (costruisce l'app FastAPI + Agent)
import agent.server as srv  # noqa: E402
check("server importato", srv.app is not None and srv.agent is not None)

print("\nStrumenti:", ", ".join(sorted(names)))
sys.exit(0 if ok else 1)
