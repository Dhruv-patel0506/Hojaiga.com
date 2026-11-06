# brain/conveyor/ingest_clean.py
"""Belt stations 1–2: data injection (read anything) and data cleaning (make it trustworthy)."""
import csv
import html
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

TEXT_EXTS = {".txt", ".md", ".rst", ".html", ".htm", ".xml", ".tex", ".log", ".py", ".js", ".ts", ".java",
             ".c", ".cpp", ".cs", ".go", ".sql", ".yaml", ".yml", ".srt", ".vtt"}
RECORD_EXTS = {".json", ".jsonl", ".csv", ".tsv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".gif", ".mp4", ".mov", ".avi", ".mkv", ".webm"}


@dataclass
class Item:
    """One unit on the belt. `text` is what language stations see; `record` keeps structured fields;
    `media` is an image/video path; `label` is filled in by label discovery."""
    item_id: str
    source: str
    modality: str                       # text | record | image | video
    text: str = ""
    record: Dict[str, Any] = field(default_factory=dict)
    media: Optional[str] = None
    label: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────── station 1: injection
def _read_records(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    ext = path.suffix.lower()
    if ext == ".jsonl":
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    v = json.loads(line)
                    out.append(v if isinstance(v, dict) else {"value": v})
                except json.JSONDecodeError:
                    continue
        return out
    if ext == ".json":
        try:
            v = json.loads(raw)
        except json.JSONDecodeError:
            return [{"text": raw}]
        if isinstance(v, list):
            return [x if isinstance(x, dict) else {"value": x} for x in v]
        return [v] if isinstance(v, dict) else [{"value": v}]
    return [dict(r) for r in csv.DictReader(io.StringIO(raw), delimiter="\t" if ext == ".tsv" else ",")]


def ingest_folder(paths: List[str]) -> Tuple[List[Item], Dict[str, Any]]:
    """Walk files/folders and turn everything into Items. Nothing is interpreted yet."""
    items: List[Item] = []
    report: Dict[str, Any] = {"files": 0, "by_modality": {}, "unreadable": []}
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for f in files:
            if any(part.startswith(".") for part in f.relative_to(root.parent if root.is_file() else root).parts):
                continue
            ext = f.suffix.lower()
            try:
                if ext in IMAGE_EXTS:
                    items.append(Item(f"{f}", str(f), "image", media=str(f), meta={"folder": f.parent.name}))
                elif ext in VIDEO_EXTS:
                    items.append(Item(f"{f}", str(f), "video", media=str(f), meta={"folder": f.parent.name}))
                elif ext in RECORD_EXTS:
                    for i, rec in enumerate(_read_records(f)):
                        items.append(Item(f"{f}#{i}", str(f), "record", record=rec))
                elif ext in TEXT_EXTS or not ext:
                    raw = f.read_text(encoding="utf-8", errors="ignore")
                    if ext in (".html", ".htm", ".xml"):
                        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
                        raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
                    for i, para in enumerate(p for p in re.split(r"\n\s*\n", raw) if p.strip()):
                        items.append(Item(f"{f}#p{i}", str(f), "text", text=para, meta={"folder": f.parent.name}))
                else:
                    continue
                report["files"] += 1
            except Exception as exc:                      # a broken file never stops the belt
                report["unreadable"].append(f"{f.name}: {exc}")
    for it in items:
        report["by_modality"][it.modality] = report["by_modality"].get(it.modality, 0) + 1
    report["items"] = len(items)
    return items, report


# ─────────────────────────────────────────────────────────────── station 2: cleaning
def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)


def _record_text(rec: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """The record's prose = its longest string field (if it clearly dominates); the rest are fields."""
    strings = {k: v for k, v in rec.items() if isinstance(v, str) and v.strip()}
    if not strings:
        return "", rec
    longest = max(strings, key=lambda k: len(strings[k]))
    others = sum(len(v) for k, v in strings.items() if k != longest)
    if len(strings[longest].split()) >= 4 and len(strings[longest]) >= others:
        return strings[longest], {k: v for k, v in rec.items() if k != longest}
    return " | ".join(f"{k}: {v}" for k, v in strings.items()), {}


def clean_items(items: List[Item], l1) -> Tuple[List[Item], Dict[str, Any]]:
    """Normalise, strip markup, redact secrets (L1 entropy test), drop junk and near-duplicates
    (L1 SimHash), verify images open. Every drop is counted by reason."""
    dropped: Dict[str, int] = {}
    kept: List[Item] = []
    seen: List[int] = []

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for it in items:
        if it.modality in ("text", "record"):
            if it.modality == "record":
                it.record = _json_safe({k: v for k, v in it.record.items() if v not in ("", None, [], {})})
                text, fields = _record_text(it.record)
                it.text, it.meta["fields"] = text, fields
            t = unicodedata.normalize("NFKC", html.unescape(it.text or ""))
            t = re.sub(r"[ \t\r\f\v]+", " ", t)
            t = re.sub(r"\n{3,}", "\n\n", t).strip()
            redacted = l1._redact_statistical_secrets(t)
            if redacted != t:
                it.meta["redacted"] = True
            it.text = redacted
            if len(it.text.split()) < 3 and it.modality == "text":
                drop("too_short")
                continue
            if it.text and l1.shannon_entropy(it.text) < 2.5:
                drop("low_information")
                continue
            if it.text:
                sh = l1.simhash64(it.text)
                if any(bin(sh ^ o).count("1") <= 3 for o in seen):
                    drop("near_duplicate")
                    continue
                seen.append(sh)
            if it.modality == "record" and not it.text and not it.record:
                drop("empty_record")
                continue
        elif it.modality == "image":
            try:
                from PIL import Image
                with Image.open(it.media) as im:
                    im.verify()
                with Image.open(it.media) as im:
                    w, h = im.size
                if min(w, h) < 16:
                    drop("image_too_small")
                    continue
                it.meta["size"] = [w, h]
            except Exception:
                drop("corrupt_image")
                continue
        kept.append(it)
    return kept, {"kept": len(kept), "dropped": dropped,
                  "redacted_items": sum(1 for i in kept if i.meta.get("redacted"))}


def load_image(path: str, max_side: int = 512) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        return np.array(im)


def load_video(path: str, frames: int = 16) -> Optional[np.ndarray]:
    p = Path(path)
    out: List[np.ndarray] = []
    if p.suffix.lower() == ".gif":
        from PIL import Image, ImageSequence
        with Image.open(p) as im:
            out = [np.array(f.convert("RGB")) for f in ImageSequence.Iterator(im)][:frames]
    else:
        try:
            import cv2
        except ImportError:
            return None
        cap = cv2.VideoCapture(str(p))
        while len(out) < frames:
            ok, fr = cap.read()
            if not ok:
                break
            out.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        cap.release()
    return np.stack(out) if out else None
