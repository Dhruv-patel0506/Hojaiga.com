"""LIVE deep-knowledge benchmark v2: OBS Studio via the PRODUCTION scan_app_tool, then WAIT for the
background learner IN THIS PROCESS (lesson v1: the learner is a daemon thread - exiting the driver
kills it mid-learn) and read every count under the REAL app key ('obs studio', lesson v1b: v1 polled
'obs'). Proves the user's chain: '+' -> dialog observed -> items -> composed recipe -> goal match."""
import os, re, sys, time, json, subprocess
sys.path.insert(0, r"d:\new_automation\All codes")

from core_organs import organ_48_app_behavior_model as bm
from core_organs import scan_learner

KEY = "obs studio"                       # the exact key the scan/learner write (learn_state row proves it)
model = bm.get_model()

def counts():
    c = model._conn
    d = c.execute("SELECT COUNT(*) n FROM bm_dialogs WHERE app_key=? AND source LIKE 'live%'", (KEY,)).fetchone()["n"]
    t = c.execute("SELECT COUNT(*) n FROM bm_transitions WHERE app_key=?", (KEY,)).fetchone()["n"]
    r = c.execute("SELECT COUNT(*) n FROM bm_templates WHERE app_key=? AND seed_note LIKE 'composed%'", (KEY,)).fetchone()["n"]
    l = c.execute("SELECT COUNT(*) n FROM bm_commands WHERE app_key=? AND source='learned'", (KEY,)).fetchone()["n"]
    f = c.execute("SELECT COUNT(*) n FROM bm_frontier WHERE app_key=? AND status='explored'", (KEY,)).fetchone()["n"]
    return {"dialogs": d, "transitions": t, "recipes": r, "learned": l, "frontier_explored": f}

print("BEFORE:", json.dumps(counts()))
print("quality before:", bm.knowledge_quality(model, KEY)["one_line"])

# v3 reset: the v2 run 'converged' on a startup QMessageBox (frontier had ONE row - the dialog's OK
# button). That converged version_hash makes scan_learner decline re-learning. Drop the stale learning
# STATE and frontier only; keep commands/transitions/dialogs so the counts below stay honest.
model._conn.execute("DELETE FROM bm_learn_state WHERE app_key=?", (KEY,))
model._conn.execute("DELETE FROM bm_frontier WHERE app_key=?", (KEY,))
model._conn.commit()
print("[bench] reset learn_state + frontier (kept commands/transitions/dialogs for honest deltas)")

def obs_pids():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True).stdout
    return {int(p.split(",")[1].strip('"')) for p in o.splitlines() if "obs64" in p}

# OBS should already be running (launched by the v1 scan). If not, the production scan will start it.
t0 = time.time()
from core_organs import organ_01_crewai_engine as o1
out1 = o1.scan_app_tool.func(app_name="obs")
s1 = str(out1)
print(f"[bench] scan #1 returned in {time.time()-t0:.1f}s | learner line:",
      next((ln.strip() for ln in s1.splitlines() if "behavior learning" in ln), "NOT PRESENT"),
      "| quality line:", next((ln.strip() for ln in s1.splitlines() if "commands OBSERVED" in ln), "-"))

def wait_learner(tag, max_s=480):
    end = time.time() + max_s
    last = ""
    while time.time() < end:
        st = scan_learner.status(KEY, model=model)
        s = st.get("status")
        if s != last:
            print(f"[bench] {tag} status: {s} | {str(st.get('why') or '')[:160]}")
            last = s
        if s in ("complete", "partial", "failed", "stale", "none"):
            return s, st
        time.sleep(5)
    return "TIMEOUT-WAITING", {}

st1, stt1 = wait_learner("run1")
mid = counts()
print("AFTER RUN1:", json.dumps(mid))
if st1 == "stale":
    print("[bench] learner was stale (thread died with v1 driver); scan #2 re-arms it")
out2 = o1.scan_app_tool.func(app_name="obs")
st2, stt2 = wait_learner("run2")
after = counts()
print("AFTER RUN2:", json.dumps(after))

rows = [dict(r) for r in model._conn.execute(
    "SELECT title, via, source, controls_json FROM bm_dialogs WHERE app_key=? AND source LIKE 'live%' ORDER BY ts",
    (KEY,))]
all_items = []
for r in rows:
    try:
        ctrl = json.loads(r["controls_json"] or "[]")
    except Exception:
        ctrl = []
    items = [c.get("name") for c in ctrl if c.get("kind") in ("listitem", "treeitem", "menuitem") and c.get("name")]
    all_items += items
    print(f"[dialog] via '{r['via'][:44]}' title '{(r['title'] or '')[:36]}' items: {items[:12]}")
tpls = [dict(r) for r in model._conn.execute(
    "SELECT name, steps_json FROM bm_templates WHERE app_key=? AND seed_note LIKE 'composed%'", (KEY,))]
print(f"[bench] composed recipes ({len(tpls)}):", [t["name"] for t in tpls][:24])
print("QUALITY:", bm.knowledge_quality(model, KEY)["one_line"])
ls = model.get_learn_state(KEY)
print("learn_state stats:", json.dumps(json.loads((ls or {}).get("stats_json") or "{}"), default=str)[:600])

checks = []
checks.append(("scan reported the background learner", "behavior learning" in s1))
checks.append(("learner reached a finished state", st1 in ("complete", "partial") or st2 in ("complete", "partial")))
checks.append(("dialog schemas OBSERVED and persisted", after["dialogs"] >= 1))
checks.append(("transitions recorded (a button's EFFECT)", after["transitions"] >= 1))
checks.append(("commands promoted to learned (earned)", after["learned"] >= 1))
# frontier: this bench RESET the frontier rows (v3 lesson), so 'explored' can only grow on a run that had
# NEW surfaces to open. Either >=3 rows explored THIS life, or honest total convergence: learn_state says
# complete/converged AND quality reports 0 surfaces still unopened (nothing left to explore - verified v11).
_ls = json.dumps(json.loads((model.get_learn_state(KEY) or {}).get("stats_json") or "{}"), default=str)
_clean_conv = ('"converged": true' in _ls) and ("0 surfaces still unopened" in bm.knowledge_quality(model, KEY)["one_line"])
checks.append(("frontier surfaces explored (or fully converged)", after["frontier_explored"] >= 3 or _clean_conv))
checks.append(("recipes composed from observed dialogs", after["recipes"] >= 1))
if after["recipes"] >= 1:
    m = model.match_template(KEY, "add display capture source to my scene")
    checks.append(("'add display capture source' goal finds a composed recipe", bool(m)))
    print("[bench] match ->", m.name if m else None)
capture_seen = bool(re.search(r"display|window|screen|capture|audio|video|source", " ".join(all_items).lower()))
print("\n================ RESULT ================")
for name, okv in checks:
    print(("PASS  " if okv else "FAIL  ") + name)
fails = [c for c in checks if not c[1]]
print("DEEP KNOWLEDGE CHAIN:", "WORKING end to end on OBS Studio" if not fails else f"PARTIAL - {[f[0] for f in fails]}")
print(f"(capture-family items seen: {capture_seen}; sample: {all_items[:16]})")

# cleanup: close the OBS processes our scans launched (none existed before v1)
for pid in obs_pids():
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
    print("[bench] terminated obs64 pid", pid)
print(f"[bench] done in {time.time()-t0:.0f}s")
