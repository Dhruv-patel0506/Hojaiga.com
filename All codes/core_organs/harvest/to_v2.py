"""
harvest.to_v2 -- the whole training set in ONE prompt format (v2: full picture + zoomed dense-strip crops + control names when known).

A v1 pair carries its element list as text ('#id role "label" [x, y, w, h]') and its picture on disk, which is all prompt_v2 needs to build the zoomed strips; the control NAMES exist only for pairs recorded
with UI Automation, so a converted v1 pair has strips but no `Names:` line. When a pair already has a v2 twin (same pair_id, recorded with names) the twin is used instead. Nothing is app-specific.

    python -m core_organs.harvest.to_v2            -> <training>/ui_training_dataset_v2_all.jsonl
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import re
from typing import Any, Dict, List, Optional

from PIL import Image

LINE = re.compile(r'^#(\d+) (\S+) (?:"((?:[^"\\]|\\.)*)"|\(unnamed icon\)) \[(\d+), (\d+), (\d+), (\d+)\]\s*$')


def parse_elements(text: str) -> List[Dict[str, Any]]:
    els = []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        label = ""
        if m.group(3) is not None:
            with contextlib.suppress(Exception):
                label = json.loads('"' + m.group(3) + '"')
        els.append({"id": int(m.group(1)), "role": m.group(2), "label": label, "box": [int(m.group(i)) for i in (4, 5, 6, 7)]})
    return els


def _read(path: str) -> List[Dict[str, Any]]:
    out = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            with contextlib.suppress(Exception):
                out.append(json.loads(line))
    return out


def convert_row(r: Dict[str, Any], root: str) -> Optional[Dict[str, Any]]:
    from . import prompt_v2 as P2
    user = r["messages"][1]["content"]
    text = user[-1].get("text", "")
    m = re.search(r"Application: (.*?)\nElements:\n(.*?)\nGoal: (.*)$", text, re.S)
    ref = next((c["image"] for c in user if c.get("type") == "image"), None)
    if not m or not isinstance(ref, str):
        return None
    path = ref if os.path.isabs(ref) else os.path.join(root, ref)
    if not os.path.isfile(path):
        return None
    els = parse_elements(m.group(2))
    if not els:
        return None
    img = Image.open(path).convert("RGB")
    som = {"elements": els, "seconds": 0.0, "size": list(img.size), "tiers_used": [], "tiers_skipped": []}
    strips = P2.dense_strips(els, img.size)
    refs = []
    stem = os.path.splitext(path)[0]
    for i, c in enumerate(P2.strip_crops(img, strips)):
        p = f"{stem}_strip{i}.jpg"
        if not os.path.isfile(p):
            c.convert("RGB").save(p, "JPEG", quality=90)
        refs.append(os.path.relpath(p, root).replace("\\", "/"))
    content, info = P2.user_content(img, som, m.group(1).strip(), m.group(3).strip(), names=None, image_ref=ref, crop_refs=refs)
    row = copy.deepcopy(r)
    row["messages"][1]["content"] = content
    row["meta"].update({"prompt_version": 2, "strips": info["n_crops"], "names": 0, "converted_from_v1": True})
    return row


def build(root: str, out_name: str = "ui_training_dataset_v2_all.jsonl") -> Dict[str, Any]:
    d = os.path.join(root, "training")
    v1 = _read(os.path.join(d, "ui_training_dataset.jsonl"))
    v2 = {r["meta"].get("pair_id"): r for r in _read(os.path.join(d, "ui_training_dataset_v2.jsonl"))}
    out, seen = [], set()
    n_twin = n_conv = n_skip = 0
    for r in v1:
        pid = r["meta"].get("pair_id")
        if pid in seen:
            continue
        seen.add(pid)
        if pid in v2:
            out.append(v2[pid])
            n_twin += 1
            continue
        c = None
        with contextlib.suppress(Exception):
            c = convert_row(r, root)
        if c is None:
            n_skip += 1
            continue
        out.append(c)
        n_conv += 1
    for pid, r in v2.items():                                           # v2-only rows (their v1 row was quarantined or never written)
        if pid not in seen:
            out.append(r)
    p = os.path.join(d, out_name)
    with open(p, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    named = sum(1 for r in out if r["meta"].get("names"))
    return {"path": p, "rows": len(out), "v2_twins_with_names": n_twin, "converted_from_v1": n_conv, "skipped": n_skip, "rows_with_names": named,
            "rows_with_strips": sum(1 for r in out if r["meta"].get("strips"))}


if __name__ == "__main__":
    from .paths import harvest_dir
    print(json.dumps(build(harvest_dir()[0]), indent=1))
