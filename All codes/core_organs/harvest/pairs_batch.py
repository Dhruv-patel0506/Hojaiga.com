"""
harvest.pairs_batch -- many short clips -> grounded training pairs, resumably, within a time budget.

For every on-topic harvested transcript: pick its UI-action moments (strict detector), download ONLY those seconds (yt-dlp sections, <= 12 s, 720p), find the scene changes, read the numbered
screen elements (Set-of-Marks) and write one pair per spoken instruction (video_explain). Clips are fetched one ahead while the previous one is processed (network and OCR overlap).

Safe to stop and re-run: every clip's outcome is recorded in training/pairs_state.json and never redone. It stops by itself when the time budget is spent or YouTube starts refusing
(`max_fail_streak` consecutive download failures) -- it does not retry into a block. Frames no pair uses are deleted; the clips themselves are small and kept.
"""
from __future__ import annotations

import glob
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from .paths import harvest_dir


def _load_state(path: str) -> Dict[str, Any]:
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"clips": {}}


def _save_state(path: str, st: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, path)


def plan_clips(root: str, per_video: int = 6, max_clip_s: float = 12.0, min_gap_s: float = 20.0, apps: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """[{app, video_id, t0, t1, key, title}] across every on-topic transcript, spread through each video (no two clips within min_gap_s), videos interleaved so a short run samples many apps."""
    from . import video_pipeline as VP
    titles: Dict[Tuple[str, str], str] = {}
    try:
        import pandas as pd
        from .paths import workbook_path
        df = pd.read_excel(workbook_path(root), sheet_name="2_YouTube_And_Transcripts")
        titles = {(str(r["app_key"]), str(r["video_id"])): str(r.get("title", "")) for _, r in df.iterrows()}
    except Exception:
        pass
    per: List[List[Dict[str, Any]]] = []
    for path in sorted(glob.glob(os.path.join(root, "transcripts_json", "*.json"))):
        base = os.path.basename(path)[:-5]
        if "__" not in base:
            continue
        app, vid = base.split("__", 1)
        if apps and app not in apps:
            continue
        try:
            segs = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        picked: List[Dict[str, Any]] = []
        for m in VP.action_moments(segs):
            t0 = m["t0"]
            if picked and t0 - picked[-1]["t0"] < min_gap_s:
                continue
            t1 = min(m["t1"], t0 + max_clip_s)
            if t1 - t0 < 3.0:
                continue
            picked.append({"app": app, "video_id": vid, "t0": round(t0, 2), "t1": round(t1, 2), "key": f"{app}:{vid}@{int(t0)}-{int(t1)}", "title": titles.get((app, vid), ""), "text": m["text"]})
            if len(picked) >= per_video:
                break
        if picked:
            per.append(picked)
    out: List[Dict[str, Any]] = []
    i = 0
    while any(per):                                              # round robin over videos
        for lst in per:
            if i < len(lst):
                out.append(lst[i])
        i += 1
        if i > 1000:
            break
    return out


def run_pairs_batch(rag, root: str = "", max_clips: int = 40, budget_s: float = 1500.0, per_video: int = 6, delay_s: float = 2.0, max_fail_streak: int = 3,
                    download: Optional[Callable[[str, float, float, str], str]] = None, som_fn: Optional[Callable[..., Dict[str, Any]]] = None, apps: Optional[List[str]] = None,
                    scene_kw: Optional[Dict[str, Any]] = None, gate: Any = "auto", min_elements: int = 6) -> Dict[str, Any]:
    from . import video_explain as VE, video_pipeline as VP
    owns_gate = False
    if gate == "auto":
        from .frame_gate import UIFrameGate
        gate = UIFrameGate(cache_path=os.path.join(root or harvest_dir()[0], "training", "frame_gate_cache.json"))
        owns_gate = True
    root = root or harvest_dir()[0]
    download = download or VP.download_section
    scene_kw = dict(sample_fps=2.0, min_change=0.01, **(scene_kw or {}))
    os.makedirs(os.path.join(root, "training"), exist_ok=True)
    state_path = os.path.join(root, "training", "pairs_state.json")
    state = _load_state(state_path)
    jsonl = os.path.join(root, "training", "ui_training_dataset.jsonl")
    todo = [c for c in plan_clips(root, per_video, apps=apps) if c["key"] not in state["clips"]][:max_clips]
    rep: Dict[str, Any] = {"planned": len(todo), "attempted": 0, "downloaded": 0, "download_failed": 0, "no_scene_change": 0, "pairs": 0, "grounded": 0, "frames_pruned": 0, "stopped": "",
                           "by_app": {}, "seconds": 0.0, "som_seconds": 0.0, "already_done": len(state["clips"])}
    t_start = time.time()
    fail_streak = 0
    clips_dir = os.path.join(root, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    def fetch(c: Dict[str, Any]) -> Tuple[Optional[str], str]:
        cached = os.path.join(clips_dir, f"{c['video_id']}_{int(c['t0'])}-{int(c['t1'])}.mp4")
        if os.path.isfile(cached):
            return cached, ""
        try:
            time.sleep(delay_s)
            return download(c["video_id"], c["t0"], c["t1"], clips_dir), ""
        except Exception as exc:
            return None, f"{type(exc).__name__}: {str(exc)[:120]}"

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = None
        for i, c in enumerate(todo):
            if time.time() - t_start > budget_s:
                rep["stopped"] = "time budget spent"
                break
            fut = pending or pool.submit(fetch, c)
            pending = None
            # prefetch the next clip only while downloads are succeeding and budget remains: after a failure, go one request at a time so a block is never pushed into
            if i + 1 < len(todo) and fail_streak == 0 and time.time() - t_start <= budget_s:
                pending = pool.submit(fetch, todo[i + 1])
            clip, err = fut.result()
            rep["attempted"] += 1
            if clip is None or not os.path.isfile(clip):
                rep["download_failed"] += 1
                if err.startswith("VideoUnavailable"):                      # this video is gone: every clip of it is skipped for good, and it says nothing about being blocked
                    rep["videos_unavailable"] = rep.get("videos_unavailable", 0) + 1
                    for other in todo:
                        if other["video_id"] == c["video_id"]:
                            state["clips"][other["key"]] = {"status": f"video_unavailable: {err[:100]}", "ts": time.time()}
                    _save_state(state_path, state)
                    todo = [o for o in todo if o["video_id"] != c["video_id"] or o is c]
                    continue
                fail_streak += 1
                state["clips"][c["key"]] = {"status": f"download_failed: {err}", "ts": time.time()}
                _save_state(state_path, state)
                if fail_streak >= max_fail_streak:
                    rep["stopped"] = f"{fail_streak} downloads failed in a row (last: {err}) -- stopping instead of retrying into a block"
                    break
                continue
            fail_streak = 0
            rep["downloaded"] += 1
            frames_dir = os.path.join(root, "frames", f"{c['video_id']}_{int(c['t0'])}")
            try:
                events = VP.extract_keyframes(clip, frames_dir, f"{c['video_id']}_{int(c['t0'])}", **scene_kw)
            except Exception as exc:
                state["clips"][c["key"]] = {"status": f"unreadable: {type(exc).__name__}", "ts": time.time()}
                _save_state(state_path, state)
                continue
            if not events:
                rep["no_scene_change"] += 1
                state["clips"][c["key"]] = {"status": "no_scene_change", "ts": time.time()}
                _save_state(state_path, state)
                continue
            path = os.path.join(root, "transcripts_json", f"{c['app']}__{c['video_id']}.json")
            segs = json.load(open(path, encoding="utf-8"))
            shifted = [dict(s, start=s["start"] - c["t0"]) for s in segs if c["t0"] - 6 <= s["start"] <= c["t1"] + 2]
            before = _count_lines(jsonl)
            r = VE.explain_video(rag, c["app"], f"{c['video_id']}@{int(c['t0'])}", shifted, events, title=c["title"], out_jsonl=jsonl, root=root, som_fn=som_fn, ingest=False, max_pairs=8, gate=gate, min_elements=min_elements)
            for k in ("sparse_frame", "not_ui_frame", "unverified_frame", "not_concrete", "step_already_used", "no_step_nearby"):
                rep[k] = rep.get(k, 0) + r.get(k, 0)
            rep["pairs"] += r["pairs"]
            rep["grounded"] += r["grounded"]
            rep["som_seconds"] += r["som_seconds"]
            a = rep["by_app"].setdefault(c["app"], {"clips": 0, "pairs": 0, "grounded": 0})
            a["clips"] += 1
            a["pairs"] += r["pairs"]
            a["grounded"] += r["grounded"]
            rep["frames_pruned"] += _prune_frames(frames_dir, jsonl, root, skip_lines=before)
            state["clips"][c["key"]] = {"status": f"done: {r['pairs']} pairs ({r['grounded']} grounded)", "pairs": r["pairs"], "ts": time.time()}
            _save_state(state_path, state)
    rep["seconds"] = round(time.time() - t_start, 1)
    rep["som_seconds"] = round(rep["som_seconds"], 1)
    if gate is not None and hasattr(gate, "stats"):
        rep["frame_gate"] = dict(gate.stats)
        if owns_gate:
            gate.unload()                                          # give the GPU back
    rep["total_pairs_on_disk"] = _count_lines(jsonl)
    return rep


def _count_lines(path: str) -> int:
    try:
        return sum(1 for l in open(path, encoding="utf-8") if l.strip())
    except Exception:
        return 0


def _prune_frames(frames_dir: str, jsonl: str, root: str, skip_lines: int = 0) -> int:
    """Delete the frames of this clip that no pair in the dataset references (events that matched no instruction)."""
    keep = set()
    try:
        for l in open(jsonl, encoding="utf-8"):
            if not l.strip():
                continue
            m = json.loads(l).get("meta", {})
            for k in ("pre", "post"):
                if m.get(k):
                    keep.add(os.path.normpath(m[k] if os.path.isabs(m[k]) else os.path.join(root, m[k])))
    except Exception:
        return 0
    n = 0
    for f in glob.glob(os.path.join(frames_dir, "*.jpg")):
        if os.path.normpath(f) not in keep:
            try:
                os.remove(f)
                n += 1
            except Exception:
                pass
    return n


def dataset_report(root: str = "", require_ui: bool = True) -> Dict[str, Any]:
    """What the dataset is worth right now: counts, validity as the trainer sees it, per app, and how far it is from the brief's 10,000-25,000."""
    from core_organs import train_qlora as TQ
    root = root or harvest_dir()[0]
    path = os.path.join(root, "training", "ui_training_dataset.jsonl")
    rows, st = TQ.load_pairs(path, grounded_only=False)
    valid, invalid, by_app, by_action = [], [], {}, {}
    unchecked = 0
    for r in rows:
        p = TQ.validate_pair(r, root, require_ui)
        (invalid if p else valid).append(r)
        if r.get("meta", {}).get("ui_frames") is not True:
            unchecked += 1
        if not p and r["meta"].get("grounded"):
            by_app[r["meta"]["app_key"]] = by_app.get(r["meta"]["app_key"], 0) + 1
            a = json.loads(r["messages"][2]["content"][0]["text"])[0]["action"]
            by_action[a] = by_action.get(a, 0) + 1
    usable = sum(by_app.values())
    vids = len({r["meta"]["video_id"].split("@")[0] for r in valid if r["meta"].get("grounded")})
    return {"pairs": len(rows), "valid": len(valid), "invalid": len(invalid), "usable_for_training": usable, "frames_not_verified_as_ui": unchecked, "videos": vids, "by_app": by_app, "by_action": by_action,
            "min_examples_needed": 200, "brief_target": "10,000-25,000", "fraction_of_min": round(usable / 200, 2)}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m core_organs.harvest.pairs_batch", description="Download short UI-action clips of harvested tutorials and turn them into grounded training pairs (resumable).")
    ap.add_argument("--max-clips", type=int, default=40)
    ap.add_argument("--budget-s", type=float, default=1500.0, help="stop after this many seconds")
    ap.add_argument("--per-video", type=int, default=6)
    ap.add_argument("--apps", nargs="*", default=None, help="app keys to restrict to")
    ap.add_argument("--no-gate", action="store_true", help="do not verify frames as software UI (such pairs are NOT usable for training)")
    ap.add_argument("--report", action="store_true", help="only print the dataset report; do nothing else")
    a = ap.parse_args(argv)
    if a.report:
        print(json.dumps(dataset_report(), indent=2, default=str))
        return 0
    from core_organs import rag
    print(json.dumps(run_pairs_batch(rag.get_rag(), max_clips=a.max_clips, budget_s=a.budget_s, per_video=a.per_video, apps=a.apps, gate=None if a.no_gate else "auto"), indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
