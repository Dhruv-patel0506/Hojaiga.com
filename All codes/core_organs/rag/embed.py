"""
rag.embed -- text embedders behind one registry (DESIGN.md section 9).

    OllamaEmbedder   nomic-embed-text on CPU (num_gpu 0: the GPU belongs to the vision model), 768-d, 'search_document:' / 'search_query:' prefixes.
    HashEmbedder     deterministic signed-hash bag of words, 64-d. Needs no service: the embedder of every offline test, and a last-resort degraded mode.

Every vector stored in the package is padded to config.VEC_DIM (zeros do not change a cosine), and every stored row names the embedder that made it, so two embedders are never
compared. An embedder that is down yields None vectors (rows are written with vector=NULL and healed later by tools.reembed); it never raises into a caller.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import config as C

_WORD = re.compile(r"[a-z0-9]+")


class DimensionTooLarge(ValueError):
    pass


class Embedder:
    id = "base"
    dim = 0

    def embed(self, texts: Sequence[str], mode: str = "document") -> Optional[List[List[float]]]:
        raise NotImplementedError


class HashEmbedder(Embedder):
    id = "hash64-v1"
    dim = 64

    def embed(self, texts: Sequence[str], mode: str = "document") -> Optional[List[List[float]]]:
        out = []
        for t in texts:
            v = np.zeros(self.dim, np.float32)
            toks = _WORD.findall((t or "").lower())
            for tok in toks:
                h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "little")
                v[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
                # character trigrams make near-spellings ('extrude'/'extruding') overlap, the way a real embedder would
            for tok in toks:
                for i in range(len(tok) - 2):
                    h = int.from_bytes(hashlib.blake2b(tok[i:i + 3].encode(), digest_size=8).digest(), "little")
                    v[h % self.dim] += 0.35 if (h >> 32) & 1 else -0.35
            n = float(np.linalg.norm(v))
            out.append((v / n if n else v).tolist())
        return out


class OllamaEmbedder(Embedder):
    id = C.TEXT_EMBEDDER_ID
    dim = 768
    _PREFIX = {"document": "search_document: ", "query": "search_query: "}

    def __init__(self, url: str = "", model: str = "nomic-embed-text", cooldown_s: float = 30.0):
        if not url:
            try:
                from core_organs.professor import config as PC
                url = PC.OLLAMA_URL
            except Exception:
                url = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434")
        self.url, self.model, self.cooldown_s = url.rstrip("/"), model, cooldown_s
        self._down_until = 0.0

    def embed(self, texts: Sequence[str], mode: str = "document") -> Optional[List[List[float]]]:
        if time.time() < self._down_until or not texts:
            return None
        try:
            import requests
            pre = self._PREFIX.get(mode, "")
            # keep_alive: Ollama unloads an idle model after 5 minutes and the next call pays ~1 s to reload it; a query embedding is on the hot path, so the model stays resident.
            # A QUERY embedding gets a short wall-clock cap (the lexical leg still answers if it is missed); documents (ingest) can take their time.
            r = requests.post(self.url + "/api/embed", json={"model": self.model, "input": [pre + (t or "")[:1500] for t in texts], "options": {"num_gpu": 0}, "keep_alive": "30m"},
                              timeout=C.QUERY_EMBED_TIMEOUT_S if mode == "query" else 30)
            e = r.json().get("embeddings") if r.status_code == 200 else None
            if e and len(e) == len(texts):
                return e
        except Exception as exc:
            # a TIMEOUT usually means the model was cold (it is loading now): retry soon. Anything else means the service is not there: back off.
            self._down_until = time.time() + (5.0 if "Timeout" in type(exc).__name__ else self.cooldown_s)
            return None
        self._down_until = time.time() + self.cooldown_s          # circuit breaker: do not hammer a service that is not there
        return None


def pad(vec: Sequence[float], dim: int = 0) -> List[float]:
    dim = dim or C.VEC_DIM
    if len(vec) > dim:
        raise DimensionTooLarge(f"embedding of {len(vec)} dims does not fit the {dim}-wide column; add a migration with a wider vector column")
    return list(vec) + [0.0] * (dim - len(vec))


class EmbedService:
    """Embedder + a persistent (embedder, mode, text-hash) -> vector LRU cache in cache.db. embed() returns padded vectors, or None per text when the embedder is unavailable."""

    def __init__(self, embedder: Embedder, cache_path: str = ""):
        self.embedder = embedder
        self._lock = threading.RLock()
        self._db = None
        if cache_path:
            self._db = sqlite3.connect(cache_path, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("CREATE TABLE IF NOT EXISTS embed_cache(k TEXT PRIMARY KEY, v BLOB, ts REAL)")
            self._db.commit()
        self.healthy = True

    @property
    def id(self) -> str:
        return self.embedder.id

    @staticmethod
    def _key(eid: str, mode: str, text: str) -> str:
        return hashlib.sha1(f"{eid}|{mode}|{text}".encode("utf-8")).hexdigest()

    def embed(self, texts: Sequence[str], mode: str = "document") -> List[Optional[List[float]]]:
        res: List[Optional[List[float]]] = [None] * len(texts)
        miss: List[int] = []
        with self._lock:
            for i, t in enumerate(texts):
                row = self._db.execute("SELECT v FROM embed_cache WHERE k=?", (self._key(self.id, mode, t),)).fetchone() if self._db else None
                if row:
                    res[i] = np.frombuffer(row[0], np.float32).tolist()
                else:
                    miss.append(i)
        if miss:
            got = None
            try:
                got = self.embedder.embed([texts[i] for i in miss], mode)
            except Exception:
                got = None
            self.healthy = got is not None
            if got:
                with self._lock:
                    for i, v in zip(miss, got):
                        p = pad(v)
                        res[i] = p
                        if self._db:
                            self._db.execute("INSERT OR REPLACE INTO embed_cache VALUES(?,?,?)", (self._key(self.id, mode, texts[i]), np.asarray(p, np.float32).tobytes(), time.time()))
                    if self._db:
                        self._db.execute("DELETE FROM embed_cache WHERE k IN (SELECT k FROM embed_cache ORDER BY ts DESC LIMIT -1 OFFSET ?)", (C.EMBED_CACHE_MAX,))
                        self._db.commit()
        return res

    def embed_one(self, text: str, mode: str = "query") -> Optional[List[float]]:
        return self.embed([text], mode)[0]


def default_embedder() -> Embedder:
    """The configured text embedder: Ollama when HOJAIGA_RAG_EMBEDDER is unset/'ollama', the hash embedder when 'hash'."""
    return HashEmbedder() if os.environ.get("HOJAIGA_RAG_EMBEDDER", "ollama").lower() == "hash" else OllamaEmbedder()
