"""python -m core_organs.harvest <command>

    apps        [--max-apps N] [--videos N] [--start K]   harvest apps -> YouTube search -> transcripts (network; resumable; stops if YouTube blocks)
    hotkeys     [--max-apps N] [--no-scrape] [--no-tldr] [--model]   hotkeys + macros -> workbook sheets 3-4 + JSONL
    ingest                                               everything harvested -> the RAG (idempotent)
    video       <video.mp4> <app_key> <video_id>         keyframes + SoM + training pairs for a local video file (no network)
    local       [--apps a,b] [--max-actions N] [--budget-s S] [--no-delta]   drive OWNED apps in the background and record pairs with UIA ground truth (no network)
    status                                               what exists on disk and in the RAG
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core_organs.harvest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apps"); a.add_argument("--max-apps", type=int, default=5); a.add_argument("--videos", type=int, default=2); a.add_argument("--start", type=int, default=0)
    h = sub.add_parser("hotkeys"); h.add_argument("--max-apps", type=int, default=5); h.add_argument("--no-scrape", action="store_true"); h.add_argument("--no-tldr", action="store_true"); h.add_argument("--model", action="store_true")
    sub.add_parser("ingest")
    v = sub.add_parser("video"); v.add_argument("path"); v.add_argument("app_key"); v.add_argument("video_id")
    lo = sub.add_parser("local"); lo.add_argument("--apps", default=""); lo.add_argument("--max-actions", type=int, default=30); lo.add_argument("--budget-s", type=float, default=600.0); lo.add_argument("--no-delta", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    from . import free_master_harvester as M, free_hotkeys_and_macros_harvester as K, paths
    if args.cmd == "apps":
        out = M.run_harvester(max_apps=args.max_apps, videos_per_app=args.videos, start=args.start)
    elif args.cmd == "hotkeys":
        out = K.run_hotkeys_and_macros_harvester(max_apps=args.max_apps, scrape=not args.no_scrape, tldr=not args.no_tldr, use_model=args.model)
    elif args.cmd == "ingest":
        from core_organs import rag
        from . import bridge
        out = bridge.ingest_all(rag.get_rag())
    elif args.cmd == "video":
        from core_organs import rag
        from . import video_pipeline as VP, video_explain as VE
        root = paths.harvest_dir()[0]
        frames = VP.extract_keyframes(args.path, f"{root}/frames/{args.video_id}", args.video_id)
        segs = json.load(open(f"{root}/transcripts_json/{args.app_key}__{args.video_id}.json", encoding="utf-8"))
        out = VE.explain_video(rag.get_rag(), args.app_key, args.video_id, segs, frames)
    elif args.cmd == "local":
        from . import local_recorder as LR
        out = LR.run_local([x.strip() for x in args.apps.split(",") if x.strip()] or None, max_actions=args.max_actions, budget_s=args.budget_s, scan_delta=not args.no_delta)
    else:
        d, deg = paths.harvest_dir(False)
        import os
        out = {"dir": d, "degraded": deg, "exists": os.path.isdir(d), "transcripts": len([f for f in os.listdir(d + "/transcripts_json")]) if os.path.isdir(d + "/transcripts_json") else 0}
        from core_organs import rag
        out["rag"] = rag.status().__dict__
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
