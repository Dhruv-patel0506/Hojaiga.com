import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/menus.py", [
    (r'''def _item_label(n: Any)''', r'''def collapse(n: Any, deadline_s: float = 1.5) -> bool:
    """Close an opener again through ExpandCollapse.Collapse: a combo-box or drop-down popup does not always follow Escape (it needs focus), the pattern always works."""
    res: Dict[str, bool] = {}

    def work() -> None:
        try:
            from .effectors import pattern_of
            p = pattern_of(n.ctrl, "ExpandCollapse")
            if p is not None:
                p.Collapse()
                res["ok"] = True
        except Exception:
            res["ok"] = False

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(deadline_s)
    return bool(res.get("ok"))


def _item_label(n: Any)'''),
    (r'''        # close it again and make sure the application is back where it was
        for _ in range(3):
            try:
                fx.key("escape")
            except Exception:
                pass
            time.sleep(0.2)
            if op.role == "tabitem":
                break''', r'''        # close it again and make sure the application is back where it was
        for tries in range(3):
            if op.role != "tabitem" and ok:
                collapse(op)
                time.sleep(0.25)
            else:
                try:
                    fx.key("escape")
                except Exception:
                    pass
                time.sleep(0.2)
            if op.role == "tabitem":
                break
            if tries >= 1:
                try:
                    fx.key("escape")
                except Exception:
                    pass'''),
])
print("ok")
