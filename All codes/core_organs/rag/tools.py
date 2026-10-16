"""
rag.tools -- maintenance and exchange (DESIGN.md sections 8-10): everything that keeps the RAG healthy without code changes.

    reembed(rag, table=None)           heal NULL vectors and move rows to the ACTIVE embedder (the whole story of an embedder swap)
    rebuild_edges(rag, app)            recompute edge counters from the observation log
    export_pack(rag, app, path)        a PII-scrubbed .hjpack (zip of JSONL): lexicon, graph structure + observations, verified fast paths, playbooks, icon labels
    import_pack(rag, path)             merge by ID; observations appended with source=pack:<origin>; trust capped at 'learned'; counters rebuilt
    merge_roots(src_root, dst_rag)     fold another storage root into this one (via packs), safe because IDs are content hashes / UUIDs and observations are append-only
    self_doc(rag, app, run_id)         documentation WRITTEN FROM GRAPH PATHS (not by a model): an unseen app becomes explainable right after a crawl
    import_manuals(rag, path)          the Professor's manual_rag.sqlite chunks -> Sub-RAG 3
    relocate_icons(rag)                one-time copy of the legacy icon_memory.db into <root>/rag/icons.db
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
import zipfile
from typing import Any, Dict, Iterable, List, Optional

from . import config as C
from . import lt
from . import schemas as S
from .embed import DimensionTooLarge
from .recovery import HUMAN_CLASSES

_EMBED_TEXT = {
    "knowledge_chunks": lambda r: f"{r['heading_path']} :: {r['text']}",
    "procedures": lambda r: r["goal"],
    "fast_paths": lambda r: r["task_pattern"] or r["command_id"],
    "error_playbooks": lambda r: r["message_template"],
    "ui_states": lambda r: r["description"],
}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PATHISH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|users|var|etc)/)", re.I)
PACK_VERSION = 1


def has_pii(text: str) -> bool:
    return bool(text and (_EMAIL.search(text) or _PATHISH.search(text)))


# ---- embeddings -------------------------------------------------------------------------------------------------------------------------------------
def reembed(rag, table: Optional[str] = None, batch: int = 64, max_batches: int = 100000) -> Dict[str, Any]:
    """Give every row of `table` (all vector tables when None) a vector from the ACTIVE embedder. Idempotent; a down embedder stops the job and reports it."""
    st = rag.st
    out: Dict[str, Any] = {}
    active = st.embed.id
    for name in ([table] if table else [t for t, sch in S.SCHEMAS.items() if "vector" in sch.names]):
        done = 0
        err = ""
        for _ in range(max_batches):
            rows = lt.fetch(st, name, f"vector IS NULL OR embedder_id <> {lt.q(active)}", batch)
            if not rows:
                break
            vecs = None
            try:
                vecs = st.embed.embed([_EMBED_TEXT[name](r) or "" for r in rows], "document")
            except DimensionTooLarge as exc:
                err = f"dimension_too_large:{exc}"
                break
            if vecs is None or all(v is None for v in vecs):
                err = "embedder_down"
                break
            changed = 0
            for r, v in zip(rows, vecs):
                if v is not None and any(v):
                    r["vector"], r["embedder_id"] = v, active
                    changed += 1
                else:
                    r["vector"], r["embedder_id"] = None, ""
            for r in rows:
                for k in ("_distance", "_score", "_rowid"):
                    r.pop(k, None)
            pa_rows = [lt.normalise(name, r) for r in rows]
            import pyarrow as pa
            st.table(name).merge_insert(S.KEYS[name]).when_matched_update_all().when_not_matched_insert_all().execute(pa.Table.from_pylist(pa_rows, schema=S.SCHEMAS[name]))
            done += changed
            if changed == 0:
                err = "no_embeddable_rows"
                break
        out[name] = {"re_embedded": done, "error": err}
    return out


def rebuild_edges(rag, app_key: str) -> int:
    return rag.graph.rebuild_edges(app_key)


def build_ann(rag, table: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Build the ANN (IVF_PQ) vector index on every table past config.IVF_PQ_MIN_ROWS (or `table`). Slow (~2 min per 50k rows): run it after bulk ingests, not inline."""
    st = rag.st
    out: Dict[str, Any] = {}
    for name in ([table] if table else [t for t, sch in S.SCHEMAS.items() if "vector" in sch.names]):
        n = st.count(name)
        built = int(st.meta.get(f"ann_rows:{name}", 0))
        if n < C.IVF_PQ_MIN_ROWS and not force:
            out[name] = {"built": False, "rows": n, "why": "below_threshold"}
            continue
        if built and n < built * 2 and not force:
            out[name] = {"built": False, "rows": n, "why": "index_still_fresh"}
            continue
        try:
            st.table(name).create_index(metric="cosine", vector_column_name="vector", num_partitions=max(8, int(n ** 0.5)), num_sub_vectors=96, replace=True)
            st.meta[f"ann_rows:{name}"] = n
            st._save_meta()
            out[name] = {"built": True, "rows": n}
        except Exception as exc:
            out[name] = {"built": False, "rows": n, "why": f"{type(exc).__name__}: {str(exc)[:80]}"}
    return out


def maintain(rag) -> Dict[str, Any]:
    """Everything that should run after a bulk ingest or on a schedule: compaction, text-index consistency, ANN indexes."""
    from . import lt
    st = rag.st
    res: Dict[str, Any] = {"compacted": [], "text_healed": []}
    for name in S.SCHEMAS:
        if st.count(name):
            lt.optimize(st, name)
            res["compacted"].append(name)
            if st.text.count(name) != st.count(name):
                res["text_healed"].append((name, st.text.heal(name, S.KEYS[name], S.FTS_TEXT[name], lt._cols(name))))
    res["ann"] = build_ann(rag)
    return res


# ---- packs ------------------------------------------------------------------------------------------------------------------------------------------
_SAFE_FAST_KINDS = {"hotkey", "chord_seq", "wm_command", "menu_accel"}


def _jl(rows: Iterable[Dict[str, Any]]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) for r in rows)


def export_pack(rag, app_key: str, path: str = "", include: Iterable[str] = ("lexicon", "graph", "fast", "playbooks", "icons")) -> str:
    """A .hjpack for one app. Screenshots, transcripts, document text and user scripts are never included; any row carrying a path or e-mail is dropped, not edited."""
    st = rag.st
    inc = set(include)
    path = path or st.path("exports", "packs", f"{app_key}-{int(time.time())}.hjpack")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    files: Dict[str, str] = {}
    meta = {"pack_version": PACK_VERSION, "app_key": app_key, "origin_uuid": st.meta.get("root_uuid", ""), "created": time.time(), "include": sorted(inc)}
    if "lexicon" in inc:
        files["commands.jsonl"] = _jl(r for r in rag.lex.db.rows("SELECT * FROM commands WHERE app_key=?", (app_key,)) if not has_pii(r["label"]))
        files["aliases.jsonl"] = _jl(r for r in rag.lex.db.rows("SELECT * FROM aliases WHERE app_key=?", (app_key,)) if not has_pii(r["surface_norm"]))
        files["app.json"] = json.dumps(rag.lex.app(app_key))
    if "graph" in inc:
        g = rag.graph.db
        nodes = []
        for n in g.rows("SELECT * FROM nodes WHERE app_key=?", (app_key,)):
            if any(has_pii(k) for k in json.loads(n["landmarks_json"])):
                continue
            for k in ("description", "screenshot_ref", "variants_json"):
                n[k] = "" if k != "variants_json" else "[]"
            nodes.append(n)
        keep = {n["state_id"] for n in nodes}
        files["nodes.jsonl"] = _jl(nodes)
        files["edges.jsonl"] = _jl(e for e in g.rows("SELECT * FROM edges WHERE app_key=?", (app_key,)) if e["src"] in keep and e["dst"] in keep and not has_pii(e["args_json"]))
        files["observations.jsonl"] = _jl(dict(o, args_json="{}", verify_note="") for o in g.rows("SELECT * FROM observations WHERE app_key=?", (app_key,)) if o["src"] in keep)
        files["aliases_states.jsonl"] = _jl(g.rows("SELECT * FROM aliases WHERE state_id IN (SELECT state_id FROM nodes WHERE app_key=?)", (app_key,)))
    if "fast" in inc:
        rows = []
        for r in lt.fetch(st, "fast_paths", lt.where_app(app_key), 100000):
            if r["trust"] != "llm" and r["kind"] in _SAFE_FAST_KINDS and not has_pii(r["payload"]):
                r.pop("vector", None)
                rows.append(r)
        files["fast_paths.jsonl"] = _jl(rows)
    if "playbooks" in inc:
        rows = []
        for r in lt.fetch(st, "error_playbooks", lt.where_app(app_key), 100000):
            r.pop("vector", None)
            if not has_pii(r["message_template"]) and not has_pii(r["resolution_json"]):
                rows.append(r)
        files["error_playbooks.jsonl"] = _jl(rows)
    if "icons" in inc and rag.icons:
        db = rag.icons._db
        rows = [{"fp": bytes(fp).hex(), "label": lab, "source": src, "n": n} for fp, lab, src, n in db.execute("SELECT fp,label,source,n FROM votes WHERE app=?", (app_key,)) if not has_pii(lab)]
        files["icons.jsonl"] = _jl(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.json", json.dumps(meta))
        for name, body in files.items():
            z.writestr(name, body)
    return path


def _rd(z: zipfile.ZipFile, name: str) -> List[Dict[str, Any]]:
    if name not in z.namelist():
        return []
    return [json.loads(l) for l in z.read(name).decode("utf-8").splitlines() if l.strip()]


def _cap(trust: str) -> str:
    return "learned" if C.TRUST_W.get(trust, 0) > C.TRUST_W["learned"] else trust


def import_pack(rag, path: str) -> Dict[str, int]:
    """Merge a pack. Idempotent: importing the same pack twice changes nothing."""
    st = rag.st
    out: Dict[str, int] = {}
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("meta.json"))
        app, origin = meta["app_key"], meta.get("origin_uuid", "")[:12]
        for c in _rd(z, "commands.jsonl"):
            rag.lex.db.execute("INSERT OR IGNORE INTO commands(command_id,app_key,label,archetype) VALUES(?,?,?,?)", (c["command_id"], c["app_key"], c["label"], c.get("archetype", "")))
        for a in _rd(z, "aliases.jsonl"):
            rag.lex.db.execute("INSERT OR IGNORE INTO aliases(app_key,surface_norm,command_id,kind,source,trust,n_seen) VALUES(?,?,?,?,?,?,?)",
                               (a["app_key"], a["surface_norm"], a["command_id"], a["kind"], "pack:" + origin, _cap(a["trust"]), a["n_seen"]))
        if "app.json" in z.namelist():
            ap = json.loads(z.read("app.json"))
            rag.lex.set_app(app, tier=ap.get("tier") if ap.get("tier", -1) >= 0 else None, archetype=ap.get("archetype", ""), version=ap.get("version", ""), toolkit=ap.get("toolkit", ""))
        rag.lex.db.commit()
        rag.lex._idf.pop(app, None)
        st.bump(f"lexicon:{app}")
        gdb = rag.graph.db
        n_nodes = n_edges = n_obs = 0
        with gdb.lock:
            for n in _rd(z, "nodes.jsonl"):
                if not gdb.one("SELECT 1 AS x FROM nodes WHERE state_id=?", (n["state_id"],)):
                    gdb.execute("INSERT INTO nodes(state_id,app_key,app_version,window_kind,modal_stack_json,landmarks_json,variants_json,exact_sig,tier,visits,first_seen,last_seen,screenshot_ref,description)"
                                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (n["state_id"], n["app_key"], n["app_version"], n["window_kind"], n["modal_stack_json"], n["landmarks_json"], "[]", n["exact_sig"],
                                                                         n["tier"], n["visits"], n["first_seen"], n["last_seen"], "", ""))
                    gdb.execute("INSERT OR IGNORE INTO sigs(app_key,sig,state_id) VALUES(?,?,?)", (n["app_key"], n["exact_sig"], n["state_id"]))
                    n_nodes += 1
            for al in _rd(z, "aliases_states.jsonl"):
                gdb.execute("INSERT OR IGNORE INTO aliases(state_id,canonical_id) VALUES(?,?)", (al["state_id"], al["canonical_id"]))
            for e in _rd(z, "edges.jsonl"):
                cur = gdb.execute("INSERT OR IGNORE INTO edges(app_key,src,dst,command_id,action_type,route,args_json,source,trust,safety,last_seen_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                  (e["app_key"], e["src"], e["dst"], e["command_id"], e["action_type"], e["route"], e["args_json"], "pack:" + origin, _cap(e["trust"]), e["safety"], e["last_seen_ts"]))
                n_edges += cur.rowcount
            for o in _rd(z, "observations.jsonl"):
                if not gdb.one("SELECT 1 AS x FROM observations WHERE ts=? AND run_id=? AND src=? AND command_id=? AND route=?", (o["ts"], o["run_id"], o["src"], o["command_id"], o["route"])):
                    gdb.execute("INSERT INTO observations(ts,run_id,app_key,src,command_id,route,args_json,expected_dst,observed_dst,ok,effect,latency_ms,verify_note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (o["ts"], o["run_id"], o["app_key"], o["src"], o["command_id"], o["route"], "{}", o["expected_dst"], o["observed_dst"], o["ok"], o["effect"], o["latency_ms"], "", "pack:" + origin))
                    n_obs += 1
            # document frequencies are an aggregate of the nodes: recompute rather than trust the pack
            gdb.execute("DELETE FROM landmark_df WHERE app_key=?", (app,))
            df: Dict[str, int] = {}
            for r in gdb.rows("SELECT landmarks_json FROM nodes WHERE app_key=?", (app,)):
                for k in json.loads(r["landmarks_json"]):
                    df[k] = df.get(k, 0) + 1
            gdb.executemany("INSERT INTO landmark_df(app_key,landmark,df) VALUES(?,?,?)", [(app, k, v) for k, v in df.items()])
            gdb.commit()
        rag.graph.rebuild_edges(app)
        out.update(nodes=n_nodes, edges=n_edges, observations=n_obs)
        fast = [dict(r, trust=_cap(r["trust"]), verified=False, source="pack:" + origin, n_ok=0, n_fail=0, consecutive_fail=0, ok_runs=[]) for r in _rd(z, "fast_paths.jsonl")]
        for r in fast:
            for k in ("vector", "embedder_id"):
                r.pop(k, None)
        out["fast_paths"] = rag.fast.upsert(fast).inserted + 0 if fast else 0
        # states are searchable by description: rebuild each imported node's handle from its (structural, PII-free) landmarks
        from . import statekey as SK
        for n in _rd(z, "nodes.jsonl"):
            rag.graph._index_state(n["app_key"], n["state_id"], SK.describe_landmarks(n["window_kind"], json.loads(n["landmarks_json"])), "")
        pbs = [dict(r, trust=_cap(r["trust"]), source="pack:" + origin, resolution=json.loads(r["resolution_json"] or "[]"), class_=r["class_"]) for r in _rd(z, "error_playbooks.jsonl")]
        for r in pbs:
            for k in ("vector", "embedder_id", "resolution_json"):
                r.pop(k, None)
        out["playbooks"] = rag.rec.upsert(pbs).inserted + 0 if pbs else 0
        icons = _rd(z, "icons.jsonl")
        if icons and rag.icons:
            for i in icons:
                rag.icons.mem.learn(bytes.fromhex(i["fp"]), i["label"], "knowledge", app)
            out["icons"] = len(icons)
    return out


def merge_roots(src_root: str, dst_rag) -> Dict[str, Any]:
    """Fold another storage root into dst_rag, app by app, through packs."""
    from .router import Rag
    from .storage import Storage
    src = Rag(Storage(src_root, dst_rag.st.embed.embedder), seed=False, icons=dst_rag.icons is not None)
    apps = sorted({r["app_key"] for r in src.lex.db.rows("SELECT app_key FROM commands UNION SELECT app_key FROM apps")} | {r["app_key"] for r in src.graph.db.rows("SELECT DISTINCT app_key FROM nodes")})
    res = {}
    tmp = dst_rag.st.path("exports", "packs")
    for app in apps:
        p = export_pack(src, app, os.path.join(tmp, f"merge-{uuid.uuid4().hex[:8]}.hjpack"))
        res[app] = import_pack(dst_rag, p)
        os.remove(p)
    src.close()
    return res


# ---- documentation from graph paths -----------------------------------------------------------------------------------------------------------------
def self_doc(rag, app_key: str, run_id: str = "", limit: int = 400) -> Dict[str, Any]:
    """Write documentation FROM the graph (observed or mapped edges), never from a model, and ingest it as source_kind=self_doc. Returns the ingest report + sentence count."""
    g = rag.graph
    lines: List[str] = []
    for e in g.db.rows("SELECT * FROM edges WHERE app_key=? AND src<>dst ORDER BY n_ok DESC, last_seen_ts DESC LIMIT ?", (app_key, limit)):
        label = rag.lex.label_of(e["command_id"])
        args = json.loads(e["args_json"] or "{}")
        dst = g.node(e["dst"]) or {}
        title = (dst.get("description") or "").split(" ", 1)[-1][:60] or "another screen"
        if e["route"] == "hotkey" and args.get("keys"):
            do = f"Press {args['keys']} ({label})"
        elif e["route"] == "menu_path" and args.get("path"):
            do = "Open " + " > ".join(args["path"] if isinstance(args["path"], list) else [str(args["path"])])
        else:
            do = f"Click {label}"
        lines.append(f"{do}. This opens {title}.")
    if not lines:
        return {"sentences": 0, "report": None}
    rep = rag.proc.ingest_document(app_key, "# How the interface fits together\n" + "\n".join(lines), f"crawl:{run_id or uuid.uuid4().hex[:8]}", kind="self_doc", title="Interface map", trust="learned")
    return {"sentences": len(lines), "report": rep}


# ---- importers --------------------------------------------------------------------------------------------------------------------------------------
def import_manuals(rag, path: str = "") -> Dict[str, Any]:
    """The Professor's manuals.db (docs + chunks) -> Sub-RAG 3. Idempotent (chunk ids are content hashes)."""
    if not path:
        from core_organs.professor.knowledge.manual_rag import MANUAL_DB
        path = MANUAL_DB
    if not os.path.isfile(path):
        return {"docs": 0, "chunks": 0, "error": "manuals_db_missing"}
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    n_docs = n_chunks = 0
    for d in db.execute("SELECT id, app, title, source, kind FROM docs").fetchall():
        text = "\n\n".join(r["text"] for r in db.execute("SELECT text FROM chunks WHERE doc=? ORDER BY ord", (d["id"],)))
        if not text.strip():
            continue
        rep = rag.proc.ingest_document(d["app"] or "", text, d["source"] or f"doc:{d['id']}", kind="manual", title=d["title"] or "", trust="official_doc", build_procedures=False)
        n_docs += 1
        n_chunks += rep.inserted + rep.updated
    db.close()
    return {"docs": n_docs, "chunks": n_chunks}


def relocate_icons(rag, legacy: str = "") -> bool:
    """Copy the legacy icon_memory.db to <root>/rag/icons.db once (only when the new file is absent). Returns True if copied."""
    dst = rag.st.path("icons.db")
    if not legacy:
        try:
            from core_organs.professor import config as PC
            legacy = PC.ICON_DB
        except Exception:
            return False
    if os.path.isfile(dst) and os.path.getsize(dst) > 0 or not os.path.isfile(legacy):
        return False
    shutil.copy2(legacy, dst)
    return True
