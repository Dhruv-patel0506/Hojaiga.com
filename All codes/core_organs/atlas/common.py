"""
atlas.common -- shared foundation of the Atlas knowledge layer.

Everything the other Atlas modules agree on lives here:

* paths and switches (all overridable by environment, so tests run on a scratch database)
* the EVIDENCE rule: a claim without evidence cannot be stored (knowledge is measured or sourced, never asserted)
* trust classes:  measured (a probe observed it)  >  static (read from the program's own files)
                  >  published (read from a public document)  >  inferred (derived by a rule or a model)
* AtlasStore: one sqlite file (the same behavior database the rest of Hojaiga uses) with its own tables

No per-app code. No network. No model calls. Pure stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = os.environ.get("HOJAIGA_ROOT", r"D:\new_automation")
DB_PATH = os.environ.get("HOJAIGA_BEHAVIOR_DB", os.path.join(ROOT, "data", "app_behavior.db"))
ATLAS_DIR = os.environ.get("HOJAIGA_ATLAS_DIR", os.path.join(ROOT, "data", "atlas"))
WEB_CACHE_DIR = os.path.join(ATLAS_DIR, "webcache")
REPORT_DIR = os.path.join(ATLAS_DIR, "reports")
EVIDENCE_DIR = os.path.join(ATLAS_DIR, "evidence")

OFFLINE = os.environ.get("HOJAIGA_ATLAS_OFFLINE", "0") == "1"
LLM_URL = os.environ.get("HOJAIGA_ATLAS_LLM_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("HOJAIGA_ATLAS_LLM_MODEL", "")          # empty = discover
EMBED_MODEL = os.environ.get("HOJAIGA_ATLAS_EMBED_MODEL", "nomic-embed-text")
USER_AGENT = "hojaiga-atlas/1.0 (local research tool; contact: none)"

TRUST = {"measured": 4, "static": 3, "published": 2, "inferred": 1}
TRUST_NAMES = {v: k for k, v in TRUST.items()}


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def now() -> float:
    return time.time()


def sha(text: Any, n: int = 16) -> str:
    if not isinstance(text, (bytes, bytearray)):
        text = str(text).encode("utf-8", "replace")
    return hashlib.sha1(text).hexdigest()[:n]


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fold(s: str) -> str:
    """Case/punctuation-insensitive form used to compare labels and to verify quotes."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def app_key_of(name: str) -> str:
    """The same key the behavior model uses; falls back to a local rule when the model is not importable."""
    try:
        from core_organs import organ_48_app_behavior_model as bm
        return bm._app_key(name)
    except Exception:
        k = re.sub(r"\.exe$", "", (name or "").strip().lower())
        return re.sub(r"[^a-z0-9]+", "_", k).strip("_")


# --------------------------------------------------------------------------------------------------
# Evidence + claims
# --------------------------------------------------------------------------------------------------

EVIDENCE_TYPES = ("file", "registry", "pe", "uia", "probe", "gesture", "url", "typelib", "config", "rule", "model", "doc")


@dataclass
class Evidence:
    """One verifiable pointer: where a statement comes from. `quote` is the literal text (for documents)."""
    type: str
    ref: str
    quote: str = ""
    ts: float = field(default_factory=now)

    def key(self) -> str:
        return f"{self.type}|{self.ref}|{sha(self.quote, 8)}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d["quote"]:
            d.pop("quote")
        return d


@dataclass
class Claim:
    app_key: str
    kind: str                  # arch.* ext.* io.* net.* cfg.* ui.* gesture.* model.* web.* stack.*
    statement: str
    trust: str = "inferred"
    confidence: float = 0.5
    evidence: List[Evidence] = field(default_factory=list)
    value: Any = None
    source: str = ""

    @property
    def id(self) -> str:
        return sha(f"{self.app_key}|{self.kind}|{fold(self.statement)}")


class EvidenceRequired(ValueError):
    """Raised when something tries to store knowledge nobody can check."""


# --------------------------------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS atlas_claims (
    id TEXT PRIMARY KEY, app_key TEXT, kind TEXT, statement TEXT, value_json TEXT,
    trust INTEGER, confidence REAL, evidence_json TEXT, source TEXT, ts REAL, n_obs INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS atlas_claims_app ON atlas_claims(app_key, kind);
CREATE TABLE IF NOT EXISTS atlas_gestures (
    id TEXT PRIMARY KEY, app_key TEXT, region TEXT, region_kind TEXT, gesture TEXT, modifiers TEXT,
    effect_class TEXT, effect_json TEXT, reversible INTEGER, delivered INTEGER, effective INTEGER,
    evidence TEXT, run_id TEXT, ts REAL, n_obs INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS atlas_gest_app ON atlas_gestures(app_key, region_kind, gesture);
CREATE TABLE IF NOT EXISTS atlas_docs (
    url TEXT PRIMARY KEY, app_key TEXT, kind TEXT, sha TEXT, bytes INTEGER, path TEXT, fetched_ts REAL, status INTEGER);
CREATE TABLE IF NOT EXISTS atlas_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, app_key TEXT, run_id TEXT, subject TEXT, features TEXT,
    predicted TEXT, observed TEXT, correct INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS atlas_priors (
    feature TEXT, outcome TEXT, n INTEGER DEFAULT 0, PRIMARY KEY (feature, outcome));
CREATE TABLE IF NOT EXISTS atlas_runs (
    run_id TEXT PRIMARY KEY, app_key TEXT, tier TEXT, started REAL, seconds REAL, metrics_json TEXT);
CREATE TABLE IF NOT EXISTS atlas_fingerprints (
    app_key TEXT, ts REAL, version_hash TEXT, structure_sig TEXT, n_commands INTEGER, n_controls INTEGER, extra_json TEXT);
"""


class AtlasStore:
    """Thread-safe sqlite access (own connection, WAL). Same file as the behavior model by default."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or DB_PATH
        ensure_dir(os.path.dirname(self.path) or ".")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # ---- generic helpers
    def _rows(self, sql: str, args: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(args))
            cols = [c[0] for c in cur.description or []]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _exec(self, sql: str, args: Sequence[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, tuple(args))
            self._conn.commit()

    # ---- claims
    def put_claim(self, c: Claim) -> str:
        """Store/merge a claim. Refuses a claim with no evidence (the anti-assertion rule)."""
        if not c.evidence:
            raise EvidenceRequired(f"claim without evidence refused: [{c.kind}] {c.statement[:80]}")
        if c.trust not in TRUST:
            raise ValueError(f"unknown trust class {c.trust!r}")
        cid = c.id
        rank = TRUST[c.trust]
        with self._lock:
            old = self._conn.execute("SELECT trust, confidence, evidence_json, n_obs FROM atlas_claims WHERE id=?", (cid,)).fetchone()
            ev = {e.key(): e.to_dict() for e in c.evidence}
            if old:
                try:
                    for d in json.loads(old[2] or "[]"):
                        e = Evidence(d.get("type", "rule"), d.get("ref", ""), d.get("quote", ""), d.get("ts", 0.0))
                        ev.setdefault(e.key(), e.to_dict())
                except Exception:
                    pass
                rank = max(rank, int(old[0] or 0))
                conf = max(float(old[1] or 0.0), c.confidence)
                n = int(old[3] or 1) + 1
            else:
                conf, n = c.confidence, 1
            evl = sorted(ev.values(), key=lambda d: d.get("ts", 0))[-12:]
            self._conn.execute(
                "INSERT OR REPLACE INTO atlas_claims (id, app_key, kind, statement, value_json, trust, confidence, evidence_json, source, ts, n_obs) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (cid, c.app_key, c.kind, c.statement[:2000], json.dumps(c.value, default=str)[:20000] if c.value is not None else None,
                 rank, round(conf, 3), json.dumps(evl, default=str), c.source, now(), n))
            self._conn.commit()
        return cid

    def claim(self, app_key: str, kind: str, statement: str, *, trust: str, evidence: Iterable[Evidence], confidence: float = 0.6,
              value: Any = None, source: str = "") -> str:
        return self.put_claim(Claim(app_key, kind, statement, trust, confidence, list(evidence), value, source))

    def claims(self, app_key: str, kind_prefix: str = "", min_trust: int = 0, limit: int = 5000) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM atlas_claims WHERE app_key=? AND trust>=?"
        args: List[Any] = [app_key, min_trust]
        if kind_prefix:
            sql += " AND kind LIKE ?"
            args.append(kind_prefix + "%")
        sql += " ORDER BY trust DESC, confidence DESC, kind LIMIT ?"
        args.append(limit)
        out = self._rows(sql, args)
        for r in out:
            r["trust_name"] = TRUST_NAMES.get(r["trust"], "?")
            try:
                r["evidence"] = json.loads(r.pop("evidence_json") or "[]")
            except Exception:
                r["evidence"] = []
            try:
                r["value"] = json.loads(r.pop("value_json")) if r.get("value_json") else None
            except Exception:
                r["value"] = None
        return out

    def count_claims(self, app_key: str) -> Dict[str, int]:
        rows = self._rows("SELECT kind, COUNT(*) n FROM atlas_claims WHERE app_key=? GROUP BY kind", (app_key,))
        return {r["kind"]: r["n"] for r in rows}

    def delete_claims(self, app_key: str, kind_prefix: str = "", source: str = "") -> int:
        sql, args = "DELETE FROM atlas_claims WHERE app_key=?", [app_key]
        if kind_prefix:
            sql += " AND kind LIKE ?"
            args.append(kind_prefix + "%")
        if source:
            sql += " AND source=?"
            args.append(source)
        with self._lock:
            n = self._conn.execute(sql, args).rowcount
            self._conn.commit()
        return n

    # ---- gestures
    def put_gesture(self, app_key: str, region: str, region_kind: str, gesture: str, modifiers: str, effect_class: str,
                    effect: Dict[str, Any], *, reversible: Optional[bool], delivered: bool, effective: Optional[bool],
                    evidence: str = "", run_id: str = "") -> str:
        gid = sha(f"{app_key}|{region_kind}|{gesture}|{modifiers}|{region}")
        with self._lock:
            old = self._conn.execute("SELECT n_obs FROM atlas_gestures WHERE id=?", (gid,)).fetchone()
            n = int(old[0]) + 1 if old else 1
            self._conn.execute(
                "INSERT OR REPLACE INTO atlas_gestures (id, app_key, region, region_kind, gesture, modifiers, effect_class, effect_json, "
                "reversible, delivered, effective, evidence, run_id, ts, n_obs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (gid, app_key, region, region_kind, gesture, modifiers, effect_class, json.dumps(effect, default=str)[:8000],
                 None if reversible is None else int(reversible), int(delivered), None if effective is None else int(effective),
                 evidence[:1500], run_id, now(), n))
            self._conn.commit()
        return gid

    def gestures(self, app_key: str, region_kind: str = "") -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM atlas_gestures WHERE app_key=?", [app_key]
        if region_kind:
            sql += " AND region_kind=?"
            args.append(region_kind)
        out = self._rows(sql + " ORDER BY region_kind, gesture, modifiers", args)
        for r in out:
            try:
                r["effect"] = json.loads(r.pop("effect_json") or "{}")
            except Exception:
                r["effect"] = {}
        return out

    # ---- docs (web cache provenance)
    def put_doc(self, url: str, app_key: str, kind: str, sha_: str, nbytes: int, path: str, status: int = 200) -> None:
        self._exec("INSERT OR REPLACE INTO atlas_docs (url, app_key, kind, sha, bytes, path, fetched_ts, status) VALUES (?,?,?,?,?,?,?,?)",
                   (url, app_key, kind, sha_, nbytes, path, now(), status))

    def doc(self, url: str) -> Optional[Dict[str, Any]]:
        r = self._rows("SELECT * FROM atlas_docs WHERE url=?", (url,))
        return r[0] if r else None

    def docs(self, app_key: str) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM atlas_docs WHERE app_key=? ORDER BY fetched_ts DESC", (app_key,))

    # ---- runs + fingerprints
    def log_run(self, run_id: str, app_key: str, tier: str, started: float, seconds: float, metrics: Dict[str, Any]) -> None:
        self._exec("INSERT OR REPLACE INTO atlas_runs (run_id, app_key, tier, started, seconds, metrics_json) VALUES (?,?,?,?,?,?)",
                   (run_id, app_key, tier, started, round(seconds, 2), json.dumps(metrics, default=str)[:60000]))

    def runs(self, app_key: str, limit: int = 20) -> List[Dict[str, Any]]:
        out = self._rows("SELECT * FROM atlas_runs WHERE app_key=? ORDER BY started DESC LIMIT ?", (app_key, limit))
        for r in out:
            try:
                r["metrics"] = json.loads(r.pop("metrics_json") or "{}")
            except Exception:
                r["metrics"] = {}
        return out

    def put_fingerprint(self, app_key: str, version_hash: str, structure_sig: str, n_commands: int, n_controls: int, extra: Dict[str, Any]) -> None:
        self._exec("INSERT INTO atlas_fingerprints (app_key, ts, version_hash, structure_sig, n_commands, n_controls, extra_json) VALUES (?,?,?,?,?,?,?)",
                   (app_key, now(), version_hash, structure_sig, n_commands, n_controls, json.dumps(extra, default=str)[:20000]))

    def fingerprints(self, app_key: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self._rows("SELECT * FROM atlas_fingerprints WHERE app_key=? ORDER BY ts DESC LIMIT ?", (app_key, limit))


_STORES: Dict[str, AtlasStore] = {}
_STORES_LOCK = threading.Lock()


def get_store(path: Optional[str] = None) -> AtlasStore:
    p = os.path.abspath(path or DB_PATH)
    with _STORES_LOCK:
        s = _STORES.get(p)
        if s is None:
            s = _STORES[p] = AtlasStore(p)
        return s


# --------------------------------------------------------------------------------------------------
# small text helpers shared by several modules
# --------------------------------------------------------------------------------------------------

def jdump(obj: Any, limit: int = 0) -> str:
    s = json.dumps(obj, indent=1, default=str, ensure_ascii=False)
    return s[:limit] if limit else s


def human_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class Timer:
    def __init__(self):
        self.t0 = time.time()
        self.marks: Dict[str, float] = {}

    def mark(self, name: str) -> float:
        t = time.time() - self.t0
        self.marks[name] = round(t, 3)
        return t

    def elapsed(self) -> float:
        return time.time() - self.t0

    def left(self, budget: float) -> float:
        return budget - self.elapsed()
