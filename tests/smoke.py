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

# memoria semantica: inietta un embedder finto e deterministico (niente Ollama)
from agent import semantic_memory as sem  # noqa: E402


def _fake_embed(text: str):
    # vettore bag-of-words su un piccolo vocabolario: sufficiente per testare
    # indicizzazione, coseno e ordinamento.
    vocab = ["caffè", "amaro", "latte", "gatto", "milano", "utente", "beve", "vive"]
    t = text.lower()
    return [float(t.count(w)) + 0.01 for w in vocab]


sem._backend = _fake_embed  # type: ignore[attr-defined]
check("embedder finto disponibile", sem.available())

# memoria
print(_remember({"subject": "utente", "fact": "beve caffè amaro"}, {}))
_remember({"subject": "utente", "fact": "vive a Milano"}, {})
recall = _recall({"query": "caffè"}, {})
check("richiamo semantico trova il caffè", "caffè" in recall and "Milano" not in recall.split("\n")[1])
recall2 = _recall({"query": "dove abita"}, {})
check("richiamo semantico attivo (sim)", "sim" in recall)
# idempotenza
again = _remember({"subject": "utente", "fact": "beve caffè amaro"}, {})
check("remember idempotente", "Già in memoria" in again)
# indice vettoriale popolato
res = sem.search("caffè", k=2)
check("ricerca vettoriale ordinata", res and res[0]["score"] >= res[-1]["score"])

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

# coda di approvazioni (outbox) con un dispatcher finto
from agent import outbox  # noqa: E402

_sent = {}
outbox.register("test.send", lambda p: (_sent.update(p) or "inviato"))
aid = outbox.enqueue("test.send", "prova", {"x": 1})
check("azione in coda", any(a["id"] == aid for a in outbox.list_pending()))
check("azione approvata ed eseguita", "eseguita" in outbox.approve(aid) and _sent.get("x") == 1)
check("azione non più pendente", not any(a["id"] == aid for a in outbox.list_pending()))
aid2 = outbox.enqueue("test.send", "prova2", {"y": 2})
check("reject annulla", "annullata" in outbox.reject(aid2))

# email/messaggi non configurati: le guardie rispondono senza crashare
from agent.tools.email import _send_email  # noqa: E402
from agent.tools.messages import _list_chats  # noqa: E402

check("send_email guardato senza config", "non configurata" in _send_email({"to": "a@b.it", "body": "ciao"}, {}).lower())
_chats = _list_chats({}, {}).lower()
check("messaggi guardati senza config", any(s in _chats for s in ("non installato", "non configurato", "non attivi")))

# Fase 6 — notifiche, presenza, scheduler, rassegna
from agent import notifications, presence  # noqa: E402
from agent import scheduler as sched  # noqa: E402
from agent.tools.reminders import _add_reminder  # noqa: E402
from agent.tools.briefing import _daily_brief  # noqa: E402
from agent.tools.vision import _who_is_here  # noqa: E402

nid = notifications.push("prova", "info")
check("notifica in coda", any(i["id"] == nid for i in notifications.since(nid - 1)))

arrivals = presence.update(["Mario"])
check("primo avvistamento = arrivo", "Mario" in arrivals)
check("secondo avvistamento non è arrivo", "Mario" not in presence.update(["Mario"]))
check("presenza corrente", "Mario" in presence.present(within=15))
check("who_is_here riconosce", "Mario" in _who_is_here({}, {}))

_add_reminder({"text": "chiama il dentista", "due_at": "2020-01-01T09:00"}, {})
_before = notifications.latest_id()
sched.scheduler._check_reminders()
check("promemoria scaduto notificato",
      any("dentista" in i["text"] for i in notifications.since(_before)))
_before2 = notifications.latest_id()
sched.scheduler._check_reminders()  # non deve rinotificare
check("promemoria non rinotificato", not notifications.since(_before2))

check("rassegna composta", "Rassegna" in _daily_brief({}, {}))

# registro
reg = build_registry()
names = {t["function"]["name"] for t in reg.schemas()}
expected = {"add_note", "list_notes", "delete_note", "add_reminder", "list_reminders",
            "complete_reminder", "remember_fact", "recall", "forget_fact", "reindex_memory",
            "look", "current_view", "get_current_time",
            "add_event", "list_events", "upcoming_events", "move_event", "delete_event", "sync_calendar",
            "list_emails", "read_email", "send_email",
            "list_chats", "read_chat", "send_message",
            "list_pending_actions", "approve_action", "reject_action",
            "who_is_here", "daily_brief"}
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
