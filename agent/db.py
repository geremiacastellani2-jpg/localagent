"""Archivio locale (SQLite): note, promemoria e fatti in memoria.

È volutamente il posto canonico dei dati: tutto resta sul Mac, interrogabile.
La memoria semantica a vettori arriverà in una fase successiva (sqlite-vec).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    tags       TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    due_at     TEXT,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject    TEXT NOT NULL,
    fact       TEXT NOT NULL,
    source     TEXT DEFAULT 'chat',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT UNIQUE,                 -- UID iCalendar (per la sync CalDAV)
    title       TEXT NOT NULL,
    start_at    TEXT NOT NULL,               -- ISO canonico YYYY-MM-DDTHH:MM:SS
    end_at      TEXT,                        -- ISO canonico (facoltativo)
    all_day     INTEGER NOT NULL DEFAULT 0,
    location    TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    caldav_href TEXT,                        -- href dell'oggetto remoto (update/delete)
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);

CREATE TABLE IF NOT EXISTS memory_vectors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,               -- 'fact', 'note', ...
    ref_id     INTEGER NOT NULL DEFAULT 0,  -- id della riga sorgente (per dedup/aggiornamento)
    text       TEXT NOT NULL,               -- testo indicizzato
    embedding  BLOB NOT NULL,               -- vettore float32
    dim        INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_vectors_ref ON memory_vectors(kind, ref_id);
"""


def connect() -> sqlite3.Connection:
    path: Path = settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
