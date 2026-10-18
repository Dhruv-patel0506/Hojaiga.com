"""
harvest.hf_gui -- open GUI datasets from Hugging Face into our pair format (APPROVED by the person: a capped subset, 400-600 pairs).

`agentsea/wave-ui-25k`: one labelled element per row (image, name, type, bbox in pixels of `resolution`, platform web | desktop | mobile, purpose, expectation). A row becomes a pair exactly like the other sources: the
picture is scanned for numbered elements (the scan the model reads), the labelled element is the numbered element that contains the labelled box, the goal is 'Click the <name>' and the answer is that click. Mobile
screenshots are skipped (this agent drives desktops and browsers). Rows are read straight from the parquet shards through the Hub file system: only the row groups asked for are downloaded (a few tens of MB each),
spread across shards for variety, never the whole dataset.

    python -m core_organs.harvest.hf_gui --limit 500
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image

from .paths import harvest_dir

DATASET = "agentsea/wave-ui-25k"
N_SHARDS = 22


def _row_groups(spread: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    return list(spread)


# (shard, row group) pairs spread across the dataset: a few groups from several shards = several sources
SPREAD = [(0, 0), (0, 6), (3, 2), (5, 4), (8, 1), (11, 7), (14, 3), (17, 5), (19, 0), (21, 2)]


def goal_of(name: str, typ: str) -> str:
    n = (name or "").strip()
    t = (typ or "").strip().lower()
    if not n:
        return ""
    return f"Click the {n}" if (t and n.lower().endswith(t)) or not t else f"Click the {n} {t}"


def scaled_box(bbox: Sequence[float], resolution: Sequence[int], size: Tuple[int, int]) -> Optional[Tuple[float, float, float, float]]:
    """A pixel box [x1, y1, x2, y2] on `resolution` -> (x, y, w, h) on the image as stored; None when degenerate."""
    if not bbox or len(bbox) < 4 or not resolution or len(resolution) < 2:
        return None
    sx, sy = size[0] / float(resolution[0]), size[1] / float(resolution[1])
    x, y, w, h = bbox[0] * sx, bbox[1] * sy, (bbox[2] - bbox[0]) * sx, (bbox[3] - bbox[1]) * sy
    return (x, y, w, h) if w >= 6 and h >= 6 else None


def convert_row(row: Dict[str, Any], root: str, som_cache: Dict[str, Any], som_fn: Any, idx: int, domain_of_platform: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """One dataset row -> a v1 pair row (and the picture on disk), or None with no side effects when the element cannot be found on the picture."""
    from . import local_recorder as LR, video_explain as VE
    plat = (row.get("platform") or "").lower()
    if plat not in ("web", "desktop"):
        return None
    goal = goal_of(row.get("name", ""), row.get("type", ""))
    if not goal:
        return None
    raw = (row.get("image") or {}).get("bytes")
    if not raw:
        return None
    h = hashlib.sha1(raw).hexdigest()[:14]
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    box = scaled_box(row.get("bbox") or [], row.get("resolution") or list(img.size), img.size)
    if box is None:
        return None
    fdir = os.path.join(root, "frames", "hf_waveui")
    os.makedirs(fdir, exist_ok=True)
    path = os.path.join(fdir, h + "_pre.jpg")
    if not os.path.isfile(path):
        img.save(path, "JPEG", quality=90)
    if h not in som_cache:
        som_cache[h] = som_fn(path)
    som = som_cache[h]
    el = LR.element_at(som, box)
    if el is None:
        return None
    key = "hf_" + (row.get("source") or "gui").lower().replace(" ", "_")[:24]
    pid = hashlib.sha1(f"{key}|{goal}|{h}|{int(box[0])},{int(box[1])}".encode()).hexdigest()[:16]
    action = [{"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None, "verify_expectation": (row.get("expectation") or "the screen changes")[:120]}]
    dom = (domain_of_platform or {"web": "website", "desktop": "desktop_app"})[plat]
    return VE.build_row(root, key, "hf_waveui", {"t": float(idx), "pre": path, "post": "", "bbox": None}, som, goal, action, pid, True, True,
                        {"source": "hf_waveui", "source_ref": f"{DATASET}", "domain": dom, "uia_name": row.get("name", ""), "uia_type": row.get("type", ""), "platform": plat})


def stream(limit: int = 500, root: str = "", out_jsonl: str = "", spread: Sequence[Tuple[int, int]] = SPREAD, log: Any = print, som_fn: Any = None) -> Dict[str, Any]:
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem
    from . import local_recorder as LR, video_pipeline as VP
    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    som_fn = som_fn or VP.som_of_frame
    seen = LR._existing_pair_ids(out_jsonl)
    fs = HfFileSystem()
    rep = {"rows_read": 0, "skipped_platform": 0, "not_found_on_picture": 0, "pairs": 0, "pairs_v2": 0, "by_platform": {}, "seconds": 0.0}
    t0 = time.time()
    som_cache: Dict[str, Any] = {}
    for shard, rg in spread:
        if rep["pairs"] >= limit:
            break
        path = f"datasets/{DATASET}/data/train-{shard:05d}-of-{N_SHARDS:05d}.parquet"
        try:
            pf = pq.ParquetFile(fs.open(path, "rb"))
            tbl = pf.read_row_group(min(rg, pf.num_row_groups - 1))
        except Exception as exc:
            log(f"[hf] shard {shard} group {rg}: {type(exc).__name__}: {str(exc)[:80]}")
            continue
        rows = tbl.to_pylist()
        log(f"[hf] shard {shard} group {rg}: {len(rows)} rows, {rep['pairs']} pairs so far, {time.time() - t0:.0f}s")
        for i, r in enumerate(rows):
            if rep["pairs"] >= limit:
                break
            rep["rows_read"] += 1
            try:
                row = convert_row(r, root, som_cache, som_fn, rep["rows_read"])
            except Exception:
                row = None
            if row is None:
                rep["skipped_platform" if (r.get("platform") or "").lower() not in ("web", "desktop") else "not_found_on_picture"] += 1
                continue
            if row["meta"]["pair_id"] in seen:
                continue
            seen.add(row["meta"]["pair_id"])
            with open(out_jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            with contextlib.suppress(Exception):
                pre = Image.open(os.path.join(root, row["meta"]["pre"])).convert("RGB")
                som = som_cache[os.path.basename(row["meta"]["pre"]).split("_")[0]]
                v2 = LR._v2_row(row, pre, som, [], root, os.path.join(root, row["meta"]["pre"]))
                with open(out_jsonl.replace(".jsonl", "_v2.jsonl"), "a", encoding="utf-8") as f2:
                    f2.write(json.dumps(v2, ensure_ascii=False) + "\n")
                rep["pairs_v2"] += 1
            rep["pairs"] += 1
            rep["by_platform"][row["meta"]["platform"]] = rep["by_platform"].get(row["meta"]["platform"], 0) + 1
            if rep["pairs"] % 25 == 0:
                log(f"[hf] {rep['pairs']} pairs, {time.time() - t0:.0f}s")
        if len(som_cache) > 60:                                           # bounded memory: the cache only helps rows that share a picture
            som_cache.clear()
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


if __name__ == "__main__":
    lim = 500
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    print(json.dumps(stream(lim), indent=1), flush=True)
