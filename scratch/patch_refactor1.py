import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


R = "D:/new_automation/All codes/core_organs/professor/"

# ---- guide_card.procedures: keep the chunk's text (a procedure's own words decide whether it needs an account)
patch(R + "knowledge/guide_card.py", [
    (r'''        out.append({"goal": goal, "cite": cite, "source": source, "steps": steps})''', r'''        out.append({"goal": goal, "cite": cite, "source": source, "steps": steps, "text": raw_text})'''),
])

# ---- menus: callback while a flyout is open
patch(R + "menus.py", [
    (r'''def expand_menus(fx: Any, hwnd: int, cat: Catalog, all_nodes: Callable[[], List[Any]], budget_s: float = 45.0, max_openers: int = 24, history: Any = None, toolkit: str = "",
                 log: Callable[[str], None] = lambda s: None, restore_popups: Optional[List[int]] = None) -> Dict[str, Any]:''', r'''def expand_menus(fx: Any, hwnd: int, cat: Catalog, all_nodes: Callable[[], List[Any]], budget_s: float = 45.0, max_openers: int = 24, history: Any = None, toolkit: str = "",
                 log: Callable[[str], None] = lambda s: None, restore_popups: Optional[List[int]] = None, on_items: Optional[Callable[[Any, List[Any]], None]] = None) -> Dict[str, Any]:'''),
    (r'''        rep["by_opener"][op.name] = added''', r'''        if on_items is not None and new:
            try:
                on_items(op, new)                                                # the flyout is OPEN right now: a picture of it can be taken
            except Exception:
                pass
        rep["by_opener"][op.name] = added'''),
])

# ---- executor: throw-away state makes settings-like verbs harmless; credentials / payment / sign-in stay human
patch(R + "executor.py", [
    (r'''        self.allow: Optional["re.Pattern"] = None ''', r'''        self.sandboxed = False                                    # the run created the state it works in (a throw-away profile, a backed-up and restored data folder)
        self.allow: Optional["re.Pattern"] = None '''),
    (r'''        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False''', r'''        if hum and cls == "sensitive" and self.sandboxed and not CREDENTIAL_RX.search(v.label + " " + " ".join(v.path)):
            hum = False                                                   # 'Profile', 'Account settings' in a throw-away profile: nothing of the user's is touched; credentials / payment / sign-in still wait for a human
        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False'''),
    (r'''KEY_AS_TEXT = ''', r'''CREDENTIAL_RX = re.compile(r"password|passcode|credential|payment|credit card|billing|bank|ssn|social security|secret|api key|token|2fa|two-factor|sign[- ]?in|log[- ]?in|sign[- ]?out|log[- ]?out", re.I)
KEY_AS_TEXT = '''),
])

# ---- guide_steps: 'Bookmarks' and 'Bookmark Manager' share a stem
patch(R + "knowledge/guide_steps.py", [
    (r'''    qw = {w for w in q.split() if len(w) > 2}
    best, best_key = None, (0.0,)
    for v in catalog.verbs:
        lw = {w for w in fold(v.label).split() if len(w) > 2}''', r'''    qw = {_stem(w) for w in q.split() if len(w) > 2}
    best, best_key = None, (0.0,)
    for v in catalog.verbs:
        lw = {_stem(w) for w in fold(v.label).split() if len(w) > 2}'''),
    (r'''def near_of(v: Any)''', r'''def _stem(w: str) -> str:
    """'bookmarks' ~ 'bookmark', 'settings' ~ 'setting': a plural is the same control word."""
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def near_of(v: Any)'''),
])

# ---- probe: a thing the probe itself ADDED can be removed again on a window the run owns
patch(R + "probe.py", [
    (r'''                if inv is not None and (cls == "safe" or (self.owned and cls == "commit")):      # a 'clear'-like inverse only where the Professor owns the data''', r'''                added_it = bool(re.match(r"(?i)^(add|new|insert|create|open)\b", h.verb)) and bool(re.match(r"(?i)^(close|remove|delete|clear)\b", cand))
                if inv is not None and (cls == "safe" or (self.owned and cls == "commit") or (self.owned and added_it)):      # a 'clear'-like inverse only where the Professor owns the data; closing the tab it just opened is the exact inverse'''),
])
print("ok")
