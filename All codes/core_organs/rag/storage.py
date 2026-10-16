"""
rag.storage -- where the RAG lives (DESIGN.md section 2): root resolution with an explicit, reported fallback, meta.json, numbered migrations, and connections.

    resolve_root()         env AI_STORAGE_ROOT -> data/rag_root.txt -> data/ai_root. A configured root that is missing (the SSD is unplugged) falls back to the default and
                           says so in Storage.degraded; it never falls back silently.
    Storage(root=None, embedder=None)
        .lance             LanceDB connection (lazy)
        .table(name)       an opened LanceDB table (created by migration 0001)
        .sql(name)         a SqliteDb: WAL, one lock, dict rows
        .embed             EmbedService (cache in cache.db)
        .gen(scope) / .bump(scope)   per-scope generation counters in cache.db: any write bumps its scope, which is what invalidates the router's result cache and the graph view
        .rel(path) / .abs(rel)       every stored file path is root-relative, so a changed drive letter breaks nothing

get_storage() is the process singleton; reset_storage() drops it (tests build their own Storage over a temp root).
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config as C
from . import embed as E

log = logging.getLogger("hojaiga.rag.storage")

_REPO_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")
DEFAULT_ROOT = os.path.join(_REPO_DATA, "ai_root")
ROOT_FILE = os.path.join(_REPO_DATA, "rag_root.txt")


def resolve_root() -> Tuple[str, List[str]]:
    """(root, degraded). degraded names a configured root that could not be used."""
    wanted = os.environ.get("AI_STORAGE_ROOT", "").strip()
    src = "env AI_STORAGE_ROOT"
    if not wanted and os.path.isfile(ROOT_FILE):
        try:
            wanted = open(ROOT_FILE, encoding="utf-8").read().strip()
            src = "data/rag_root.txt"
        except Exception:
            wanted = ""
    if not wanted:
        return DEFAULT_ROOT, []
    drive = os.path.splitdrive(wanted)[0]
    usable = os.path.isdir(drive + os.sep) if drive else True
    if usable:
        try:
            os.makedirs(wanted, exist_ok=True)
            return wanted, []
        except Exception:
            pass
    log.warning("rag storage root %r (%s) is not available; falling back to %r", wanted, src, DEFAULT_ROOT)
    return DEFAULT_ROOT, [f"storage_root_missing:{wanted}"]


class SqliteDb:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")

    def execute(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.db.execute(sql, tuple(args))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.lock:
            self.db.executemany(sql, rows)

    def script(self, sql: str) -> None:
        with self.lock:
            self.db.executescript(sql)

    def rows(self, sql: str, args: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, tuple(args)).fetchall()]

    def one(self, sql: str, args: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        with self.lock:
            r = self.db.execute(sql, tuple(args)).fetchone()
            return dict(r) if r else None

    def commit(self) -> None:
        with self.lock:
            self.db.commit()

    def close(self) -> None:
        with self.lock:
            try:
                self.db.commit()
                self.db.close()
            except Exception:
                pass


class Storage:
    def __init__(self, root: Optional[str] = None, embedder: Optional[E.Embedder] = None):
        if root:
            self.root, self.degraded = os.path.abspath(root), []
        else:
            self.root, self.degraded = resolve_root()
        self.base = os.path.join(self.root, "rag")
        for sub in ("lancedb", "blobs/screens", "blobs/icons", "exports/packs"):
            os.makedirs(os.path.join(self.base, *sub.split("/")), exist_ok=True)
        self._sql: Dict[str, SqliteDb] = {}
        self._lock = threading.RLock()
        self._lance = None
        self._text = None
        self._tables: Dict[str, Any] = {}
        self.meta = self._load_meta()
        self.embed = E.EmbedService(embedder or E.default_embedder(), os.path.join(self.base, "embed_cache.db"))
        self._ensure_gens()
        self.migrate()
        self.meta["active_text_embedder"] = self.embed.id
        self._save_meta()

    # ---- meta ---------------------------------------------------------------------------------------------------------------------------------------
    @property
    def _meta_path(self) -> str:
        return os.path.join(self.base, "meta.json")

    def _load_meta(self) -> Dict[str, Any]:
        try:
            with open(self._meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"root_uuid": uuid.uuid4().hex, "schema_version": 0, "created_at": time.time(), "vec_dim": C.VEC_DIM, "embedders": {}}

    def _save_meta(self) -> None:
        tmp = self._meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2, sort_keys=True)
        os.replace(tmp, self._meta_path)

    # ---- paths --------------------------------------------------------------------------------------------------------------------------------------
    def path(self, *parts: str) -> str:
        return os.path.join(self.base, *parts)

    def rel(self, p: str) -> str:
        try:
            return os.path.relpath(p, self.root).replace("\\", "/")
        except ValueError:
            return p.replace("\\", "/")

    def abs(self, rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(self.root, rel))

    # ---- connections --------------------------------------------------------------------------------------------------------------------------------
    def sql(self, name: str) -> SqliteDb:
        with self._lock:
            if name not in self._sql:
                self._sql[name] = SqliteDb(self.path(name + ".db"))
            return self._sql[name]

    @property
    def lance(self):
        with self._lock:
            if self._lance is None:
                import lancedb
                self._lance = lancedb.connect(self.path("lancedb"))
            return self._lance

    @property
    def text(self):
        """The SQLite FTS5 lexical index (rag.textindex) for every vector-backed table."""
        with self._lock:
            if getattr(self, "_text", None) is None:
                from .textindex import TextIndex
                self._text = TextIndex(self)
            return self._text

    def table_names(self) -> List[str]:
        r = self.lance.list_tables()
        return list(getattr(r, "tables", r) or [])

    def table(self, name: str):
        with self._lock:
            if name not in self._tables:
                self._tables[name] = self.lance.open_table(name)
            return self._tables[name]

    def count(self, name: str) -> int:
        try:
            return int(self.table(name).count_rows())
        except Exception:
            return 0

    # ---- generations --------------------------------------------------------------------------------------------------------------------------------
    def _ensure_gens(self) -> None:
        self.sql("cache").execute("CREATE TABLE IF NOT EXISTS gens(scope TEXT PRIMARY KEY, gen INTEGER NOT NULL)")
        self.sql("cache").commit()

    def gen(self, scope: str) -> int:
        r = self.sql("cache").one("SELECT gen FROM gens WHERE scope=?", (scope,))
        return int(r["gen"]) if r else 0

    def bump(self, scope: str) -> int:
        db = self.sql("cache")
        with db.lock:
            db.execute("INSERT INTO gens(scope,gen) VALUES(?,1) ON CONFLICT(scope) DO UPDATE SET gen=gen+1", (scope,))
            db.commit()
        return self.gen(scope)

    # ---- migrations ---------------------------------------------------------------------------------------------------------------------------------
    def migrate(self) -> int:
        from . import migrations
        applied = int(self.meta.get("schema_version", 0))
        mods = sorted(m.name for m in pkgutil.iter_modules(migrations.__path__) if m.name[:4].isdigit())
        for name in mods:
            n = int(name[:4])
            if n <= applied:
                continue
            mod = importlib.import_module(f"{migrations.__name__}.{name}")
            mod.up(self)
            self.meta["schema_version"] = applied = n
            self._save_meta()
            log.info("rag migration %s applied", name)
        return applied

    def close(self) -> None:
        for db in self._sql.values():
            db.close()
        self._sql.clear()
        self._tables.clear()
        self._lance = None
        self._text = None


_singleton: Optional[Storage] = None
_slock = threading.Lock()


def get_storage() -> Storage:
    global _singleton
    with _slock:
        if _singleton is None:
            _singleton = Storage()
        return _singleton


def reset_storage() -> None:
    global _singleton
    with _slock:
        if _singleton is not None:
            _singleton.close()
        _singleton = None
