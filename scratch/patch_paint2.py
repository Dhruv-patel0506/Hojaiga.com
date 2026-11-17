import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ---------------------------------------------------------------- a pattern getter that exists for EVERY control class
patch("D:/new_automation/All codes/core_organs/professor/effectors.py", [
    (r'''class InputRefused(Exception):''', r'''def pattern_of(ctrl: Any, name: str) -> Any:
    """The UI Automation pattern `name` ('Invoke', 'Toggle', 'SelectionItem', 'ExpandCollapse', 'Value', 'Text', 'LegacyIAccessible') of ANY control: the uiautomation package defines
    Get<Name>Pattern only on some control classes (a ListItem has no GetInvokePattern), GetPattern(PatternId) works on all of them."""
    g = getattr(ctrl, f"Get{name}Pattern", None)
    if g is not None:
        return g()
    import uiautomation as ua
    return ctrl.GetPattern(getattr(ua.PatternId, f"{name}Pattern"))


class InputRefused(Exception):'''),
    (r'''                for getter, call, label in (("GetInvokePattern", "Invoke", "Invoke"), ("GetTogglePattern", "Toggle", "Toggle"), ("GetSelectionItemPattern", "Select", "Select"),
                                            ("GetExpandCollapsePattern", "Expand", "Expand")):
                    if getter == "GetTogglePattern" and "toggle" not in getattr(node, "pats", []):
                        continue
                    if getter == "GetInvokePattern" and "invoke" not in getattr(node, "pats", []) and getattr(node, "pats", None):
                        continue
                    p = getattr(ctrl, getter)()
                    if p is not None:
                        getattr(p, call)()
                        result["how"] = f"UIA {label}"
                        return''', r'''                have = set(getattr(node, "pats", []) or [])
                for pname, call, label, need in (("Invoke", "Invoke", "Invoke", "invoke"), ("Toggle", "Toggle", "Toggle", "toggle"), ("SelectionItem", "Select", "Select", "select"),
                                                 ("ExpandCollapse", "Expand", "Expand", "expand")):
                    if have and need not in have:
                        continue
                    p = pattern_of(ctrl, pname)
                    if p is not None:
                        getattr(p, call)()
                        result["how"] = f"UIA {label}"
                        return'''),
    (r'''                p = node.ctrl.GetValuePattern()
                if p is None:
                    result["how"] = "no value pattern"
                    return
                p.SetValue(text)''', r'''                p = pattern_of(node.ctrl, "Value")
                if p is None:
                    result["how"] = "no value pattern"
                    return
                p.SetValue(text)'''),
    (r'''                p = node.ctrl.GetSelectionItemPattern()
                if p is None:
                    result["how"] = "no selection pattern"
                    return
                p.RemoveFromSelection()''', r'''                p = pattern_of(node.ctrl, "SelectionItem")
                if p is None:
                    result["how"] = "no selection pattern"
                    return
                p.RemoveFromSelection()'''),
    (r'''                vp = best.ctrl.GetValuePattern()''', r'''                vp = pattern_of(best.ctrl, "Value")'''),
])
patch("D:/new_automation/All codes/core_organs/professor/menus.py", [
    (r'''            if n.role == "tabitem":
                p = ctrl.GetSelectionItemPattern()
                if p is not None:
                    p.Select()
                    res["how"] = "UIA Select (tab)"
                    return
            p = ctrl.GetExpandCollapsePattern() if ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2)) else None
            if p is not None:
                p.Expand()
                res["how"] = "UIA Expand"
                return
            if n.role == "menuitem":
                p = ctrl.GetInvokePattern()
                if p is not None:''', r'''            from .effectors import pattern_of
            if n.role == "tabitem":
                p = pattern_of(ctrl, "SelectionItem")
                if p is not None:
                    p.Select()
                    res["how"] = "UIA Select (tab)"
                    return
            p = pattern_of(ctrl, "ExpandCollapse") if ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2)) else None
            if p is not None:
                p.Expand()
                res["how"] = "UIA Expand"
                return
            if n.role == "menuitem":
                p = pattern_of(ctrl, "Invoke")
                if p is not None:'''),
])
patch("D:/new_automation/All codes/core_organs/professor/probe.py", [
    (r'''        c = n.ctrl
        if getattr(c, "IsPassword", False):
            return None
        vp = c.GetValuePattern()''', r'''        c = n.ctrl
        if getattr(c, "IsPassword", False):
            return None
        from .effectors import pattern_of
        vp = pattern_of(c, "Value")'''),
])

# ---------------------------------------------------------------- executor: an 'expand' route and opener detection from the live node
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        el = self._element_for(v)
        if el is not None and not text:
            out.append(Route("click", f"centre of '{v.label}'", 4, (int(el.bbox.cx), int(el.bbox.cy))))
        return out''', r'''        if not text and (v.role in ("dropdown", "menu_item") or "menu" in (v.leads_to or "")):
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))
        el = self._element_for(v)
        if el is not None and not text:
            out.append(Route("click", f"centre of '{v.label}'", 4, (int(el.bbox.cx), int(el.bbox.cy))))
        return out'''),
    (r'''        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)''', r'''        if r.kind == "expand":
            from . import menus as MN
            n0 = self._live_node(v)
            if n0 is None:
                return False, "control not found in the live tree"
            return MN._expand(self.fx, n0)
        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)'''),
    (r'''            if v is not None and self._is_opener(v) and not v.path and not rep.dry_run:
                self._hold_open()''', r'''            live0 = None
            if v is not None and not v.path and not rep.dry_run:
                try:
                    live0 = self._live_node(v)
                except Exception:
                    live0 = None
            if v is not None and not v.path and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()'''),
])
patch("D:/new_automation/All codes/core_organs/professor/harvest.py", [
    (r'''              leads_to=("opens a menu" if n.role == "splitbutton" else ""), aid=n.aid, role=role)''', r'''              leads_to=("opens a menu" if (n.role == "splitbutton" or "expand" in (n.pats or [])) else ""), aid=n.aid, role=role)'''),
])

# ---------------------------------------------------------------- parse: 'the desired **Width** and **Height**', alternatives
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''(?:(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?|\bthe\s+)$"''', r'''(?:(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?|\bthe\s+(?:\w+\s+){0,2})$"'''),
    (r'''                    fm = re.search(r"(?i)\b(?:in|into)\s+the\s+\**([^*,.;]+?)\**\s+and\s+\**([^*,.;]+?)\**\s+(?:text\s+)?(?:boxes|fields|areas|inputs)\b", piece)''', r'''                    fm = re.search(r"(?i)\b(?:in|into)\s+the\s+\**([^*,.;]+?)\**\s+and\s+\**([^*,.;]+?)\**\s+(?:text\s+)?(?:boxes|fields|areas|inputs)\b", piece) or \
                        (re.search(r"(?i)\b(?:enter|type|set|specify|input)\b[^.*]*?\*\*([^*]+)\*\*\s+and\s+\*\*([^*]+)\*\*", piece) if not st.text else None)'''),
])
print("ok")
