import io, json
C = "D:/new_automation/All codes/core_organs/professor/data/app_catalog.json"
cat = json.load(io.open(C, "r", encoding="utf-8"))
for a in cat["apps"]:
    if a["key"] in ("notepad", "mspaint", "systemsettings"):
        for sd in a["seeds"]:
            if isinstance(sd, dict) and sd["url"].startswith("https://support.microsoft.com/en-us/windows/"):
                sd["depth"] = 1
                sd["pages"] = 25
                sd["scope"] = "/en-us/windows/"
            elif isinstance(sd, dict) and sd["url"].startswith("https://support.microsoft.com/en-us/accessibility/windows/"):
                sd["depth"] = 1
                sd["pages"] = 25
                sd["scope"] = "/en-us/accessibility/windows/"
io.open(C, "w", encoding="utf-8", newline="\n").write(json.dumps(cat, indent=2, ensure_ascii=False))
print("ok")
