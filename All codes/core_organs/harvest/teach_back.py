"""
harvest.teach_back -- ask the knowledge pool to TEACH an app back, and time it.

    python -m core_organs.harvest.teach_back excalidraw                      lesson: what kind of app, the shortcuts (proven first), the drag / modifier gestures
    python -m core_organs.harvest.teach_back excalidraw --ask "undo"         the answer to one question, with the row it came from
    python -m core_organs.harvest.teach_back excalidraw --quiz 5             5 questions in the terminal: it asks for a shortcut, you type it, it marks you
    python -m core_organs.harvest.teach_back --list                          every app the pool has rows for

Read-only and offline: no window is opened, no key is pressed, no network, no model. Every stage prints how many milliseconds it took. A row marked PROVEN was pressed in a real
browser and its effect observed; a row marked LEAD was read off a video or heard in one and has not been tried.
"""
from __future__ import annotations

import argparse
import contextlib
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


def pretty(chord: str) -> str:
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in (chord or "").split("+"))


def app_keys(rag: Any) -> Dict[str, int]:
    from core_organs.rag import lt
    out: Dict[str, int] = {}
    for r in lt.fetch(rag.fast.st, "fast_paths", "app_key != ''", 100000):
        out[r["app_key"]] = out.get(r["app_key"], 0) + 1
    return out


def resolve_key(rag: Any, name: str, keys: Optional[Dict[str, int]] = None) -> Tuple[str, List[str]]:
    """The app key for what the person typed: an exact key, else the key that contains the text (webapp:excalidraw.com for 'excalidraw'), preferring the one with most rows."""
    keys = keys if keys is not None else app_keys(rag)
    n = re.sub(r"[^a-z0-9.]+", "", (name or "").lower())
    if name in keys:
        return name, []
    hits = sorted((k for k in keys if n and n in re.sub(r"[^a-z0-9.]+", "", k.lower())), key=lambda k: -keys[k])
    return (hits[0] if hits else ""), hits[1:5]


def rows_of(rag: Any, key: str) -> List[Dict[str, Any]]:
    """Hotkey rows of one app with their CURRENT trust / verified state (the overlay is applied by find())."""
    from core_organs.rag import lt
    out = []
    for r in lt.fetch(rag.fast.st, "fast_paths", f"app_key = {lt.q(key)}", 2000):
        if r.get("kind") != "hotkey" or not r.get("payload"):
            continue
        cur = None
        with contextlib.suppress(Exception):
            cur = rag.fast.find(key, r["task_pattern"], r["payload"])
        cur = cur or r
        out.append({"action": r["task_pattern"], "chord": r["payload"], "trust": cur.get("trust", r.get("trust", "")), "verified": bool(cur.get("verified")),
                    "context": str(cur.get("context") or r.get("context") or ""), "note": str(cur.get("notes") or cur.get("note") or "")})
    return sorted(out, key=lambda x: (not x["verified"], x["action"].lower()))


def shown(action: str) -> str:
    """Display name: a run-together OCR name ('CopytoclipboardasPNG') is split with the pool's own vocabulary; the stored row is not changed."""
    if re.search(r"[A-Za-z]{15,}", action or ""):
        with contextlib.suppress(Exception):
            from core_organs.harvest import fact_cleaner as FC
            return FC.clean_action(action) or action
    return action


def mark(r: Dict[str, Any]) -> str:
    if "REFUTED" in r.get("context", "").upper():
        return "REFUTED"
    return "PROVEN" if r["verified"] else ("lead  " if r["trust"] in ("web", "transcript", "llm") else r["trust"][:6].ljust(6))


def lesson(rag: Any, key: str, rows: Sequence[Dict[str, Any]], top: int = 25) -> List[str]:
    out = [f"=== {key} ==="]
    with contextlib.suppress(Exception):
        from core_organs.harvest import transfer_priors as TP
        a = TP.archetype_map().get(key, "")
        if a:
            out.append(f"kind of app: {a.replace('_', ' ')}")
    nv = sum(1 for r in rows if r["verified"])
    out.append(f"{len(rows)} shortcuts in the pool: {nv} PROVEN by a real key press, {len(rows) - nv} leads from videos")
    out.append("")
    out.append("SHORTCUTS (proven first)")
    for r in list(rows)[:top]:
        flag = f"   [{r['context'][:90]}]" if mark(r) == "REFUTED" else ""
        out.append(f"  {pretty(r['chord']).ljust(20)} {shown(r['action']):<44} {mark(r)}{flag}")
    if len(rows) > top:
        out.append(f"  ... and {len(rows) - top} more (use --ask or --quiz)")
    with contextlib.suppress(Exception):
        from core_organs.harvest import consolidate as C
        g = C.AppGraph.load(key)
        gs = g.gestures() if hasattr(g, "gestures") else []
        if gs:
            out += ["", "MODIFIER GESTURES (hold a key while you drag / click)"]
            for x in gs[:8]:
                out.append(f"  hold {x['modifier'].upper()} while {x['gesture']}: {x.get('effect', '')}   ({x.get('videos', 1)} video(s))")
        dr = g.drags() if hasattr(g, "drags") else []
        if dr:
            out += ["", f"DRAG PATHS seen in the videos: {len(dr)} (the shapes are searchable as vectors)"]
        out += ["", f"learned from {len(g.videos)} video(s); {len(g.edges)} distinct on-screen actions seen"]
    return out


def answer(rag: Any, key: str, question: str, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Best rows for a question: the lexicon's own matcher first (aliases, trust), then word overlap with the action names."""
    qs = set(re.findall(r"[a-z]{3,}", question.lower())) - {"how", "the", "can", "you", "what", "does", "this", "that", "with", "for", "and", "do", "to", "i"}
    by_chord = {(r["action"].lower(), r["chord"]): r for r in rows}
    got: List[Tuple[float, Dict[str, Any]]] = []
    with contextlib.suppress(Exception):
        for m in rag.lex.resolve(key, question, limit=6):
            label = rag.lex.label_of(m.command_id).lower()
            for (a, c), r in by_chord.items():
                if a == label:
                    got.append((m.score + (0.5 if r["verified"] else 0), r))
    for r in rows:
        w = set(re.findall(r"[a-z]{3,}", r["action"].lower()))
        if qs and w & qs:
            got.append((len(w & qs) / max(1, len(w)) + (0.5 if r["verified"] else 0), r))
    seen, out = set(), []
    for s, r in sorted(got, key=lambda x: -x[0]):
        if (r["action"], r["chord"]) not in seen:
            seen.add((r["action"], r["chord"]))
            out.append(r)
    return out[:4]


def quiz(rows: Sequence[Dict[str, Any]], n: int, ask=input) -> Dict[str, int]:
    pool = [r for r in rows if re.search(r"[A-Za-z]{3}", r["action"]) and len(r["action"].split()) <= 6]
    random.shuffle(pool)
    right = 0
    asked = pool[:n]
    for i, r in enumerate(asked, 1):
        norm = lambda s: "+".join(sorted(p for p in re.split(r"[\s+]+", s.lower().strip().replace("control", "ctrl").replace("command", "cmd")) if p))
        reply = ask(f"  Q{i}. Shortcut for '{r['action']}'?  ")
        ok = norm(reply) == norm(r["chord"])
        right += ok
        print(("   correct" if ok else f"   no - it is {pretty(r['chord'])}") + ("" if r["verified"] else "   (a lead, not yet proven)"))
    return {"asked": len(asked), "right": right}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Teach an app back from the knowledge pool (offline, read-only, timed).")
    ap.add_argument("app", nargs="?", default="")
    ap.add_argument("--ask", default="")
    ap.add_argument("--quiz", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    from core_organs import rag as R
    rag = R.get_rag()
    t_open = (time.perf_counter() - t0) * 1000
    keys = app_keys(rag)
    if a.list or not a.app:
        for k, n in sorted(keys.items(), key=lambda kv: -kv[1]):
            print(f"{n:4d}  {k}")
        return 0
    key, alts = resolve_key(rag, a.app, keys)
    if not key:
        print(f"no app matching '{a.app}'. Try --list.")
        return 1
    t1 = time.perf_counter()
    rows = rows_of(rag, key)
    t_rows = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    if a.ask:
        res = answer(rag, key, a.ask, rows)
        print(f"Q: {a.ask}   (app: {key})")
        for r in res or []:
            print(f"  press {pretty(r['chord'])}  -> {shown(r['action'])}   [{mark(r).strip()}]  {r['context'][:90]}")
        if not res:
            print("  the pool has no row for that. (It has " + str(len(rows)) + " shortcuts for this app; run without --ask to see them.)")
    elif a.quiz:
        print(f"=== quiz on {key}: type the shortcut (e.g. ctrl+s) ===")
        r = quiz(rows, a.quiz)
        print(f"score {r['right']}/{r['asked']}")
    else:
        print("\n".join(lesson(rag, key, rows, a.top)))
    t_teach = (time.perf_counter() - t2) * 1000
    print(f"\n[timing] open pool {t_open:.0f} ms | read this app's rows {t_rows:.0f} ms | build the answer {t_teach:.0f} ms | total {(time.perf_counter() - t0) * 1000:.0f} ms"
          + (f" | other matches: {', '.join(alts)}" if alts else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
