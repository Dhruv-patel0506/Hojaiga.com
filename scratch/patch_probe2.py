p = r"D:\new_automation\scratch\probe_day1_full.py"
s = open(p, encoding="utf-8").read()
i = s.index("_orig_crawl = bm.crawl_e0")
j = s.index("with sb.LiveApp(\"notepad\") as ln")
s = s[:i] + s[j:]
s = s.replace('    print(json.dumps(rep, default=str)[:4500])', '''    print(json.dumps(rep, default=str)[:3000])
    key = bm._app_key("paint")
    cmds = m.commands(key, limit=5000)
    print("paint commands known:", len(cmds), "| with shortcut:", sum(1 for c in cmds if c["shortcut"]), "| ctrl+s:", [(c["name"], c["menu_path"], c["risk"]) for c in cmds if (c["shortcut"] or "").lower().replace(" ", "") in ("ctrl+s",)])
    print("crawled set:", getattr(runner, "ladder", None) and getattr(runner.ladder, "_crawled", None))''')
open(p, "w", encoding="utf-8").write(s)
print("ok")
