base = r"D:\new_automation\All codes\core_organs\atlas"

# ---------------------------------------------------------------- scanner.py: structure scan after the cartographer in deep/full tiers
p = base + r"\scanner.py"
s = open(p, encoding="utf-8").read()
a = s.index("                # ---- fast: the engine's structure scan")
b = s.index("                # ---- deep: exploration + conventions")
block = s[a:b]
new_block = '''                # ---- fast: the engine's structure scan (deep / full: AFTER the cartographer, which first brings the program to a working document)
                def do_structure() -> None:
                    if still_frame:
                        live["structure"] = {"skipped": "the window exposes only its frame to UI Automation: the engine's structure scan has nothing to read and is not run on a window we do not own"}
                    elif not polite or tier != "instant":
                        try:
                            from core_organs import fast_scan
                            rep = fast_scan.deep_scan(str(target) if not isinstance(target, int) else os.path.basename(exe), self.model, budget_s=min(30.0, max(8.0, budget * 0.35)),
                                                      vision=False, target_hwnd=h, close_if_launched=False, force=False)
                            live["structure"] = {"seconds": rep.get("seconds"), "within_budget": rep.get("within_budget"), "tree": rep.get("tree"), "error": rep.get("error")}
                        except Exception as exc:
                            live["structure"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                        T.mark("structure")
                if tier not in ("deep", "full") or not uia_rich or polite:
                    do_structure()

'''
s = s[:a] + new_block + s[b:]
old = '''                    T.mark("explore")
'''
new = '''                    T.mark("explore")
                    do_structure()
'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- explorer.py: second pass never overwrites the ribbon map; only save a map that has surfaces
p = base + r"\explorer.py"
s = open(p, encoding="utf-8").read()
old = '''                self.stats["uimap_file"] = self.carto.save()
                self.uimap = m'''
new = '''                if m.get("surfaces"):
                    self.stats["uimap_file"] = self.carto.save()
                    self.uimap = m'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)

p = base + r"\scanner.py"
s = open(p, encoding="utf-8").read()
old = "again = self._explore(h, app_name, key, min(60.0, budget * 0.2), gest_pristine, learner, run_id + \"b\")"
assert old in s
s = s.replace(old, "again = self._explore(h, app_name, key, min(60.0, budget * 0.2), gest_pristine, learner, run_id + \"b\", passes=(\"menus\", \"tabs\", \"openers\"))", 1)
s = s.replace("    def _explore(self, hwnd: int, name: str, key: str, budget_s: float, pristine: bool, learner, run_id: str) -> Dict[str, Any]:",
              "    def _explore(self, hwnd: int, name: str, key: str, budget_s: float, pristine: bool, learner, run_id: str, passes=(\"ribbon\", \"menus\", \"tabs\", \"openers\")) -> Dict[str, Any]:", 1)
s = s.replace("        st = ex.run()\n        if ex.uimap.get(\"surfaces\"):", "        st = ex.run(passes)\n        if ex.uimap.get(\"surfaces\"):", 1)
open(p, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- uimap.py: readiness = no start-screen choice AND a real ribbon
p = base + r"\uimap.py"
s = open(p, encoding="utf-8").read()
old = '''        nodes = self.settle(3.0)
        strips = self.tab_strips(nodes)
        if strips and len(self.region_controls(nodes, strips[0][0])) >= 8:
            return {"state": "ready"}
        cands = ['''
new = '''        nodes = self.settle(3.0)
        strips = self.tab_strips(nodes)
        cands = ['''
assert old in s
s = s.replace(old, new, 1)
old = '''        if not cands:
            return {"state": "unknown", "why": "no ribbon and no 'Blank ...' start-screen choice"}'''
new = '''        if not cands:
            if strips and len(self.region_controls(nodes, strips[0][0])) >= 8:
                return {"state": "ready"}
            return {"state": "unknown", "why": "no ribbon and no 'Blank ...' start-screen choice"}'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("round4 ok")
