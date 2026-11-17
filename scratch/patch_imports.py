import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/sweeper.py", [
    (r'''from .capture import Frame, changed_boxes, changed_fraction, frame_from_image, frame_hash, grab_box, grab_screen, grab_window, hash_distance, \
    monitor_at, pick_target_window, window_info, foreground_hwnd''', r'''from .capture import Frame, changed_boxes, changed_fraction, frame_from_image, frame_hash, grab_box, grab_composite, grab_screen, grab_window, hash_distance, \
    monitor_at, pick_target_window, window_info, foreground_hwnd, virtual_screen'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        g = GS.ground_step(gs, self.catalog)
        if g.how in ("path", "label", "chord") and g.verb is not None:
            ns = self._step_for_verb(g.verb, st.goal, g.conf, "guide", st.cite, gs.action if gs.action in ("on", "off") else "", gs.text if (gs.action == "type" and gs.text) else "")
            ns.index = st.index
            ns.note = "grounded just in time (the control appeared after an earlier step)"
            return ns''', r'''        g = GS.ground_step(gs, self.catalog)
        if g.how in ("path", "label", "chord") and g.verb is not None:
            txt = gs.text if (gs.action == "type" and gs.text) else ""
            if not txt and gs.action in ("type", "set") and (g.verb.role in FIELD_ROLES or g.verb.role == "field"):
                txt = self.placeholder                                    # the manual says only 'enter a name': a neutral placeholder stands in
            ns = self._step_for_verb(g.verb, st.goal, g.conf, "guide", st.cite, gs.action if gs.action in ("on", "off") else "", txt)
            ns.index = st.index
            ns.note = "grounded just in time (the control appeared after an earlier step)" + (" - the manual gives no literal value: a neutral placeholder is entered" if txt == self.placeholder else "")
            return ns'''),
])
print("ok")
