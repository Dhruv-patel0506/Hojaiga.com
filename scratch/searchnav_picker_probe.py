"""Offline check of the searchnav field picker against the REAL Settings catalog."""
import sys, json, re
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import executor as X
from core_organs.professor.harvest import Catalog

cat = Catalog.load(r"d:\new_automation\data\professor\catalogs\systemsettings.json") if hasattr(Catalog, "load") else None
if cat is None:
    d = json.load(open(r"d:\new_automation\data\professor\catalogs\systemsettings.json", encoding="utf-8"))
    from core_organs.professor.harvest import Verb
    cat = type("C", (), {"verbs": [Verb(**{k: v for k, v in w.items() if k in Verb.__dataclass_fields__}) for w in d.get("verbs", [])]})()
FR = X.Executor.FIELD_ROLES
SRX = X.Executor.SEARCH_RX
cands = [c for c in cat.verbs if c.enabled and SRX.search(c.label or "")
         and ((c.role or "").lower() in FR or "search" in " ".join(c.path).lower()
              or (c.role or "").lower() in ("button", "dropdown"))]
pick = next((c for c in cands if (c.role or "").lower() in FR), None) or (cands[0] if cands else None)
print("cands:", [(c.label, c.role) for c in cands])
print("pick :", pick.label if pick else None, "|", pick.role if pick else None, "|", pick.aid if pick else None)
assert pick is not None and pick.aid == "CommandSearchTextBox", "picker did not choose the real box"
print("PICKER OK")
