import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ---------------------------------------------------------------- guide_steps: plain editing keys
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''_SKIP_TARGETS = {"it", "this",''', r'''PLAIN_KEYS = {"enter": "enter", "return": "enter", "tab": "tab", "escape": "escape", "esc": "escape", "space": "space", "spacebar": "space", "backspace": "backspace", "delete": "delete", "del": "delete",
              "home": "home", "end": "end", "page up": "pageup", "page down": "pagedown", "pageup": "pageup", "pagedown": "pagedown", "up arrow": "up", "down arrow": "down", "left arrow": "left", "right arrow": "right"}
_SKIP_TARGETS = {"it", "this",'''),
    (r'''    if st.target:
        v, c = resolve_label(catalog, st.target)''', r'''    if not st.path and st.action in ("press", "click", "select", "type") and fold(st.target) in PLAIN_KEYS and not st.text:
        return Grounded(st, None, 1.0, "key", f"the {st.target} key (an editing key, not a menu command)")
    if st.target:
        v, c = resolve_label(catalog, st.target)'''),
])

# ---------------------------------------------------------------- effector: UIA text insertion
patch("D:/new_automation/All codes/core_organs/professor/effectors.py", [
    (r'''    @_guarded
    def click_xy(self, sx: int, sy: int, button: str = "left") -> Tuple[bool, str]:''', r'''    @_guarded
    def insert_text(self, text: str, deadline_s: float = 2.5) -> Tuple[bool, str]:
        """Type into the window's main editor through UI Automation (ValuePattern, appending): for toolkits that ignore posted characters (XAML / WinUI measured on Notepad). No focus, no keystrokes."""
        g = self._gate("insert_text")
        if g:
            return g
        result: dict = {}

        def work() -> None:
            try:
                from core_organs import fast_uia
                nodes = fast_uia.snapshot(self.hwnd, timeout_ms=3000) or []
                cands = [n for n in nodes if "value" in (n.pats or []) and n.ctype in ("EditControl", "DocumentControl") and n.enabled and not n.offscreen and n.rect[2] > n.rect[0]]
                if not cands:
                    result["how"] = "no editable control with a value pattern"
                    return

                def rank(n):
                    try:
                        foc = bool(n.ctrl.HasKeyboardFocus)
                    except Exception:
                        foc = False
                    return (1 if foc else 0, (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]))
                best = max(cands, key=rank)
                vp = best.ctrl.GetValuePattern()
                if vp is None or vp.IsReadOnly:
                    result["how"] = "editor is read-only"
                    return
                vp.SetValue((vp.Value or "") + text)
                result["how"] = f"UIA SetValue (append {len(text)} chars to '{best.name or best.ctype}')"
            except Exception as exc:
                result["how"] = f"UIA error {type(exc).__name__}"

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(deadline_s)
        how = result.get("how", "UIA call still running")
        return self._rec("insert_text", (how.startswith("UIA SetValue"), how))

    @_guarded
    def click_xy(self, sx: int, sy: int, button: str = "left") -> Tuple[bool, str]:'''),
])

# ---------------------------------------------------------------- executor: key steps, text routes, logging
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''            elif g.how == "typed":
                s = Step(0, st.raw, None, "", [], "text", text=st.text, safety="safe", routes=["text:posted characters"], expected="the typed text appears", source="guide", cite=gp["cite"])''',
     r'''            elif g.how == "typed":
                s = Step(0, st.raw, None, "", [], "text", text=st.text, safety="safe", routes=["text:posted characters", "text:uia value"], expected="the typed text appears", source="guide", cite=gp["cite"])
            elif g.how == "key":
                from .knowledge.guide_steps import PLAIN_KEYS
                key = PLAIN_KEYS.get(fold(st.target), fold(st.target))
                s = Step(0, st.raw, None, "", [], "key", text=key, safety="safe", routes=[f"key:{key}"], expected=f"the {key} key is delivered", source="guide", cite=gp["cite"])'''),
    (r'''            if st.kind == "text":
                s0 = snapshot(self.hwnd)
                ok, how = self.fx.text(st.text)
                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                status = "done" if ok and d.effect() != "no_effect" else ("no_effect" if ok else "refused")
                rep.results.append(StepResult(st.index, label, status, route="text", tried=["text"], effect=d.effect(), summary=how + "; " + d.summary(), ms=int((time.time() - t0) * 1000)))
                if status != "done":
                    rep.stopped = f"step {st.index + 1}: typing had no visible effect"
                    break
                continue''', r'''            if st.kind in ("text", "key"):
                if st.kind == "text":
                    ways = [("text:posted", lambda: self.fx.text(st.text)), ("text:uia", lambda: self.fx.insert_text(st.text))]
                else:
                    ways = [(f"key:{st.text}", lambda: self.fx.key(st.text))]
                    alt = KEY_AS_TEXT.get(st.text)
                    if alt:
                        ways.append(("text:uia", lambda: self.fx.insert_text(alt)))
                tried_t: List[str] = []
                status, effect, summary, route_used = "no_effect", "", "", ""
                for rname, fn in ways:
                    s0 = snapshot(self.hwnd)
                    ok, how = fn()
                    tried_t.append(f"{rname} -> {how}")
                    if not ok:
                        status, summary = ("refused" if how.startswith("refused") else "no_effect"), how
                        if status == "refused":
                            break
                        continue
                    s1 = self._settle(s0, settle_s)
                    d = delta(s0, s1)
                    self._log_text_attempt(st, rname, how, s0, s1, d)
                    effect, summary, route_used = d.effect(), how + "; " + d.summary(), rname
                    if effect != "no_effect":
                        status = "done"
                        break
                    status = "no_effect"
                if status == "no_effect" and st.kind == "key" and st.text in SOFT_KEYS and route_used:
                    status = "done"                                       # a movement / dismiss key may legitimately change nothing that is visible
                    summary += " (key delivered; nothing visible was expected to change)"
                rep.results.append(StepResult(st.index, label, status, route=route_used or (ways[0][0]), tried=tried_t, effect=effect, summary=summary, ms=int((time.time() - t0) * 1000)))
                if status != "done":
                    rep.stopped = f"step {st.index + 1}: {'typing' if st.kind == 'text' else 'the ' + st.text + ' key'} had no visible effect"
                    break
                continue'''),
    (r'''    def _log_attempt(self, st: Step, v: Any, r: Route, how: str, s0: Any, s1: Any, d: Any) -> None:''', r'''    def _log_text_attempt(self, st: Step, route: str, how: str, s0: Any, s1: Any, d: Any) -> None:
        if self.history is None:
            return
        try:
            self.history.log(self.app_key, "guide" if st.source == "guide" else "exec", "type" if st.kind == "text" else "key", (st.text or st.goal)[:60], route, s0.sig, f"{len(s0.names)} controls", s1.sig,
                             d.summary(), d.effect(), d.effect() != "no_effect", None, "", {"how": how, "cite": st.cite}, toolkit=self.toolkit, archetype=self.archetype, role="document", safety="safe")
        except Exception:
            pass

    def _log_attempt(self, st: Step, v: Any, r: Route, how: str, s0: Any, s1: Any, d: Any) -> None:'''),
    (r'''SPLIT_RX = re.compile(''', r'''KEY_AS_TEXT = {"enter": "\r\n", "tab": "\t", "space": " "}                 # when a toolkit ignores the posted key, the same character can be inserted through the editor's value pattern
SOFT_KEYS = {"escape", "home", "end", "up", "down", "left", "right", "pageup", "pagedown", "tab", "space"}
SPLIT_RX = re.compile('''),
])
print("ok")
