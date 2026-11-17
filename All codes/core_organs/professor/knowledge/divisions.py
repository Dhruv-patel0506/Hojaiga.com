"""
professor.knowledge.divisions -- the Hojaiga sub-division frame applied to any repository.

classify(path, text_hint)  -> (division_id, score, runner_up)   path segments weigh most, then identifiers found in the file
summarize(rows)            -> per-division file / symbol counts for a repo, in the frame's fixed order
The classifier is a transparent keyword scorer (data/divisions.json), not a model: the same repository always lands in the same divisions, and the
reason is inspectable (`why`). Files that match nothing stay `unclassified` rather than being forced into a division.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import config as CFG

_CACHE: Dict[str, Any] = {}
_SPLIT = re.compile(r"[^a-z0-9]+")
GENERATED = os.path.join(CFG.DATA_DIR, "divisions.generated.json")      # written by adopt_document(): the user's own document wins over the built-in seven


def load() -> List[Dict[str, Any]]:
    """The divisions in force: the user's adopted 'sub-divisions' document when one was adopted, else the built-in seven (data/divisions.json)."""
    if "divs" not in _CACHE:
        for path in (os.environ.get("HOJAIGA_DIVISIONS_FILE", ""), GENERATED, CFG.DIVISIONS_FILE):
            if path and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        _CACHE["divs"] = json.load(fh)["divisions"]
                    _CACHE["from"] = path
                    break
                except Exception:
                    continue
        else:
            _CACHE["divs"] = []
    return _CACHE["divs"]


def reload() -> None:
    _CACHE.clear()


def source_in_use() -> str:
    load()
    return _CACHE.get("from", "")


# --------------------------------------------------------------------------------------------- the user's own document
_WANT = "subdivisionsofhojaigasystem"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_subdivisions_file(extra_dirs: Sequence[str] = (), max_depth: int = 3) -> str:
    """Look for a file named like 'sub-divisions of hojaiga system ' (any case, hyphens/spaces/trailing space ignored, any extension) in the project, the
    architecture folders and the user's Downloads / Documents / Desktop / OneDrive. Returns its path or ''."""
    home = os.path.expanduser("~")
    roots = [CFG.ROOT, os.path.join(CFG.ROOT, "extra MD files"), CFG.ARCHITECTURE_STANDARDS_DIR, os.path.join(home, "Downloads"), os.path.join(home, "Documents"),
             os.path.join(home, "Desktop"), os.path.join(home, "OneDrive"), *extra_dirs]
    skip = {"hojaiga_env", "venv", "node_modules", ".git", "__pycache__", "site-packages", "AppData", "scratch", "data"}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        base_depth = root.rstrip("\\/").count(os.sep)
        for cur, dirs, files in os.walk(root):
            if cur.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
            for f in files:
                stem = _norm(os.path.splitext(f)[0])
                if stem.startswith(_WANT) or (stem and "subdivision" in stem and "hojaiga" in stem):
                    return os.path.join(cur, f)
    return ""


_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.*\S)")


def parse_document(path: str) -> List[Dict[str, Any]]:
    """Divisions from a document: the heading level that has the most siblings (>= 3) names the divisions; bullets / sub-headings under each are its organs;
    the content words of heading + bullets become the classifier's signals. Returns [] when no such structure is found."""
    from .manual_rag import read_text
    text, _kind = read_text(path)
    heads: List[Tuple[int, str, int]] = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,4})\s+(.*\S)", ln)
        if m:
            heads.append((len(m.group(1)), re.sub(r"[*_`]+", "", m.group(2)).strip(), i))
    if not heads:
        return []
    counts: Dict[int, int] = {}
    for lvl, _h, _i in heads:
        counts[lvl] = counts.get(lvl, 0) + 1
    cand = [l for l, c in counts.items() if c >= 3]
    if not cand:
        return []
    level = min(cand)
    tops = [(h, i) for lvl, h, i in heads if lvl == level]
    out: List[Dict[str, Any]] = []
    stop = {"the", "and", "of", "for", "to", "in", "a", "an", "is", "are", "with", "layer", "division", "organ", "system", "hojaiga"}
    for n, (title, start) in enumerate(tops):
        end = tops[n + 1][1] if n + 1 < len(tops) else len(lines)
        body = lines[start + 1:end]
        organs = [m.group(1).strip() for ln in body for m in [_BULLET.match(ln)] if m][:12]
        organs += [h for lvl, h, i in heads if start < i < end and lvl == level + 1][:8]
        words: Dict[str, int] = {}
        for w in _SPLIT.split((title + " " + " ".join(organs) + " " + " ".join(body[:40])).lower()):
            if len(w) >= 3 and w not in stop:
                words[w] = words.get(w, 0) + 1
        sig = [w for w, _c in sorted(words.items(), key=lambda kv: -kv[1])][:24]
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or f"division_{n}"
        out.append({"id": slug, "name": re.sub(r"^\W*(\d+[.)]?\s*)?", "", title), "organs": organs, "role": " ".join(body[:2])[:160].strip(), "signals": sig})
    return out if len(out) >= 3 else []


def adopt_document(path: str = "") -> Dict[str, Any]:
    """Parse the user's sub-divisions document (found automatically when no path is given) and make it THE frame for every later classification."""
    path = path or find_subdivisions_file()
    if not path:
        return {"ok": False, "error": "no file named like 'sub-divisions of hojaiga system' found (searched project, architecture folders, Downloads, Documents, Desktop, OneDrive)",
                "in_use": source_in_use() or "built-in seven layers"}
    try:
        divs = parse_document(path)
    except Exception as exc:
        return {"ok": False, "path": path, "error": f"{type(exc).__name__}: {exc}"}
    if not divs:
        return {"ok": False, "path": path, "error": "document has no recognisable division headings (need >= 3 headings at one level)"}
    os.makedirs(os.path.dirname(GENERATED), exist_ok=True)
    with open(GENERATED, "w", encoding="utf-8") as fh:
        json.dump({"source": path, "divisions": divs}, fh, indent=1, ensure_ascii=False)
    reload()
    return {"ok": True, "path": path, "divisions": [d["name"] for d in divs], "written": GENERATED}


def _tokens(text: str) -> List[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [t for t in _SPLIT.split(text.lower()) if t]


def classify(path: str, text_hint: str = "") -> Tuple[str, float, str, List[str]]:
    """(division id | 'unclassified', score, runner-up id, matched signals). Path tokens count 3x, identifier tokens 1x."""
    divs = load()
    ptoks = _tokens(path)
    ttoks = _tokens(text_hint[:4000]) if text_hint else []
    scores: List[Tuple[float, str, List[str]]] = []
    for d in divs:
        sig = set(d["signals"])
        hit_p = [t for t in ptoks if t in sig or any(len(s) > 4 and t.startswith(s) for s in sig)]
        hit_t = [t for t in ttoks if t in sig]
        s = 3.0 * len(hit_p) + min(6, len(hit_t)) * 1.0
        scores.append((s, d["id"], sorted(set(hit_p + hit_t))[:6]))
    scores.sort(reverse=True)
    if not scores or scores[0][0] <= 0:
        return "unclassified", 0.0, "", []
    best = scores[0]
    return best[1], round(best[0], 1), (scores[1][1] if len(scores) > 1 and scores[1][0] > 0 else ""), best[2]


def names() -> Dict[str, str]:
    return {d["id"]: d["name"] for d in load()}


def summarize(rows: Iterable[Tuple[str, int]]) -> List[Dict[str, Any]]:
    """rows = (division_id, n) -> ordered list with names and roles."""
    tally: Dict[str, int] = {}
    for div, n in rows:
        tally[div] = tally.get(div, 0) + n
    out = []
    for d in load():
        out.append({"id": d["id"], "name": d["name"], "organs": d["organs"], "role": d["role"], "files": tally.get(d["id"], 0)})
    if tally.get("unclassified"):
        out.append({"id": "unclassified", "name": "Unclassified", "organs": [], "role": "no signal matched", "files": tally["unclassified"]})
    return out
