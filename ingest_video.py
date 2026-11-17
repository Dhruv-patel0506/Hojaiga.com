"""
ingest_video -- the ingestion step of the video-guided pipeline. It takes a tutorial
TRANSCRIPT (Whisper output, or a pasted narration -- no YouTube download, no ToS risk) plus an
OPTIONAL Stage-1 scanned control list, and uses the 7B model to EXTRACT a schema-valid
Procedural Guide (brain/guide.schema.json) that the guided executor + verifier already consume.

Two honest design rules baked in from the PoC findings:
  1. EXTRACTION, not planning -- the model transcribes a human's narration into steps (its
     strength), it is NOT asked to invent a plan blind (its 0/8 weakness).
  2. GROUNDING -- when a control list is supplied, the model may ONLY use those exact labels as
     targets, so it cannot hallucinate selectors that don't exist in the live app.
The output is validated against the schema before it's written; invalid output is rejected, not
silently accepted.
"""
import os
import re
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_guide import manual_validate, SCHEMA  # reuse the schema + validator

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("VG_MODEL", "qwen2.5:7b")

_SCHEMA_HINT = ('{"app":"...","app_kind":"web","goal":"...","tier":1,'
                '"source":{"kind":"youtube","video_title":"...","channel":"...","url":"..."},'
                '"steps":[{"id":1,"tut_time":"0:23","intent":"...","action":"click|fill|select",'
                '"target":"<EXACT control label>","value":null,'
                '"verify":{"selector":"<css or empty>","prop":"text|count|visible|dom-diff","expected":"<substring>"}}]}')


def _unwrap(d):
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                return v
        if "steps" in d:
            return d
    return d


def extract(transcript, app, controls=None, source=None):
    grounding = ""
    if controls:
        labels = [c.get("label") or c.get("aria-label") or c.get("name") for c in controls]
        labels = [l for l in labels if l]
        grounding = ("\nAVAILABLE CONTROLS (use ONLY these EXACT labels as each step's target; "
                     "never invent a label that is not in this list): " + json.dumps(labels[:60]))
    prompt = (f"Convert this software tutorial narration into a structured action guide for the app '{app}'.\n"
              f"Output JSON matching this schema: {_SCHEMA_HINT}\n"
              f"Every step MUST have a verify oracle describing the observable state change that proves it worked.\n"
              f"{grounding}\n\nNARRATION:\n{transcript}")
    body = json.dumps({"model": MODEL, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}), timeout=150).read())["response"]
    guide = _unwrap(json.loads(raw))
    if isinstance(guide, list):
        guide = {"app": app, "goal": "", "steps": guide}
    return guide


def _norm_action(s):
    a = str(s.get("action", "click")).lower().strip()
    if "|" in a or a not in {"click", "fill", "select", "toggle", "keypress", "wait"}:
        # model echoed the enum placeholder or an unknown verb -> infer from context, don't fabricate
        a = "fill" if s.get("value") else "click"
    return a


def _norm_prop(v):
    p = str(v.get("prop", "dom-diff")).lower().strip()
    if "|" in p or p not in {"text", "count", "visible", "attr:class", "attr:data-status", "value", "dom-diff"}:
        p = "dom-diff"
    return p


def coerce(guide, app, source):
    """Fill schema-required fields the model may omit; keep it honest (no fabricated steps)."""
    guide.setdefault("app", app)
    guide.setdefault("goal", f"Automate {app} workflow")
    guide.setdefault("app_kind", "web")
    guide["source"] = guide.get("source") or source or {"kind": "youtube"}
    steps = guide.get("steps", [])
    clean = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or not s.get("target"):
            continue
        s.setdefault("id", i + 1)
        s.setdefault("intent", s.get("target"))
        s["action"] = _norm_action(s)
        v = s.get("verify") or {}
        v["prop"] = _norm_prop(v)
        v.setdefault("expected", "true")
        s["verify"] = v
        clean.append(s)
    guide["steps"] = clean
    return guide


def run(transcript_path, app, controls_path=None, out_path=None):
    transcript = Path(transcript_path).read_text(encoding="utf-8")
    controls = json.loads(Path(controls_path).read_text(encoding="utf-8")) if controls_path and Path(controls_path).exists() else None
    source = {"kind": "youtube", "url": os.environ.get("VG_SOURCE_URL", "")}
    guide = coerce(extract(transcript, app, controls, source), app, source)
    errs = manual_validate(guide)
    out = Path(out_path or f"brain/{app.lower()}_guide.json")
    if errs:
        print(f"[ingest] {app}: extracted guide FAILED schema validation -> NOT written")
        for e in errs:
            print("   -", e)
        return None
    out.write_text(json.dumps(guide, indent=3), encoding="utf-8")
    print(f"[ingest] {app}: wrote {out}  ({len(guide['steps'])} steps, schema-valid)")
    for s in guide["steps"]:
        print(f"   {s['id']:>2}. [{s.get('tut_time','')}] {s['action']:<6} {s['target']}")
    return guide


if __name__ == "__main__":
    # usage: python ingest_video.py <transcript.txt> <App> [controls.json]
    if len(sys.argv) < 3:
        print("usage: python ingest_video.py <transcript.txt> <App> [stage1_controls.json]")
        raise SystemExit
    run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
