"""Bridge Matrix: casella unica per WhatsApp, SMS, iMessage, Telegram…

L'agente si collega a un homeserver Matrix (Synapse) su cui girano i bridge
mautrix. Ogni chat di ogni rete diventa una stanza Matrix; qui la leggiamo e ci
scriviamo. Vedi `deploy/matrix/` per far partire homeserver + bridge WhatsApp e
`docs/whatsapp.md` per collegare il tuo numero.

matrix-nio è async: gira in un thread con il suo event loop. I tool (sincroni)
leggono da un buffer in memoria e inviano in modo thread-safe. Se matrix-nio non
è installato o Matrix non è configurato, tutto degrada con grazia.

Nota e2ee: se le stanze del bridge sono cifrate serve `matrix-nio[e2e]` (libolm);
in alternativa disattiva la cifratura lato bridge. Vedi la doc.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque

from .config import settings

try:
    from nio import AsyncClient, MatrixRoom, RoomMessageText

    _AVAILABLE = True
except Exception:  # pragma: no cover - dipende dall'ambiente
    _AVAILABLE = False


def status() -> str:
    if not _AVAILABLE:
        return "matrix-nio non installato (pip install matrix-nio) — messaggi non attivi."
    if not settings.matrix_configured():
        return "Matrix non configurato (MATRIX_HOMESERVER/USER/TOKEN) — messaggi non attivi."
    return "Matrix configurato."


class MatrixBridge:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._messages: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._room_names: dict[str, str] = {}
        self._started = False
        self._ready = threading.Event()

    def available(self) -> bool:
        return _AVAILABLE and settings.matrix_configured()

    def start(self) -> None:
        if not self.available() or self._started:
            return
        self._started = True
        threading.Thread(target=self._run, daemon=True, name="matrix-bridge").start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception:
            self._started = False

    async def _main(self) -> None:
        client = AsyncClient(
            settings.matrix_homeserver, settings.matrix_user, device_id=settings.matrix_device_id
        )
        if settings.matrix_token:
            client.access_token = settings.matrix_token
            client.user_id = settings.matrix_user
        else:
            await client.login(settings.matrix_password, device_name="maggiordomo")
        self._client = client
        client.add_event_callback(self._on_message, RoomMessageText)
        self._ready.set()
        await client.sync_forever(timeout=30000, full_state=True)

    async def _on_message(self, room: "MatrixRoom", event: "RoomMessageText") -> None:
        self._room_names[room.room_id] = getattr(room, "display_name", None) or room.room_id
        self._messages[room.room_id].append(
            {"sender": event.sender, "body": event.body, "ts": event.server_timestamp}
        )

    def _resolve_room(self, query: str) -> str | None:
        if query in self._messages:
            return query
        ql = query.lower()
        for rid, name in self._room_names.items():
            if ql in name.lower():
                return rid
        return None

    def rooms(self) -> list[dict]:
        return [
            {"room_id": rid, "name": self._room_names.get(rid, rid), "count": len(dq)}
            for rid, dq in self._messages.items()
        ]

    def recent(self, room_query: str, limit: int = 15):
        rid = self._resolve_room(room_query)
        if not rid:
            return None
        return self._room_names.get(rid, rid), list(self._messages[rid])[-limit:]

    def send(self, room_query: str, text: str) -> str:
        if not self.available() or not self._client or not self._loop:
            return "[errore] bridge Matrix non attivo"
        rid = self._resolve_room(room_query)
        if not rid:
            return f"[errore] stanza non trovata: {room_query}"
        fut = asyncio.run_coroutine_threadsafe(
            self._client.room_send(
                rid, "m.room.message", {"msgtype": "m.text", "body": text}
            ),
            self._loop,
        )
        fut.result(timeout=30)
        return f"messaggio inviato a {self._room_names.get(rid, rid)}"


bridge = MatrixBridge()
