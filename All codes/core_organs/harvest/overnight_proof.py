"""
overnight_proof -- every few minutes: how full is the knowledge pool, a picture of the screen, and a growth chart. The pictures are the proof that the unattended run was really running.

    python -m core_organs.harvest.overnight_proof run [--every-min 15] [--hours 10]     loop: counts -> growth.jsonl, screenshot, growth.png
    python -m core_organs.harvest.overnight_proof once                                  one tick
Output: reports/overnight_proof/<date>/  shot_HHMMSS.png (the screen, 1280 px wide), growth.png (counts over time), growth.jsonl
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

ROOT = r"D:\new_automation"
OUT = os.path.join(ROOT, "reports", "overnight_proof")


def counts() -> Dict[str, Any]:
    snap: Dict[str, Any] = {"when": time.strftime("%Y-%m-%d %H:%M:%S")}
    with contextlib.suppress(Exception):
        from core_organs import rag as R
        from core_organs.rag import lt
        rag = R.get_rag()
        for t in ("fast_paths", "procedures", "knowledge_chunks", "ui_states"):                      # this loop lives for hours: a cached table handle stays on the version it opened, so move it to the newest one
            with contextlib.suppress(Exception):
                rag.fast.st.table(t).checkout_latest()
        snap["fast_paths"] = int(rag.fast.st.count("fast_paths"))
        snap["procedures"] = int(rag.fast.st.count("procedures"))
        snap["knowledge_chunks"] = int(rag.fast.st.count("knowledge_chunks"))
        snap["ui_states"] = int(rag.fast.st.count("ui_states"))
        rows = rag.fast._overlay(lt.fetch(rag.fast.st, "fast_paths", "fast_id IS NOT NULL", 100000))        # the learning overlay is where 'verified' lives
        snap["fast_verified"] = sum(1 for r in rows if r.get("verified"))
        snap["fast_rea_static"] = sum(1 for r in rows if r.get("source") == "rea_static")
    with contextlib.suppress(Exception):
        db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        snap["lexicon_commands"] = db.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
        snap["lexicon_apps"] = db.execute("SELECT COUNT(DISTINCT app_key) FROM commands").fetchone()[0]
        db.close()
    for name, path in (("web_sites", os.path.join(ROOT, "reports", "web_curriculum", "progress.jsonl")), ("native_programs", os.path.join(ROOT, "reports", "rea_pipeline", "native_ledger.jsonl"))):
        with contextlib.suppress(Exception):
            snap[name] = sum(1 for _ in open(path, encoding="utf-8"))
    with contextlib.suppress(Exception):
        snap["web_action_rows"] = sum(1 for _ in open(os.path.join(ROOT, "data", "ai_root", "harvest", "training", "web_action_rows.jsonl"), encoding="utf-8"))
    return snap


def screenshot(folder: str) -> str:
    with contextlib.suppress(Exception):
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[0]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        w = 1280
        img = img.resize((w, int(img.height * w / img.width)))
        p = os.path.join(folder, time.strftime("shot_%H%M%S.png"))
        img.save(p)
        return p
    return ""


def chart(folder: str) -> str:
    rows = [json.loads(l) for l in open(os.path.join(folder, "growth.jsonl"), encoding="utf-8") if l.strip()]
    if len(rows) < 2:
        return ""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ts = list(range(len(rows)))
    labels = [r["when"][11:16] for r in rows]
    series = [("procedures", "#1f6feb"), ("fast_paths", "#d29922"), ("knowledge_chunks", "#2da44e"), ("lexicon_commands", "#8957e5"), ("web_action_rows", "#cf222e"), ("web_sites", "#0a7ea4"), ("native_programs", "#6e7781")]
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    for k, c in series:
        ys = [r.get(k) for r in rows]
        if any(y is not None for y in ys):
            ax.plot(ts, [y if y is not None else float("nan") for y in ys], label=f"{k} ({[y for y in ys if y is not None][-1]})", color=c, lw=2)
    step = max(1, len(ts) // 10)
    ax.set_xticks(ts[::step])
    ax.set_xticklabels(labels[::step])
    ax.set_title("Knowledge pool growth, unattended run")
    ax.set_xlabel("time of day")
    ax.set_ylabel("count")
    ax.grid(alpha=.25)
    ax.legend(loc="upper left", fontsize=8)
    p = os.path.join(folder, "growth.png")
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def tick() -> Dict[str, Any]:
    folder = os.path.join(OUT, time.strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    snap = counts()
    snap["screenshot"] = screenshot(folder)
    with open(os.path.join(folder, "growth.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    snap["chart"] = chart(folder)
    return snap


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "once"])
    ap.add_argument("--every-min", type=float, default=15.0)
    ap.add_argument("--hours", type=float, default=10.0)
    a = ap.parse_args(argv)
    end = time.time() + a.hours * 3600
    while True:
        s = tick()
        print("TICK", json.dumps({k: v for k, v in s.items() if k not in ("screenshot", "chart")}), "|", os.path.basename(s.get("screenshot", "")), flush=True)
        if a.cmd == "once" or time.time() > end:
            return 0
        time.sleep(a.every_min * 60)


if __name__ == "__main__":
    sys.exit(main())
