"""
rag.lt -- the helpers every vector-backed sub-RAG shares: idempotent upsert into LanceDB (vectors + rows) AND the SQLite FTS5 text index (rag.textindex), embedding at write time (NULL when the
embedder is down), and app-prefiltered hybrid search fused by reciprocal rank (DESIGN.md sections 5.3, 9).

Why two stores per table: LanceDB owns the vectors and the full rows; SQLite FTS5 owns the lexical leg. LanceDB's own FTS was measured (0.30) to ignore rows written after its index was built for
any term the index already knows, and to cost 45-80 ms at 5k rows; FTS5 is transactional with the write, so a row is searchable the moment it is stored.
Mutable learning state (counters, promotion) lives in learn.db, never in a rewritten row, so hot-path updates never touch either index.

Search never mixes embedding spaces: the vector leg only sees rows whose embedder_id equals the ACTIVE embedder; the lexical leg sees everything. The legs run in parallel (both release the GIL).
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import pyarrow as pa

from . import config as C
from . import schemas as S

_TOK = re.compile(r"[A-Za-z0-9_]+")
COMPACT_EVERY_WRITES = 25
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="rag-lt")
AppKeys = Union[str, Sequence[str]]

_STOP = frozenset("a an the of to in on for and or is it its this that these those with as at by be are was were how do does did i you my me we our can could should would will what where when which who why "
                  "from into your there here so if then than just also not no yes please".split())


def q(s: Any) -> str:
    """SQL string literal for a LanceDB filter."""
    return "'" + str(s).replace("'", "''") + "'"


def terms_of(text: str) -> List[str]:
    """Content words only: stopwords have the longest posting lists and no signal. If a query is ALL stopwords it is kept whole (better a slow answer than none)."""
    toks = _TOK.findall(text or "")
    keep = [t for t in toks if t.lower() not in _STOP]
    return (keep or toks)[:12]


def _cols(table: str, extra: Sequence[str] = ()) -> List[str]:
    """Every column except the wide vectors: results never need them, and reading them is most of a query's cost."""
    return [n for n in S.SCHEMAS[table].names if n not in ("vector", "visual_vec")] + list(extra)


def _default(field: pa.Field) -> Any:
    t = field.type
    if pa.types.is_string(t):
        return ""
    if pa.types.is_boolean(t):
        return False
    if pa.types.is_integer(t):
        return 0
    if pa.types.is_floating(t):
        return 0.0
    if pa.types.is_list(t) or pa.types.is_fixed_size_list(t):
        return None if pa.types.is_fixed_size_list(t) else []
    return None


def normalise(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """A row with every schema column present (defaults filled), schema_v and extra_json set. Unknown keys are folded into extra_json, never dropped, never an error."""
    sch = S.SCHEMAS[table]
    out: Dict[str, Any] = {}
    extra = {}
    try:
        extra = json.loads(row.get("extra_json") or "{}")
    except Exception:
        extra = {}
    names = set(sch.names)
    for k, v in row.items():
        if k not in names:
            extra[k] = v
    for f in sch:
        v = row.get(f.name)
        out[f.name] = _default(f) if v is None and f.name not in ("vector", "visual_vec") else v
    out["schema_v"] = C.SCHEMA_VERSION
    out["extra_json"] = json.dumps(extra, ensure_ascii=False, sort_keys=True)
    for k in ("vector", "visual_vec"):
        if k in out and out[k] is not None:
            out[k] = [float(x) for x in out[k]]
    return out


def _slim(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if k not in ("vector", "visual_vec")}


def _ensure_text(st, table: str) -> None:
    st.text.ensure_consistent(table, S.KEYS[table], S.FTS_TEXT[table], _cols(table))


# ---- maintenance ------------------------------------------------------------------------------------------------------------------------------------
def maintain(st, table: str, force: bool = False) -> bool:
    """Compact the Lance table every COMPACT_EVERY_WRITES writes (many tiny fragments slow every scan). Returns True if it ran."""
    writes = int(st.meta.get(f"writes:{table}", 0))
    if not force and writes < COMPACT_EVERY_WRITES:
        return False
    try:
        st.table(table).optimize()
    except Exception:
        pass
    st.meta[f"writes:{table}"] = 0
    st._save_meta()
    return True


def optimize(st, table: str) -> None:
    """After a bulk ingest."""
    maintain(st, table, force=True)


def upsert(st, table: str, rows: Iterable[Dict[str, Any]], embed_field: str = "", embed_text=None) -> Tuple[int, int, List[str]]:
    """Idempotent write by the table's key. embed_field: the row column to embed ('' = no vector). Returns (inserted, updated, degraded)."""
    rows = [normalise(table, r) for r in rows]
    if not rows:
        return 0, 0, []
    _ensure_text(st, table)
    degraded: List[str] = []
    if embed_field and "vector" in S.SCHEMAS[table].names:
        need = [i for i, r in enumerate(rows) if r.get("vector") is None]
        texts = [(embed_text(rows[i]) if embed_text else rows[i].get(embed_field, "")) or "" for i in need]
        vecs = st.embed.embed(texts, "document") if need else []
        for i, v in zip(need, vecs):
            if v is not None and any(v):
                rows[i]["vector"], rows[i]["embedder_id"] = v, st.embed.id
        if need and any(rows[i]["vector"] is None for i in need):
            degraded.append("embedder_down")
    key = S.KEYS[table]
    dedup: Dict[str, Dict[str, Any]] = {r[key]: r for r in rows}          # one row per key in a batch (the last wins): merge_insert rejects ambiguous matches
    rows = list(dedup.values())
    tbl = pa.Table.from_pylist(rows, schema=S.SCHEMAS[table])
    t = st.table(table)
    try:
        res = t.merge_insert(key).when_matched_update_all().when_not_matched_insert_all().execute(tbl)
        ins, upd = int(res.num_inserted_rows), int(res.num_updated_rows)
    except Exception:
        ids = ", ".join(q(r[key]) for r in rows)
        t.delete(f"{key} IN ({ids})")
        t.add(tbl)
        ins, upd = len(rows), 0
    st.text.put(table, [_slim(r) for r in rows], key, S.FTS_TEXT[table])
    st.meta[f"writes:{table}"] = int(st.meta.get(f"writes:{table}", 0)) + 1
    maintain(st, table)
    return ins, upd, degraded


# ---- search -----------------------------------------------------------------------------------------------------------------------------------------
def _apps(app_key: AppKeys) -> List[str]:
    if not app_key:
        return []
    return [app_key] if isinstance(app_key, str) else list(app_key)


def where_app(app_key: AppKeys, extra: str = "") -> str:
    apps = _apps(app_key)
    w = ""
    if len(apps) == 1:
        w = f"app_key = {q(apps[0])}"
    elif apps:
        w = f"app_key IN ({', '.join(q(a) for a in apps)})"
    if extra:
        w = f"({w}) AND ({extra})" if w else extra
    return w


def rrf(lists: Sequence[Sequence[Dict[str, Any]]], key: str, k: int = C.RRF_K) -> List[Dict[str, Any]]:
    score: Dict[str, float] = {}
    keep: Dict[str, Dict[str, Any]] = {}
    for lst in lists:
        for rank, r in enumerate(lst):
            score[r[key]] = score.get(r[key], 0.0) + 1.0 / (k + rank + 1)
            keep.setdefault(r[key], r)
    out = []
    for kid, s in sorted(score.items(), key=lambda kv: -kv[1]):
        r = dict(keep[kid])
        r["_rrf"] = s
        out.append(r)
    return out


def search(st, table: str, text: str, app_key: AppKeys = "", where: str = "", limit: int = 10, use_vector: bool = True, vec_text: str = "") -> List[Dict[str, Any]]:
    """App-prefiltered hybrid search -> rows with _rrf. Legs: FTS5 (lexical), vector (active embedder only), in parallel. `where` (Lance SQL) applies to the vector leg only."""
    if st.count(table) == 0:
        return []
    _ensure_text(st, table)
    key = S.KEYS[table]
    apps = _apps(app_key)
    jobs: List[Any] = []
    terms = terms_of(text)
    if terms:
        jobs.append(lambda: st.text.search(table, terms, apps, limit * 3))
    if use_vector and "vector" in S.SCHEMAS[table].names:
        qv = st.embed.embed_one(vec_text or text, "query")
        if qv is not None and any(qv):
            def vec_leg():
                wv = where_app(apps, f"embedder_id = {q(st.embed.id)}" + (f" AND ({where})" if where else ""))
                s = st.table(table).search(qv).distance_type("cosine").select(_cols(table) + ["_distance"]).where(wv, prefilter=True).limit(limit * 3)
                return [r for r in s.to_list() if r.get("_distance", 0.0) <= C.VEC_MAX_DISTANCE]
            jobs.append(vec_leg)

    def run(fn):
        try:
            return fn()
        except Exception:
            return []
    legs = list(_POOL.map(run, jobs)) if len(jobs) > 1 else [run(j) for j in jobs]
    legs = [l for l in legs if l]
    if not legs:
        return []
    return rrf(legs, key)[:limit]


def fetch(st, table: str, where: str, limit: int = 1000, columns: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Rows matching `where` (Lance SQL). Pass `columns` whenever the vectors are not needed: a row with a 768-d vector is ~3 KB, and 20k of them is seconds."""
    if st.count(table) == 0:
        return []
    q_ = st.table(table).search()
    if where:
        q_ = q_.where(where)
    if columns:
        q_ = q_.select(list(columns))
    return q_.limit(limit).to_list()


def update(st, table: str, where: str, values: Dict[str, Any]) -> int:
    """Change STATIC columns of the matching rows by re-merging the full rows (rare: ingest-time corrections). Mutable learning state belongs in learn.db, not here."""
    rows = fetch(st, table, where, 10000)
    if not rows:
        return 0
    for r in rows:
        r.update(values)
        for k in ("_distance", "_score", "_relevance_score", "_rowid", "_rrf"):
            r.pop(k, None)
    key = S.KEYS[table]
    pa_rows = [normalise(table, r) for r in rows]
    st.table(table).merge_insert(key).when_matched_update_all().when_not_matched_insert_all().execute(pa.Table.from_pylist(pa_rows, schema=S.SCHEMAS[table]))
    st.text.put(table, [_slim(r) for r in pa_rows], key, S.FTS_TEXT[table])
    return len(rows)


def drop_app(st, table: str, app_key: str) -> int:
    n = st.table(table).count_rows(where_app(app_key)) if st.count(table) else 0
    if n:
        st.table(table).delete(where_app(app_key))
    st.text.delete_app(table, app_key)
    return int(n)
