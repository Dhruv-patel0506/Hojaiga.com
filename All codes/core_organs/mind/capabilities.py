"""
capabilities -- what an app CAN do, read from what the scanners found in it (the lexicon), grouped into the kinds of operation a job is made of.

    coverage("blender_3d")            -> {'draw': {'n': 12, 'examples': [...]}, 'table': {'n': 0}, ...}
    can_do("webapp:notion.so", "document")   -> {'ok': False, 'have': [...], 'missing': ['structure'], 'how': {...}}
    matrix()                          -> every app x every operation class (counts) - and the gaps the next scan should aim at
    python -m core_organs.mind.capabilities [matrix | app <key> | job <kind>]

The classes are about words, not apps: drawing, selecting, transforming, colouring, text, tables, text formatting, document structure, inserting, files, editing, reviewing, automating, communicating, searching.
A job (workflow.skeleton's kind) needs some of them; an app that lacks one is reported as missing it, so the gap is a to-do for the scanner, not a surprise during a task.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Sequence

LEXICON = os.environ.get("HOJAIGA_LEXICON", r"D:\new_automation\data\ai_root\rag\lexicon.db")

OPS: Dict[str, str] = {
    "draw": r"shape|line|pencil|pen|brush|rectangle|ellipse|circle|polygon|curve|eraser|sketch|stroke|arc|bezier|spline|extrude|bevel|primitive|mesh|vertex|vertices|edge|sculpt|paint",
    "select": r"select|selection|lasso|marquee|deselect|pick|highlight",
    "transform": r"move|rotate|scale|resize|flip|crop|align|distribute|group|ungroup|arrange|transform|mirror|translate|snap|bring to front|send to back",
    "colour": r"colou?r|fill|palette|shade|opacity|gradient|swatch|hue|saturation|brightness|contrast",
    "text": r"text|font|label|caption|annotate|annotation|typography|wordart",
    "table": r"table|row|rows|column|columns|cell|cells|merge|sort|pivot|chart|formula|sum|average|spreadsheet|sheet|filter",
    "format_text": r"bold|italic|underline|strikethrough|font size|heading|style|styles|align|bullet|bullets|numbering|numbered|indent|line spacing|paragraph|superscript|subscript",
    "structure": r"outline|page break|section|contents|table of contents|header|footer|page number|layout|template|slide|master|margin|orientation|columns|navigation pane|bookmark",
    "insert": r"insert|add|image|picture|photo|link|hyperlink|comment|attach|embed|upload",
    "file": r"save|save as|open|new|export|import|print|share|download|close|rename|duplicate|pdf",
    "edit": r"undo|redo|copy|paste|cut|delete|remove|find|replace|duplicate|clear",
    "review": r"spell|spelling|proofread|grammar|track changes|review|preview|zoom|compare|check",
    "automate": r"macro|record|script|batch|automation|automate|shortcut|workflow|schedule|trigger|zap|api|webhook|template",
    "communicate": r"send|reply|compose|message|mail|email|post|publish|share|invite|chat|call|meeting|comment",
    "search_nav": r"search|find|navigate|go to|browse|menu|home|back|forward|tab|next|previous",
}
_RX = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in OPS.items()}

# what a job is made of (workflow.skeleton kinds)
JOBS: Dict[str, Sequence[str]] = {
    "document": ("structure", "format_text", "insert", "file", "edit", "review"),
    "table": ("table", "format_text", "file", "edit"),
    "drawing": ("draw", "select", "transform", "colour", "file", "edit"),
    "email": ("communicate", "edit", "file"),
    "post": ("communicate", "insert", "format_text"),
    "form": ("search_nav", "edit"),
    "research": ("search_nav", "file"),
    "general": ("search_nav",),
}


def _db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{LEXICON}?mode=ro", uri=True)


def classes_of(label: str) -> List[str]:
    return [k for k, rx in _RX.items() if rx.search(label or "")]


def _labels(app_key: str, db: Optional[sqlite3.Connection] = None) -> List[str]:
    own = db is None
    db = db or _db()
    try:
        return [r[0] for r in db.execute("SELECT label FROM commands WHERE app_key=?", (app_key,))]
    finally:
        if own:
            db.close()


def coverage(app_key: str, labels: Optional[Sequence[str]] = None, examples: int = 5) -> Dict[str, Dict[str, Any]]:
    labs = list(labels) if labels is not None else _labels(app_key)
    out: Dict[str, Dict[str, Any]] = {k: {"n": 0, "examples": []} for k in OPS}
    for lab in labs:
        for k in classes_of(lab):
            out[k]["n"] += 1
            if len(out[k]["examples"]) < examples:
                out[k]["examples"].append(lab[:70])
    return out


def can_do(app_key: str, kind: str, labels: Optional[Sequence[str]] = None, need: int = 1) -> Dict[str, Any]:
    cov = coverage(app_key, labels)
    want = JOBS.get(kind, JOBS["general"])
    have = [c for c in want if cov[c]["n"] >= need]
    missing = [c for c in want if cov[c]["n"] < need]
    return {"app": app_key, "job": kind, "ok": not missing, "have": have, "missing": missing, "how": {c: cov[c]["examples"][:3] for c in have}}


def matrix(min_commands: int = 20) -> Dict[str, Any]:
    db = _db()
    try:
        apps = [r[0] for r in db.execute("SELECT app_key FROM commands GROUP BY app_key HAVING COUNT(*) >= ?", (min_commands,))]
        rows = {a: coverage(a, _labels(a, db)) for a in apps}
    finally:
        db.close()
    jobs = {k: sorted(a for a in apps if all(rows[a][c]["n"] >= 1 for c in need)) for k, need in JOBS.items()}
    gaps = collections.Counter(c for a in apps for c in OPS if rows[a][c]["n"] == 0)
    return {"apps": len(apps), "by_class_apps_with_it": {c: sum(1 for a in apps if rows[a][c]["n"] >= 1) for c in OPS}, "jobs_apps_that_can": {k: len(v) for k, v in jobs.items()},
            "jobs_examples": {k: v[:6] for k, v in jobs.items()}, "class_gaps_by_count": dict(gaps)}


def best_for(kind: str, top: int = 8, min_commands: int = 20) -> List[Dict[str, Any]]:
    """Apps ranked by how much of a job's operation classes they cover (then by how many commands were found): where to start, and what each is missing."""
    db = _db()
    try:
        apps = [r[0] for r in db.execute("SELECT app_key FROM commands GROUP BY app_key HAVING COUNT(*) >= ?", (min_commands,))]
        out = [can_do(a, kind, _labels(a, db)) for a in apps]
    finally:
        db.close()
    want = len(JOBS.get(kind, JOBS["general"]))
    out.sort(key=lambda d: (-len(d["have"]), len(d["missing"])))
    for d in out:
        d["covers"] = f"{len(d['have'])}/{want}"
    return out[:top]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["matrix", "app", "job"])
    ap.add_argument("arg", nargs="?", default="")
    a = ap.parse_args(argv)
    import json
    if a.cmd == "matrix":
        print(json.dumps(matrix(), indent=1))
    elif a.cmd == "app":
        print(json.dumps(coverage(a.arg), indent=1))
    else:
        print(json.dumps([{"app": d["app"], "covers": d["covers"], "missing": d["missing"]} for d in best_for(a.arg)], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
