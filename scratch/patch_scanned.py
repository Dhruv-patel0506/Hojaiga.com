import ast
import io
import json

P = "D:/new_automation/All codes/core_organs/professor/checkpoints.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


rep('''def app_status(stages: Dict[str, Dict[str, str]], rep: Dict[str, Any]) -> str:
    if stages.get("launched", {}).get("state") == "fail" or rep.get("error"):
        return "failed"
    if all(s["state"] in ("ok", "skipped") for s in stages.values()):
        return "done"
    return "partial"''', '''def app_status(stages: Dict[str, Dict[str, str]], rep: Dict[str, Any], guide_expected: bool = True) -> str:
    """done | scanned (everything fine, but the guide was not run: a later full run still has work to do) | partial | failed"""
    if stages.get("launched", {}).get("state") == "fail" or rep.get("error"):
        return "failed"
    if all(s["state"] in ("ok", "skipped") for s in stages.values()):
        return "done" if guide_expected else "scanned"
    return "partial"''')
rep("status = app_status(stages, rep)", "status = app_status(stages, rep, guide_expected=guide)")
rep('''    lines += ["", "✔ done · ◐ partly (see the report) · ✖ failed · – not applicable · · not run yet", ""]''',
    '''    lines += ["", "✔ done · ◐ partly (see the report) · ✖ failed · – not applicable · · not run yet.   status 'scanned' = scan-only run, the guide still has to be run", ""]''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
f = io.open(T, "r", encoding="utf-8").read()
old = '''"launch_failure_is_failed": st_dead == "failed" and s_dead["launched"]["state"] == "fail",'''
assert old in f
f = f.replace(old, old + '''
                  "scan_only_is_not_done": CK.app_status(s_good, good, guide_expected=False) == "scanned",''', 1)
ast.parse(f)
io.open(T, "w", encoding="utf-8", newline="\n").write(f)

# the smoke run (scan only) must not make the first real run skip Notepad
SP = "D:/new_automation/data/professor/scan_checkpoints.json"
st = json.load(io.open(SP, "r", encoding="utf-8"))
if st.get("apps", {}).get("notepad", {}).get("status") == "done":
    st["apps"]["notepad"]["status"] = "scanned"
    json.dump(st, io.open(SP, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("ok", {k: v["status"] for k, v in st.get("apps", {}).items()})
