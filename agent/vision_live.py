"""Vista live "vera": descrizione continua della scena in background.

Finché la camera è attiva, un thread chiede periodicamente al modello
multimodale (VLM) di descrivere il frame corrente — ogni LIVE_DESCRIBE_SECONDS,
o prima se l'insieme degli oggetti cambia. La descrizione finisce nello stato
e quindi nello "Stato attuale" del prompt: il modello sa cosa c'è davanti alla
camera anche senza chiamare strumenti.
"""

from __future__ import annotations

import threading
import time

from . import state
from .config import settings

_PROMPT = (
    "Sei gli occhi di un assistente personale. In 2-3 frasi, in italiano corretto, "
    "descrivi la scena inquadrata: ambiente, oggetti principali e dove si trovano, "
    "persone e cosa stanno facendo, eventuale testo leggibile. Solo ciò che è "
    "visibile, niente supposizioni."
)


class LiveDescriber:
    def __init__(self) -> None:
        self._started = False
        # session -> (timestamp ultimo tentativo, insieme etichette a quel momento)
        self._last: dict[str, tuple[float, frozenset]] = {}
        self._busy = threading.Lock()

    def enabled(self) -> bool:
        return settings.live_describe_enabled and settings.live_describe_seconds > 0

    def start(self) -> None:
        if self._started or not self.enabled():
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True, name="live-describer").start()

    def should_describe(self, session: str, now: float | None = None) -> bool:
        now = now or time.time()
        age = state.frame_age(session)
        if age is None or age > 10:
            return False
        labels = frozenset(state.get_objects(session))
        last = self._last.get(session)
        if last is None:
            return True
        ts, prev = last
        if now - ts >= settings.live_describe_seconds:
            return True
        return labels != prev and (now - ts) >= 5  # la scena è cambiata

    def describe_once(self, session: str) -> bool:
        from .llm import vision_describe

        frame = state.get_frame(session)
        if not frame:
            return False
        labels = frozenset(state.get_objects(session))
        self._last[session] = (time.time(), labels)
        try:
            text = vision_describe(frame, _PROMPT, max_tokens=220).strip()
        except Exception as exc:  # noqa: BLE001
            state.set_scene_error(session, str(exc)[:200])
            return False
        if text:
            state.set_scene(session, text)
        return bool(text)

    def _loop(self) -> None:
        while True:
            try:
                for s in state.active_sessions():
                    if self.should_describe(s) and self._busy.acquire(blocking=False):
                        try:
                            self.describe_once(s)
                        finally:
                            self._busy.release()
            except Exception:
                pass
            time.sleep(2)


live_describer = LiveDescriber()
