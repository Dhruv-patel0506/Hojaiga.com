r"""
youtube_pattern_mix_tagger.py -- which of the 25 interface archetypes an app's tutorial transcripts point to, and whether it is a HYBRID (two or three patterns of similar strength).

    python -X utf8 youtube_pattern_mix_tagger.py            # reads <harvest>/transcripts_json/<app_key>__<video_id>.json, writes <harvest>/youtube_rag/app_pattern_mix.jsonl

One line per app: {app_key, n_videos, n_words, ranked: [[archetype, score], ...top 3], hybrid, status}. The words are the narration of every transcript of that app, scored by
core_organs.rag.archetypes.ArchetypeRouter (the same word-signal prior the scanner uses on control names). It is a HINT for building the training set: narration says "timeline", "layers",
"canvas" far more often than it says a control name, so the evidence is weaker than a live scan, which always overrides it. `hybrid` = the second archetype scores >= 60% of the first.
Read-only on the transcripts; no network, no GPU, no model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def harvest_dir() -> Path:
    env = os.environ.get("HOJAIGA_HARVEST_DIR", "").strip()
    return Path(env) if env else ROOT / "data" / "ai_root" / "harvest"


def raw_scores(app_key: str, text: str, router: Any, min_words: int = 150) -> Optional[Dict[str, float]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    if len(words) < min_words:
        return None
    sig = {"app": app_key, "title": "", "controls": [(0, w) for w in sorted(set(words))]}
    return {a: float(s) for a, s in router.classify(sig, 25)}


def mix_from(scores: Optional[Dict[str, float]], base: Dict[str, float], top: int = 3, ratio: float = 0.6) -> Dict[str, Any]:
    """Narration says 'open', 'save', 'file' in every tutorial, so file_manager scores high for EVERY app. `base` is each archetype's mean score over all tagged apps. (Dividing by it was tried
    and rejected: with ~12 apps the small baselines amplified noise and turned WhatsApp into an audio workstation.)"""
    if scores is None:
        return {"ranked": [], "raw_top": [], "hybrid": False, "status": "too_little_text"}
    pos = sorted(((a, v) for a, v in scores.items() if v > 0), key=lambda kv: -kv[1])
    if not pos:
        return {"ranked": [], "raw_top": [], "hybrid": False, "status": "no_signal"}
    top1 = pos[0][1]
    raw_top = [[a, round(v, 3)] for a, v in pos[:top]]
    # the first pattern is the raw winner (checked by eye: calculator, chat_messenger, text_editor, raster_editor ...). A SECOND or THIRD pattern must be strong (>= ratio of the first) AND
    # clearly above what tutorials of any app give for it (>= 1.5 x its mean), otherwise it is the generic-narration echo, not part of the app.
    extra = [[a, round(v / top1, 3)] for a, v in pos[1:] if v >= ratio * top1 and v >= 1.5 * base.get(a, 0.0)][: top - 1]
    ranked = [[pos[0][0], 1.0]] + extra
    return {"ranked": ranked, "raw_top": raw_top, "hybrid": len(ranked) >= 2, "status": "ok"}


def tag_all(hdir: Path, out: Optional[Path] = None) -> Dict[str, Any]:
    from core_organs.rag import archetypes as A
    router = A.ArchetypeRouter()
    by_app: Dict[str, List[Path]] = defaultdict(list)
    for p in sorted((hdir / "transcripts_json").glob("*__*.json")):
        by_app[p.name.split("__", 1)[0]].append(p)
    out = out or (hdir / "youtube_rag" / "app_pattern_mix.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, files in sorted(by_app.items()):
        text = []
        for p in files:
            try:
                segs = json.loads(p.read_text(encoding="utf-8"))
                text += [str(s.get("text", "")) for s in segs] if isinstance(segs, list) else []
            except (OSError, ValueError):
                continue
        body = " ".join(text)
        rows.append((key, len(files), len(body.split()), raw_scores(key, body, router)))
    got = [r[3] for r in rows if r[3]]
    base = {a: sum(g.get(a, 0.0) for g in got) / len(got) for a in (got[0] if got else {})}
    n_h = n_ok = 0
    with open(out, "w", encoding="utf-8") as f:
        for key, nv, nw, sc in rows:
            m = mix_from(sc, base)
            m["baseline_apps"] = len(got)                            # a lift over fewer than ~20 apps is a rough correction, and the row says how many it was computed from
            f.write(json.dumps({"app_key": key, "n_videos": nv, "n_words": nw, **m}, ensure_ascii=False) + chr(10))
            n_ok += m["status"] == "ok"
            n_h += bool(m["hybrid"])
    return {"apps": len(by_app), "tagged": n_ok, "hybrid": n_h, "out": str(out)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--harvest-dir", default=str(harvest_dir()))
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    print(json.dumps(tag_all(Path(a.harvest_dir), Path(a.out) if a.out else None)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
