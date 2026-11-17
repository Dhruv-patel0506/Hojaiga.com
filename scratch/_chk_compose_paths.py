"""Offline proof of compose_paths + knowledge_quality (organ_48): synthetic observed data in a
temp DB, then assert real recipes are composed with gateable steps, and quality counts them."""
import os, sys, json, tempfile, sqlite3, time
sys.path.insert(0, r"d:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_BEHAVIOR_DB", tempfile.mktemp(suffix="_compose.db"))

from core_organs import organ_48_app_behavior_model as bm
from core_organs import knowledge_store as ks

model = bm.BehaviorModel(os.environ["HOJAIGA_BEHAVIOR_DB"])
ks.ensure(model)
key = bm._app_key("obs studio")

# the opener: what the scan/learner would have catalogued from the OBS toolbar
cid = model.upsert_command(key, {"name": "Add", "goal": "Add a new source", "menu_path": "Sources Toolbar > Add",
                                 "verb": "invoke", "risk": "E1", "source": "scan"},
                           source="catalog", origin="layout", evidence="test")
# a classic menu opener (should route verb=menu)
model.upsert_command(key, {"name": "New", "goal": "new", "menu_path": "File > New", "verb": "menu",
                           "risk": "E1", "menu_id": 42000, "source": "scan"},
                     source="catalog", origin="e0:File", evidence="test")

dlg_controls = [
    {"kind": "list", "name": "", "aid": "OBSExtras", "enabled": True, "patterns": []},
    {"kind": "listitem", "name": "Display Capture", "aid": "", "enabled": True, "patterns": ["select"]},
    {"kind": "listitem", "name": "Window Capture", "aid": "", "enabled": True, "patterns": ["select"]},
    {"kind": "listitem", "name": "Browser", "aid": "", "enabled": True, "patterns": ["select"]},
    {"kind": "button", "name": "OK", "aid": "", "enabled": True, "patterns": ["invoke"]},
    {"kind": "button", "name": "Cancel", "aid": "", "enabled": True, "patterns": ["invoke"]},
    {"kind": "_roles", "commit": "OK", "cancel": "Cancel", "fields": [], "toggles": []},
]
model._conn.execute(
    "INSERT OR REPLACE INTO bm_dialogs(dialog_id, app_key, title, controls_json, source, via, n_controls, ts)"
    " VALUES (?,?,?,?,?,?,?,?)",
    ("dlg_test1", key, "Add/Remove Sources", json.dumps(dlg_controls), "live:uia",
     "Sources Toolbar > Add", len(dlg_controls), time.time()))
# a dialog whose opener is E2 -> must NEVER be composed
model.upsert_command(key, {"name": "Disconnect", "goal": "disconnect", "menu_path": "x", "verb": "invoke",
                           "risk": "E2", "source": "scan"}, source="catalog", origin="layout", evidence="t")
model._conn.execute(
    "INSERT OR REPLACE INTO bm_dialogs(dialog_id, app_key, title, controls_json, source, via, n_controls, ts)"
    " VALUES (?,?,?,?,?,?,?,?)",
    ("dlg_test2", key, "Confirm", json.dumps([{"kind": "menuitem", "name": "Yes"}]), "live:win32",
     "Disconnect", 1, time.time()))
model._conn.commit()

out = bm.compose_paths(model, "OBS Studio")
print("compose_paths:", out)
assert out["composed"] == 3, f"expected 3 recipes (3 items on the Add dialog), got {out['composed']}"
assert out["dialogs_used"] == 1, out
rows = [dict(r) for r in model._conn.execute("SELECT * FROM bm_templates WHERE app_key=?", (key,))]
by_name = {r["name"]: r for r in rows}
assert "add--display-capture" in by_name, sorted(by_name)
tpl = json.loads(by_name["add--display-capture"]["steps_json"])
assert [s["id"] for s in tpl] == ["open", "choose-display-capture", "close"], tpl
assert all(s.get("post") for s in tpl), "every step must be gateable (machine-checkable postcondition)"
assert tpl[0]["do"][0]["name"] == "Add" and tpl[0]["post"][0]["title_contains"] == "add/remove sources"
assert tpl[1]["do"][0]["name"] == "Display Capture" and tpl[1]["post"][0]["kind"] == "element_present"
assert tpl[2]["do"][0]["verb"] == "key", "close step posts ESC, never clicks OK"
assert "OK" not in json.dumps(tpl), "recipe must NOT commit: cancel-only by construction"
assert not any("disconnect" in n for n in by_name), "E2 opener must never be composed into a path"

# match_template must FIND the recipe for a natural goal (this is the Jarvis-side payoff)
m = model.match_template("obs studio", "add display capture to my scene")
print("match:", m.name if m else None, "| score:", round(m.score, 2) if m else "-")
assert m and "display-capture" in m.name, "a 'add display capture' goal must route to the composed recipe"

# idempotent: composing again replaces, does not duplicate
out2 = bm.compose_paths(model, "OBS Studio")
assert out2["composed"] == 3
n = model._conn.execute("SELECT COUNT(*) c FROM bm_templates WHERE app_key=?", (key,)).fetchone()["c"]
assert n == 3, n

q = bm.knowledge_quality(model, key)
print("quality:", json.dumps(q, indent=1))
assert q["dialogs_mapped"] == 2 and q["recipes"] == 3 and q["commands"] == 3, q

# _opener_label edge cases
assert bm._opener_label("@tab:Home@ Font > More Options") == "More Options"
assert bm._opener_label("Sources Toolbar > Add") == "Add"
assert bm._opener_label("Add") == "Add"
print("ALL COMPOSE CHECKS PASSED")
