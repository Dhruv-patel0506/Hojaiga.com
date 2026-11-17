"""Audit: latest live report per app -> task outcomes and failure causes grouped by kind."""
import json, glob, os, re, collections, sys

APPS = sys.argv[1:] or ["notepad", "mspaint", "winword", "powerpnt", "systemsettings", "chrome_tabs", "code", "blender", "obs64"]


def cause(why: str) -> str:
    w = why or ""
    rules = [
        (r"not found in the live tree", "control not reachable on screen (closed menu / panel / not visible)"),
        (r"value pattern|text into", "typing into the document failed"),
        (r"precondition|poll\(\) False|disabled", "precondition not met (needs a selection / object / mode)"),
        (r"needs a human|waiting for a human|sensitive|runtime|supervision", "blocked on purpose (human yes)"),
        (r"did something, but not what was expected", "verification contradicted"),
        (r"file dialog|dialog here, but none", "file dialog expected, none open"),
        (r"no such control is in the application's catalog|cannot be grounded|ungrounded", "step not grounded (no matching control)"),
        (r"gesture", "pointer gesture"),
        (r"key|chord|posted-keys", "keyboard input not accepted"),
        (r"no route produced a visible effect|nothing changed|no_effect", "no visible effect from any route"),
    ]
    for rx, k in rules:
        if re.search(rx, w, re.I):
            return k
    return "other: " + w[:70]


tot = collections.Counter()
for app in APPS:
    files = sorted(glob.glob(f"D:/new_automation/data/professor/apprun/{app}_2026*.json"), key=os.path.getmtime)
    rep = None
    for p in reversed(files):
        d = json.load(open(p, encoding="utf-8"))
        if d.get("tasks"):
            rep = (p, d)
            break
    if rep is None:
        print(f"{app:15s} no run with tasks")
        continue
    p, d = rep
    c = collections.Counter(t["final"] for t in d["tasks"])
    causes = collections.Counter(cause(t["attempts"][-1]["why"]) for t in d["tasks"] if t["final"] != "ok")
    tot.update(causes)
    print(f"{app:15s} {os.path.basename(p)[:-5]:32s} ok {c.get('ok',0)} blocked {c.get('blocked',0)} failed {c.get('failed',0)}")
    for k, n in causes.most_common():
        print(f"      {n} x {k}")
print("\nALL causes:")
for k, n in tot.most_common():
    print(f"  {n:3d}  {k}")
