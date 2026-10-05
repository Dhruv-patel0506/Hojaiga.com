"""
static_knowledge.py -- everything knowable about an app BEFORE it is ever started (zero UI, zero launch).

First contact with an app used to mean: launch it, wait for its tree, crawl menus, probe. This module reads what the
app already says about itself, in milliseconds, and stores it as dated, sourced facts + catalog-trust commands:

  1. the program file       PE headers (GUI/console, .NET, imports), version info, manifest (elevation = HITL)
  2. its UI toolkit         fingerprinted from imports + sibling files (Qt, WinUI, Electron/Chromium, Java, WPF, MFC,
                            GPU canvases ...) with that toolkit's PERCEPTION/INPUT STRATEGY (measured facts of this repo:
                            XAML ignores posted keys, Chromium builds its tree only after an accessibility wake, ...)
  3. its command structure  menu bar + context menus + accelerator table + prompt strings from the PE resources, joined
                            by command ID (see pe_resources); Store-package manifests (file types, verbs, protocols)
  4. what it opens          file-type associations (registry + Appx manifest) and the command line that opens a file
  5. shipped data sources   keymap / keybinding / menu / manifest-"contributes" files and Electron's package.json
                            (also inside app.asar), found by SHAPE (file-name patterns + parsers), never by app name
  6. a capability profile   inferred from the evidence above (what it can DO), with an archetype ranking by evidence

Nothing here is per-app: the tables below describe UI toolkits, file formats and generic UI vocabulary. Every fact is
stored with its source; commands enter at `catalog` trust (never `learned`: only a verified run earns that).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from core_organs import pe_resources as pr

_IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------------------------
# DATA: UI toolkits (not apps). `files` match names under the exe directory (depth <= 2), `imports` match imported DLL
# names. `strategy` is what the loop should assume about driving ANY app built on that toolkit.
# ---------------------------------------------------------------------------------------------

FRAMEWORKS: List[Dict[str, Any]] = [
    {"id": "electron", "files": [r"(^|/)resources/app\.asar$", r"(^|/)resources/app/package\.json$", r"^electron\.exe$"],
     "imports": [], "family": "chromium",
     "strategy": {"uia": "after-wake", "native_menus": False, "input": ["uia_invoke", "post_click_coord", "key"],
                  "ocr_fallback": True, "cdp": "possible-with-remote-debugging-port",
                  "notes": "web content: the accessibility tree is built only after an accessibility client is detected"}},
    {"id": "chromium", "files": [r"(^|/)chrome_100_percent\.pak$", r"(^|/)v8_context_snapshot\.bin$", r"(^|/)chrome_elf\.dll$"],
     "imports": ["chrome_elf.dll"], "family": "chromium",
     "strategy": {"uia": "after-wake", "native_menus": False, "input": ["uia_invoke", "post_click_coord", "key"],
                  "ocr_fallback": True, "cdp": "possible-with-remote-debugging-port",
                  "notes": "web content: the accessibility tree is built only after an accessibility client is detected"}},
    {"id": "cef_embedded", "files": [r"(^|/)libcef\.dll$", r"(^|/)(cef|cef_)\w*\.pak$"], "imports": ["libcef.dll"], "family": "chromium",
     "strategy": {"uia": "after-wake-often-empty", "native_menus": False, "input": ["ocr_coord_click", "key"],
                  "ocr_fallback": True, "cdp": "only-if-embedder-enabled",
                  "notes": "embedded browser: the UIA tree can stay empty even after a wake; OCR/vision rung needed"}},
    {"id": "winui3", "files": [r"(^|/)Microsoft\.UI\.Xaml\.dll$", r"(^|/)Microsoft\.WindowsAppRuntime\w*\.dll$", r"xamlui\.dll$"],
     "imports": ["microsoft.ui.xaml.dll", "microsoft.windowsappruntime.bootstrap.dll"], "family": "xaml",
     "strategy": {"uia": "full", "native_menus": False, "input": ["uia_invoke", "uia_pattern"], "posted_keys": "ignored",
                  "posted_mouse": "often-ignored", "ocr_fallback": False,
                  "notes": "XAML host: posted keys/mouse are not delivered to XAML input; drive through UIA patterns"}},
    {"id": "uwp_xaml", "files": [r"(^|/)AppxManifest\.xml$"], "imports": ["windows.ui.xaml.dll"], "family": "xaml",
     "strategy": {"uia": "full", "native_menus": False, "input": ["uia_invoke", "uia_pattern"], "posted_keys": "ignored",
                  "posted_mouse": "often-ignored", "ocr_fallback": False,
                  "notes": "packaged app on a XAML host; hidden windows may expose controls with empty rectangles"}},
    {"id": "qt", "files": [r"(^|/)Qt[56]?Core\.dll$", r"(^|/)Qt[56]Widgets\.dll$", r"(^|/)platforms/qwindows\.dll$"],
     "imports": ["qt5core.dll", "qt6core.dll", "qt5widgets.dll", "qt6widgets.dll"], "family": "qt",
     "strategy": {"uia": "partial", "native_menus": False, "input": ["uia_invoke", "post_click_coord", "key"],
                  "ocr_fallback": True, "notes": "Qt accessibility is partial: names usually present, patterns often missing"}},
    {"id": "java", "files": [r"(^|/)jvm\.dll$", r"(^|/)\w+\.jar$", r"(^|/)jre/", r"(^|/)jbr/"], "imports": ["jvm.dll"], "family": "java",
     "strategy": {"uia": "absent-without-access-bridge", "native_menus": False, "input": ["ocr_coord_click", "key"],
                  "ocr_fallback": True, "notes": "Swing/AWT/JavaFX: no UIA unless the Java Access Bridge is on; use OCR/vision"}},
    {"id": "gtk", "files": [r"(^|/)libgtk-[34][\w.-]*\.dll$"], "imports": [], "family": "gtk",
     "strategy": {"uia": "partial", "native_menus": False, "input": ["key", "post_click_coord"], "ocr_fallback": True,
                  "notes": "GTK on Windows exposes little UIA"}},
    {"id": "wxwidgets", "files": [r"(^|/)wx\w*(u|ud)?_core[\w_.]*\.dll$"], "imports": [], "family": "win32",
     "strategy": {"uia": "good", "native_menus": True, "input": ["wm_command", "uia_invoke", "key"],
                  "ocr_fallback": False, "notes": "wrapper over native controls"}},
    {"id": "tk", "files": [r"(^|/)tcl\d+t?\.dll$", r"(^|/)tk\d+t?\.dll$"], "imports": ["tcl86t.dll", "tk86t.dll"], "family": "tk",
     "strategy": {"uia": "partial", "native_menus": True, "input": ["wm_command", "key", "post_click_coord"],
                  "ocr_fallback": True, "notes": "Tk menubar is a native HMENU; widgets are custom-drawn"}},
    {"id": "flutter", "files": [r"(^|/)flutter_windows\.dll$"], "imports": ["flutter_windows.dll"], "family": "gpu_canvas",
     "strategy": {"uia": "semantics-only-when-enabled", "native_menus": False, "input": ["key", "ocr_coord_click"],
                  "ocr_fallback": True, "notes": "own renderer; UIA semantics tree only if accessibility is requested"}},
    {"id": "unity", "files": [r"(^|/)UnityPlayer\.dll$", r"_Data/"], "imports": ["unityplayer.dll"], "family": "gpu_canvas",
     "strategy": {"uia": "none", "native_menus": False, "input": ["key", "ocr_coord_click"], "ocr_fallback": True,
                  "notes": "game/engine canvas: no accessibility tree; vision/OCR only"}},
    {"id": "sdl_canvas", "files": [r"(^|/)SDL[23]?\.dll$"], "imports": ["sdl2.dll", "sdl3.dll"], "family": "gpu_canvas",
     "strategy": {"uia": "none", "native_menus": False, "input": ["key", "ocr_coord_click"], "ocr_fallback": True,
                  "notes": "own renderer; no accessibility tree"}},
    {"id": "office_ribbon", "files": [r"(^|/)mso\d*(win32client)?\.dll$", r"(^|/)mso\d+\w*\.dll$"],
     "imports": ["mso.dll", "mso20win32client.dll", "mso30win32client.dll", "mso40uiwin32client.dll", "mso98win32client.dll", "mso99lwin32client.dll"],
     "family": "office",
     "strategy": {"uia": "full-ribbon", "native_menus": False, "input": ["uia_invoke", "uia_pattern", "key"],
                  "ocr_fallback": False, "notes": "ribbon exposed through UIA (tabs, groups, buttons); backstage/file dialogs are separate windows"}},
    {"id": "mfc", "files": [r"(^|/)mfc\d+\w*\.dll$"], "imports": ["mfc42.dll", "mfc42u.dll", "mfc100.dll", "mfc100u.dll", "mfc110u.dll",
                                                                "mfc120u.dll", "mfc140.dll", "mfc140u.dll"], "family": "win32",
     "strategy": {"uia": "good", "native_menus": True, "input": ["wm_command", "post_click", "key"], "ocr_fallback": False,
                  "notes": "classic HMENU + accelerator table: every command has an ID reachable with WM_COMMAND"}},
    {"id": "wpf", "files": [r"(^|/)PresentationFramework\.dll$", r"(^|/)PresentationCore\.dll$"], "imports": ["presentationnative_v0300.dll", "wpfgfx_v0400.dll"],
     "family": "dotnet", "strategy": {"uia": "full", "native_menus": False, "input": ["uia_invoke", "uia_pattern", "post_click"],
                                      "ocr_fallback": False, "notes": ".NET WPF: rich UIA with AutomationIds"}},
    {"id": "winforms", "files": [r"(^|/)System\.Windows\.Forms\.dll$"], "imports": [], "family": "dotnet", "needs_clr": True,
     "strategy": {"uia": "good", "native_menus": True, "input": ["uia_invoke", "wm_command", "post_click"], "ocr_fallback": False,
                  "notes": ".NET WinForms: native controls, UIA via MSAA bridge"}},
    {"id": "python_app", "files": [r"(^|/)python3\d*\.dll$", r"(^|/)(PyQt|PySide)\d?/"], "imports": [], "family": "python",
     "strategy": {"uia": "depends-on-gui-lib", "native_menus": False, "input": ["uia_invoke", "key"], "ocr_fallback": True,
                  "notes": "frozen python app: behaviour follows its GUI library"}},
]

# generic Windows convention: the file name patterns of data that enumerate commands
SOURCE_FILE_PATTERNS = [
    (r"^keybindings?[\w.-]*\.(json|jsonc)$", "keymap_json"), (r"^keymaps?[\w.-]*\.(json|jsonc|py|txt|ini|conf)$", "keymap_any"),
    (r"^(default[-_])?(shortcuts?|hotkeys?|accelerators?)[\w.-]*\.(json|ini|conf|txt|xml)$", "keymap_any"),
    (r"^[\w.-]*\.(keymap|kbd)$", "keymap_any"), (r"^package\.json$", "manifest_contributes"),
    (r"^(default[-_])?(settings|preferences|config)[\w.-]*\.(json|jsonc|ini|conf)$", "settings"),
]

# file extension -> generic category (what KIND of document an app works on)
EXT_CATEGORY = {
    "text": {".txt", ".log", ".md", ".ini", ".cfg", ".conf", ".inf", ".csv", ".tsv", ".nfo", ".rtf", ".text"},
    "code": {".py", ".js", ".ts", ".json", ".xml", ".html", ".htm", ".css", ".c", ".cpp", ".h", ".java", ".cs", ".go", ".rs",
             ".php", ".rb", ".sh", ".bat", ".ps1", ".yaml", ".yml", ".sql", ".lua", ".kt", ".swift"},
    "image": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico", ".svg", ".psd", ".heic", ".raw"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".mid", ".midi"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".mpg", ".mpeg"},
    "spreadsheet": {".xlsx", ".xls", ".xlsm", ".ods", ".csv"},
    "document": {".docx", ".doc", ".odt", ".rtf", ".pdf", ".dotx"},
    "presentation": {".pptx", ".ppt", ".odp", ".ppsx"},
    "archive": {".zip", ".7z", ".rar", ".tar", ".gz", ".iso", ".cab"},
    "model3d": {".blend", ".obj", ".fbx", ".stl", ".3ds", ".dae", ".gltf", ".glb", ".step", ".stp", ".dwg", ".dxf"},
    "web": {".html", ".htm", ".url", ".mhtml", ".xhtml", ".webloc"},
    "registry": {".reg"},
    "font": {".ttf", ".otf", ".fon"},
}

# generic UI vocabulary -> capability (matched against command labels / menu paths / dialog titles)
LABEL_CAPS = {
    # file operations only count when they ARE the label (a path segment), not when the word appears inside another label
    # ('Open Navigation' opens a pane; it is not 'open a file')
    "save": r"(^|> )save( all)?(\.\.\.|\u2026)?\s*$", "save_as": r"(^|> )(save as|save a copy|export( as)?)\b", "open": r"(^|> )open( file| folder| recent| with| project| workspace| a)?(\.\.\.|\u2026)?\s*$",
    "new": r"(^|> )new( file| document| window| tab| project| folder)?(\.\.\.|\u2026)?\s*$",
    "print": r"(^|> )print\b", "undo": r"\bundo\b", "redo": r"\bredo\b", "find": r"\bfind\b|\bsearch\b", "replace": r"\breplace\b",
    "zoom": r"\bzoom\b", "clipboard": r"\b(copy|paste|cut)\b", "select_all": r"\bselect all\b", "word_wrap": r"\bword wrap\b",
    "font": r"\bfont\b", "insert": r"\binsert\b", "table": r"\btable\b", "layer": r"\blayers?\b", "filter": r"\bfilters?\b",
    "drawing_tools": r"\b(brush|pencil|eraser|fill|shapes?|crop|resize|rotate|canvas)\b",
    "run_build": r"\b(run|debug|build|compile)\b", "terminal": r"\b(terminal|console|command prompt)\b",
    "media_transport": r"\b(play|pause|playlist|seek|next track|previous track)\b", "browsing": r"\b(bookmarks?|downloads?|address bar|reading list)\b",
    "tabs": r"\b(new tab|close tab|next tab)\b", "spreadsheet_ops": r"\b(chart|formula|cell|sheet|pivot|sort)\b",
    "slides": r"\bslides?\b", "modeling": r"\b(mesh|extrude|vertex|vertices|render|modifier|bevel)\b",
    "file_browsing": r"\b(folder|directory|rename|properties)\b", "calculator_ops": r"\b(memory|scientific|programmer|clear entry|standard)\b",
    "registry_ops": r"\b(hive|registry)\b|\bnew (key|value)\b", "settings": r"\b(settings|preferences|options)\b", "help": r"\b(help|about)\b",
    "view_modes": r"\b(view|status bar|toolbar|sidebar|full screen)\b", "formatting": r"\b(bold|italic|underline|align|bullet|indent)\b",
}

# archetype -> capability weights (+ extension categories as "ext:<cat>"). Evidence ranking, not a name list.
ARCHETYPE_RULES: Dict[str, Dict[str, float]] = {
    "text_editor": {"ext:text": 3, "find": 1, "replace": 1.5, "word_wrap": 2, "font": 1, "save_as": 0.5, "clipboard": 0.5, "undo": 0.5,
                    "layer": -3, "drawing_tools": -3, "spreadsheet_ops": -2, "slides": -2, "run_build": -1},
    "raster_editor": {"ext:image": 3, "drawing_tools": 2.5, "layer": 2, "filter": 1.5, "zoom": 0.5, "save_as": 0.5, "word_wrap": -2},
    "ide": {"ext:code": 3, "run_build": 2.5, "terminal": 2, "find": 0.5, "replace": 0.5, "save": 0.3},
    "office_doc": {"ext:document": 2, "ext:spreadsheet": 2, "ext:presentation": 2, "spreadsheet_ops": 1.5, "slides": 1.5,
                   "formatting": 1.5, "table": 1, "insert": 1, "print": 0.3},
    "media_player": {"ext:audio": 2.5, "ext:video": 2.5, "media_transport": 3},
    "file_manager": {"file_browsing": 2.5, "ext:archive": 0.5, "folder": 0},
    "browser": {"ext:web": 3, "browsing": 3, "tabs": 2.5},
    "3d_suite": {"ext:model3d": 3, "modeling": 3, "layer": 0.3},
    "calculator": {"calculator_ops": 4, "save": -2, "open": -2, "print": -2},
    "system_tool": {"registry_ops": 3, "ext:registry": 2, "settings": 0.3},
}

# What DEFINES a kind of app. Shared file verbs (open / save / print / find / undo) appear in nearly every program and can
# never make one a 'text editor' by themselves: a kind is only claimed when at least one of its defining capabilities is present.
ARCHETYPE_DEFINING: Dict[str, set] = {
    "text_editor": {"word_wrap", "replace", "font"},
    "raster_editor": {"drawing_tools", "layer", "filter"},
    "ide": {"run_build", "terminal"},
    "office_doc": {"spreadsheet_ops", "slides", "formatting", "table", "insert"},
    "media_player": {"media_transport"},
    "file_manager": {"file_browsing"},
    "browser": {"tabs", "browsing"},
    "3d_suite": {"modeling"},
    "calculator": {"calculator_ops"},
    "system_tool": {"registry_ops"},
}

# ---------------------------------------------------------------------------------------------
# 1. locating the program
# ---------------------------------------------------------------------------------------------

def exe_for(target: Any) -> str:
    """hwnd -> its process image; existing path -> itself; otherwise a name resolved via PATH / App Paths / Start menu."""
    if isinstance(target, int) and target:
        try:
            from core_organs import organ_48_app_behavior_model as bm
            return bm._exe_of_hwnd(target)
        except Exception:
            return ""
    t = str(target or "").strip().strip('"')
    if t and os.path.isfile(t):
        return os.path.abspath(t)
    import shutil
    name = t if t.lower().endswith(".exe") else t + ".exe"
    alias = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", os.path.basename(name))
    if os.path.lexists(alias):                       # an app-execution alias launches the Store package, not a same-named stub
        p = exe_for_package(os.path.splitext(os.path.basename(name))[0])
        if p:
            return p
    w = shutil.which(name)
    if w:
        return os.path.abspath(w)
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + os.path.basename(name)) as k:
                    v, _ = winreg.QueryValueEx(k, "")
                    if v and os.path.isfile(v.strip('"')):
                        return v.strip('"')
            except OSError:
                continue
    except Exception:
        pass
    p = exe_for_package(t)
    if p:
        return p
    try:
        from core_organs import universal_scan as us
        r = us.resolve_app(t)
        if r and len(r) > 1 and r[1] and os.path.isfile(str(r[1])):
            return str(r[1])
    except Exception:
        pass
    return ""


def _is_shared_dir(d: str) -> bool:
    """A directory many unrelated programs live in (System32, the Windows dir, a Program Files root, a user's
    Downloads/Desktop): its file list describes the OS, not the program."""
    dl = os.path.normcase(os.path.abspath(d)).rstrip("\\")
    shared = {os.path.normcase(os.environ.get(v, "")).rstrip("\\") for v in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)",
                                                                             "ProgramW6432", "USERPROFILE", "TEMP")}
    shared |= {os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), x).lower() for x in ("system32", "syswow64")}
    shared |= {os.path.join(os.environ.get("USERPROFILE", ""), x).lower() for x in ("downloads", "desktop", "documents")}
    return dl in shared


def appx_packages() -> Dict[str, str]:
    """installed Store packages: {package full name: root folder}, from the per-user package repository (the folder
    itself is not listable, but its manifest is readable)."""
    out: Dict[str, str] = {}
    try:
        import winreg
        base = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as k:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(k, name) as sk:
                        root, _ = winreg.QueryValueEx(sk, "PackageRootFolder")
                        out[name] = root
                except OSError:
                    continue
    except Exception:
        pass
    return out


def exe_for_package(name: str) -> str:
    """'notepad' / 'calculator' -> the packaged app's entry exe, by matching package name or execution alias."""
    want = re.sub(r"[^a-z0-9]", "", (name or "").lower().replace(".exe", ""))
    if len(want) < 3:
        return ""
    for full, root in appx_packages().items():
        pname = full.split("_")[0].lower()
        if want not in re.sub(r"[^a-z0-9]", "", pname):
            continue
        info = appx_info(root)
        entry = info.get("entry_exe", "")
        if entry:
            p = os.path.join(root, entry)
            if os.path.isfile(p):
                return p
    return ""


def package_root(exe: str) -> str:
    """The Store-package folder an exe lives in ('' for a classic install)."""
    m = re.search(r"^(.*?\\WindowsApps\\[^\\]+)\\", exe or "", re.I)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------------------------
# 2. Store-package manifest
# ---------------------------------------------------------------------------------------------

def appx_info(pkg_root: str) -> Dict[str, Any]:
    """AppxManifest.xml: identity, entry exe + execution alias, file types with their verbs (CLI parameters), protocols,
    capabilities, runtime dependencies. {} when unreadable."""
    out: Dict[str, Any] = {}
    mf = os.path.join(pkg_root, "AppxManifest.xml")
    try:
        text = open(mf, encoding="utf-8", errors="replace").read()
    except Exception as exc:
        return {"error": f"manifest-unreadable:{type(exc).__name__}"}
    m = re.search(r'<Identity\s+Name="([^"]+)"[^>]*Version="([^"]+)"', text)
    if m:
        out["package"], out["package_version"] = m.group(1), m.group(2)
    m = re.search(r'<Application\s+[^>]*Executable="([^"]+)"', text)
    out["entry_exe"] = m.group(1) if m else ""
    m = re.search(r'ExecutionAlias\s+Alias="([^"]+)"', text)
    out["alias"] = m.group(1) if m else ""
    ft: Dict[str, List[str]] = {}
    verbs: Dict[str, str] = {}
    for blk in re.finditer(r'<uap:FileTypeAssociation\s+Name="([^"]+)">(.*?)</uap:FileTypeAssociation>', text, re.S):
        exts = re.findall(r"<uap:FileType>([^<]+)</uap:FileType>", blk.group(2))
        ft[blk.group(1)] = [e.strip().lower() for e in exts]
        for vid, params in re.findall(r'<uap\d*:Verb\s+Id="([^"]+)"\s+Parameters="([^"]*)"', blk.group(2)):
            verbs.setdefault(vid.lower(), params.replace("&quot;", '"'))
    out["file_types"] = sorted({e for v in ft.values() for e in v})
    out["verbs"] = verbs
    out["protocols"] = re.findall(r'<uap:Protocol\s+Name="([^"]+)"', text)
    out["capabilities"] = re.findall(r'<(?:\w+:)?Capability\s+Name="([^"]+)"', text)
    out["dependencies"] = re.findall(r'<PackageDependency\s+Name="([^"]+)"', text)
    out["ui_framework_hint"] = ("winui3" if any("windowsappruntime" in d.lower() for d in out["dependencies"]) else
                                "uwp_xaml" if any("vclibs" in d.lower() or "net.native" in d.lower() for d in out["dependencies"]) else "")
    return out


# ---------------------------------------------------------------------------------------------
# 3. file-type associations (registry), reverse-indexed once per process
# ---------------------------------------------------------------------------------------------

_FT_INDEX: Optional[Dict[str, Any]] = None


def _cmd_exe(cmd: str) -> str:
    m = re.match(r'\s*"([^"]+)"', cmd) or re.match(r"\s*(\S+\.exe)", cmd, re.I)
    return os.path.expandvars(m.group(1)).lower() if m else ""


def _file_type_index() -> Dict[str, Any]:
    global _FT_INDEX
    if _FT_INDEX is not None:
        return _FT_INDEX
    idx: Dict[str, Any] = {"by_path": {}, "by_name": {}, "open_cmd": {}}
    if not _IS_WINDOWS:
        _FT_INDEX = idx
        return idx
    import winreg
    root = winreg.HKEY_CLASSES_ROOT
    progid_exts: Dict[str, set] = {}
    try:
        i = 0
        exts: List[str] = []
        while True:
            try:
                k = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            if k.startswith("."):
                exts.append(k)
        for ext in exts:
            try:
                with winreg.OpenKey(root, ext) as hk:
                    try:
                        d, _ = winreg.QueryValueEx(hk, "")
                        if d:
                            progid_exts.setdefault(d, set()).add(ext.lower())
                    except OSError:
                        pass
                    try:
                        with winreg.OpenKey(hk, "OpenWithProgids") as hp:
                            j = 0
                            while True:
                                try:
                                    nm, _v, _t = winreg.EnumValue(hp, j)
                                except OSError:
                                    break
                                j += 1
                                progid_exts.setdefault(nm, set()).add(ext.lower())
                    except OSError:
                        pass
                    try:
                        with winreg.OpenKey(hk, "OpenWithList") as hl:
                            j = 0
                            while True:
                                try:
                                    nm = winreg.EnumKey(hl, j)
                                except OSError:
                                    break
                                j += 1
                                idx["by_name"].setdefault(nm.lower(), set()).add(ext.lower())
                    except OSError:
                        pass
            except OSError:
                continue
        for progid, exts_ in progid_exts.items():
            try:
                with winreg.OpenKey(root, progid + r"\shell\open\command") as hc:
                    cmd, _ = winreg.QueryValueEx(hc, "")
            except OSError:
                continue
            exe = _cmd_exe(cmd)
            if exe:
                idx["by_path"].setdefault(exe, set()).update(exts_)
                idx["open_cmd"].setdefault(exe, cmd)
        try:
            with winreg.OpenKey(root, "Applications") as ha:
                j = 0
                while True:
                    try:
                        nm = winreg.EnumKey(ha, j)
                    except OSError:
                        break
                    j += 1
                    try:
                        with winreg.OpenKey(ha, nm + r"\SupportedTypes") as hs:
                            e = 0
                            while True:
                                try:
                                    vn, _v, _t = winreg.EnumValue(hs, e)
                                except OSError:
                                    break
                                e += 1
                                idx["by_name"].setdefault(nm.lower(), set()).add(vn.lower())
                    except OSError:
                        pass
                    try:
                        with winreg.OpenKey(ha, nm + r"\shell\open\command") as hc:
                            cmd, _ = winreg.QueryValueEx(hc, "")
                            ex = _cmd_exe(cmd)
                            if ex:
                                idx["open_cmd"].setdefault(ex, cmd)
                    except OSError:
                        pass
        except OSError:
            pass
    except Exception:
        pass
    _FT_INDEX = idx
    return idx


def file_types_for(exe: str) -> Dict[str, Any]:
    idx = _file_type_index()
    low = (exe or "").lower()
    exts = set(idx["by_path"].get(low, set())) | set(idx["by_name"].get(os.path.basename(low), set()))
    return {"extensions": sorted(exts), "open_command": idx["open_cmd"].get(low, "")}


# ---------------------------------------------------------------------------------------------
# 4. framework fingerprint
# ---------------------------------------------------------------------------------------------

def _list_files(root: str, max_entries: int = 4000, depth: int = 2) -> List[str]:
    out: List[str] = []
    root = root.rstrip("\\/")
    base_depth = root.count(os.sep)
    try:
        for dp, dn, fn in os.walk(root):
            if dp.count(os.sep) - base_depth >= depth:
                dn[:] = []
            rel = os.path.relpath(dp, root).replace("\\", "/")
            rel = "" if rel == "." else rel + "/"
            for d in dn:
                out.append(rel + d + "/")
            for f in fn:
                out.append(rel + f)
            if len(out) >= max_entries:
                break
    except Exception:
        pass
    return out


def fingerprint_framework(exe: str, info: Dict[str, Any], files: List[str], appx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ranked toolkit matches (most specific first, FRAMEWORKS order). Always includes a native-Win32 fallback when the
    program imports only classic system DLLs."""
    imports = [i.lower() for i in info.get("imports", [])]
    out: List[Dict[str, Any]] = []
    for order, fw in enumerate(FRAMEWORKS):
        why: List[str] = []
        score = 0
        for pat in fw["files"]:
            rx = re.compile(pat, re.I)
            hit = next((f for f in files if rx.search(f)), None)
            if hit:
                why.append(f"file:{hit}")
                score += 1                       # a file merely lying nearby: a bundled library is not the toolkit
                break
        for imp in fw["imports"]:
            if imp in imports:
                why.append(f"import:{imp}")
                score += 3                       # the program itself links it
                break
        if fw.get("needs_clr") and not info.get("clr"):
            continue
        if fw["id"] == "uwp_xaml" and not (appx and not appx.get("error")):
            why = [w for w in why if w.startswith("import:")]
        if fw["id"] == "uwp_xaml" and appx and appx.get("ui_framework_hint") == "uwp_xaml":
            why.append("appx:dependencies")
            score += 3
        if fw["id"] == "winui3" and appx and appx.get("ui_framework_hint") == "winui3":
            why.append("appx:WindowsAppRuntime")
            score += 3
        if why:
            out.append({"id": fw["id"], "family": fw["family"], "evidence": why, "strategy": fw["strategy"],
                        "score": score, "_order": order})
    out.sort(key=lambda f: (-f["score"], f["_order"]))
    for o in out:
        o.pop("_order", None)
    if info.get("clr") and not any(o["family"] == "dotnet" for o in out):
        out.append({"id": "dotnet", "family": "dotnet", "evidence": ["pe:clr-header"],
                    "strategy": {"uia": "good", "native_menus": False, "input": ["uia_invoke", "post_click"], "ocr_fallback": False,
                                 "notes": "managed assembly (toolkit not identified)"}})
    classic = {"user32.dll", "gdi32.dll", "comctl32.dll", "comdlg32.dll", "shell32.dll", "kernel32.dll", "advapi32.dll"}
    if not out and info.get("ok") and imports and (classic & set(imports) or any(i.startswith("api-ms-win") for i in imports)):
        out.append({"id": "win32_native", "family": "win32", "evidence": ["imports:classic-system-dlls"],
                    "strategy": {"uia": "good", "native_menus": True, "input": ["wm_command", "uia_invoke", "post_click", "key"],
                                 "ocr_fallback": False, "notes": "plain Win32: HMENU readable without actuation; WM_COMMAND works headless"}})
    return out


# ---------------------------------------------------------------------------------------------
# 5. shipped data sources (found by shape)
# ---------------------------------------------------------------------------------------------

def _read_asar_member(asar: str, member: str, max_bytes: int = 2_000_000) -> str:
    """Read one file out of an Electron .asar (a JSON header + concatenated files)."""
    try:
        with open(asar, "rb") as fh:
            head = fh.read(16)
            hsize = struct.unpack_from("<I", head, 4)[0]
            jlen = struct.unpack_from("<I", head, 12)[0]
            if jlen <= 0 or jlen > 64 * 1024 * 1024:
                return ""
            meta = json.loads(fh.read(jlen).decode("utf-8", "replace"))
            node = meta
            for part in member.split("/"):
                node = node["files"][part]
            off, size = int(node["offset"]), int(node["size"])
            if size > max_bytes:
                return ""
            fh.seek(8 + hsize + off)
            return fh.read(size).decode("utf-8", "replace")
    except Exception:
        return ""


def parse_manifest_contributes(obj: Any) -> List[Dict[str, Any]]:
    """The `contributes` block of an extension-style package.json: command titles + keybindings. Works for any host that
    uses this manifest format (it is a format, not an app)."""
    out: List[Dict[str, Any]] = []
    if not isinstance(obj, dict):
        return out
    c = obj.get("contributes")
    if not isinstance(c, dict):
        return out
    keys: Dict[str, str] = {}
    for kb in c.get("keybindings", []) or []:
        if isinstance(kb, dict) and kb.get("command") and (kb.get("key") or kb.get("win")):
            keys.setdefault(kb["command"], str(kb.get("win") or kb.get("key")))
    for cm in c.get("commands", []) or []:
        if not isinstance(cm, dict) or not cm.get("command"):
            continue
        title = cm.get("title")
        if isinstance(title, dict):
            title = title.get("value") or title.get("original")
        if not isinstance(title, str) or title.startswith("%"):
            title = cm["command"]
        cat = cm.get("category")
        cat = cat.get("value") if isinstance(cat, dict) else cat
        name = f"{cat}: {title}" if cat and isinstance(cat, str) and not cat.startswith("%") else title
        out.append({"name": name, "goal": title, "verb": "palette", "palette_title": name, "command_id": cm["command"],
                    "shortcut": _chord(keys.get(cm["command"], "")), "origin_fmt": "manifest-contributes", "opaque": True})
    return out


def _chord(s: str) -> str:
    s = (s or "").lower().replace("cmd", "meta").replace("control", "ctrl")
    return re.sub(r"\s*\+\s*", "+", s).strip()


def harvest_install_sources(exe: str, *, budget_s: float = 3.0, max_files: int = 60) -> Dict[str, Any]:
    """Find and parse command/keymap/settings sources next to the program and in its Electron asar. Bounded by time and
    count. Returns {'commands': [...], 'settings_toggles': n, 'sources': [{'path','kind','found'}], 'skipped': [...]}."""
    from core_organs import organ_48_app_behavior_model as bm
    t0 = time.time()
    rep: Dict[str, Any] = {"commands": [], "settings_toggles": 0, "sources": [], "skipped": []}
    base = package_root(exe) or os.path.dirname(exe)
    if not base or not os.path.isdir(base):
        rep["skipped"].append("no-install-dir")
        return rep
    rx = [(re.compile(p, re.I), kind) for p, kind in SOURCE_FILE_PATTERNS]
    cands: List[Tuple[str, str]] = []
    try:
        for dp, dn, fn in os.walk(base):
            depth = dp[len(base):].count(os.sep)
            if depth > 4 or time.time() - t0 > budget_s:
                dn[:] = []
                if time.time() - t0 > budget_s:
                    rep["skipped"].append("walk-budget")
                    break
            dn[:] = [d for d in dn if d.lower() not in ("node_modules", "locales", "assets", "__pycache__", ".git")]
            for f in fn:
                for r, kind in rx:
                    if r.match(f):
                        cands.append((os.path.join(dp, f), kind))
                        break
            if len(cands) > 400:
                break
    except Exception as exc:
        rep["skipped"].append(f"walk:{type(exc).__name__}")
    asar = os.path.join(base, "resources", "app.asar")
    asar_texts: List[Tuple[str, str]] = []
    if os.path.isfile(asar):
        t = _read_asar_member(asar, "package.json")
        if t:
            asar_texts.append((asar + "!package.json", t))
    seen_cmds: set = set()
    n_files = 0
    for path, kind in sorted(cands, key=lambda c: (c[1] == "manifest_contributes", len(c[0])))[:max_files * 4]:
        if n_files >= max_files or time.time() - t0 > budget_s * 2:
            break
        try:
            if os.path.getsize(path) > 1_500_000:
                continue
            text = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        found: List[Dict[str, Any]] = []
        if kind == "manifest_contributes":
            try:
                found = parse_manifest_contributes(json.loads(text))
            except Exception:
                found = []
        elif kind in ("keymap_json", "keymap_any"):
            found = bm.harvest_keymap_text(text)
        elif kind == "settings":
            tog = bm.harvest_settings_schema(text)
            if tog:
                rep["settings_toggles"] += len(tog)
                rep["sources"].append({"path": path, "kind": kind, "found": len(tog)})
                n_files += 1
            continue
        if found:
            n_files += 1
            rep["sources"].append({"path": path, "kind": kind, "found": len(found)})
            for c in found:
                ident = (c["name"].lower(), c.get("shortcut", ""))
                if ident not in seen_cmds:
                    seen_cmds.add(ident)
                    rep["commands"].append(c)
    for path, text in asar_texts:
        try:
            obj = json.loads(text)
        except Exception:
            continue
        rep["sources"].append({"path": path, "kind": "electron_package_json", "found": 0,
                               "name": obj.get("name", ""), "main": obj.get("main", "")})
        rep["electron_package"] = {k: obj.get(k) for k in ("name", "productName", "version", "main") if obj.get(k)}
        rep["electron_package"]["dependencies"] = sorted((obj.get("dependencies") or {}).keys())[:40]
    rep["elapsed_s"] = round(time.time() - t0, 2)
    return rep


# ---------------------------------------------------------------------------------------------
# 6. capability profile (evidence -> what it can do -> which kind of app)
# ---------------------------------------------------------------------------------------------

# an extension belongs to ONE category: the most specific one listed first ('.html' is web before it is code, '.csv'
# spreadsheet before text), otherwise a program that opens .html would count twice
_CAT_ORDER = ["web", "spreadsheet", "document", "presentation", "model3d", "image", "audio", "video", "archive", "registry",
              "font", "text", "code"]


def ext_categories(exts: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in exts:
        for cat in _CAT_ORDER:
            if e in EXT_CATEGORY.get(cat, ()):
                out[cat] = out.get(cat, 0) + 1
                break
    return out


def infer_profile(*, labels: List[str], exts: List[str], dialog_titles: List[str] = (), regions: List[str] = (),
                  framework_ids: List[str] = (), description: str = "") -> Dict[str, Any]:
    """Capabilities = which generic UI vocabularies the app's own labels exhibit; archetype = rule-weighted evidence.
    Returns {'capabilities': {cap: n_labels}, 'ext_categories': {...}, 'archetypes': [(name, score)], 'archetype', 'margin'}"""
    # an embedded chord / hint is not part of the label: 'Save (Ctrl+S)' is the label 'save'
    hay = [re.sub(r"\s*\([^)]*\)\s*$", "", l.lower()).strip() for l in list(labels) + list(dialog_titles)]
    caps: Dict[str, int] = {}
    for cap, rx in LABEL_CAPS.items():
        r = re.compile(rx, re.I)
        n = sum(1 for h in hay if r.search(h))
        if n:
            caps[cap] = n
    cats = ext_categories(list(exts))
    ev = dict(caps)
    total_cat = sum(cats.values())
    for c, n in cats.items():
        # a category's SHARE of what the app opens, scaled so a program that opens only that kind of file counts as
        # strong evidence (4 'text' types out of 4 = 4.0) while one that opens 40 kinds and 2 are text is weak (0.2)
        ev[f"ext:{c}"] = round(4.0 * (n / total_cat) * min(1.0, total_cat / 3.0), 2) if total_cat else 0     # one type is thin evidence
    scores: List[Tuple[str, float]] = []
    support: Dict[str, int] = {}
    for arch, weights in ARCHETYPE_RULES.items():
        s = 0.0
        n_pos = 0
        for k, w in weights.items():
            if k in ev:
                # saturating: ten 'file' labels are not ten times the evidence of one
                s += w * min(1.0, 0.5 + 0.25 * ev[k]) if w > 0 else w
                # breadth: a second kind of evidence, or ONE vocabulary matched by >= 3 different labels (a calculator's
                # Memory / Scientific / Standard / Clear entry) - never a single stray keyword
                n_pos += (2 if ev[k] >= 3 else 1) if w > 0 else 0
        scores.append((arch, round(s, 2)))
        support[arch] = n_pos
    scores.sort(key=lambda x: -x[1])
    top = scores[0] if scores else ("", 0.0)
    second = scores[1][1] if len(scores) > 1 else 0.0
    # description words are a weak tie-break only (the product's own FileDescription), never the decider
    margin = round(top[1] - second, 2)
    # thin, tied or single-keyword evidence stays honest: a kind is claimed only with >= 2 independent kinds of support
    defined = bool(ARCHETYPE_DEFINING.get(top[0], set()) & set(caps)) if top[0] else False
    arch = top[0] if (top[1] >= 2.5 and margin >= 0.6 and support.get(top[0], 0) >= 2 and defined) else "unclassified"
    profile = {"capabilities": caps, "ext_categories": cats, "archetypes": scores[:4], "archetype": arch, "margin": margin,
               "has_ribbon": "office_ribbon" in framework_ids or "ribbon" in [r.lower() for r in regions],
               "has_menus": any(re.match(r"^(file|edit|view|help)\b", h) for h in hay),
               "file_centric": bool({"open", "save", "save_as", "new"} & set(caps))}
    return profile


# ---------------------------------------------------------------------------------------------
# 7. the whole static read
# ---------------------------------------------------------------------------------------------

def harvest(target: Any, *, with_install_sources: bool = True) -> Dict[str, Any]:
    """Everything knowable about `target` (hwnd | exe path | name) without running it."""
    t0 = time.time()
    exe = exe_for(target)
    d: Dict[str, Any] = {"target": target if not isinstance(target, int) else f"hwnd:{target}", "exe": exe, "ok": False,
                         "commands": [], "dialogs": [], "skipped": []}
    if not exe or not os.path.isfile(exe):
        d["skipped"].append("exe-not-found")
        d["elapsed_s"] = round(time.time() - t0, 3)
        return d
    d["exe_name"] = os.path.basename(exe)
    pkg = package_root(exe)
    d["package_root"] = pkg
    info = pr.pe_info(exe)
    d["pe"] = {k: info.get(k) for k in ("ok", "machine", "subsystem", "clr", "size", "why")}
    d["pe"]["imports_n"] = len(info.get("imports", []))
    res = pr.read_resources(exe)
    d["version_info"] = res.get("version", {})
    d["manifest"] = res.get("manifest", {})
    d["requires_elevation"] = bool(d["manifest"].get("requires_admin")) or d["manifest"].get("execution_level") == "highestAvailable"
    d["resource_summary"] = {"menus": len(res["menus"]), "accelerators": len(res["accelerators"]),
                             "strings": len(res["strings"]), "dialogs": len(res["dialogs"]), "sources": [os.path.basename(s) for s in res["sources"]]}
    d["skipped"] += res.get("skipped", [])
    cmds = pr.commands_from_resources(res)
    kinds = pr.classify_menus(res)
    d["menu_structure"] = {"bars": len(kinds["menu_bars"]), "contexts": len(kinds["context_menus"])}
    d["commands"].extend(cmds)
    for dlg in res["dialogs"]:
        d["dialogs"].append({"title": dlg["title"], "resource": dlg["name"],
                             "controls": [{"kind": c["kind"], "text": c["text"], "id": c["id"]} for c in dlg["controls"]
                                          if c["kind"] not in ("static",) or c["text"]]})
    appx: Dict[str, Any] = {}
    if pkg:
        appx = appx_info(pkg)
        d["appx"] = {k: v for k, v in appx.items() if k != "file_types"}
    ft = file_types_for(exe)
    exts = sorted(set(ft["extensions"]) | set(appx.get("file_types", [])))
    d["file_types"] = exts
    open_cmd = ft["open_command"]
    d["cli_open"] = open_cmd or (f"{appx.get('alias')} {appx.get('verbs', {}).get('edit', '%1')}".strip() if appx.get("alias") else "")
    shared = _is_shared_dir(os.path.dirname(exe)) and not pkg
    d["shared_install_dir"] = shared
    files = [] if shared else _list_files(pkg or os.path.dirname(exe))      # a shared dir (System32) says nothing about THIS program
    d["frameworks"] = fingerprint_framework(exe, info, files, appx)
    if with_install_sources and not shared:
        src = harvest_install_sources(exe)
        d["install_sources"] = {k: v for k, v in src.items() if k != "commands"}
        d["commands"].extend(src["commands"])
    labels = [c.get("menu_path") or c["name"] for c in d["commands"]]
    d["profile"] = infer_profile(labels=labels, exts=exts, dialog_titles=[x["title"] for x in d["dialogs"] if x["title"]],
                                 framework_ids=[f["id"] for f in d["frameworks"]], description=d["version_info"].get("FileDescription", ""))
    d["strategy"] = (d["frameworks"][0]["strategy"] if d["frameworks"] else {})
    d["ok"] = True
    d["elapsed_s"] = round(time.time() - t0, 3)
    return d


def ingest(model, app_name: str, d: Dict[str, Any], *, version_hash: str = "") -> Dict[str, Any]:
    """Write a static dossier into the behavior DB: facts (sourced), dialog schemas, catalog-trust commands."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import knowledge_store as ks
    key = bm._app_key(app_name)
    rep = {"app_key": key, "commands": 0, "dialogs": 0, "facts": 0}
    if not d.get("ok"):
        return rep
    src = "static"
    for fact in ("exe", "exe_name", "package_root", "pe", "version_info", "manifest", "requires_elevation", "resource_summary",
                 "menu_structure", "appx", "file_types", "cli_open", "frameworks", "strategy", "install_sources", "profile"):
        if fact in d and d[fact] not in (None, "", {}, []):
            ks.put_fact(model, key, fact, d[fact], source=src, confidence=0.9)
            rep["facts"] += 1
    for c in d.get("commands", []):
        cc = {k: v for k, v in c.items() if k not in ("origin_fmt",)}
        cc.setdefault("risk", None)
        if cc.get("risk") is None:
            cc.pop("risk")
        origin = f"static:{c.get('origin_fmt', '')}"
        ev = []
        if c.get("help"):
            ev.append("help=" + c["help"][:80])
        if c.get("access_chain"):
            ev.append("alt=" + c["access_chain"])
        if c.get("menu_kind") == "context":
            ev.append("context-menu")
        model.upsert_command(key, cc, source="catalog", origin=origin, evidence="; ".join(ev))
        rep["commands"] += 1
    for dlg in d.get("dialogs", []):
        if dlg["controls"]:
            ks.put_dialog(model, key, dlg["title"], dlg["controls"], source="static:dialog-template", via=f"resource {dlg['resource']}")
            rep["dialogs"] += 1
    return rep
