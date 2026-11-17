import io, json, os, re, sys
p = r'D:\new_automation\data\professor\apprun\systemsettings_20261012_203250'
print(os.listdir(p))
for f in os.listdir(p):
    if f.endswith(".json"):
        d = json.load(io.open(os.path.join(p, f), encoding="utf-8"))
        s = json.dumps(d)
        for m in sorted(set(re.findall(r"control not found in the live tree.{0,240}", s))):
            print("NOTE:", m.replace("\\n", " ")[:280])
            print()
        for m in sorted(set(re.findall(r"the app.s own search.{0,240}", s))):
            print("SEARCH:", m.replace("\\n", " ")[:280])
            print()
