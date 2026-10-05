"""
pe_resources.py -- read what a Windows program SAYS about itself, straight from its file (no launch, no UI).

A classic Win32/MFC program ships its whole command structure as data inside the .exe (or its language
file .exe.mui): the menu tree with every command ID, the accelerator (shortcut) table keyed by those same
IDs, the string table (MFC status-bar prompts = a one-line description of each command), and every dialog
template (title, each control's class/text/ID). Reading them costs milliseconds and needs no accessibility
tree, no focus, no window - and it contains items a live crawl can never see (context menus, dialogs that
only exist after a click). Nothing here is per-app: it is the PE/resource file format, the same for all.

    info = pe_info(path)                 # machine, subsystem (GUI/console), .NET?, imported DLLs, sections
    res  = read_resources(path)          # {'menus': [...], 'accelerators': [...], 'strings': {id: str},
                                         #  'dialogs': [...], 'version': {...}, 'manifest': {...}}
    cmds = commands_from_resources(res)  # menu leaves joined with accelerator + help text, by command ID

Every function degrades: unreadable / not a PE / no resources => empty result + a `skipped` note, never an
exception. Pure ctypes + struct (no third-party PE library).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

_IS_WINDOWS = os.name == "nt"

RT_MENU, RT_DIALOG, RT_STRING, RT_ACCELERATOR, RT_VERSION, RT_MANIFEST = 4, 5, 6, 9, 16, 24
LOAD_LIBRARY_AS_DATAFILE = 0x00000002
LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020

# ---------------------------------------------------------------------------------------------
# 1. PE headers (struct only): machine, subsystem, CLR header, imports, delay imports, sections
# ---------------------------------------------------------------------------------------------

_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64", 0x1C4: "arm"}
_SUBSYSTEMS = {1: "native", 2: "gui", 3: "console", 5: "os2", 7: "posix", 9: "wince", 10: "efi"}


def _rva_to_off(sections: List[Tuple[int, int, int, int]], rva: int) -> Optional[int]:
    for va, vsize, raw_ptr, raw_size in sections:
        if va <= rva < va + max(vsize, raw_size):
            return raw_ptr + (rva - va)
    return None


def _cstr(buf: bytes, off: int, limit: int = 260) -> str:
    end = buf.find(b"\x00", off, off + limit)
    return buf[off:end if end >= 0 else off + limit].decode("ascii", "replace")


def pe_info(path: str) -> Dict[str, Any]:
    """Headers + import table of a PE file, read by SEEKING (a 200 MB Electron exe costs the same as a 50 KB one: only the
    header, the section table and the import descriptors are touched). Never raises: {'ok': False, 'why': ...} for
    anything that is not a readable PE."""
    out: Dict[str, Any] = {"ok": False, "path": path}
    try:
        fh = open(path, "rb")
    except Exception as exc:
        out["why"] = f"unreadable: {type(exc).__name__}"
        return out
    with fh:
        try:
            fh.seek(0, os.SEEK_END)
            out["size"] = fh.tell()
            fh.seek(0)
            head = fh.read(4096)
            if head[:2] != b"MZ":
                out["why"] = "not an MZ/PE file"
                return out
            e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
            if e_lfanew > 1 << 20:
                out["why"] = "implausible PE header offset"
                return out
            if e_lfanew + 4096 > len(head):
                fh.seek(0)
                head = fh.read(e_lfanew + 4096)
            if head[e_lfanew:e_lfanew + 4] != b"PE\0\0":
                out["why"] = "no PE signature"
                return out
            machine, nsec, _ts, _sym, _nsym, opt_size, chars = struct.unpack_from("<HHIIIHH", head, e_lfanew + 4)
            opt = e_lfanew + 24
            magic = struct.unpack_from("<H", head, opt)[0]
            pe32plus = magic == 0x20B
            subsystem = struct.unpack_from("<H", head, opt + 68)[0]
            dd_off = opt + (112 if pe32plus else 96)
            nrva = struct.unpack_from("<I", head, dd_off - 4)[0]
            dirs = [struct.unpack_from("<II", head, dd_off + 8 * i) for i in range(min(nrva, 16))]
            sec_off = opt + opt_size
            sections = []
            for i in range(nsec):
                _n, vsize, va, rsize, rptr = struct.unpack_from("<8sIIII", head, sec_off + 40 * i)
                sections.append((va, vsize, rptr, rsize))
            out.update(machine=_MACHINES.get(machine, hex(machine)), subsystem=_SUBSYSTEMS.get(subsystem, str(subsystem)),
                       dll=bool(chars & 0x2000), pe32plus=pe32plus, sections=nsec)
            out["clr"] = len(dirs) > 14 and dirs[14][0] != 0           # a .NET (managed) assembly
            out["has_resources"] = len(dirs) > 2 and dirs[2][0] != 0

            def read_rva(rva: int, n: int) -> bytes:
                off = _rva_to_off(sections, rva)
                if off is None:
                    return b""
                fh.seek(off)
                return fh.read(n)

            imports: List[str] = []
            for di, step in ((1, 20), (13, 32)):                       # import table, delay-import table
                if len(dirs) <= di or dirs[di][0] == 0:
                    continue
                table = read_rva(dirs[di][0], min(max(dirs[di][1], step * 2), 64 * 1024))
                for off in range(0, len(table) - step + 1, step):
                    if di == 1:
                        name_rva = struct.unpack_from("<I", table, off + 12)[0]
                        if name_rva == 0:
                            break
                    else:
                        name_rva = struct.unpack_from("<I", table, off + 4)[0]
                        if name_rva == 0 and struct.unpack_from("<I", table, off)[0] == 0:
                            break
                    raw = read_rva(name_rva, 128)
                    if raw:
                        imports.append(_cstr(raw, 0, 128).lower())
            out["imports"] = sorted(set(i for i in imports if i))
            out["ok"] = True
        except Exception as exc:
            out["why"] = f"parse error: {type(exc).__name__}: {exc}"
    return out


# ---------------------------------------------------------------------------------------------
# 2. Resource loading (Win32 resource API on a DATAFILE handle: nothing is executed)
# ---------------------------------------------------------------------------------------------

def _mui_candidates(path: str) -> List[str]:
    """Language-neutral programs keep their resources in <dir>\\<lang>\\<name>.mui. Preferred languages first."""
    d, n = os.path.split(path)
    langs: List[str] = []
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.LCIDToLocaleName(lid, buf, 85, 0):
            langs.append(buf.value)
    except Exception:
        pass
    langs += ["en-US", "en-GB"]
    out, seen = [], set()
    for lg in langs:
        p = os.path.join(d, lg, n + ".mui")
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            out.append(p)
    return out


class _Module:
    """A resource-only module handle: LoadLibraryEx(AS_DATAFILE). Closed with .close()."""

    def __init__(self, path: str):
        k32 = ctypes.windll.kernel32
        k32.LoadLibraryExW.restype = ctypes.c_void_p
        k32.LoadLibraryExW.argtypes = [wt.LPCWSTR, ctypes.c_void_p, wt.DWORD]
        self.h = k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE)
        if not self.h:
            self.h = k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_DATAFILE)
        self.path = path

    def close(self) -> None:
        if self.h:
            try:
                k32 = ctypes.windll.kernel32
                k32.FreeLibrary.argtypes = [ctypes.c_void_p]
                k32.FreeLibrary(self.h)
            except Exception:
                pass
            self.h = None

    def names(self, rtype: int) -> List[Any]:
        """Names (int ids or str) of every resource of this type."""
        out: List[Any] = []
        if not self.h:
            return out
        k32 = ctypes.windll.kernel32
        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

        def cb(_h, _t, name, _p):
            try:
                v = name or 0
                out.append(int(v) if v < 0x10000 else ctypes.wstring_at(v))
            except Exception:
                pass
            return True
        k32.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, PROC, ctypes.c_void_p]
        k32.EnumResourceNamesW(self.h, ctypes.c_void_p(rtype), PROC(cb), None)
        return out

    def data(self, rtype: int, name: Any) -> bytes:
        k32 = ctypes.windll.kernel32
        k32.FindResourceW.restype = ctypes.c_void_p
        k32.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        k32.LoadResource.restype = ctypes.c_void_p
        k32.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k32.LockResource.restype = ctypes.c_void_p
        k32.LockResource.argtypes = [ctypes.c_void_p]
        k32.SizeofResource.restype = wt.DWORD
        k32.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nm = ctypes.c_void_p(name) if isinstance(name, int) else ctypes.cast(ctypes.c_wchar_p(name), ctypes.c_void_p)
        hres = k32.FindResourceW(self.h, nm, ctypes.c_void_p(rtype))
        if not hres:
            return b""
        size = k32.SizeofResource(self.h, hres)
        hg = k32.LoadResource(self.h, hres)
        ptr = k32.LockResource(hg) if hg else None
        return ctypes.string_at(ptr, size) if ptr and size else b""


# ---------------------------------------------------------------------------------------------
# 3. Resource parsers
# ---------------------------------------------------------------------------------------------

MF_GRAYED, MF_CHECKED, MF_POPUP, MF_END = 0x1, 0x8, 0x10, 0x80
MFT_SEPARATOR = 0x800


def _wstr(b: bytes, off: int) -> Tuple[str, int]:
    """NUL-terminated UTF-16LE string at `off` -> (text, offset after the terminator)."""
    end = off
    while end + 1 < len(b) and (b[end] or b[end + 1]):
        end += 2
    return b[off:end].decode("utf-16-le", "replace"), end + 2


def parse_menu(b: bytes) -> List[Dict[str, Any]]:
    """RT_MENU -> nested [{'text','id','flags','children':[...]}] (classic MENUITEMTEMPLATE and MENUEX)."""
    if len(b) < 4:
        return []
    ver, hdr = struct.unpack_from("<HH", b, 0)
    pos = 4 + hdr
    items: List[Dict[str, Any]] = []

    def classic(pos: int) -> Tuple[List[Dict[str, Any]], int]:
        out: List[Dict[str, Any]] = []
        while pos + 2 <= len(b):
            opt = struct.unpack_from("<H", b, pos)[0]
            pos += 2
            if opt & MF_POPUP:
                text, pos = _wstr(b, pos)
                kids, pos = classic(pos)
                out.append({"text": text, "id": 0, "flags": opt & ~MF_END, "children": kids})
            else:
                mid = struct.unpack_from("<H", b, pos)[0]
                pos += 2
                text, pos = _wstr(b, pos)
                out.append({"text": text, "id": mid, "flags": opt & ~MF_END, "children": []})
            if opt & MF_END:
                break
        return out, pos

    def ex(pos: int) -> Tuple[List[Dict[str, Any]], int]:
        out: List[Dict[str, Any]] = []
        while pos + 14 <= len(b):
            mtype, mstate, mid, res = struct.unpack_from("<IIIH", b, pos)
            pos += 14
            text, pos = _wstr(b, pos)
            pos = (pos + 3) & ~3
            kids: List[Dict[str, Any]] = []
            if res & 1:                                         # popup: help id then the sub-items
                pos += 4
                kids, pos = ex(pos)
            flags = (MF_GRAYED if mstate & 3 else 0) | (MF_CHECKED if mstate & 8 else 0) | \
                    (MFT_SEPARATOR if mtype & MFT_SEPARATOR else 0)
            out.append({"text": text, "id": mid, "flags": flags, "children": kids})
            if res & 0x80:
                break
        return out, pos

    try:
        items, _ = ex(pos) if ver == 1 else classic(pos)
    except Exception:
        return []
    return items


def parse_accelerators(b: bytes) -> List[Dict[str, Any]]:
    """RT_ACCELERATOR -> [{'id': cmd, 'chord': 'ctrl+shift+s', ...}]"""
    out = []
    for i in range(0, len(b) - 7, 8):
        flags, key, cmd = struct.unpack_from("<HHH", b, i)
        mods = [m for bit, m in ((0x08, "ctrl"), (0x10, "alt"), (0x04, "shift")) if flags & bit]
        out.append({"id": cmd, "chord": "+".join(mods + [_key_name(key, bool(flags & 1))]), "virt": bool(flags & 1)})
        if flags & 0x80:
            break
    return out


_VK_NAMES = {0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x1B: "esc", 0x20: "space", 0x21: "pageup", 0x22: "pagedown",
             0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x2D: "insert",
             0x2E: "delete", 0xBB: "=", 0xBD: "-", 0xBC: ",", 0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDD: "]",
             0xDC: "\\", 0xBA: ";", 0xDE: "'", 0x6B: "numpad+", 0x6D: "numpad-", 0x6A: "numpad*", 0x6F: "numpad/",
             0x90: "numlock", 0x91: "scroll", 0x13: "pause", 0x2C: "printscreen"}


def _key_name(key: int, virt: bool) -> str:
    if virt:
        if 0x70 <= key <= 0x87:
            return f"f{key - 0x6F}"
        if 0x30 <= key <= 0x39 or 0x41 <= key <= 0x5A:
            return chr(key).lower()
        if 0x60 <= key <= 0x69:
            return f"numpad{key - 0x60}"
        return _VK_NAMES.get(key, f"vk{key:#x}")
    return chr(key).lower() if 32 < key < 127 else f"ascii{key}"


def parse_string_block(block_id: int, b: bytes) -> Dict[int, str]:
    """RT_STRING block (16 strings) -> {string_id: text}"""
    out: Dict[int, str] = {}
    pos = 0
    for i in range(16):
        if pos + 2 > len(b):
            break
        ln = struct.unpack_from("<H", b, pos)[0]
        pos += 2
        if ln:
            out[(block_id - 1) * 16 + i] = b[pos:pos + ln * 2].decode("utf-16-le", "replace")
        pos += ln * 2
    return out


_DLG_CLASSES = {0x80: "button", 0x81: "edit", 0x82: "static", 0x83: "listbox", 0x84: "scrollbar", 0x85: "combobox"}
_BS_KIND = {0: "pushbutton", 1: "defpushbutton", 2: "checkbox", 3: "autocheckbox", 4: "radiobutton", 5: "3state",
            6: "auto3state", 7: "groupbox", 9: "autoradiobutton"}


def _sz_or_ord(b: bytes, pos: int) -> Tuple[Any, int]:
    if pos + 2 > len(b):
        return "", pos
    first = struct.unpack_from("<H", b, pos)[0]
    if first == 0:
        return "", pos + 2
    if first == 0xFFFF:
        return struct.unpack_from("<H", b, pos + 2)[0], pos + 4
    return _wstr(b, pos)


def parse_dialog(b: bytes) -> Optional[Dict[str, Any]]:
    """RT_DIALOG (DLGTEMPLATE and DLGTEMPLATEEX) -> {'title','controls':[{'class','text','id','kind'}]}"""
    try:
        ex = len(b) >= 4 and struct.unpack_from("<HH", b, 0) == (1, 0xFFFF)
        if ex:
            _help, _exs, style, n = struct.unpack_from("<IIIH", b, 4)
            pos = 18 + 8
            menu, pos = _sz_or_ord(b, pos)
            cls, pos = _sz_or_ord(b, pos)
            title, pos = _sz_or_ord(b, pos)
            if style & 0x40:                                    # DS_SETFONT: pointsize, weight, italic, charset, face
                pos += 6
                _face, pos = _wstr(b, pos)
        else:
            style, _exs, n = struct.unpack_from("<IIH", b, 0)
            pos = 18
            menu, pos = _sz_or_ord(b, pos)
            cls, pos = _sz_or_ord(b, pos)
            title, pos = _sz_or_ord(b, pos)
            if style & 0x40:
                pos += 2
                _face, pos = _wstr(b, pos)
        controls: List[Dict[str, Any]] = []
        for _ in range(n):
            pos = (pos + 3) & ~3
            if ex:
                _h, _ex, cstyle, x, y, cx, cy, cid = struct.unpack_from("<IIIhhhhI", b, pos)
                pos += 24
            else:
                cstyle, _ex, x, y, cx, cy, cid = struct.unpack_from("<IIhhhhH", b, pos)
                pos += 18
            ccls, pos = _sz_or_ord(b, pos)
            ctext, pos = _sz_or_ord(b, pos)
            extra = struct.unpack_from("<H", b, pos)[0]
            pos += 2 + extra
            cname = _DLG_CLASSES.get(ccls, ccls) if isinstance(ccls, int) else str(ccls).lower()
            kind = cname
            if cname == "button":
                kind = _BS_KIND.get(cstyle & 0xF, "button")
            controls.append({"class": cname, "kind": kind, "text": ctext if isinstance(ctext, str) else "",
                             "id": int(cid) & 0xFFFF, "rect": (x, y, cx, cy)})
        return {"title": title if isinstance(title, str) else "", "controls": controls}
    except Exception:
        return None


def _fix_mojibake(t: str) -> str:
    """Some files store UTF-8 bytes in their version strings ('MicrosoftÂ®'): undo that round trip."""
    if "Â" in t or "Ã" in t:
        try:
            return t.encode("latin-1").decode("utf-8")
        except Exception:
            return t
    return t


def read_version(path: str) -> Dict[str, str]:
    """StringFileInfo of the file (ProductName, FileDescription, CompanyName, OriginalFilename, ...)."""
    out: Dict[str, str] = {}
    try:
        ver = ctypes.windll.version
        ver.GetFileVersionInfoSizeW.restype = wt.DWORD
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return out
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return out
        lp = ctypes.c_void_p()
        ln = wt.UINT()
        langs: List[str] = []
        if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(lp), ctypes.byref(ln)) and ln.value >= 4:
            raw = ctypes.string_at(lp.value, ln.value)
            for i in range(0, len(raw) - 3, 4):
                lang, cp = struct.unpack_from("<HH", raw, i)
                langs.append(f"{lang:04x}{cp:04x}")
        langs += ["040904b0", "040904e4", "000004b0"]
        for lc in langs:
            for key in ("ProductName", "FileDescription", "CompanyName", "OriginalFilename", "InternalName",
                        "ProductVersion", "FileVersion", "LegalCopyright"):
                if key in out:
                    continue
                if ver.VerQueryValueW(buf, f"\\StringFileInfo\\{lc}\\{key}", ctypes.byref(lp), ctypes.byref(ln)) and ln.value:
                    out[key] = _fix_mojibake(ctypes.wstring_at(lp.value, ln.value).rstrip("\x00").strip())
            if out.get("ProductName") or out.get("FileDescription"):
                break
    except Exception:
        pass
    return out


def read_manifest(raw: bytes) -> Dict[str, Any]:
    """Application manifest facts that change how the app can be driven (elevation = HITL, DPI, common controls)."""
    text = raw.decode("utf-8", "replace") if raw else ""
    out: Dict[str, Any] = {}
    m = re.search(r'requestedExecutionLevel[^>]*level\s*=\s*"(\w+)"', text, re.I)
    out["execution_level"] = m.group(1) if m else ""
    out["requires_admin"] = out["execution_level"].lower() == "requireadministrator"
    out["dpi_aware"] = bool(re.search(r"dpiaware|permonitor", text, re.I))
    out["common_controls_v6"] = "microsoft.windows.common-controls" in text.lower()
    out["ui_access"] = bool(re.search(r'uiAccess\s*=\s*"true"', text, re.I))
    return out


# ---------------------------------------------------------------------------------------------
# 4. Read everything a file ships
# ---------------------------------------------------------------------------------------------

def read_resources(path: str, *, max_dialogs: int = 400) -> Dict[str, Any]:
    """Menus / accelerators / strings / dialogs / version / manifest of `path` merged with its .mui files.
    Returns {'ok', 'sources': [paths read], 'menus': [{'name','items'}], 'accelerators': [..], 'strings': {id: str},
    'dialogs': [{'name','title','controls'}], 'version': {...}, 'manifest': {...}, 'skipped': [...]}"""
    res: Dict[str, Any] = {"ok": False, "sources": [], "menus": [], "accelerators": [], "strings": {}, "dialogs": [],
                           "version": {}, "manifest": {}, "skipped": []}
    if not _IS_WINDOWS or not path or not os.path.isfile(path):
        res["skipped"].append("not-a-file")
        return res
    res["version"] = read_version(path)
    for src in [path] + _mui_candidates(path):
        mod = _Module(src)
        if not mod.h:
            res["skipped"].append(f"load-failed:{os.path.basename(src)}")
            continue
        try:
            before = (len(res["menus"]), len(res["accelerators"]), len(res["strings"]), len(res["dialogs"]))
            for name in mod.names(RT_MENU):
                items = parse_menu(mod.data(RT_MENU, name))
                if items:
                    res["menus"].append({"name": name, "items": items, "source": os.path.basename(src)})
            for name in mod.names(RT_ACCELERATOR):
                for a in parse_accelerators(mod.data(RT_ACCELERATOR, name)):
                    a["table"] = name
                    res["accelerators"].append(a)
            for name in mod.names(RT_STRING):
                if isinstance(name, int):
                    res["strings"].update(parse_string_block(name, mod.data(RT_STRING, name)))
            for name in mod.names(RT_DIALOG)[:max_dialogs]:
                d = parse_dialog(mod.data(RT_DIALOG, name))
                if d:
                    d["name"] = name
                    res["dialogs"].append(d)
            if not res["manifest"]:
                for name in mod.names(RT_MANIFEST)[:1]:
                    res["manifest"] = read_manifest(mod.data(RT_MANIFEST, name))
            after = (len(res["menus"]), len(res["accelerators"]), len(res["strings"]), len(res["dialogs"]))
            if after != before:
                res["sources"].append(src)
        except Exception as exc:
            res["skipped"].append(f"parse:{os.path.basename(src)}:{type(exc).__name__}")
        finally:
            mod.close()
    res["menus"] = _dedupe_best(res["menus"], lambda m: sum(1 for _ in _walk_text(m["items"])))
    res["dialogs"] = _dedupe_best(res["dialogs"], lambda d: len(d["title"]) + sum(len(c["text"]) for c in d["controls"]))
    uniq, seen_acc = [], set()
    for a in res["accelerators"]:
        k = (a["id"], a["chord"])
        if k not in seen_acc:
            seen_acc.add(k)
            uniq.append(a)
    res["accelerators"] = uniq
    res["ok"] = bool(res["menus"] or res["accelerators"] or res["dialogs"] or res["strings"])
    return res


def _walk_text(items: List[Dict[str, Any]]):
    for it in items:
        if it["text"]:
            yield it["text"]
        yield from _walk_text(it["children"])


def _dedupe_best(rows: List[Dict[str, Any]], richness) -> List[Dict[str, Any]]:
    """The .exe holds a language-neutral skeleton, the .mui the same resource WITH text: keep the richer copy per name."""
    best: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        cur = best.get(r["name"])
        if cur is None or richness(r) > richness(cur):
            best[r["name"]] = r
    return list(best.values())


# ---------------------------------------------------------------------------------------------
# 5. Join: command IDs link the menu tree, the accelerator table and the string table
# ---------------------------------------------------------------------------------------------

def clean_label(text: str) -> Tuple[str, str, str]:
    """('&Save As...\\tCtrl+Shift+S') -> ('Save As...', 'ctrl+shift+s', 's' (the &-mnemonic))."""
    label, _, accel = (text or "").partition("\t")
    mnem = re.search(r"&(.)", label)
    label = label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()
    chord = re.sub(r"\s*\+\s*", "+", accel.strip().lower().replace("control", "ctrl")).strip("+ ")
    return label, chord, (mnem.group(1).lower() if mnem else "")


def commands_from_resources(res: Dict[str, Any], *, menu_names: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Menu leaves as command dicts: {name, menu_path, menu_id, shortcut, access_key, help, verb:'wm_command',
    checkable, disabled_at_rest, origin_fmt}. A command ID in the accelerator table whose menu item carries no
    shortcut text still gets its chord; the string table's prompt (MFC: 'long help\\nshort name') becomes `help`."""
    accel_by_id: Dict[int, List[str]] = {}
    for a in res.get("accelerators", []):
        accel_by_id.setdefault(a["id"], []).append(a["chord"])
    strings = res.get("strings", {})
    strings = strings if _strings_describe_commands(res) else {}
    kinds = classify_menus(res)
    out: List[Dict[str, Any]] = []
    seen: set = set()

    def walk(items: List[Dict[str, Any]], path: List[str], menu: Any, mnems: List[str]) -> None:
        for it in items:
            if it["flags"] & MFT_SEPARATOR and not it["text"]:
                continue
            label, chord, mnem = clean_label(it["text"])
            if not label:
                continue
            if it["children"]:
                walk(it["children"], path + [label], menu, mnems + [mnem])
                continue
            cid = it["id"]
            chords = accel_by_id.get(cid, [])
            shortcut = chord or (chords[0] if chords else "")
            prompt = strings.get(cid, "")
            help_text, _, short = prompt.partition("\n")
            mp = " > ".join(path + [label])
            ident = (menu, mp, cid)
            if ident in seen:
                continue
            seen.add(ident)
            out.append({"name": label, "goal": label, "menu_path": mp, "menu_id": cid or None, "shortcut": shortcut,
                        "alt_shortcuts": [c for c in chords if c != shortcut], "access_key": mnem,
                        # the &-mnemonics along the path are a keyboard-only route through a classic menu bar:
                        # Alt, F, A  ==  File > Save As (all letters known only if every level declared one)
                        "access_chain": "".join(mnems + [mnem]) if all(mnems + [mnem]) else "",
                        "help": help_text.strip(), "verb": "wm_command" if cid else "menu",
                        "checkable": bool(it["flags"] & MF_CHECKED), "disabled_at_rest": bool(it["flags"] & MF_GRAYED),
                        "menu_kind": "context" if menu in kinds["context_menus"] else "bar",
                        "menu_resource": str(menu), "origin_fmt": "pe-menu-resource"})

    for m in res.get("menus", []):
        if menu_names is None or m["name"] in menu_names:
            walk(m["items"], [], m["name"], [])
    return out


def _stem_set(text: str) -> set:
    return {w[:5] for w in re.findall(r"[a-z]{3,}", (text or "").lower())}


def _strings_describe_commands(res: Dict[str, Any]) -> bool:
    """A string whose ID equals a command ID is that command's prompt ONLY in MFC-style programs. In other programs the
    two ID spaces just overlap (Notepad: string 1 is 'Cannot open the file', command 1 is File > New), and joining them
    attaches false help text. Evidence test: across every menu leaf that has a string, how often does the string share a
    word stem with the label (or carry MFC's 'prompt NEWLINE short name' form)? Join only above 40%."""
    strings = res.get("strings", {})
    hit = tot = 0

    def leaves(items):
        for it in items:
            if it["children"]:
                yield from leaves(it["children"])
            elif it["id"] and it["text"]:
                yield it
    for m in res.get("menus", []):
        for it in leaves(m["items"]):
            s = strings.get(it["id"])
            if not s:
                continue
            tot += 1
            label = clean_label(it["text"])[0]
            if chr(10) in s and label.lower() == s.split(chr(10))[-1].strip().lower():
                hit += 1
            elif _stem_set(label) & _stem_set(s):
                hit += 1
    return tot >= 4 and hit / tot >= 0.4


def classify_menus(res: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Which RT_MENU resource is the main menu bar and which are context (right-click) menus? A menu bar's
    top level items are all popups (File/Edit/View...); a context menu is a single popup with commands."""
    bars, contexts = [], []
    for m in res.get("menus", []):
        items = [i for i in m["items"] if not (i["flags"] & MFT_SEPARATOR and not i["text"])]
        if not items:
            continue
        if len(items) >= 2 and all(i["children"] for i in items):
            bars.append(m["name"])
        else:
            contexts.append(m["name"])
    return {"menu_bars": bars, "context_menus": contexts}
