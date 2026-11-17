import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine
e = VerbAliasEngine(AppCatalog())
for q in ("obs", "obs studio", "open obs"):
    print(q, "->", e.resolve_detailed(q))
