import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/probe.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''def snapshot(hwnd: int, with_image: bool = True, nodes: Optional[list] = None) -> Snapshot:
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    nodes = nodes if nodes is not None else (fast_uia.snapshot(hwnd, timeout_ms=4000) or [])
    ox = oy = 0
    if nodes and nodes[0].rect[2] > nodes[0].rect[0]:
        ox, oy = nodes[0].rect[0], nodes[0].rect[1]
    names: Dict[str, str] = {}
    texts: Dict[str, str] = {}
    states: Dict[str, str] = {}
    cont: Dict[str, List[str]] = {}
    ordinals: Dict[str, int] = {}
    frame_ids: Set[int] = set()                                   # the window's OWN frame (title bar, caption buttons, system menu) says where the window is, not what the application is doing
    for n in nodes:
        if n.ctype == "TitleBarControl" or (n.parent in frame_ids):
            frame_ids.add(n.idx)
            continue
        if n.offscreen or not n.name or n.rect[2] <= n.rect[0]:
            continue
        if n.role in ("button", "menuitem") and fold(n.name) in safety.CHROME and n.parent >= 0 and nodes[n.parent].ctype in ("WindowControl", "TitleBarControl"):
            continue
        k = _key(n, ordinals)
        if n.role in TEXTY:
            texts[k] = n.name
        else:
            names[k] = n.name
        if n.role in ACTIVE_ROLES or n.pats:
            states[k] = f"sel={n.selected},tog={n.toggle_state},exp={n.expand_state},en={n.enabled}"
        p, container = n.parent, ""
        while p >= 0:
            q = nodes[p]
            if q.name and q.role in ("pane", "group", "tab", "toolbar", "list", "tree", "menubar", "statusbar", "window", "custom"):
                container = q.name
                break
            p = q.parent
        cont.setdefault(container or "(window)", []).append(fold(n.name))
    try:
        wins = tuple(sorted(hin.process_windows(hwnd, include_hidden=False)))
    except Exception:
        wins = ()''', r'''def _editable_value(n: Any) -> Optional[str]:
    """The text inside an edit field / document (UI Automation ValuePattern), or None. Password fields are never read."""
    try:
        if "value" not in (n.pats or []) or n.ctype not in ("EditControl", "DocumentControl"):
            return None
        c = n.ctrl
        if getattr(c, "IsPassword", False):
            return None
        vp = c.GetValuePattern()
        v = vp.Value if vp is not None else None
        return None if v is None else str(v)
    except Exception:
        return None


def snapshot(hwnd: int, with_image: bool = True, nodes: Optional[list] = None, popups: bool = True) -> Snapshot:
    """The application's state as the accessibility tree sees it: the window AND its open pop-ups / dialogs (a dialog's fields are part of what the step did), control identities, the text of
    labels, the VALUE of edit fields and documents (a typed character must show up), the state of toggles."""
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    nodes = nodes if nodes is not None else (fast_uia.snapshot(hwnd, timeout_ms=4000) or [])
    groups: List[list] = [nodes]
    if popups:
        try:
            for w in hin.popup_windows(hwnd)[:6]:
                g = fast_uia.snapshot(w, timeout_ms=2500) or []
                if g:
                    groups.append(g)
        except Exception:
            pass
    names: Dict[str, str] = {}
    texts: Dict[str, str] = {}
    states: Dict[str, str] = {}
    cont: Dict[str, List[str]] = {}
    ordinals: Dict[str, int] = {}
    read_values = 0
    for gi, nodes in enumerate(groups):
        frame_ids: Set[int] = set()                               # the window's OWN frame (title bar, caption buttons, system menu) says where the window is, not what the application is doing
        pre = f"w{gi}:" if gi else ""
        for n in nodes:
            if n.ctype == "TitleBarControl" or (n.parent in frame_ids):
                frame_ids.add(n.idx)
                continue
            if n.offscreen or n.rect[2] <= n.rect[0]:
                continue
            val = _editable_value(n) if read_values < 10 else None
            if val is not None:
                read_values += 1
            if not n.name and val is None:
                continue
            if n.role in ("button", "menuitem") and fold(n.name) in safety.CHROME and n.parent >= 0 and nodes[n.parent].ctype in ("WindowControl", "TitleBarControl"):
                continue
            k = pre + _key(n, ordinals)
            if n.role in TEXTY:
                texts[k] = (n.name or n.role) if val is None else f"{n.name or n.role}={val[:60]}[{len(val)}]"
            else:
                names[k] = n.name
            if n.role in ACTIVE_ROLES or n.pats:
                states[k] = f"sel={n.selected},tog={n.toggle_state},exp={n.expand_state},en={n.enabled}"
            p, container = n.parent, ""
            while p >= 0:
                q = nodes[p]
                if q.name and q.role in ("pane", "group", "tab", "toolbar", "list", "tree", "menubar", "statusbar", "window", "custom"):
                    container = q.name
                    break
                p = q.parent
            cont.setdefault(container or "(window)", []).append(fold(n.name or n.role))
    try:
        wins = tuple(sorted(hin.process_windows(hwnd, include_hidden=False)))
    except Exception:
        wins = ()''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
