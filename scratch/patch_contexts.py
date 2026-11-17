p = r"D:\new_automation\All codes\core_organs\atlas\uimap.py"
s = open(p, encoding="utf-8").read()

old = "    # ------------------------------------------------------------------------------------------ backstage"
new = '''    # ------------------------------------------------------------------------------------------ contexts (selection-dependent UI)
    def tab_names(self, nodes) -> List[str]:
        st = self.tab_strips(nodes)
        return [t.name for t in st[0][1]] if st else []

    def undo_button(self, nodes):
        cands = [n for n in nodes if n.ctype == "ButtonControl" and re.fullmatch(r"undo", _f(n.name)) and "invoke" in n.pats and n.enabled and n.rect != (0, 0, 0, 0)]
        return cands[0] if cands else None

    def contexts(self, max_contexts: int = 6) -> List[Dict[str, Any]]:
        """Some UI exists only while something is selected (a table's own tabs, enabled font controls). In the DISPOSABLE document the scan created, perform a few
        immediate 'insert' actions taken from the map itself (an item of an Insert-like tab's drop-down), see which tabs appear and which disabled controls
        become enabled, read the new tabs, then undo and verify the window is back to its starting tab set. Never runs in a document the scan did not create."""
        ex = self.ex
        if not (self.created_workspace or ex.pristine):
            return [{"skipped": "not a document this scan created: no actions are performed in it"}]
        cands: List[Tuple[str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
        for s in self.map["surfaces"]:
            if s["kind"] != "ribbon-tab" or not re.search(r"insert|add|new", s["name"], re.I):
                continue
            for g in s["groups"]:
                for c in g["controls"]:
                    lt = c.get("leads_to") or {}
                    if lt.get("type") not in ("menu", "gallery") or not c.get("enabled", True):
                        continue
                    if X.UNSAFE_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["name"]) or RUNTIME_RX.search(c["name"]):
                        continue
                    for it in lt.get("items") or []:
                        if isinstance(it, dict) and not X.OPENER_RX.search(it["name"]) and it.get("enabled", True) and not it.get("items") \
                                and not (X.UNSAFE_RX.search(it["name"]) or X.SENSITIVE_RX.search(it["name"]) or RUNTIME_RX.search(it["name"])):
                            cands.append((s["name"], g, c, it))
                            break
        out: List[Dict[str, Any]] = []
        base_tabs = self.tab_names(ex.snap(ms=6000))
        base_enabled = {}
        for s in self.map["surfaces"]:
            if s["kind"] == "ribbon-tab":
                for g in s["groups"]:
                    for c in g["controls"]:
                        base_enabled[(s["name"], c["name"], c.get("aid", ""))] = c.get("enabled", True)
        for sname, g, c, it in cands[:max_contexts]:
            if self.left() < 40 or not self.alive():
                break
            cond = f"{sname} > {g['name']} > {c['name']} > {it['name']}" if g.get("name") else f"{sname} > {c['name']} > {it['name']}"
            self.act(f"context: {cond}")
            path = [{"kind": "surface", "name": sname}] + ([{"kind": "group", "name": g["name"]}] if g.get("name") else []) + [{"kind": "control", "name": c["name"]}, {"kind": "item", "name": it["name"]}]
            rec: Dict[str, Any] = {"when": cond, "applied": False}
            try:
                dr = drive(ex.hwnd, path)
                rec["applied"] = bool(dr.get("ok"))
                rec["why"] = dr.get("why", "")
            except Exception as exc:
                rec["why"] = f"{type(exc).__name__}: {str(exc)[:60]}"
            time.sleep(1.0)
            cur = self.settle(2.5)
            now_tabs = self.tab_names(cur)
            new_tabs = [t for t in now_tabs if t not in base_tabs]
            rec["new_tabs"] = new_tabs
            for t in new_tabs[:4]:
                if self.left() < 20:
                    break
                nodes2, strip2, ver = self.select_tab(t, ())
                if strip2 is None:
                    continue
                surf = self.read_tab(t, nodes2, strip2)
                surf.update(id=f"context:{t}", kind="context-tab", when=cond, verified_selected=ver)
                self.map["surfaces"].append(surf)
            # which controls that were disabled are enabled now (read the first tab again)
            first = next((t for t in base_tabs), None)
            if first:
                nodes3, strip3, ver3 = self.select_tab(first, ())
                if strip3 is not None:
                    enabled_now = {(c2["name"], c2.get("aid", "")): c2["enabled"] for c2 in self.region_controls(nodes3, strip3)}
                    unlocked = []
                    for s in self.map["surfaces"]:
                        if s["name"] != first:
                            continue
                        for g2 in s["groups"]:
                            for c2 in g2["controls"]:
                                if not c2.get("enabled", True) and enabled_now.get((c2["name"], c2.get("aid", ""))):
                                    c2.setdefault("enabled_when", []).append(cond)
                                    unlocked.append(c2["name"])
                    rec["unlocked"] = unlocked[:60]
            # undo: back to the starting tab set
            for _ in range(4):
                cur = ex.snap(ms=6000)
                if self.tab_names(cur) == base_tabs:
                    break
                ub = self.undo_button(cur)
                if ub is None:
                    break
                ex.uia(ub, "GetInvokePattern", "Invoke", wait=1.0)
                time.sleep(0.8)
            X._u32.PostMessageW(ex.hwnd, 0x0100, 0x1B, 0)
            X._u32.PostMessageW(ex.hwnd, 0x0101, 0x1B, 0)
            rec["restored"] = self.tab_names(ex.snap(ms=6000)) == base_tabs
            if not rec["restored"]:
                self.stats["unwind_failures"] += 1
            out.append(rec)
            if not rec["restored"]:
                break                                               # the document is not back to its start: stop acting in it
        return out

    # ------------------------------------------------------------------------------------------ backstage'''
assert old in s
s = s.replace(old, new, 1)

old = '''        qa = self.quick_access(self.settle(2.0))'''
new = '''        if os.environ.get("HOJAIGA_ATLAS_CONTEXTS", "1") != "0":
            try:
                self.map["contexts"] = self.contexts()
            except Exception as exc:
                self.map["contexts"] = [{"error": f"{type(exc).__name__}: {str(exc)[:100]}"}]
        qa = self.quick_access(self.settle(2.0))'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
