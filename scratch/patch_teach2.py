p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
old = '''    if t in ("menu", "gallery") and lt.get("items"):
        names = [i["name"] if isinstance(i, dict) else str(i) for i in lt["items"]]
        return f"It offers {len(names)} choice(s): " + ", ".join(names[:10]) + (" ..." if len(names) > 10 else "")'''
new = '''    if t in ("menu", "gallery") and lt.get("items"):
        names = [i["name"] if isinstance(i, dict) else str(i) for i in lt["items"]]
        txt = f"It offers {len(names)} choice(s): " + ", ".join(names[:10]) + (" ..." if len(names) > 10 else "")
        more = []
        for i in lt["items"]:
            if isinstance(i, dict) and (i.get("leads_to") or {}).get("type") == "dialog":
                il = i["leads_to"]
                flds = [f["name"] for f in (il.get("fields") or []) if isinstance(f, dict) and f.get("name")][:8]
                more.append(f"choosing **{i['name']}** opens the dialog **{il.get('dialog')}**" + (f" ({', '.join(flds)})" if flds else ""))
        if more:
            txt += ". " + "; ".join(more[:3])
        return txt'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)

p = r"D:\new_automation\All codes\core_organs\si_tests_atlas.py"
s = open(p, encoding="utf-8").read()
s = s.replace('''"teacher: route to the item": "Pictures" in (best.get("text") or "") and "This Device" in (best.get("text") or ""),''', '''"teacher: route to the control": "Pictures" in (best.get("text") or "") and "Images" in (best.get("text") or ""),''')
s = s.replace('''"teacher: dialog fields in the outcome": "Insert Picture" in (best.get("outcome") or "") and "File name" in (best.get("outcome") or ""),''', '''"teacher: items + dialog + fields in the outcome": all(x in (best.get("outcome") or "") for x in ("This Device", "Insert Picture", "File name")),''')
s = s.replace('''                     "personal item inside a popup dropped? (named list only)": True, "shortcut read''', '''                     "shortcut read''')
open(p, "w", encoding="utf-8").write(s)
print("ok")
