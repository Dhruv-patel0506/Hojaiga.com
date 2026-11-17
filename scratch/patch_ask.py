p = r"D:\new_automation\All codes\core_organs\hojaiga_atlas.py"
s = open(p, encoding="utf-8").read()
old = '''def ask(target, question, **kw):
    a = atlas()
    return qa.ask(C.app_key_of(str(target)), question, a.store, a.model, **kw)'''
new = '''def ask(target, question, **kw):
    """Answer from what the scanner learned. A 'how do I ...' question is first answered from the scanned UI map (step-by-step routes); everything else, and
    anything the map cannot place, from the evidenced facts."""
    a = atlas()
    key = C.app_key_of(str(target))
    r = qa.ask(key, question, a.store, a.model, **kw)
    try:
        if teach.load_map(key):
            t = teach.howto(key, question, use_model=False)
            if t.get("ok") and t["best"]["score"] >= 4.0:
                r["ui_routes"] = t["routes"]
                r["answer"] = t["answer"]
                r["method"] = "ui-map"
    except Exception:
        pass
    return r'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
