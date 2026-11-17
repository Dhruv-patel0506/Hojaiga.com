import ast
import io

D = "D:/new_automation/All codes/core_organs/professor/dialogs.py"
s = io.open(D, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:100]
    s = s.replace(old, new, 1)


rep('''    edits = [k for k in kids if k[2] == "Edit" and inside(k[0], "ComboBoxEx32")] or [k for k in kids if k[2] == "Edit" and k[4] in (0x480, 0x47C)]
    if edits:
        info.edit_hwnd = edits[0][0]
        info.file_edit = edits[0][0]
        info.default_name = edits[0][3].strip()''', '''    def edit_score(k: Tuple[int, int, str, str, int]) -> int:
        """Which Edit is the FILE NAME field: the Vista dialog's id 1001, the classic ids, an edit inside a combo box; never the search box or the address bar."""
        sc = 0
        if k[4] == 1001 or k[4] in (0x480, 0x47C):
            sc += 3
        if inside(k[0], "ComboBoxEx32"):
            sc += 2
        if inside(k[0], "ComboBox"):
            sc += 1
        if any(inside(k[0], bad) for bad in ("UniversalSearchBand", "SearchEditBoxWrapperClass", "Address Band Root", "ToolbarWindow32", "Breadcrumb Parent")):
            sc -= 10
        return sc
    edits = sorted((k for k in kids if k[2] == "Edit"), key=lambda k: -edit_score(k))
    if edits and edit_score(edits[0]) >= 1:
        info.edit_hwnd = edits[0][0]
        info.file_edit = edits[0][0]
        info.default_name = edits[0][3].strip()''')
rep('''        base = _safe(name or (re.sub(r"(?i)\\b(open|import|select|choose|browse|file|to|from)\\b", " ", hint or "").strip().replace(" ", "_")[:24] or "fixture")) or "fixture"''',
    '''        base = _safe(name) if name else "hojaiga-fixture"                         # the name the application proposed when it proposed one, else a plain one''')
rep('''_IGNORABLE_NAMES = ("CanIncludeInClipboardHistory",''', '''_IGNORABLE_PREFIXES = ("chromium", "chrome", "application/x-", "cf_", "windows.clipboard", "microsoft office", "x-")        # the source-tracking tokens browsers and Office add: losing them changes nothing the person sees
_IGNORABLE_NAMES = ("CanIncludeInClipboardHistory",''')
rep('''                elif name in _IGNORABLE_NAMES:
                    continue''', '''                elif name in _IGNORABLE_NAMES or name.lower().startswith(_IGNORABLE_PREFIXES):
                    continue''')
ast.parse(s)
io.open(D, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
