import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


R = "D:/new_automation/All codes/core_organs/"
patch(R + "professor/dialogs.py", [
    (r'''r"\b(click|press|select|choose)\b[^.>]{0,12}\b(open|save|select folder|ok|upload|insert|import|export)\b|"''', r'''r"\b(click|press|select|choose)\b[^.>]{0,12}\b(open|save|select folder|upload|insert|import|export)\b|"'''),
])
patch(R + "professor/executor.py", [
    ('''    @staticmethod
    def _is_file_step(st: Step) -> bool:
        from .dialogs import is_file_step_text
        return st.kind == "dialog" or (st.source == "guide" and st.kind in ("unknown", "verb") and is_file_step_text(st.goal or ""))''', '''    def _is_file_step(self, st: Step) -> bool:
        """Does this step of the guide belong to a file dialog? By its wording; 'click OK / Done' only while a file dialog the handler completed is still being followed."""
        from .dialogs import is_file_step_text
        if st.kind == "dialog":
            return True
        if st.source != "guide" or st.kind not in ("unknown", "verb"):
            return False
        g = st.goal or ""
        return is_file_step_text(g) or (self._file_followups > 0 and bool(re.search(r"(?i)\\b(click|press|select|choose)\\b\\W*(ok|done|apply|confirm)\\b", g)))'''),
])
patch(R + "si_tests_apprun.py", [
    ('''        file_steps = [X.Executor._is_file_step(st(g)) for g in ("Select the image you want to open.", "Type a name for your file in the File name box.", "Click Save.", "In the Save As dialog, choose a folder.")]
        not_file_steps = [X.Executor._is_file_step(st(g)) for g in ("Click File > Open.", "Select the Pencil tool.", "Rotate the picture.")]''',
     '''        file_steps = [ex._is_file_step(st(g)) for g in ("Select the image you want to open.", "Type a name for your file in the File name box.", "Click Save.", "In the Save As dialog, choose a folder.")]
        not_file_steps = [ex._is_file_step(st(g)) for g in ("Click File > Open.", "Select the Pencil tool.", "Rotate the picture.", "Select OK.", "Select Save as from the File menu.")]
        ex._file_followups = 2
        ok_while_following = ex._is_file_step(st("Select OK."))
        ex._file_followups = 0'''),
    ('''"file_step_wording_vs_ordinary_steps": all(file_steps) and not any(not_file_steps),''', '''"file_step_wording_vs_ordinary_steps": all(file_steps) and not any(not_file_steps) and ok_while_following,'''),
    ('''"workflow_becomes_a_task": task["goal"] == "Header and footer" and len(task["steps"]) == 3 and task["source"] == "https://example.test/guide"}''',
     '''"workflow_becomes_a_task": task["goal"] == "Header and footer" and len(task["steps"]) == hdr["step_count"] and task["source"] == "https://example.test/guide"}'''),
])
print("ok")
