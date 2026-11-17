p = r"D:\new_automation\All codes\core_organs\atlas\uimap.py"
s = open(p, encoding="utf-8").read()

old = "    # ------------------------------------------------------------------------------------------ backstage"
new = '''    # ------------------------------------------------------------------------------------------ everything else in the main window
    CHROME_NAMES = {"minimize", "maximize", "restore", "close", "system", "help", "ribbon display options"}

    def window_surface(self, nodes, mapped: Set[Tuple[str, str, str]], limit: int = 90) -> Optional[Dict[str, Any]]:
        """Controls of the main window that no other surface covers (status bar, side panes, docks, a calculator's keypad, a mixer's buttons): grouped by the nearest named
        container, drop-downs expanded and read exactly like ribbon controls. This is the whole map for programs without a ribbon or a menu bar."""
        ex = self.ex
        groups: Dict[str, List[Dict[str, Any]]] = collections.OrderedDict()
        n_total = 0
        for n in nodes:
            if n.ctype not in CONTROL_TYPES or not CONTROL_TYPES.get(n.ctype) or n.ctype in ("TextControl", "ListItemControl", "EditControl") and not ("invoke" in n.pats or "select" in n.pats or "value" in n.pats):
                continue
            if not (n.name or n.aid) or n.rect == (0, 0, 0, 0) or n.offscreen and not n.name:
                continue
            if _f(n.name) in self.CHROME_NAMES or (n.ctype, n.name, n.aid) in mapped:
                continue
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in COMPOSITE_PARENTS:
                continue
            if private_context(nodes, n):
                continue
            if n.ctype == "ListItemControl" and par is not None and par.ctype == "ListControl":
                continue
            grp = ""
            for a in ancestors(nodes, n):
                if a.ctype in (GROUP_TYPES | {"PaneControl", "ListControl", "TabControl", "StatusBarControl", "TreeControl", "DocumentControl"}) and a.name and _f(a.name) not in GENERIC_NAMES and a.idx != 0:
                    grp = a.name
                    break
                if a.ctype == "StatusBarControl":
                    grp = "Status bar"
                    break
            c = {"name": n.name or n.aid, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": (n.help or "")[:140], "enabled": bool(n.enabled), "group": grp, "rect": n.rect, "_node": n}
            if n.toggle_state in (0, 1, 2):
                c["state"] = {0: "off", 1: "on", 2: "indeterminate"}[n.toggle_state]
            groups.setdefault(grp or "(main)", []).append(c)
            n_total += 1
            if n_total >= limit * 4:
                break
        if not groups:
            return None
        surf: Dict[str, Any] = {"id": "window", "kind": "window", "name": "Window", "groups": []}
        expanded = 0
        for gname, gcs in groups.items():
            g = {"name": gname, "controls": []}
            for c in gcs:
                if not self.alive():
                    break
                unsafe = bool(X.UNSAFE_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["name"]))
                self.stats["controls"] += 1
                if unsafe:
                    c["leads_to"] = {"type": "not-opened", "why": "capture / share / account / destructive control: named, never opened by a scan"}
                    self.stats["skipped_unsafe"] += 1
                elif "expand" in c["pats"] and c["enabled"] and c["kind"] != "combobox" and expanded < limit and self.left() > 15:
                    items, info = self.expand_read(c["_node"])
                    expanded += 1
                    self.stats["expanded"] += 1
                    self.stats["items"] += len(items)
                    c["leads_to"] = ({"type": "menu", "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
                                     if items else {"type": "unknown", "why": info.get("why") or "expanded, nothing read"})
                elif c["kind"] in ("toggle", "checkbox"):
                    c["leads_to"] = {"type": "toggle", "state": c.get("state", "")}
                elif X.OPENER_RX.search(c["name"]) and not RUNTIME_RX.search(c["name"]):
                    c["leads_to"] = {"type": "dialog", "pending": True}
                elif c["kind"] in ("edit", "spinner", "slider", "combobox"):
                    c["leads_to"] = {"type": "value-entry"}
                else:
                    c["leads_to"] = {"type": "command"}
                g["controls"].append(c)
            surf["groups"].append(g)
            self.stats["groups"] += 1
        return surf

    def mapped_ids(self) -> Set[Tuple[str, str, str]]:
        out: Set[Tuple[str, str, str]] = set()
        for s in self.map["surfaces"]:
            for g in s["groups"]:
                for c in g["controls"]:
                    nd = c.get("_node")
                    if nd is not None:
                        out.add((nd.ctype, nd.name, nd.aid))
        return out

    # ------------------------------------------------------------------------------------------ backstage'''
assert old in s
s = s.replace(old, new, 1)

old = '''        mb = self.menubar(self.settle(2.0))
        if mb:
            self.map["surfaces"].append(mb)'''
new = '''        mb = self.menubar(self.settle(2.0))
        if mb:
            self.map["surfaces"].append(mb)
        try:
            ws = self.window_surface(self.settle(2.0), self.mapped_ids())
            if ws:
                self.open_pending_dialogs(ws, None)
                self.map["surfaces"].append(ws)
        except Exception as exc:
            self.map["window_surface_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"'''
assert old in s
s = s.replace(old, new, 1)

# applicable also for programs with neither ribbon nor menu bar: the window surface is the map
old = '''        self.map["applicable"] = bool(strips) or any(n.ctype == "MenuBarControl" for n in nodes)
        if not self.map["applicable"]:
            self.map["why"] = "no tab strip and no menu bar in the UI tree"
            return self.map'''
new = '''        self.map["applicable"] = bool(strips) or any(n.ctype == "MenuBarControl" for n in nodes) or sum(1 for n in nodes if (set(n.pats) & {"invoke", "toggle", "expand", "select"}) and n.name) >= 6'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("window surface ok")
