"""Il cervello: un loop di chat con tool-calling OpenAI-compatibile.

Funziona identico contro Ollama (locale) e OpenRouter (cloud) perché entrambi
espongono la stessa API. La cronologia è per-sessione, in memoria (utente singolo).
"""

from __future__ import annotations

from .db import init_db
from .llm import router
from .tools import build_registry

SYSTEM_PROMPT = """\
Sei "Maggiordomo", un assistente personale che gira in locale sul Mac dell'utente.
Rispondi sempre in italiano, in modo diretto e conciso.

Hai a disposizione degli strumenti. Regole d'uso:
- Per note, promemoria, calendario e memoria dei fatti, USA gli strumenti: non
  fingere di aver salvato qualcosa senza chiamarli.
- Per il calendario le date vanno in ISO 8601. Se l'utente usa riferimenti
  relativi ("domani", "venerdì alle 15", "tra un'ora"), chiama prima
  `get_current_time` per sapere la data di oggi e poi calcola l'ISO corretto.
- Quando l'utente chiede cosa vedi, di descrivere l'ambiente, di identificare o
  leggere qualcosa inquadrato dalla camera, USA lo strumento `look`.
- Quando l'utente rivela qualcosa di durevole su di sé (preferenze, persone,
  progetti), salvalo con `remember_fact`. Prima di rispondere a domande sul suo
  conto, considera `recall`.
- Non inventare informazioni. Se uno strumento restituisce un errore, spiegalo
  con parole semplici.
"""

MAX_STEPS = 6
MAX_HISTORY = 40  # messaggi conservati per sessione (oltre al system prompt)


class Agent:
    def __init__(self) -> None:
        init_db()
        self.registry = build_registry()
        self._histories: dict[str, list[dict]] = {}

    def _history(self, session: str) -> list[dict]:
        if session not in self._histories:
            self._histories[session] = [{"role": "system", "content": SYSTEM_PROMPT}]
        return self._histories[session]

    def reset(self, session: str) -> None:
        self._histories.pop(session, None)

    def chat(self, session: str, user_message: str) -> str:
        history = self._history(session)
        history.append({"role": "user", "content": user_message})

        client, model = router.resolve("chat")
        tools = self.registry.schemas()
        context = {"session": session}

        final_text = ""
        for _ in range(MAX_STEPS):
            resp = client.chat.completions.create(
                model=model,
                messages=history,
                tools=tools,
                tool_choice="auto",
            )
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
