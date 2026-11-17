import io, json
C = "D:/new_automation/All codes/core_organs/professor/data/app_catalog.json"
cat = json.load(io.open(C, "r", encoding="utf-8"))
for a in cat["apps"]:
    if a["key"] == "mspaint":
        a["seeds"].append({"url": "https://support.microsoft.com/en-us/windows/get-microsoft-paint-a6b9578c-ed1c-5b09-0699-4ed8115f9aa9", "depth": 0, "pages": 1})
    if a["key"] == "chrome":
        a["seeds"] = ["https://support.google.com/chrome/answer/2364824?hl=en&co=GENIE.Platform%3DDesktop", "https://support.google.com/chrome/answer/2391819?hl=en&co=GENIE.Platform%3DDesktop"] + [s for s in a["seeds"]]
io.open(C, "w", encoding="utf-8", newline="\n").write(json.dumps(cat, indent=2, ensure_ascii=False))
