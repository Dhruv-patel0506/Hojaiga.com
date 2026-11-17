import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''    root = os.path.dirname(os.path.abspath(exe))
    if not os.path.isdir(root):
        return [], [f"install folder not found: {root}"]
    roots = [root]'''
new = '''    root = os.path.dirname(os.path.abspath(exe))
    if not os.path.isdir(root):
        return [], [f"install folder not found: {root}"]
    shared = shared_folder_reason(root)
    if shared:
        return [], [f"{root} is {shared}: it holds many applications, so none of its files is THIS application's guide (a guide must come from a page you name, or the web if you enabled it)"]
    roots = [root]'''
assert old in s
s = s.replace(old, new, 1)
old2 = "def local_candidates("
new2 = '''def shared_folder_reason(folder: str) -> str:
    """'' for an application's own folder; otherwise why it is NOT (Windows system folders, Program Files roots, a user's home, any folder holding dozens of programs)."""
    f = os.path.normcase(os.path.abspath(folder)).rstrip("\\\\/")
    shared = set()
    for var, subs in (("WINDIR", ("", "system32", "syswow64", "winsxs", "system")), ("SystemRoot", ("", "system32", "syswow64")), ("ProgramFiles", ("",)), ("ProgramFiles(x86)", ("",)),
                      ("ProgramW6432", ("",)), ("ProgramData", ("",)), ("USERPROFILE", ("", "downloads", "desktop", "documents")), ("LOCALAPPDATA", ("", "programs")), ("APPDATA", ("",))):
        base = os.environ.get(var)
        if base:
            for sub in subs:
                shared.add(os.path.normcase(os.path.abspath(os.path.join(base, sub))).rstrip("\\\\/"))
    if f in shared:
        return "a shared system / profile folder"
    try:
        n_exe = sum(1 for e in os.scandir(folder) if e.name.lower().endswith(".exe"))
    except OSError:
        n_exe = 0
    return f"a folder with {n_exe} executables" if n_exe > 60 else ""


def local_candidates('''
assert old2 in s
s = s.replace(old2, new2, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("shared-folder guard added")
