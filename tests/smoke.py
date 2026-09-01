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

from datetime import datetime as _dt, timedelta as _td  # noqa: E402
_tomorrow = (_dt.now() + _td(days=1)).strftime("%Y-%m-%d")
res = _add_event(
    {"title": "Dentista", "start_at": f"{_tomorrow}T15:00", "end_at": f"{_tomorrow}T15:30", "location": "Centro"},
    {},
)
check("evento creato", "Dentista" in res)
day = _list_events({"date": _tomorrow}, {})
check("evento nell'agenda del giorno", "Dentista" in day)
empty = _list_events({"date": "2030-01-01"}, {})
check("giorno vuoto gestito", "Nessun evento" in empty)
up = _upcoming({"limit": 5}, {})
check("prossimi eventi elencati", "Dentista" in up)
moved = _move_event({"id": 1, "start_at": f"{_tomorrow}T16:00"}, {})
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

# router ibrido — semantica di "auto"
import time as _t  # noqa: E402
from agent import llm as llmmod  # noqa: E402
from agent.config import settings as _cfg  # noqa: E402

_oldkey = _cfg.openrouter_api_key
llmmod._OLLAMA_OK = (_t.time(), False)  # simula: Ollama giù
_cfg.openrouter_api_key = ""
check("auto senza nulla → local", llmmod.resolve_chat_tier() == "local")
check("vision senza chiave → local", llmmod.resolve_vision_tier() == "local")
_cfg.openrouter_api_key = "sk-test"
check("auto con chiave e Ollama giù → cloud", llmmod.resolve_chat_tier() == "cloud")
check("vision con chiave → cloud", llmmod.resolve_vision_tier() == "cloud")
llmmod._OLLAMA_OK = (_t.time(), True)  # simula: Ollama su
check("ibrido: chat resta locale con Ollama su", llmmod.resolve_chat_tier() == "local")
check("override cloud rispettato", llmmod.resolve_chat_tier("cloud") == "cloud")
_cfg.openrouter_api_key = _oldkey
llmmod._OLLAMA_OK = None

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

# contesto "Stato attuale" iniettato nel system prompt a ogni turno
set_frame("ctx", "data:image/jpeg;base64,AAAA", ["person", "person", "cup"])
from agent.state import set_faces  # noqa: E402
set_faces("ctx", ["Anna"])
ctx = srv.build_context("ctx")
check("contesto: data e ora presenti", "Data e ora correnti" in ctx)
check("contesto: oggetti contati (in italiano)", "persona×2" in ctx and "tazza" in ctx)
check("contesto: volti riconosciuti", "Anna" in ctx)
check("contesto: agenda inclusa", "Agenda di oggi" in ctx)
set_frame("ctx", None)
check("contesto: camera spenta segnalata", "Camera: spenta" in srv.build_context("ctx"))

# il context_block finisce nel system prompt del turno
from agent.core import Agent as _Agent  # noqa: E402
_a = _Agent()
hist = _a._history("t1")
_sys = "Stato attuale"
try:
    _a.chat("t1", "ciao", context_block="- Data e ora correnti: test")
except Exception:
    pass  # nessun modello in CI: l'importante è lo stato della history
check("system prompt aggiornato col contesto", "Data e ora correnti: test" in _a._history("t1")[0]["content"])

# foto allegata al messaggio: diventa la vista corrente della sessione
import os as _os
_os.environ["SCHEDULER_ENABLED"] = "false"
from fastapi.testclient import TestClient  # noqa: E402
from agent.state import get_frame as _gf  # noqa: E402

with TestClient(srv.app) as _c:
    _c.post("/chat", json={"session": "img", "message": "guarda questa foto",
                           "image": "data:image/jpeg;base64,AAAA"})
check("foto allegata diventa la vista", _gf("img") == "data:image/jpeg;base64,AAAA")

# fallback automatico su 429: il cloud è rate-limited, si passa al locale
from agent import core as _core  # noqa: E402


class _Msg:
    content = "ok dal locale"
    tool_calls = None


class _Resp:
    class _Choice:
        message = _Msg()

    choices = [_Choice()]


class _Completions:
    def __init__(self, fail):
        self.fail = fail

    def create(self, **_kw):
        if self.fail:
            raise RuntimeError("Error code: 429 - rate-limited upstream")
        return _Resp()


class _Client:
    def __init__(self, fail):
        self.chat = type("C", (), {"completions": _Completions(fail)})()


def _fake_resolve(task="chat", vision=False, override=None):
    if override == "local":
        return _Client(False), "fake-local", "local"
    return _Client(True), "fake-cloud", "cloud"


_old_resolve = _core.router.resolve
_core.router.resolve = _fake_resolve
try:
    _ag = _core.Agent()
    out = _ag.chat("rl", "ciao")
    check("fallback 429 cloud→locale", out == "ok dal locale" and _ag.last_tier == "local")
finally:
    _core.router.resolve = _old_resolve


# vista live: rilevazioni con posizione, eventi, scena, report, descrittore
from agent import state as _st, vision_info as _vi  # noqa: E402
from agent.vision_live import live_describer as _ld  # noqa: E402

_dets = [{"label": "person", "score": 0.9, "box": [0.3, 0.1, 0.4, 0.8]},
         {"label": "cup", "score": 0.7, "box": [0.05, 0.75, 0.1, 0.15]}]
_st.set_frame("lv", "data:image/jpeg;base64,AAAA", detections=_dets)
_st.set_frame("lv", "data:image/jpeg;base64,AAAA", detections=_dets)  # stabile → evento
_desc = _vi.describe_detections(_st.get_detections("lv"))
check("posizioni in italiano", "persona" in _desc and "tazza" in _desc and "al centro" in _desc)
check("specchio: la tazza (x piccolo nel frame) è a destra per l'utente", "a destra" in _desc)
check("evento 'in vista' registrato", any("in vista: persona, tazza" in t for _, t in _st.get_events("lv")))
_st.set_scene("lv", "Una persona seduta alla scrivania con una tazza.")
_lines = "\n".join(_vi.report_lines("lv"))
check("report: camera attiva con posizioni", "Camera: ATTIVA" in _lines and "persona (" in _lines)
check("report: scena inclusa", "Scena (descritta" in _lines)
_rt = _vi.report_text("lv")
check("current_view completo", "Eventi recenti" in _rt and "Scena" in _rt)
_j = _vi.json_report("lv")
check("json /vision", _j["active"] and _j["detections"][0]["label_it"] == "persona"
      and _j["scene"]["text"].startswith("Una persona"))
import agent.llm as _llm  # noqa: E402
_orig_vd = _llm.vision_describe
_llm.vision_describe = lambda frame, prompt, max_tokens=500: "Scena finta: scrivania e tazza."
try:
    check("descrittore: prima volta → descrive", _ld.should_describe("lv"))
    check("descrittore: describe_once scrive la scena",
          _ld.describe_once("lv") and _st.get_scene("lv")[0].startswith("Scena finta"))
    check("descrittore: subito dopo non ridescrive", not _ld.should_describe("lv"))
finally:
    _llm.vision_describe = _orig_vd
with TestClient(srv.app) as _c:
    _r = _c.get("/vision?session=lv").json()
    check("/vision endpoint", _r["objects"].get("persona") == 1 and _r["objects"].get("tazza") == 1)
    _fr = _c.post("/frame", json={"session": "lv2", "frame": "data:image/jpeg;base64,AAAA",
                                  "detections": [{"label": "laptop", "score": 0.8, "box": [0.4, 0.4, 0.2, 0.2]}],
                                  "faces": ["Marco"]}).json()
    check("/frame accetta rilevazioni e volti", _fr["ok"] and _st.get_faces("lv2") == ["Marco"]
          and _st.get_detections("lv2")[0]["label"] == "laptop")
    check("contesto turno include posizioni e persone",
          "portatile (" in srv.build_context("lv2") and "Marco" in srv.build_context("lv2"))

print("\nStrumenti:", ", ".join(sorted(names)))
sys.exit(0 if ok else 1)
