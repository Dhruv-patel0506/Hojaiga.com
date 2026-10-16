"""
harvest.bridge -- harvested data -> the federated RAG (rag/). Idempotent: ids are content hashes, so re-running changes nothing.

    ingest_transcripts(rag, root)   transcripts_json/*.json (+ sheet 2 for titles) -> Sub-RAG 3 chunks and procedures, grounded against the app's Lexicon
    ingest_hotkeys(rag, rows)       sheet 3 / JSONL -> Sub-RAG 4 hotkey / chord_seq rows (trust by source: seed -> seed, web_table -> web, llm -> llm; never verified); seed / web actions also
                                    register low-trust commands in the Lexicon, model-written ones never do
    ingest_macros(rag, rows)        sheet 4 / JSONL -> Sub-RAG 4 script / com / cli rows with a params schema inferred from the template's {slots}; sandbox = scripting_route
    ingest_all(rag, root)           everything under <root>, in that order, returning one report

Table names in the RAG are knowledge_chunks / procedures / fast_paths (not the brief's workflow_knowledge / fast_execution): one schema serves every source.
A hotkey row gets a command_id when the app's Lexicon knows the action, or registers it (seed / published-table rows only); model-written rows are stored matched by their task text alone.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from .free_master_harvester import app_key_of
from .paths import harvest_dir, workbook_path

_SLOT = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_PATH_HINT = re.compile(r"(path|file|dwg|scr|folder|dir|output|input|script)", re.I)
_NUM_HINT = re.compile(r"(size|count|width|depth|height|radius|length|distance|angle|row|col|segments|number|amount|scale|units|width|bevel)", re.I)
SOURCE_TRUST = {"seed": "seed", "web_table": "web", "tldr": "seed", "llm": "llm", "keymap_file": "catalog"}
KIND_OF_EXEC = {"headless_python_bpy": "script", "autocad_script_scr": "script", "win32_com_automation": "com", "websocket_and_cli": "cli", "cli_command": "cli"}


def infer_schema(*templates: str) -> Dict[str, Dict[str, Any]]:
    """{slot: {type, required}} from the {slots} a template contains: names that look like paths are paths, quantities are numbers, the rest short strings."""
    schema: Dict[str, Dict[str, Any]] = {}
    for t in templates:
        for s in _SLOT.findall(t or ""):
            schema[s] = {"type": "path" if _PATH_HINT.search(s) else "number" if _NUM_HINT.search(s) else "string", "required": True}
    return schema


def norm_keys(shortcut: str) -> tuple:
    """('hotkey' | 'chord_seq', payload) from a human shortcut: 'Ctrl + B' -> hotkey 'ctrl+b'; 'G then Z then {distance}' / 'L + Enter' sequences -> chord_seq 'g z {distance}'."""
    s = re.sub(r"\s+", " ", str(shortcut).strip())
    if re.search(r"\bthen\b|→|->", s, re.I):
        parts = [p.strip().lower().replace(" ", "") for p in re.split(r"\bthen\b|→|->", s, flags=re.I) if p.strip()]
        return "chord_seq", " ".join(parts)
    low = s.lower().replace(" + ", "+").replace(" +", "+").replace("+ ", "+")
    if re.fullmatch(r"[a-z]{1,6}(\+enter)", low):                       # 'L + Enter' typed commands
        return "chord_seq", low.replace("+", " ")
    return "hotkey", low.replace(" ", "")


def _app_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        name = str(r.get("app_name") or "").strip()
        if name:
            by.setdefault(app_key_of(name), []).append(r)
    return by


def ingest_hotkeys(rag, rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    out = {"rows": 0, "with_command": 0}
    recs = []
    for app, items in _app_rows(rows).items():
        for r in items:
            shortcut, action = str(r.get("shortcut") or "").strip(), str(r.get("action") or "").strip()
            if not shortcut or not action:
                continue
            kind, payload = norm_keys(shortcut)
            hit = rag.lex.best(app, action)
            src = str(r.get("source") or "seed")
            created = False
            if not hit and src in ("seed", "web_table", "keymap_file"):
                # a published shortcut table IS a list of the application's commands: register the action (low trust, so a learned/catalog name always outranks it) so spoken steps can ground to it.
                # Model-written rows never create commands.
                cid = rag.lex.add_command(app, action, source="hotkey_table", trust=SOURCE_TRUST.get(src, "seed"))
                hit, created = rag.lex.best(app, action), True
                out["commands_created"] = out.get("commands_created", 0) + 1
            rec = {"app_key": app, "kind": kind, "command_id": hit.command_id if hit else "", "task_pattern": action, "payload": payload, "source": src, "trust": SOURCE_TRUST.get(src, "seed"),
                   "verified": False, "context": str(r.get("category") or ""), "params_schema_json": infer_schema(payload)}
            recs.append(rec)
            out["with_command"] += 1 if hit else 0
    out["rows"] = len(recs)
    if recs:
        rep = rag.fast.upsert(recs)
        out["inserted"], out["updated"] = rep.inserted, rep.updated
    return out


def ingest_macros(rag, rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    out = {"rows": 0}
    recs = []
    for app, items in _app_rows(rows).items():
        for r in items:
            tpl, task = str(r.get("code_template") or "").strip(), str(r.get("task_pattern") or "").strip()
            if not tpl or not task:
                continue
            kind = KIND_OF_EXEC.get(str(r.get("execution_type") or "").lower(), "cli")
            src = str(r.get("source") or "seed")
            recs.append({"app_key": app, "kind": kind, "task_pattern": task, "payload": tpl, "source": src, "trust": SOURCE_TRUST.get(src, "seed"), "verified": False,
                         "context": str(r.get("execution_type") or ""), "params_schema_json": infer_schema(tpl),
                         "extra_json": json.dumps({"cli_trigger": str(r.get("cli_trigger") or ""), "tier": r.get("tier")})})
    out["rows"] = len(recs)
    if recs:
        rep = rag.fast.upsert(recs)
        out["inserted"], out["updated"] = rep.inserted, rep.updated
    return out


def _sheet(root: str, name: str) -> List[Dict[str, Any]]:
    path = workbook_path(root)
    if not os.path.isfile(path):
        return []
    import pandas as pd
    try:
        return pd.read_excel(path, sheet_name=name).fillna("").to_dict("records")
    except Exception:
        return []


def ingest_transcripts(rag, root: str = "", build_procedures: bool = True) -> Dict[str, Any]:
    root = root or harvest_dir()[0]
    titles = {(str(r.get("app_key")), str(r.get("video_id"))): r for r in _sheet(root, "2_YouTube_And_Transcripts")}
    out = {"files": 0, "chunks": 0, "skipped": 0}
    for path in sorted(glob.glob(os.path.join(root, "transcripts_json", "*.json"))):
        base = os.path.basename(path)[:-5]
        if "__" not in base:
            out["skipped"] += 1
            continue
        app, vid = base.split("__", 1)
        try:
            segs = json.load(open(path, encoding="utf-8"))
        except Exception:
            out["skipped"] += 1
            continue
        title = str(titles.get((app, vid), {}).get("title", "")) or vid
        rep = rag.proc.ingest_transcript(app, segs, vid, title, caption="auto_caption", build_procedures=build_procedures)
        out["files"] += 1
        out["chunks"] += rep.inserted + rep.updated
    return out


def _jsonl(root: str) -> List[Dict[str, Any]]:
    p = os.path.join(root, "sub_rag4_hotkeys_and_macros.jsonl")
    if not os.path.isfile(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def audit_topics(rag=None, root: str = "", fix: bool = False) -> Dict[str, Any]:
    """Re-judge every harvested transcript with the on-topic gate. With fix=True: quarantine the off-topic files and (when `rag` is given) remove their chunks/procedures from the store."""
    from .free_master_harvester import on_topic
    root = root or harvest_dir()[0]
    rows = {(str(r.get("app_key")), str(r.get("video_id"))): r for r in _sheet(root, "2_YouTube_And_Transcripts")}
    names = {str(r.get("app_key")): str(r.get("app_name")) for r in _sheet(root, "1_Master_1000_Apps")}
    out = {"checked": 0, "off_topic": [], "removed_chunks": 0}
    for path in sorted(glob.glob(os.path.join(root, "transcripts_json", "*.json"))):
        base = os.path.basename(path)[:-5]
        if "__" not in base:
            continue
        app, vid = base.split("__", 1)
        try:
            body = " ".join(s.get("text", "") for s in json.load(open(path, encoding="utf-8")))
        except Exception:
            continue
        out["checked"] += 1
        title = str(rows.get((app, vid), {}).get("title", ""))
        if not on_topic(names.get(app, app.replace("_", " ")), title, body):
            out["off_topic"].append({"app": app, "video_id": vid, "title": title})
            if fix:
                off = os.path.join(root, "transcripts_json", "_off_topic")
                os.makedirs(off, exist_ok=True)
                os.replace(path, os.path.join(off, os.path.basename(path)))
                if rag is not None:
                    out["removed_chunks"] += rag.proc.forget_source(app, vid)
    return out


def ingest_all(rag, root: str = "") -> Dict[str, Any]:
    root = root or harvest_dir()[0]
    hot = _sheet(root, "3_Hotkeys_Matrix")
    mac = _sheet(root, "4_Superhuman_Macros_CLI")
    if not hot and not mac:                                    # no workbook: the JSONL export carries the same rows
        rows = _jsonl(root)
        hot = [r for r in rows if r.get("rag_sub_table") == "sub_rag4_hotkeys"]
        mac = [r for r in rows if r.get("rag_sub_table") == "sub_rag4_superhuman_macros"]
    # hotkeys and macros first: they register the commands that spoken steps in the transcripts then ground to
    report = {"hotkeys": ingest_hotkeys(rag, hot), "macros": ingest_macros(rag, mac)}
    report["transcripts"] = ingest_transcripts(rag, root)
    try:
        from core_organs.rag import tools
        report["maintain"] = tools.maintain(rag, ann=False)           # the ANN build is minutes long: an explicit step (rag.tools.build_ann)
    except Exception as exc:
        report["maintain"] = {"error": f"{type(exc).__name__}"}
    return report
