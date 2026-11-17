p = r"D:\new_automation\All codes\core_organs\atlas\planner.py"
s = open(p, encoding="utf-8").read()
old = "    # --- command-line switches"
new = '''    # --- the scanned UI map (ribbon / menu / File view): step-by-step routes with the items inside drop-downs and the dialogs they open
    try:
        from . import teach, uimap as _um
        from . import explorer as _xp
        tr = teach.routes_for(key, subgoal, limit=4, use_model=False)
        for r in tr.get("routes", []) if tr.get("ok") else []:
            if r["score"] < 2.5:
                continue
            risky = bool(_xp.UNSAFE_RX.search(r["control"]) or _xp.SENSITIVE_RX.search(r["control"]) or _um.RUNTIME_RX.search(r["control"]))
            routes.append({"effector": "ribbon_path", "detail": {"path": r["path"], "shortcut": r["shortcut"], "dialog": r["dialog"]}, "label": r["text"].replace("**", "")[:140],
                           "why": (r["outcome"] or "route read from the live window") + ("; needs a selection first" if r["preconditions"] else ""), "trust": "measured", "risk": "E2" if risky else "EU",
                           "score": 2.2 + min(2.0, r["score"] / 6.0) - (0.6 if r["preconditions"] else 0.0), "expect": [], "verified": False, "evidence": [f"uimap:{key}"]})
    except Exception:
        pass
    # --- command-line switches'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('EXECUTABLE = ("invoke_control", "menu_path", "key", "wm_command", "dialog_path")', 'EXECUTABLE = ("invoke_control", "menu_path", "key", "wm_command", "dialog_path", "ribbon_path")')
old = '''            elif ch["effector"] == "key":'''
new = '''            elif ch["effector"] == "ribbon_path":
                from . import uimap as _um
                dr = _um.drive(hwnd, d.get("path") or [])
                ok, how = bool(dr.get("ok")), dr.get("why") or "; ".join(str(x) for x in dr.get("steps", []))[:200]
            elif ch["effector"] == "key":'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("planner patched")
