import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-30:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/"
patch(B + "professor/session.py", [
    ("speak: bool = True, image: Optional[Image.Image] = None) -> Dict[str, Any]:", "speak: bool = True, image: Optional[Image.Image] = None, model: Optional[Tuple[ScreenModel, Image.Image]] = None) -> Dict[str, Any]:"),
    ("        sm, img, info = self.look(hwnd, image=image)\n        cat, _arch = self.frame(sm, hwnd)\n        boxes, labels, hotkeys, missing", "        sm, img = model if model is not None else self.look(hwnd, image=image)[:2]\n        cat, _arch = self.frame(sm, hwnd)\n        boxes, labels, hotkeys, missing"),
])
patch(B + "si_tests_professor.py", [
    ("""        res, ran = GF.search_dorks(ident, GF.default_fetch, stub, delay_s=0.7, sleep=lambda s: sleeps.append(s))
        ranked = GF.rank_results(ident, res)""", """        res, ran = GF.search_dorks(ident, GF.default_fetch, stub, delay_s=0.7, sleep=lambda s: sleeps.append(s))
        n_queries = len(seen_q)
        ranked = GF.rank_results(ident, res)"""),
    ("\"queries_run_politely_and_merged\": len(seen_q) == 5 and len(sleeps) == 4", "\"queries_run_politely_and_merged\": n_queries == 5 and len(sleeps) == 4"),
    ("""    for a in tr.arrival[1:-1]:
        v1, v2 = tr.velocity(a - 0.004), tr.velocity(a + 0.004)
        joins.append(math.hypot(v1[0] - v2[0], v1[1] - v2[1]) / max(1.0, math.hypot(*tr.velocity(a))))""", """    wide = []
    for a in tr.arrival[1:-1]:
        v1, v2 = tr.velocity(a - 0.0005, h=1.25e-4), tr.velocity(a + 0.0005, h=1.25e-4)
        joins.append(math.hypot(v1[0] - v2[0], v1[1] - v2[1]) / max(1.0, math.hypot(*tr.velocity(a, h=1.25e-4))))
        w1, w2 = tr.velocity(a - 0.004, h=1e-3), tr.velocity(a + 0.004, h=1e-3)                  # the same jump measured 8x wider: a continuous curve's jump shrinks with the probe distance
        wide.append(math.hypot(w1[0] - w2[0], w1[1] - w2[1]) / max(1.0, math.hypot(*tr.velocity(a, h=1e-3))))"""),
    ("\"no_stop_and_go_velocity_continuous_at_joins\": all(j < 0.15 for j in joins),", "\"no_stop_and_go_velocity_continuous_at_joins\": all(j < 0.05 for j in joins) and all(j < w for j, w in zip(joins, wide)),"),
    ("    out = ps.demonstrate(sk, image=img)", "    out = ps.demonstrate(sk, model=(sm, img))"),
])
print("fix2 applied")
