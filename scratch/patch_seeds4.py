import io, json
C = "D:/new_automation/All codes/core_organs/professor/data/app_catalog.json"
cat = json.load(io.open(C, "r", encoding="utf-8"))
for a in cat["apps"]:
    if a["key"] == "mspaint":
        for u in ("https://www.digitalcitizen.life/paint-windows-11/", "https://pureinfotech.com/use-image-layers-paint-windows-11/", "https://geekchamp.com/how-to-use-microsoft-paint-in-windows-11/",
                  "https://winaero.com/the-full-list-of-keyboard-shortcut-for-microsoft-paint"):
            a["seeds"].append({"url": u, "depth": 0, "pages": 1})
io.open(C, "w", encoding="utf-8", newline="\n").write(json.dumps(cat, indent=2, ensure_ascii=False))
print("ok")
