"""
hojaiga_mvp -- the product entrypoint. ONE request in plain words; the section decides whether to understand, teach or do.

    python hojaiga_mvp.py "how do I add a cube in Blender?"
    python hojaiga_mvp.py "build a wooden dining table in Blender"
    python hojaiga_mvp.py "learn Calculator"
    python hojaiga_mvp.py --list
    python hojaiga_mvp.py "build a stool" --app Blender --mode delegate --file <earlier .blend inside a sandbox>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="?", default="")
    ap.add_argument("--app", default="")
    ap.add_argument("--mode", default="auto", choices=["auto", "understand", "teach", "delegate"])
    ap.add_argument("--file", default="", help="continue in a document from an earlier run (same-file case)")
    ap.add_argument("--learn", default="auto", choices=["auto", "always", "never"])
    ap.add_argument("--no-recall", action="store_true", help="do not start from stored recipes")
    ap.add_argument("--no-vlm", action="store_true")
    ap.add_argument("--live", action="store_true", help="teach: look at the live screen and point")
    ap.add_argument("--tutor", action="store_true", help="the live tutor: the program on screen, red marks, voice (needs --app)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.tutor:
        import hojaiga_tutor
        return hojaiga_tutor.main([a.app or a.task] + ([a.task] if a.app and a.task else []))
    from sections import HoJaiga
    hj = HoJaiga().discover()
    if a.list or not a.task:
        print(json.dumps(hj.listing(), indent=1))
        return 0
    rep = hj.handle(a.task, app=a.app, mode=a.mode, file=a.file, learn=a.learn, recall=not a.no_recall, vlm=not a.no_vlm, live=a.live)
    print(json.dumps(rep, indent=1, default=str))
    return 0 if not rep.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
