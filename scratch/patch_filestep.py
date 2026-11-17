import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch(R + "dialogs.py", [
    (r'''FILE_STEP_RX = re.compile(r"(?i)(\b(file name|filename|folder|directory|browse|location|save in|save as type|file type|files of type|where to save|where you want to save)\b|"
                          r"\b(choose|select|pick|find|locate|navigate to|go to|open|double-?click)\b[^.>]{0,40}\b(file|files|image|images|picture|photo|document|folder|csv|spreadsheet|pdf)\b|"''',
     r'''FILE_STEP_RX = re.compile(r"(?i)(\b(file name|filename|folder|directory|browse|location|save in|save as type|file type|files of type|where to save|where you want to save)\b|"
                          r"\b(choose|select|pick|find|locate|navigate to|go to|open|double-?click)\b[^.>]{0,40}\b(files?(?!\s+(?:menu|tab|button))|images?|pictures?|photos?|documents?|folders?|csv|spreadsheet|pdf)\b|"'''),
    ('''# ===================================================================================================================== the clipboard''', '''_MENU_PATH_RX = re.compile(r"(?:[\\w&./+-]+(?:\\s[\\w&./+-]+){0,2}\\s*>\\s*)+[\\w&./+-]+(?:\\s[\\w&./+-]+)?")


def is_file_step_text(raw: str) -> bool:
    """Does a guide step belong to a file dialog? A menu path ('Select File > Page setup') and the File MENU are not file choosing, whatever words they share with it."""
    t = _MENU_PATH_RX.sub(" ", (raw or "").replace("**", ""))
    return bool(FILE_STEP_RX.search(t))


# ===================================================================================================================== the clipboard'''),
])
patch(R + "executor.py", [
    ('''        from .dialogs import FILE_STEP_RX
        return st.kind == "dialog" or (st.source == "guide" and st.kind in ("unknown", "verb") and bool(FILE_STEP_RX.search(st.goal or "")))''',
     '''        from .dialogs import is_file_step_text
        return st.kind == "dialog" or (st.source == "guide" and st.kind in ("unknown", "verb") and is_file_step_text(st.goal or ""))'''),
])
patch(R + "workflows.py", [
    ('''    from .dialogs import FILE_STEP_RX, COPY_RX, PASTE_RX''', '''    from .dialogs import is_file_step_text, COPY_RX, PASTE_RX'''),
    ('''    if how == "dialog" or FILE_STEP_RX.search(raw):''', '''    if how == "dialog" or is_file_step_text(raw):'''),
])
print("ok")
