p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
NL = chr(92) + "n"
s += '''

# ---------------------------------------------------------------------------------------------------- descriptions + workflows
def describe(key: str, control: str, *, use_model: bool = True) -> Dict[str, Any]:
    """What does this control DO, in plain words. The structural facts come from the map (certain); the one-sentence meaning comes from the local language model
    reading ONLY that context (marked inferred - it is the model's understanding of the label, not something the scan measured)."""
    ex = explain(key, control)
    if not ex.get("ok"):
        return ex
    ex["trust"] = "measured (structure)"
    if not use_model:
        return ex
    try:
        from . import llm
        if not llm.available():
            return ex
        ctx = {"control": ex["control"], "where": ex["text"].replace("**", ""), "shortcut": ex["shortcut"], "outcome": ex["outcome"].replace("**", ""), "dialog": ex["dialog"]}
        r = llm.chat("You explain desktop-application commands to a beginner. Using ONLY the context, say in 1-2 plain sentences what the control does and when a person would use it. "
                     "Do not invent options that are not in the context. Reply JSON: {\\"meaning\\": \\"...\\"}", json.dumps(ctx), timeout=60, max_tokens=160)
        mean = (r.get("json") or {}).get("meaning") if isinstance(r.get("json"), dict) else None
        if isinstance(mean, str) and mean.strip():
            ex["meaning"] = mean.strip()
            ex["meaning_trust"] = "inferred (local model reading the scanned context)"
    except Exception:
        pass
    return ex


def workflow(key: str, task: str, *, use_model: bool = True) -> Dict[str, Any]:
    """A multi-step task ("make a short presentation with a title slide, a picture and a table"): decomposed into sub-goals, each answered with its best route from the
    scanned map (and a programmatic alternative where the object model has one). Ungrounded steps are said to be ungrounded."""
    from . import planner
    from core_organs import organ_48_app_behavior_model as bm
    st = C.get_store()
    pl = planner.plan(key, task, st, bm.get_model(), use_model=use_model)
    steps = []
    for stp in pl["steps"]:
        rts = [r for r in stp.get("routes", []) if r["effector"] in ("ribbon_path", "dialog_path", "menu_path", "invoke_control", "api_operator", "com_method")]
        item = {"n": stp["n"], "goal": stp["goal"], "grounded": stp["grounded"]}
        if rts:
            item["route"] = rts[0]["label"]
            item["why"] = rts[0].get("why", "")
            item["effector"] = rts[0]["effector"]
        elif stp.get("chosen"):
            item["route"] = stp["chosen"]["label"]
            item["effector"] = stp["chosen"]["effector"]
        api = api_routes(key, stp["goal"], limit=1)
        if api:
            item["programmatic"] = api[0]["call"] + " (" + api[0]["via"] + ")"
        steps.append(item)
    lines = [f"Plan for: {task}", ""]
    for i in steps:
        lines.append(f"{i['n']}. {i['goal']}" + ("" if i["grounded"] else "  [NOT GROUNDED: the scan found nothing for this]"))
        if i.get("route"):
            lines.append(f"   {i['route']}" + (f" - {i['why']}" if i.get("why") else ""))
        if i.get("programmatic"):
            lines.append(f"   or by code: {i['programmatic']}")
    return {"ok": True, "steps": steps, "complete": pl.get("complete"), "answer": "''' + NL + '''".join(lines), "decomposition": pl.get("decomposition")}
'''
open(p, "w", encoding="utf-8").write(s)

# CLI
p = r"D:\new_automation\All codes\core_organs\hojaiga_atlas.py"
s = open(p, encoding="utf-8").read()
s = s.replace('''    python hojaiga_atlas.py overview <app>''', '''    python hojaiga_atlas.py describe <app> "<control>"       what a control does (structure measured; one-line meaning from the local model)
    python hojaiga_atlas.py workflow <app> "<task>"          a multi-step task as a sequence of routes (+ programmatic alternatives)
    python hojaiga_atlas.py overview <app>''', 1)
s = s.replace('''    if cmd == "overview":''', '''    if cmd == "describe":
        _out(teach.describe(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv), as_json)
        return 0
    if cmd == "workflow":
        r = teach.workflow(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv)
        print(r["answer"]) if not as_json else _out(r, True)
        return 0
    if cmd == "overview":''', 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
