"""Scheduler proattivo: fa "scattare" i promemoria e manda la rassegna del mattino.

Gira in un thread in background (come il bridge Matrix). Scrive nella coda delle
notifiche, che la UI web mostra. Volutamente semplice: si sveglia a intervalli e
controlla cosa è dovuto.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import briefing, notifications
from .calendar_store import now_iso
from .config import settings
from .db import connect, init_db


class Scheduler:
    def __init__(self) -> None:
        self._started = False
        self._last_brief_date: str | None = None

    def start(self) -> None:
        if not settings.scheduler_enabled or self._started:
            return
        init_db()
        self._started = True
        threading.Thread(target=self._loop, daemon=True, name="scheduler").start()

    def _loop(self) -> None:
        while True:
            try:
                self._check_reminders()
                self._check_brief()
            except Exception:
                pass
            time.sleep(max(15, settings.scheduler_interval_seconds))

    def _check_reminders(self) -> None:
        now = now_iso()
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT id, text FROM reminders "
                "WHERE done = 0 AND notified = 0 AND due_at IS NOT NULL AND due_at <= ?",
                (now,),
            ).fetchall()
            for r in rows:
                notifications.push(f"⏰ Promemoria: {r['text']}", "reminder")
                conn.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (r["id"],))
            conn.commit()
        finally:
            conn.close()

    def _check_brief(self) -> None:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        if now.hour == settings.brief_hour and self._last_brief_date != today:
            self._last_brief_date = today
            notifications.push(briefing.compose_brief(), "brief")


scheduler = Scheduler()
