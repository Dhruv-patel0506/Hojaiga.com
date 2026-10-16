"""
rag.textindex -- the lexical leg of every vector-backed table, on SQLite FTS5 (text.db). Replaces LanceDB's own FTS, which (measured on lancedb 0.30) ignores rows written after its index was
built for any term the index already knows, and costs 45-80 ms at only 5k rows.

    per Lance table T:   ti_T(rowid, id UNIQUE, app_key, data JSON)      the row's non-vector columns, so a lexical hit needs no second read from Lance
                         tf_T  FTS5(app, text)  contentless, porter + unicode61, app = one token per app_key
    put()                transactional with the caller; a replace keeps the rowid
    search()             cascade: (1) AND of the content terms -- precise and cheap -- (2) if that falls short, OR over the rarest terms by document frequency
    heal()               rebuild from the Lance table when counts disagree (text.db lost or a write was interrupted)

An app is matched with `app : <token>` inside the MATCH expression (a posting-list intersection), never by post-filtering, so another app's rows are never scored.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import config as C

_TOK = re.compile(r"[A-Za-z0-9_]+")
_NAME = re.compile(r"^[a-z_]+$")


def app_token(app_key: str) -> str:
    return "a" + hashlib.sha1((app_key or "").encode("utf-8")).hexdigest()[:12]


class TextIndex:
    def __init__(self, st):
        self.st = st
        self.db = st.sql("text")
        self._ready: Dict[str, bool] = {}
        self._checked: Dict[str, bool] = {}
        self._lock = threading.RLock()

    # ---- schema -------------------------------------------------------------------------------------------------------------------------------------
    def _ensure(self, table: str) -> None:
        if self._ready.get(table):
            return
        assert _NAME.match(table), table
        with self.db.lock:
            self.db.execute(f"CREATE TABLE IF NOT EXISTS ti_{table}(rowid INTEGER PRIMARY KEY, id TEXT UNIQUE, app_key TEXT, data TEXT)")
            self.db.execute(f"CREATE INDEX IF NOT EXISTS ix_ti_{table}_app ON ti_{table}(app_key)")
            self.db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS tf_{table} USING fts5(app, text, tokenize='porter unicode61', content='', contentless_delete=1)")
            self.db.commit()
        self._ready[table] = True

    def count(self, table: str) -> int:
        self._ensure(table)
        return int(self.db.one(f"SELECT COUNT(*) AS n FROM ti_{table}")["n"])

    # ---- writes -------------------------------------------------------------------------------------------------------------------------------------
    def put(self, table: str, rows: Sequence[Dict[str, Any]], key: str, text_of: Callable[[Dict[str, Any]], str]) -> int:
        """Insert or replace rows (dicts of non-vector columns). One transaction."""
        if not rows:
            return 0
        self._ensure(table)
        with self.db.lock:
            for r in rows:
                rid = self.db.one(f"SELECT rowid FROM ti_{table} WHERE id=?", (r[key],))
                data = json.dumps({k: v for k, v in r.items() if k not in ("vector", "visual_vec") and not k.startswith("_")}, ensure_ascii=False, default=str)
                if rid:
                    rowid = rid["rowid"]
                    self.db.execute(f"DELETE FROM tf_{table} WHERE rowid=?", (rowid,))
                    self.db.execute(f"UPDATE ti_{table} SET app_key=?, data=? WHERE rowid=?", (r.get("app_key", ""), data, rowid))
                else:
                    cur = self.db.execute(f"INSERT INTO ti_{table}(id,app_key,data) VALUES(?,?,?)", (r[key], r.get("app_key", ""), data))
                    rowid = cur.lastrowid
                self.db.execute(f"INSERT INTO tf_{table}(rowid,app,text) VALUES(?,?,?)", (rowid, app_token(r.get("app_key", "")), text_of(r) or ""))
            self.db.commit()
        return len(rows)

    def delete_app(self, table: str, app_key: str) -> int:
        self._ensure(table)
        with self.db.lock:
            ids = [x["rowid"] for x in self.db.rows(f"SELECT rowid FROM ti_{table} WHERE app_key=?", (app_key,))]
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                ph = ",".join("?" for _ in chunk)
                self.db.execute(f"DELETE FROM tf_{table} WHERE rowid IN ({ph})", chunk)
                self.db.execute(f"DELETE FROM ti_{table} WHERE rowid IN ({ph})", chunk)
            self.db.commit()
        return len(ids)

    # ---- search -------------------------------------------------------------------------------------------------------------------------------------
    def _run(self, table: str, match: str, limit: int) -> List[Dict[str, Any]]:
        sql = f"SELECT ti_{table}.data AS data FROM tf_{table} JOIN ti_{table} ON ti_{table}.rowid = tf_{table}.rowid WHERE tf_{table} MATCH ? ORDER BY bm25(tf_{table}, 0.0, 1.0) LIMIT ?"
        try:
            return [json.loads(r["data"]) for r in self.db.rows(sql, (match, limit))]
        except Exception:
            return []

    def _df(self, table: str, app_tok: str, term: str, cap: int = 3000) -> int:
        try:
            r = self.db.one(f"SELECT COUNT(*) AS n FROM (SELECT 1 FROM tf_{table} WHERE tf_{table} MATCH ? LIMIT ?)", (f'app : ({app_tok}) AND text : "{term}"', cap))
            return int(r["n"]) if r else cap
        except Exception:
            return cap

    def search(self, table: str, terms: Sequence[str], app_keys: Sequence[str], limit: int) -> List[Dict[str, Any]]:
        """Ranked rows (best first). terms: content words (stopwords already removed). app_keys: the apps to search ([] = every app)."""
        terms = [t for t in dict.fromkeys(t.lower() for t in terms) if t]
        if not terms:
            return []
        self._ensure(table)
        toks = [app_token(a) for a in app_keys]
        scope = f"app : ({' OR '.join(toks)}) AND " if toks else ""
        qt = [f'"{t}"' for t in terms[:6]]
        # 1. every content term (precise, small intersections)
        rows = self._run(table, f"{scope}text : ({' AND '.join(qt)})", limit)
        if len(rows) >= limit or len(terms) == 1:
            return rows
        # 2. otherwise OR over the rarest terms: common words have the longest posting lists and the least signal
        if len(toks) == 1:
            ranked = sorted(terms[:8], key=lambda t: self._df(table, toks[0], t))
        else:
            ranked = terms[:4]
        more = self._run(table, f"{scope}text : ({' OR '.join(chr(34) + t + chr(34) for t in ranked[:4])})", limit)
        seen = {id(r) for r in rows}
        keys = {json.dumps(r, sort_keys=True) for r in rows}
        for r in more:
            k = json.dumps(r, sort_keys=True)
            if k not in keys:
                keys.add(k)
                rows.append(r)
        return rows[:limit]

    # ---- repair -------------------------------------------------------------------------------------------------------------------------------------
    def heal(self, table: str, key: str, text_of: Callable[[Dict[str, Any]], str], columns: Sequence[str]) -> int:
        """Rebuild the text index of `table` from its Lance rows (non-vector columns only). Returns rows indexed."""
        self._ensure(table)
        with self.db.lock:
            self.db.execute(f"DELETE FROM tf_{table}")
            self.db.execute(f"DELETE FROM ti_{table}")
            self.db.commit()
        n, off = 0, 0
        t = self.st.table(table)
        while True:
            rows = t.search().select(list(columns)).limit(2000).offset(off).to_list()
            if not rows:
                break
            self.put(table, rows, key, text_of)
            n += len(rows)
            off += 2000
        return n

    def ensure_consistent(self, table: str, key: str, text_of: Callable[[Dict[str, Any]], str], columns: Sequence[str]) -> bool:
        """Once per process per table: if the text index and the Lance table disagree on row count, heal. Returns True if a heal ran."""
        with self._lock:
            if self._checked.get(table):
                return False
            self._checked[table] = True
        if self.count(table) != self.st.count(table):
            self.heal(table, key, text_of, columns)
            return True
        return False
