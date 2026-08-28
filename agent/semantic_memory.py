"""Memoria semantica — livello 2: richiamo per significato.

Affianca i fatti strutturati (livello 1) con un indice vettoriale: ogni testo
importante viene trasformato in un embedding (locale, via Ollama `nomic-embed-text`,
così resta privato) e il richiamo cerca per similarità del coseno.

Scala da utente singolo: qualche migliaio di vettori. La ricerca è brute-force in
Python/NumPy — semplice e affidabile, senza estensioni native. Se in futuro
l'archivio cresce molto, si passa a sqlite-vec senza cambiare l'interfaccia.

Se gli embedding non sono disponibili (Ollama spento), `search` ritorna None e i
chiamanti ricadono con grazia sulla ricerca per parole chiave.
"""

from __future__ import annotations

import struct

import httpx

from .config import settings
from .db import connect

try:
    import numpy as np

    _NP = True
except Exception:  # pragma: no cover
    _NP = False


# --- backend di embedding (i test lo sostituiscono con uno finto) ---------------

def _ollama_embed(text: str) -> list[float] | None:
    host = settings.ollama_native_base()
    r = httpx.post(
        f"{host}/api/embeddings",
        json={"model": settings.embed_model, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("embedding")


_backend = _ollama_embed


def embed(text: str) -> list[float] | None:
    """Ritorna l'embedding del testo, o None se il backend non è disponibile."""
    try:
        vec = _backend(text)
        return vec or None
    except Exception:
        return None


# --- (de)serializzazione dei vettori -------------------------------------------

def _to_blob(vec) -> bytes:
    if _NP:
        return np.asarray(vec, dtype="float32").tobytes()
    return struct.pack(f"{len(vec)}f", *vec)


def _from_blob(blob: bytes, dim: int):
    if _NP:
        return np.frombuffer(blob, dtype="float32")
    return list(struct.unpack(f"{dim}f", blob))


# --- indicizzazione e ricerca ---------------------------------------------------

def index_text(kind: str, ref_id: int, text: str) -> bool:
    """Indicizza (o reindicizza) un testo. Ritorna False se non c'è embedding."""
    vec = embed(text)
    if vec is None:
        return False
    blob = _to_blob(vec)
    conn = connect()
    try:
        conn.execute("DELETE FROM memory_vectors WHERE kind = ? AND ref_id = ?", (kind, ref_id))
        conn.execute(
            "INSERT INTO memory_vectors (kind, ref_id, text, embedding, dim) VALUES (?, ?, ?, ?, ?)",
            (kind, ref_id, text, blob, len(vec)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_ref(kind: str, ref_id: int) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM memory_vectors WHERE kind = ? AND ref_id = ?", (kind, ref_id))
        conn.commit()
    finally:
        conn.close()


def _cosine(a, b) -> float:
    if _NP:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def search(query: str, k: int = 5) -> list[dict] | None:
    """Top-k per similarità. None = embedding non disponibili; [] = indice vuoto."""
    qv = embed(query)
    if qv is None:
        return None
    conn = connect()
    try:
        rows = conn.execute("SELECT kind, ref_id, text, embedding, dim FROM memory_vectors").fetchall()
    finally:
        conn.close()
    if not rows:
        return []

    q = _from_blob(_to_blob(qv), len(qv))  # normalizza il tipo come i vettori salvati
    scored = []
    for r in rows:
        if r["dim"] != len(qv):
            continue  # embedding di un modello diverso: salta
        v = _from_blob(r["embedding"], r["dim"])
        scored.append((_cosine(v, q), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"kind": r["kind"], "ref_id": r["ref_id"], "text": r["text"], "score": round(s, 3)}
        for s, r in scored[:k]
    ]


def available() -> bool:
    """True se il backend di embedding risponde (fa una chiamata di prova)."""
    return embed("ping") is not None
