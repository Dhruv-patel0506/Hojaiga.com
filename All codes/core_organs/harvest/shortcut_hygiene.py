"""
shortcut_hygiene -- which of the unproven shortcut rows in the RAG cannot possibly be a keyboard command of that app, without pressing anything.

    python -m core_organs.harvest.shortcut_hygiene            report only (reports/shortcut_hygiene/<stamp>.json + .md)
    python -m core_organs.harvest.shortcut_hygiene --apply    also write 'JUNK (static): <reason>' into the row's context (text only: nothing is deleted, verified stays as it was)

Rules (each is a fact about keys, not a guess about a program):
  not_a_chord      a part of the chord is not a key (a word that came from a sentence: 'show', 'hear', 'ctrl+show windows')
  mac_only         command / cmd / option: macOS modifiers, on a Windows app row
  operating_system the chord belongs to Windows itself (Win+..., Ctrl+Alt+Del, PrtScn), not to the application
  goal_is_chord    the goal text is the chord itself ("Control+S"), so the row says nothing about WHAT it does
  tutorial_step    the goal is an instruction sentence from a how-to ("Press F6 until ...", "To close the Keyboard dialog box ..."), not a command name
Rows that pass are 'plausible': still unproven until a live check. A verified row is never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence

MODS = {"ctrl", "control", "alt", "shift", "win", "meta", "super"}
MAC = {"cmd", "command", "option", "opt", "⌘", "⌥"}
NAMED = {"enter", "return", "esc", "escape", "tab", "space", "delete", "del", "backspace", "up", "down", "left", "right", "home", "end", "pageup", "pagedown", "page_up", "page_down", "insert", "plus", "minus",
         "prtscn", "printscreen", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12", "numpad_minus", "numpad_plus", "period", "comma", "slash", "backslash", "wheelupmouse",
         "leftmouse", "rightmouse", "wheeldownmouse", "ret", "back_space", "middlemouse", "accent_grave", "semicolon", "quote", "equal", "grless", "numpad_period", "numpad_slash", "numpad_asterix", "pause", "caps_lock", "left_bracket", "right_bracket", "lmb", "rmb", "left_arrow", "right_arrow", "up_arrow", "down_arrow", "page_up", "page_down", "alt+f"}
OS_CHORDS = {"ctrl+alt+delete", "ctrl+shift+esc", "alt+tab", "alt+f4", "prtscn"}


def is_key(tok: str) -> bool:
    t = tok.strip().lower()
    return bool(t) and (len(t) == 1 or t in NAMED or t in MODS or t in MAC or re.fullmatch(r"f\d{1,2}", t) is not None or re.fullmatch(r"numpad_?\w+", t) is not None or t in {"↑", "↓", "←", "→", "±"})


def classify(app_key: str, chord: str, goal: str) -> Dict[str, str]:
    """{'verdict': 'junk'|'unnamed'|'plausible', 'reason': ...} for a hotkey row (chord like 'ctrl+shift+p'). junk: cannot be a keyboard command of that app. unnamed: the chord may be real but nothing says what it does."""
    c = (chord or "").strip().lower()
    parts = [p for p in re.split(r"\+", c) if p] or [c]
    if c.endswith("++"):
        parts = parts[:-1] + ["+"]
    g = (goal or "").strip()
    if not c:
        return {"verdict": "junk", "reason": "not_a_chord: empty"}
    if any(p in MAC for p in parts) and not app_key.lower().startswith(("webapp:", "chrome", "code")):
        return {"verdict": "junk", "reason": "mac_only: " + c}
    if any(p in MAC for p in parts):
        return {"verdict": "junk", "reason": "mac_only: " + c}
    bad = [p for p in parts if not is_key(p)]
    if bad:
        return {"verdict": "junk", "reason": f"not_a_chord: '{bad[0]}' is not a key"}
    if "win" in parts or "meta" in parts or c in OS_CHORDS or "prtscn" in parts:
        return {"verdict": "junk", "reason": "operating_system: " + c}
    flat = re.sub(r"[^a-z0-9+]", "", g.lower())
    if flat and flat == re.sub(r"[^a-z0-9+]", "", c.replace("control", "ctrl")) or flat == re.sub(r"[^a-z0-9+]", "", c):
        return {"verdict": "unnamed", "reason": "goal_is_chord: the chord may be real, but the goal text only repeats the keys"}
    if re.match(r"^(press|to |on your|from any|do one of|choose |use the|find the|enter a|in the|on the|at the top|from the list|toolbar is)\b", g.lower()) or len(g.split()) >= 14 or re.search(r"\b(until you hear|you hear)\b", g.lower()):
        return {"verdict": "unnamed", "reason": "tutorial_step: the chord may be real, but the goal is an instruction sentence, not a command name"}
    return {"verdict": "plausible", "reason": ""}


def run(rag: Any, apply: bool = False, out_dir: str = "") -> Dict[str, Any]:
    df = rag.fast.st.table("fast_paths").to_pandas().drop(columns=["vector"])
    rows = df[(df["kind"] == "hotkey") & (~df["verified"].astype(bool))]
    res: List[Dict[str, Any]] = []
    for _, r in rows.iterrows():
        v = classify(str(r["app_key"]), str(r["payload"]), str(r["task_pattern"]))
        res.append({"fast_id": r["fast_id"], "app": r["app_key"], "chord": r["payload"], "goal": str(r["task_pattern"])[:90], "trust": r["trust"], **v, "context": str(r.get("context") or "")})
    junk = [x for x in res if x["verdict"] == "junk"]
    applied = 0
    if apply:
        for x in junk:
            if x["context"].startswith(("JUNK", "REFUTED")):
                continue
            note = f"JUNK (static): {x['reason']}" + (f" | was: {x['context'][:100]}" if x["context"] else "")
            rag.fast.annotate(x["fast_id"], note)
            applied += 1
    by_app: Dict[str, Dict[str, int]] = {}
    for x in res:
        d = by_app.setdefault(x["app"], {"rows": 0, "junk": 0})
        d["rows"] += 1
        d["junk"] += x["verdict"] == "junk"
    by_reason: Dict[str, int] = {}
    for x in junk:
        k = x["reason"].split(":")[0]
        by_reason[k] = by_reason.get(k, 0) + 1
    unnamed = [x for x in res if x["verdict"] == "unnamed"]
    summary = {"unproven_hotkey_rows": len(res), "junk": len(junk), "unnamed_goal": len(unnamed), "plausible": len(res) - len(junk) - len(unnamed), "by_reason": by_reason, "annotated": applied,
               "by_app": dict(sorted(by_app.items(), key=lambda kv: -kv[1]["rows"]))}
    out_dir = out_dir or os.path.join(r"D:\new_automation\reports", "shortcut_hygiene")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json.dump({"summary": summary, "rows": res}, open(os.path.join(out_dir, stamp + ".json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    md = [f"# Shortcut hygiene {stamp}", "", f"{len(res)} unproven hotkey rows: **{len(junk)} cannot be a keyboard command of that app**, {len(unnamed)} have a chord that may be real but a goal text that says nothing (an instruction sentence / the chord itself), {summary['plausible']} plausible (still unproven).", "",
          "By reason: " + ", ".join(f"{k} {v}" for k, v in by_reason.items()), "", "## Junk rows", ""]
    md += [f"- `{x['app']}` {x['chord']} — {x['goal'][:70]} — {x['reason']}" for x in junk] + ["", "## Chord may be real, goal text unusable", ""] + [f"- `{x['app']}` {x['chord']} — {x['goal'][:70]}" for x in unnamed]
    open(os.path.join(out_dir, stamp + ".md"), "w", encoding="utf-8").write("\n".join(md))
    summary["report"] = os.path.join(out_dir, stamp + ".md")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Static hygiene of the unproven shortcut rows.")
    ap.add_argument("--apply", action="store_true", help="write 'JUNK (static): reason' into the rows' context text")
    a = ap.parse_args(argv)
    from core_organs import rag as R
    s = run(R.get_rag(), a.apply)
    print(json.dumps({k: v for k, v in s.items() if k != "by_app"}, indent=1))
    for app, d in list(s["by_app"].items())[:14]:
        print(f"  {app:28s} rows {d['rows']:3d}  junk {d['junk']:3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
