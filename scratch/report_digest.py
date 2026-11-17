"""Read the parts of a run report that explain the wall clock: the background tree reader, the dialogs that owned the window, and the per-procedure verdicts."""
import json
import sys

p = sys.argv[1]
r = json.load(open(p, encoding="utf-8"))
print("app", r.get("app"), "result", r.get("result"), "seconds", r.get("seconds"), "counts", r.get("counts"))
print("tree_mirror:", r.get("tree_mirror"))
print("modals:", r.get("modals"))
print("eye:", r.get("eye"))
print("sibling_frames:", r.get("sibling_frames"))
print("workflows:", r.get("workflows"))
print("book_prefer_hits:", sum(1 for t in (r.get("tasks") or []) for s in (t.get("results") or []) if any("the eye" in str(x) or "modal:" in str(x) or "step cap" in str(x) for x in (s.get("tried") or []))))
for t in (r.get("tasks") or []):
    hits = [f"  step {s.get('index')} [{s.get('status')}] {x}" for s in (t.get("results") or []) for x in (s.get("tried") or [])
            if ("the eye" in str(x) or "modal:" in str(x) or "step cap" in str(x))]
    if hits:
        print(t.get("goal"), "->")
        print("\n".join(hits[:6]))
print("popups:", (r.get("popups") or [])[:3])
print("relaunches:", r.get("relaunches"))
ph = r.get("phases", {})
print("phases:", {k: (v if not isinstance(v, dict) else {kk: v[kk] for kk in list(v)[:6]}) for k, v in list(ph.items()) if k in
                  ("launch", "tree", "scan", "reuse", "guide", "practice", "close", "pointer")})
print("ml:", json.dumps(r.get("ml", {}))[:400])
print("history:", json.dumps(r.get("history", {}))[:400])
for t in r.get("tasks", []):
    print(f"  - {t.get('final'):8} {str(t.get('goal'))[:58]:58} steps={t.get('steps_in_guide')} attempts={len(t.get('attempts') or [])}")
    a = (t.get("attempts") or [{}])[-1]
    print(f"      {str(a.get('why'))[:150]}")
