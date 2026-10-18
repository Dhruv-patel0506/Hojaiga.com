"""python -m core_organs.harvest <command>

    apps        [--max-apps N] [--videos N] [--start K]   harvest apps -> YouTube search -> transcripts (network; resumable; stops if YouTube blocks)
    hotkeys     [--max-apps N] [--no-scrape] [--no-tldr] [--model]   hotkeys + macros -> workbook sheets 3-4 + JSONL
    ingest                                               everything harvested -> the RAG (idempotent)
    video       <video.mp4> <app_key> <video_id>         keyframes + SoM + training pairs for a local video file (no network)
    local       [--apps a,b] [--max-actions N] [--budget-s S] [--no-delta]   drive OWNED apps in the background and record pairs with UIA ground truth (no network)
    loop        [--hours H] [--target N] [--videos V] [--apps a,b]   the slow YouTube route: per app, transcripts (local whisper when captions are refused) then clips -> pairs, until N usable pairs
    status                                               what exists on disk and in the RAG
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core_organs.harvest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apps"); a.add_argument("--max-apps", type=int, default=5); a.add_argument("--videos", type=int, default=2); a.add_argument("--start", type=int, default=0); a.add_argument("--cooldowns", default="600,1200", help="seconds to wait (and re-ask) after a caption refusal, comma list"); a.add_argument("--wait", action="store_true", help="old behaviour on a 429: cool-offs, then local speech recognition (default: fail over to static sources at once)")
    h = sub.add_parser("hotkeys"); h.add_argument("--max-apps", type=int, default=5); h.add_argument("--no-scrape", action="store_true"); h.add_argument("--no-tldr", action="store_true"); h.add_argument("--model", action="store_true")
    sub.add_parser("ingest")
    v = sub.add_parser("video"); v.add_argument("path"); v.add_argument("app_key"); v.add_argument("video_id")
    lo = sub.add_parser("local"); lo.add_argument("--apps", default=""); lo.add_argument("--max-actions", type=int, default=30); lo.add_argument("--budget-s", type=float, default=600.0); lo.add_argument("--no-delta", action="store_true"); lo.add_argument("--nav", default=None, help="comma list: only these navigation entries"); lo.add_argument("--no-base", action="store_true"); lo.add_argument("--per-pass", type=int, default=0); lo.add_argument("--sizes", default="", help="comma list of WxH window sizes to lay each app out at, e.g. 900x640,1100x760,1400x900")
    ws = sub.add_parser("websites"); ws.add_argument("--urls", default=""); ws.add_argument("--max-actions", type=int, default=15); ws.add_argument("--which", default="all", choices=["all", "websites", "webapps"])
    sb = sub.add_parser("search-browser"); sb.add_argument("--apps", default=""); sb.add_argument("--tutorials", type=int, default=3)
    wb = sub.add_parser("web"); wb.add_argument("--apps", default=""); wb.add_argument("--minutes", type=float, default=20.0)
    lp = sub.add_parser("loop"); lp.add_argument("--hours", type=float, default=4.0); lp.add_argument("--target", type=int, default=200); lp.add_argument("--videos", type=int, default=6); lp.add_argument("--apps", default=""); lp.add_argument("--whisper", action="store_true", help="transcribe locally when captions are refused (slow)")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    from . import free_master_harvester as M, free_hotkeys_and_macros_harvester as K, paths
    if args.cmd == "apps":
        out = M.run_harvester(max_apps=args.max_apps, videos_per_app=args.videos, start=args.start, block_cooldowns=tuple(float(x) for x in args.cooldowns.split(",") if x.strip()), whisper_fallback=args.wait, on_block="wait" if args.wait else "failover")
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
    elif args.cmd == "loop":
        from . import youtube_loop as YL
        out = YL.run_loop(args.hours, args.target, args.videos, [x.strip() for x in args.apps.split(",") if x.strip()] or None, whisper=args.whisper, log=lambda s: print(s, flush=True))
    elif args.cmd == "search-browser":
        from . import search_browser as _SB, free_master_harvester as _M2
        names = [x.strip() for x in args.apps.split(",") if x.strip()] or [a["app_name"] for a in _M2.CORE_APPS][:10]
        out = _SB.run(names, max_tutorials=args.tutorials)
    elif args.cmd == "websites":
        from . import web_recorder as _WR
        urls = [u for u in args.urls.split(",") if u.strip()] or ((_WR.SITES_WEBSITE if args.which in ("all", "websites") else []) + (_WR.SITES_WEBAPP if args.which in ("all", "webapps") else []))
        out = _WR.record_sites(urls, max_actions=args.max_actions)
    elif args.cmd == "web":
        from . import web_search_failover as WF, free_master_harvester as _M
        names = [x.strip() for x in args.apps.split(",") if x.strip()] or [a["app_name"] for a in _M.CORE_APPS][:12]
        out = WF.run_batch(names, args.minutes)
    elif args.cmd == "local":
        from . import local_recorder as LR
        out = LR.run_local([x.strip() for x in args.apps.split(",") if x.strip()] or None, max_actions=args.max_actions, budget_s=args.budget_s, scan_delta=not args.no_delta,
                           nav_items=[x.strip() for x in args.nav.split(",") if x.strip()] if args.nav is not None else None, base_pass=not args.no_base, per_pass_actions=args.per_pass,
                           sizes=[tuple(int(v) for v in z.lower().split("x")) for z in args.sizes.split(",") if "x" in z] or None)
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
