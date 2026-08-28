"""Coda di approvazioni per le azioni in uscita (email, messaggi…).

Ogni azione che esce dal Mac — inviare un'email, un messaggio WhatsApp — non parte
subito: viene messa in coda con un riepilogo. L'utente approva o rifiuta. È la
"conferma umana su ogni invio" del blueprint, condivisa da tutte le capacità.

I moduli che sanno eseguire un tipo di azione registrano un dispatcher:
    outbox.register("email.send", funzione_che_invia)
"""

from __future__ import annotations

import json
from typing import Callable

from .db import connect

Dispatcher = Callable[[dict], str]
_DISPATCHERS: dict[str, Dispatcher] = {}


def register(kind: str, fn: Dispatcher) -> None:
    _DISPATCHERS[kind] = fn


def enqueue(kind: str, summary: str, payload: dict) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO pending_actions (kind, summary, payload) VALUES (?, ?, ?)",
            (kind, summary, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return int(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        conn.close()


def list_pending() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, summary, created_at FROM pending_actions "
            "WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get(action_id: int) -> dict | None:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _set_status(action_id: int, status: str, result: str = "") -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE pending_actions SET status = ?, result = ? WHERE id = ?",
            (status, result, action_id),
        )
        conn.commit()
    finally:
        conn.close()


def approve(action_id: int) -> str:
    action = get(action_id)
    if not action:
        return f"Nessuna azione #{action_id}."
    if action["status"] != "pending":
        return f"L'azione #{action_id} è già '{action['status']}'."
    fn = _DISPATCHERS.get(action["kind"])
    if fn is None:
        _set_status(action_id, "failed", "nessun dispatcher")
        return f"[errore] tipo di azione non gestito: {action['kind']}"
    try:
        payload = json.loads(action["payload"])
        result = fn(payload)
        _set_status(action_id, "done", result)
        return f"✓ Azione #{action_id} eseguita: {result}"
    except Exception as exc:  # noqa: BLE001
        _set_status(action_id, "failed", str(exc))
        return f"[errore] esecuzione azione #{action_id} fallita: {exc}"


def reject(action_id: int) -> str:
    action = get(action_id)
    if not action:
        return f"Nessuna azione #{action_id}."
    if action["status"] != "pending":
        return f"L'azione #{action_id} è già '{action['status']}'."
    _set_status(action_id, "rejected")
    return f"Azione #{action_id} annullata."
