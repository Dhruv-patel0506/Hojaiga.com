"""
harvest.youtube_loop -- the slow, patient YouTube route: one app at a time, transcripts, then clips -> pairs for THAT app, until a target of usable pairs or a deadline.

Why a loop and not one big batch: this address is allowed only a few caption requests per window, so captions are mostly unavailable and videos are transcribed locally (faster-whisper, CPU int8, ~1 per 4
minutes). Doing harvest and pairs per app keeps the dataset growing steadily from the first app on and lets the run be stopped at any point with everything so far usable. The two heavy steps never overlap
(Whisper on the CPU starves the VLM gate: measured, the gate then answers nothing). No browser cookies are read. A refusal of the AUDIO fetch as well stops the whole loop.

    python -m core_organs.harvest loop --hours 4 --target 200 [--videos 6] [--apps notepad,vlc]
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from .paths import harvest_dir


def _usable(root: str) -> int:
    from . import pairs_batch as PB
    try:
        return int(PB.dataset_report(root, require_ui=True)["usable_for_training"])
    except Exception:
        return 0


def run_loop(hours: float = 4.0, target: int = 200, videos_per_app: int = 6, apps: Optional[List[str]] = None, max_tier: int = 2, clips_per_app: int = 40, log=print) -> Dict[str, Any]:
    from . import free_master_harvester as M, pairs_batch as PB
    root = harvest_dir()[0]
    state_path = os.path.join(root, "harvest_state.json")
    deadline = time.time() + hours * 3600.0
    names = [a for a in M.CORE_APPS if a["tier"] <= max_tier]
    if apps:
        want = {x.lower() for x in apps}
        names = [a for a in names if a["app_name"].lower() in want or M.app_key_of(a["app_name"]) in want]
    out: Dict[str, Any] = {"start_usable": _usable(root), "rounds": [], "stopped": ""}
    try:
        os.remove(state_path)                                   # earlier one-or-two-video visits must not hide an app: cached transcripts are not re-fetched
    except OSError:
        pass
    for rnd in range(3):                                        # up to three sweeps over the apps (each sweep asks for `videos_per_app` more videos per app)
        for a in names:
            if time.time() >= deadline:
                out["stopped"] = "deadline"
                return out
            if _usable(root) >= target:
                out["stopped"] = "target reached"
                return out
            key = M.app_key_of(a["app_name"])
            try:
                st = json.load(open(state_path, encoding="utf-8"))
            except Exception:
                st = {"done_apps": {}}
            st["done_apps"].pop(key, None)
            json.dump(st, open(state_path, "w", encoding="utf-8"))
            t0 = time.time()
            h = M.run_harvester(max_apps=1, videos_per_app=videos_per_app * (rnd + 1), only_apps=[a["app_name"]], block_cooldowns=(60,), whisper_fallback=True, write_workbook=True)
            p = PB.run_pairs_batch(None, root, max_clips=clips_per_app, budget_s=min(900.0, max(60.0, deadline - time.time())), per_video=8, apps=[key])
            row = {"round": rnd + 1, "app": key, "harvest": h["stats"], "blocked": h["blocked"], "clips": p.get("attempted", 0), "pairs_added": p.get("pairs", 0), "grounded": p.get("grounded", 0),
                   "usable_now": _usable(root), "seconds": round(time.time() - t0)}
            out["rounds"].append(row)
            log(json.dumps(row))
            if h["blocked"]:
                out["stopped"] = "blocked (audio fetch refused too)"
                return out
    out["stopped"] = "sweeps done"
    return out
