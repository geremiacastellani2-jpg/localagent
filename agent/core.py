"""Il cervello: un loop di chat con tool-calling OpenAI-compatibile.

Funziona identico contro Ollama (locale) e OpenRouter (cloud) perché entrambi
espongono la stessa API. La cronologia è per-sessione, in memoria (utente singolo).
"""

from __future__ import annotations

from . import llm
from .db import init_db
from .llm import router
from .tools import build_registry

SYSTEM_PROMPT = """\
Sei "Maggiordomo", un assistente personale che gira in locale sul Mac dell'utente.
Scrivi sempre in ITALIANO corretto e naturale: frasi ben costruite, grammatica
curata, niente calchi dall'inglese né parole inventate. Tono diretto e conciso,
come un maggiordomo competente. Se non sei sicuro di una parola, usa una
formulazione semplice.

Hai a disposizione degli strumenti. Regole d'uso:
- Per note, promemoria, calendario e memoria dei fatti, USA gli strumenti: non
  fingere di aver salvato qualcosa senza chiamarli.
- Per il calendario le date vanno in ISO 8601. Se l'utente usa riferimenti
  relativi ("domani", "venerdì alle 15", "tra un'ora"), chiama prima
  `get_current_time` per sapere la data di oggi e poi calcola l'ISO corretto.
- In fondo a queste istruzioni trovi la sezione "Stato attuale", rigenerata a ogni
  turno: data e ora CORRENTI, stato della camera (oggetti in vista con la loro
  posizione, persone riconosciute), la "Scena" descritta poco fa dalla vista, gli
  eventi recenti della camera, l'agenda di oggi e i contatori. È informazione
  REALE e aggiornata: usala con naturalezza, come se stessi guardando tu. Non
  dire mai che non conosci l'ora o che non puoi vedere quando lo Stato attuale
  dice il contrario.
- Per una descrizione dettagliata della scena, identificare un oggetto o leggere
  testo inquadrato usa `look`; per l'elenco rapido `current_view`; per sapere chi
  è riconosciuto `who_is_here`.
- Se l'utente chiede un riepilogo della giornata / "come sono messo", usa
  `daily_brief`.
- Quando l'utente rivela qualcosa di durevole su di sé (preferenze, persone,
  progetti), salvalo con `remember_fact`. Prima di rispondere a domande sul suo
  conto, considera `recall`.
- Email e messaggi (WhatsApp/SMS via Matrix): puoi leggerli liberamente. Per gli
  INVII non inviare mai direttamente: `send_email` e `send_message` mettono l'invio
  in coda di approvazione e tornano un id. Mostra all'utente l'anteprima e chiedi
  conferma; invia solo quando lui approva, chiamando `approve_action` con quell'id.
  Usa `list_pending_actions` per vedere cosa è in attesa e `reject_action` per
  annullare.
- Non inventare informazioni. Se uno strumento restituisce un errore, spiegalo
  con parole semplici.
"""

MAX_STEPS = 6
MAX_ROTATIONS = 3  # candidati cloud gratuiti da provare per turno prima di cambiare tier
MAX_HISTORY = 40  # messaggi conservati per sessione (oltre al system prompt)


class Agent:
    def __init__(self) -> None:
        init_db()
        self.registry = build_registry()
        self._histories: dict[str, list[dict]] = {}
        self.last_tier: str = ""
        self.last_model: str = ""

    def _history(self, session: str) -> list[dict]:
        if session not in self._histories:
            self._histories[session] = [{"role": "system", "content": SYSTEM_PROMPT}]
        return self._histories[session]

    def reset(self, session: str) -> None:
        self._histories.pop(session, None)

    def chat(
        self,
        session: str,
        user_message: str,
        tier: str | None = None,
        context_block: str | None = None,
    ) -> str:
        history = self._history(session)
        # rigenera il system prompt con lo stato corrente: così anche i modelli
        # deboli nel tool-calling hanno sempre data/ora, vista e agenda
        system = SYSTEM_PROMPT
        if context_block:
            system += "\n## Stato attuale (aggiornato automaticamente)\n" + context_block
        history[0] = {"role": "system", "content": system}
        history.append({"role": "user", "content": user_message})

        client, model, used_tier = router.resolve("chat", override=tier)
        self.last_tier, self.last_model = used_tier, model
        tools = self.registry.schemas()
        context = {"session": session}

        final_text = ""
        st = {"client": client, "model": model, "tier": used_tier, "use_tools": True,
              "tried": {model}, "switched": False}
        for _ in range(MAX_STEPS):
            resp = self._complete(history, tools, st)
            client, model = st["client"], st["model"]
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            # registra il turno dell'assistente (con eventuali tool_calls)
            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
            history.append(assistant_entry)

            if not tool_calls:
                final_text = msg.content or ""
                break

            # esegue gli strumenti e accoda i risultati
            for tc in tool_calls:
                result = self.registry.run(tc.function.name, tc.function.arguments, context)
                history.append(
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": result}
                )
        else:
            final_text = "Ho raggiunto il numero massimo di passi senza concludere. Riprova a riformulare."

        self._trim(session)
        return final_text or "(nessuna risposta)"

    def _complete(self, history: list[dict], tools: list[dict], st: dict):
        """Una chiamata al modello, con i ripieghi che NON contano come passi:
        - modello senza tool-calling → riprova senza strumenti;
        - 429 su un gratuito del cloud → prossimo della rosa (max MAX_ROTATIONS);
        - rosa esaurita (o locale saturo) → cambia tier una volta.
        """
        for _attempt in range(MAX_ROTATIONS + 4):
            try:
                if st["use_tools"]:
                    return st["client"].chat.completions.create(
                        model=st["model"], messages=history, tools=tools, tool_choice="auto"
                    )
                return st["client"].chat.completions.create(model=st["model"], messages=history)
            except Exception as exc:
                low = str(exc).lower()
                if st["use_tools"] and ("tool" in low or "function" in low):
                    st["use_tools"] = False  # lo "Stato attuale" nel prompt compensa
                    continue
                if not llm.is_rate_limit_error(exc):
                    raise
                if st["tier"] == "cloud":
                    llm.mark_rate_limited(st["model"])
                    nxt = [c for c in llm.available_candidates(False) if c not in st["tried"]]
                    if nxt and len(st["tried"]) < MAX_ROTATIONS:
                        st["model"] = nxt[0]
                        st["tried"].add(nxt[0])
                        self.last_model = nxt[0]
                        continue
                if not st["switched"]:
                    other = "local" if st["tier"] == "cloud" else "cloud"
                    try:
                        c, m, t = router.resolve("chat", override=other)
                    except Exception:
                        raise exc
                    st.update(client=c, model=m, tier=t, switched=True)
                    st["tried"].add(m)
                    self.last_tier, self.last_model = t, m
                    continue
                raise
        raise RuntimeError("troppi tentativi con i modelli disponibili")

    def _trim(self, session: str) -> None:
        history = self._histories.get(session)
        if not history:
            return
        system, rest = history[0], history[1:]
        if len(rest) > MAX_HISTORY:
            # non tagliare in mezzo a una coppia tool_call/tool: risincronizza dal
            # primo messaggio 'user' rimasto
            rest = rest[-MAX_HISTORY:]
            while rest and rest[0]["role"] in {"tool", "assistant"}:
                rest.pop(0)
        self._histories[session] = [system, *rest]
