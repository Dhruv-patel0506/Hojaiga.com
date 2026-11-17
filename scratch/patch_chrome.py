p = r"D:\new_automation\All codes\core_organs\atlas\uimap.py"
s = open(p, encoding="utf-8").read()

# 1. quick access surface + chrome dedupe helpers
old = "    # ------------------------------------------------------------------------------------------ backstage"
new = '''    def quick_access(self, nodes) -> Optional[Dict[str, Any]]:
        """The quick-access toolbar (a ToolBar named like it): its buttons, and the items of its own customise drop-down."""
        qa = next((n for n in nodes if n.ctype == "ToolBarControl" and re.search(r"quick access", n.name or "", re.I)), None)
        if qa is None:
            return None
        surf: Dict[str, Any] = {"id": "qat", "kind": "toolbar", "name": "Quick Access Toolbar", "groups": [{"name": "", "controls": []}]}
        for n in subtree(nodes, qa.idx):
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in COMPOSITE_PARENTS:
                continue
            if n.ctype not in CONTROL_TYPES or not CONTROL_TYPES.get(n.ctype) or not (n.name or n.aid):
                continue
            c = {"name": n.name or n.aid, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": "", "enabled": bool(n.enabled), "group": "", "rect": n.rect, "_node": n}
            if "expand" in n.pats and re.search(r"customi[sz]e", n.name or "", re.I) and self.left() > 10:
                items, info = self.expand_read(n)
                c["leads_to"] = {"type": "menu", "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
            elif "expand" in n.pats:
                c["leads_to"] = {"type": "menu", "items": [], "note": "history / list drop-down: contents depend on the document"}
            else:
                c["leads_to"] = {"type": "toggle" if "toggle" in n.pats else "command"}
            surf["groups"][0]["controls"].append(c)
            self.stats["controls"] += 1
        return surf if surf["groups"][0]["controls"] else None

    def hoist_chrome(self) -> None:
        """Controls that repeat on every tab outside any group (display options...) belong to the ribbon, not to a tab: one surface, said once."""
        tabs = [s for s in self.map["surfaces"] if s["kind"] == "ribbon-tab"]
        if len(tabs) < 3:
            return
        count: Dict[Tuple[str, str], int] = collections.Counter()
        for s in tabs:
            for g in s["groups"]:
                if g["name"] in ("(ungrouped)", ""):
                    for c in g["controls"]:
                        count[(c["name"], c.get("aid", ""))] += 1
        shared = {k for k, v in count.items() if v >= max(3, len(tabs) - 1)}
        if not shared:
            return
        chrome: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()
        for s in tabs:
            for g in s["groups"]:
                keep = []
                for c in g["controls"]:
                    k = (c["name"], c.get("aid", ""))
                    if g["name"] in ("(ungrouped)", "") and k in shared:
                        if k not in seen:
                            seen.add(k)
                            chrome.append(c)
                    else:
                        keep.append(c)
                g["controls"] = keep
            s["groups"] = [g for g in s["groups"] if g["controls"]]
        if chrome:
            self.map["surfaces"].append({"id": "ribbon-chrome", "kind": "toolbar", "name": "Ribbon (all tabs)", "groups": [{"name": "", "controls": chrome}]})

    # ------------------------------------------------------------------------------------------ backstage'''
assert old in s
s = s.replace(old, new, 1)

# 2. call them
old = '''        mb = self.menubar(self.settle(2.0))
        if mb:
            self.map["surfaces"].append(mb)'''
new = '''        qa = self.quick_access(self.settle(2.0))
        if qa:
            self.map["surfaces"].insert(0, qa)
        self.hoist_chrome()
        mb = self.menubar(self.settle(2.0))
        if mb:
            self.map["surfaces"].append(mb)'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
