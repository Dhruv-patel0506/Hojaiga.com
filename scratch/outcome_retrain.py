"""RETRAIN the outcome model from the whole state-transition history, under the new burst guard.
Fresh model -> fit_rows over every logged row in order (prequential scoring stays honest: each row is predicted before it trains) -> compare with the deployed model -> archive the old, install the new."""
import sys, os, json, shutil, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import history as HS
from core_organs.professor import config as CFG
from core_organs.professor.ml.outcome import OutcomeModel

ML = os.path.join(CFG.DATA_DIR, "ml")
h = HS.History()
rows = h.rows(since_id=0, limit=100000)
print("history rows:", len(rows))

old = OutcomeModel(os.path.join(ML, "outcome.npz"))
print("deployed (all-time prequential):", json.dumps(old.metrics(), default=str))

fresh = OutcomeModel(None)
res = fresh.fit_rows(rows, epochs=3, batch=32)
print("retrained prequential:", json.dumps(res, default=str))

stamp = time.strftime("%Y%m%d_%H%M%S")
if res["ok_accuracy"] + 0.02 < old.metrics()["ok_accuracy"]:
    print("NOT installed: retrained accuracy", res["ok_accuracy"], "is below the deployed", old.metrics()["ok_accuracy"], "- keeping the deployed model")
    raise SystemExit(0)
for ext in ("", ".json"):
    src = os.path.join(ML, "outcome.npz" + ext)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(ML, f"outcome.npz{ext}.pre_burstguard_{stamp}"))
fresh.save(os.path.join(ML, "outcome.npz"))
print("installed retrained model; old archived as outcome.npz.pre_burstguard_" + stamp)

# and what does the retrained model now say about the burst contexts the audit flagged?
from core_organs.professor.ml.outcome import context_from_row
for probe in [{"app": "blender", "label": "Blender File", "route": "click"},
              {"app": "mspaint", "label": "Save as", "route": "control"}]:
    p = fresh.predict(probe)
    print("p_ok", probe["app"], probe["label"], "->", round(p["p_ok"], 3), "likely", p["likely_effect"])
