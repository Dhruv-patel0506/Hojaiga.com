"""
rea_sweep -- reverse engineer EVERY application found on this computer with REA (static: nothing is started, nothing is driven), and file what it reveals into the RAG.

    python -m core_organs.harvest.rea_sweep run [--workers 3] [--only "Name,Name"] [--limit N] [--phase fast|native]
    python -m core_organs.harvest.rea_sweep report

What is read, by kind of program (found from the files, not from a list of names):
  Electron / JavaScript   REA analyze-javascript-application (modules, IPC channels, windows, preload, endpoints) + the app's own archive mined for menu labels with their accelerators, commands and
                          key bindings (package.json), the English locale files (= the app's whole interface vocabulary), IPC channel names, deep-link protocols, hosts it talks to
  .NET (managed)          REA inspect-managed-members on the executable and its largest managed libraries: types, methods, user-visible string literals, shortcuts, P/Invoke boundaries
  Go / Rust               REA inspect-go-binary / inspect-rust-binary: build, modules, dependencies
  Native (Qt / MFC / Delphi / Win32)   already read by the static pass (imports, menu + accelerator resources); phase 'native' adds Ghidra's string table (2-4 min per program)
Never analysed: security products, anti-cheat and exam-proctoring software. Everything is static; a finished app is not redone.

Structured findings (menu label + accelerator, declared commands, key bindings) become commands and hotkey LEADS (source rea_static, trust catalog, never verified). Free-text findings
(UI strings, IPC channels, hosts, libraries) go into a document the RAG can retrieve.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import contextlib
import json
import os
import re
import struct
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_organs import rea_bridge as RB
from core_organs.harvest import machine_sweep as MS

NEVER = re.compile(r"defender|windows security|mcafee|webadvisor|vanguard|anti.?cheat|easyanticheat|battleye|lockdown|respondus|antivirus|security health", re.I)
MAX_JS_BYTES = 60_000_000


# ---- reading an Electron archive (ASAR) or an unpacked app folder --------------------------------------------------------------------------------------------
class Archive:
    """Read-only view of an ASAR file or a folder: list of paths and a way to read one file. No code is executed."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.files: Dict[str, Tuple[int, int]] = {}
        self.is_dir = os.path.isdir(path)
        if self.is_dir:
            for a, _, fs in os.walk(path):
                for f in fs:
                    p = os.path.join(a, f)
                    self.files[os.path.relpath(p, path).replace("\\", "/")] = (0, os.path.getsize(p))
            return
        with open(path, "rb") as f:
            head = f.read(16)
            _, _, _, jl = struct.unpack("<IIII", head)
            hdr = json.loads(f.read(jl).decode("utf-8", "replace"))
            self.base = 8 + struct.unpack("<I", head[4:8])[0]
        def walk(node: Dict[str, Any], prefix: str) -> None:
            for name, ent in (node.get("files") or {}).items():
                p = f"{prefix}/{name}" if prefix else name
                if "files" in ent:
                    walk(ent, p)
                elif "offset" in ent and not ent.get("unpacked"):
                    self.files[p] = (int(ent["offset"]), int(ent["size"]))
        walk(hdr, "")

    def read(self, rel: str, limit: int = 4_000_000) -> bytes:
        off, size = self.files[rel]
        if self.is_dir:
            with open(os.path.join(self.path, rel.replace("/", os.sep)), "rb") as f:
                return f.read(min(size, limit))
        with open(self.path, "rb") as f:
            f.seek(self.base + off)
            return f.read(min(size, limit))


_ACCEL = re.compile(r"""(?:label|title)\s*:\s*['"`]([^'"`\n]{2,48})['"`][^{}]{0,260}?accelerator\s*:\s*['"`]([^'"`\n]{2,40})['"`]""", re.S)
_ACCEL2 = re.compile(r"""accelerator\s*:\s*['"`]([^'"`\n]{2,40})['"`][^{}]{0,260}?(?:label|title)\s*:\s*['"`]([^'"`\n]{2,48})['"`]""", re.S)
_IPC = re.compile(r"""ipc(?:Main|Renderer)\s*\.\s*(?:handle|on|once|invoke|send|handleOnce)\s*\(\s*['"`]([A-Za-z0-9_:.\-/]{3,64})['"`]""")
_PROTO = re.compile(r"""setAsDefaultProtocolClient\s*\(\s*['"`]([a-z][a-z0-9+.\-]{1,30})['"`]""")
_GSHORT = re.compile(r"""globalShortcut\s*\.\s*register\s*\(\s*['"`]([^'"`\n]{2,40})['"`]""")
_URL = re.compile(r"""https?://([A-Za-z0-9.\-]{4,60})(?:[:/][^\s'"`<>)]{0,80})?""")
_REGCMD = re.compile(r"""registerCommand\s*\(\s*['"`]([A-Za-z0-9_.\-]{3,80})['"`]""")
_LOCALE = re.compile(r"(^|/)(locales?|i18n|lang|languages|translations|strings|messages)/([^/]*)?(en([-_][A-Za-z]{2})?)\.(json|js)$|(^|/)en([-_][A-Za-z]{2})?\.json$|(^|/)messages\.json$", re.I)
_SKIP_DIR = re.compile(r"(^|/)(node_modules|\.git|test|tests|__tests__|docs?|examples?)/", re.I)
_CHORD = re.compile(r"^(?:(?:CmdOrCtrl|CommandOrControl|Ctrl|Control|Alt|Option|Shift|Super|Meta)\+)*(?:[A-Za-z0-9]|F\d{1,2}|Enter|Esc|Escape|Tab|Space|Home|End|Delete|Backspace|Insert|PageUp|PageDown|Up|Down|Left|Right|Plus|[\[\],./;'\\\-=`])$")


def _flat_strings(obj: Any, out: List[str], depth: int = 0) -> None:
    if depth > 5 or len(out) > 6000:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _flat_strings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:400]:
            _flat_strings(v, out, depth + 1)
    elif isinstance(obj, str) and 2 <= len(obj) <= 70 and re.search(r"[A-Za-z]{2}", obj) and not re.search(r"[{}<>=\\]|https?://|^\W|\.(js|json|png|svg)$|\$\{", obj):
        out.append(obj)


def mine_archive(ar: Archive, budget_s: float = 90.0) -> Dict[str, Any]:
    out: Dict[str, Any] = {"files": len(ar.files), "menu": [], "ipc": [], "protocols": [], "global_shortcuts": [], "hosts": {}, "commands": [], "keybindings": [], "locale_strings": [], "libraries": [], "package": {}}
    js_read = 0
    hosts: collections.Counter = collections.Counter()
    ipc, menu, glob, proto, cmds = set(), {}, set(), set(), set()
    deadline = time.time() + budget_s                                                                  # a big app (VS Code: thousands of modules) must not hold the whole sweep; what was read by then is kept
    out["stopped_by_time"] = False
    for rel in sorted(ar.files):
        if time.time() > deadline:
            out["stopped_by_time"] = True
            break
        low = rel.lower()
        size = ar.files[rel][1]
        try:
            if low == "package.json" or low.endswith("/package.json") and rel.count("/") <= 1:
                pj = json.loads(ar.read(rel, 600_000).decode("utf-8", "replace"))
                if not out["package"]:
                    out["package"] = {k: pj.get(k) for k in ("name", "productName", "version", "description", "main", "author") if pj.get(k)}
                    out["libraries"] = sorted((pj.get("dependencies") or {}).keys())[:60]
                ct = pj.get("contributes") or {}
                for c in ct.get("commands", []) or []:
                    t = c.get("title") if isinstance(c, dict) else None
                    if t:
                        cmds.add((str(c.get("category", "")) + ": " if c.get("category") else "") + str(t))
                for kb in ct.get("keybindings", []) or []:
                    if isinstance(kb, dict) and kb.get("key") and kb.get("command"):
                        out["keybindings"].append({"key": kb["key"], "command": kb["command"]})
                continue
            if _LOCALE.search(rel) and low.endswith(".json") and size < 3_000_000 and len(out["locale_strings"]) < 2500:
                _flat_strings(json.loads(ar.read(rel, 3_000_000).decode("utf-8", "replace")), out["locale_strings"])
                continue
            if low.endswith((".js", ".mjs", ".cjs")) and not _SKIP_DIR.search(low) and size < 2_500_000 and js_read < MAX_JS_BYTES:      # the label/accelerator patterns can backtrack on huge minified lines
                txt = ar.read(rel, 2_500_000).decode("utf-8", "replace")
                js_read += len(txt)
                for m in _ACCEL.finditer(txt):
                    menu[(m.group(1).strip(), m.group(2).strip())] = rel
                for m in _ACCEL2.finditer(txt):
                    menu[(m.group(2).strip(), m.group(1).strip())] = rel
                ipc.update(_IPC.findall(txt))
                proto.update(_PROTO.findall(txt))
                glob.update(_GSHORT.findall(txt))
                cmds.update(_REGCMD.findall(txt))
                for h in _URL.findall(txt):
                    if not re.search(r"(w3\.org|schemas\.|example\.|localhost|127\.0|github\.com/(?!login)|npmjs|mozilla|chromium|electronjs|nodejs|apache|opensource|ietf|json-schema|xmlsoap|microsoft\.com/(?:fwlink|schemas))", h):
                        hosts[h.lower()] += 1
        except Exception:
            continue
    out["menu"] = [{"label": l, "accelerator": a, "file": f} for (l, a), f in list(menu.items())[:400]]
    out["ipc"] = sorted(ipc)[:600]
    out["protocols"] = sorted(proto)[:20]
    out["global_shortcuts"] = sorted(glob)[:30]
    out["hosts"] = dict(hosts.most_common(40))
    out["commands"] = sorted(cmds)[:800]
    out["locale_strings"] = list(dict.fromkeys(out["locale_strings"]))[:2500]
    out["js_bytes_read"] = js_read
    return out


# ---- finding what a program is made of ------------------------------------------------------------------------------------------------------------------------
def _name_tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if t not in ("the", "app", "apps", "microsoft", "windows", "desktop", "program", "files", "programs", "user", "inc", "for")}


def _is_inside(path: str, folder: str) -> bool:
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder)).rstrip("\\/")
    return len(b) > 3 and (a == b or a.startswith(b + os.sep))


def find_archives(e: Dict[str, Any]) -> List[str]:
    """Archives that belong to THIS application: the folder its program is in, and a parent folder only if it is the app's own install folder or is named after the app. A shared parent
    (Programs, AppData\\Local, the Anaconda folder) holds OTHER applications' archives; measured: Duolingo, Docker Desktop and IDLE each picked up a neighbour's package when this climbed."""
    want = _name_tokens(e.get("name", "")) | _name_tokens(os.path.splitext(os.path.basename(e.get("exe") or ""))[0])
    inst = e.get("install_dir") or ""
    roots = []
    for p in (e.get("exe"), e.get("shortcut_target")):
        if p and os.path.exists(p):
            d = p if os.path.isdir(p) else os.path.dirname(p)
            roots.append(d)
            for up in (os.path.dirname(d), os.path.dirname(os.path.dirname(d))):
                own = (inst and os.path.isdir(inst) and _is_inside(up, inst) and len(os.path.splitdrive(inst.rstrip("\\/"))[1]) > 1) or bool(want & _name_tokens(os.path.basename(up)))
                if own:
                    roots.append(up)
    if inst and os.path.isdir(inst) and len(os.path.splitdrive(inst.rstrip("\\/"))[1]) > 1:
        roots.append(inst)
    seen, out = set(), []
    for r in roots:
        if not r or len(os.path.splitdrive(r.rstrip("\\/"))[1]) <= 1 or not os.path.isdir(r) or r.lower() in seen or r.rstrip("\\").lower() in (r"c:\program files", r"c:\program files (x86)", r"c:\users", r"c:", r"d:"):
            continue
        seen.add(r.lower())
        cands = [os.path.join(r, "resources", "app.asar"), os.path.join(r, "resources", "app"), os.path.join(r, "app.asar")]
        with contextlib.suppress(Exception):
            for sub in os.listdir(r):                                                                  # app-3.4.1 (Squirrel), a hashed folder (VS Code), current ...
                sp = os.path.join(r, sub)
                if os.path.isdir(sp) and sub.lower() not in ("node_modules", "locales", "swiftshader"):
                    cands += [os.path.join(sp, "resources", "app.asar"), os.path.join(sp, "resources", "app")]
        for c in cands:
            if os.path.exists(c) and c.lower() not in seen:
                seen.add(c.lower())
                out.append(c)
    return out[:3]


def is_managed(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            d = f.read(4096)
            pe = struct.unpack_from("<I", d, 0x3C)[0]
            if d[pe:pe + 4] != b"PE\0\0":
                return False
            magic = struct.unpack_from("<H", d, pe + 24)[0]
            dd = pe + 24 + (96 if magic == 0x10B else 112)
            rva, size = struct.unpack_from("<II", d, dd + 14 * 8)
            return rva != 0 and size != 0
    except Exception:
        return False


def managed_files(e: Dict[str, Any], top: int = 4) -> List[str]:
    exe = e.get("exe") or ""
    if not exe or not os.path.isfile(exe):
        return []
    d = os.path.dirname(exe)
    out = [exe] if is_managed(exe) else []
    stem = re.split(r"[._\- ]", os.path.splitext(os.path.basename(exe))[0])[0].lower()                 # the app's own libraries share the first word of its name (Grammarly.*.dll); third-party libraries do not
    lib = re.compile(r"^(system|microsoft\.(win32|csharp|extensions|identitymodel)|netstandard|mscorlib|newtonsoft|api-ms|vcruntime|ucrt|msvc|bouncycastle|fsharp|dapper|google\.protobuf|languageext|dynamicdata|grace|"
                     r"nlog|serilog|castle|autofac|rx|reactiveui|splat|polly|sqlite|sharpzip|icsharp)", re.I)
    with contextlib.suppress(Exception):
        own, other = [], []
        for f in os.listdir(d):
            if not f.lower().endswith(".dll") or lib.match(f):
                continue
            p = os.path.join(d, f)
            (own if stem and f.lower().startswith(stem) else other).append(p)
        pick = sorted(own, key=os.path.getsize, reverse=True)[:8] + sorted(other, key=os.path.getsize, reverse=True)[:3]
        out += [p for p in pick if is_managed(p) and p != exe][:top]
    return out[:top + 1]


_UI_STR = re.compile(r"^&?[A-Z][A-Za-z0-9&' /\-]{2,40}(\.\.\.|…)?$")
_STR_NOISE = re.compile(r"^(System|Microsoft|Windows|Newtonsoft)\.|Exception|Error:|^[A-Z][a-z]+[A-Z][A-Za-z]+$|^[A-Z0-9_]{3,}$|\{\d|%[sd]")


def mine_managed(nr: Dict[str, Any]) -> Dict[str, Any]:
    ns = collections.Counter((t.get("namespace") or "") for t in nr.get("types", []))
    strings = []
    us = nr.get("user_strings") or {}
    for u in (us.get("literals", []) if isinstance(us, dict) else us) or []:
        s = u.get("value") if isinstance(u, dict) else u
        if isinstance(s, str):
            strings.append(s)
    ui = [s for s in dict.fromkeys(strings) if _UI_STR.match(s) and not _STR_NOISE.search(s)]
    chords = [s for s in dict.fromkeys(strings) if re.fullmatch(r"(?:Ctrl|Alt|Shift)(?:\+(?:Ctrl|Alt|Shift))*\+(?:[A-Z0-9]|F\d{1,2}|Del|Ins|Home|End|Enter|Esc|Tab|Space)", s)]
    pinv = [m for m in (nr.get("member_refs") or []) if isinstance(m, dict) and m.get("kind") == "pinvoke"][:10]
    return {"assembly": (nr.get("assembly") or {}).get("name"), "version": (nr.get("assembly") or {}).get("version"), "types": len(nr.get("types", [])), "methods": len(nr.get("methods", [])),
            "namespaces": [n for n, _ in ns.most_common(14) if n], "user_strings_total": len(strings), "ui_strings": ui[:300], "chords": chords[:40], "pinvoke": len(pinv)}


# ---- one application -------------------------------------------------------------------------------------------------------------------------------------------
def analyze(e: Dict[str, Any], phase: str = "fast", js_timeout_s: int = 75) -> Dict[str, Any]:
    t0 = time.time()
    res: Dict[str, Any] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kinds": []}
    arcs = find_archives(e)
    if arcs:
        res["kinds"].append("electron/js")
        arch = []
        for a in arcs[:2]:
            item: Dict[str, Any] = {"path": a}
            try:
                item["mined"] = mine_archive(Archive(a))
            except Exception as ex:
                item["mined_error"] = f"{type(ex).__name__}: {str(ex)[:100]}"
            if not arch:                                                                               # REA's own graph of the first archive, time-boxed: a big bundle is partial anyway and the mining above is what carries the vocabulary
                from core_organs import rea_desktop as RD
                item["rea"] = RD.desktop_app(a, analysis_timeout_ms=js_timeout_s * 1000)
            arch.append(item)
        res["js"] = arch
    man = managed_files(e)
    if man:
        res["kinds"].append(".net")
        parts = []
        for p in man:
            r = RB.run("inspect-managed-members", p, timeout=240)
            if r["ok"]:
                m = mine_managed(RB.nr_of(r))
                m["path"] = p
                parts.append(m)
            else:
                parts.append({"path": p, "error": (r["error"] or "")[:120]})
        res["managed"] = parts
    exe = e.get("exe")
    if exe and os.path.isfile(exe) and os.path.getsize(exe) < 400e6 and not arcs:
        for cmd, tag in (("inspect-go-binary", "go"), ("inspect-rust-binary", "rust")):
            if (e.get("static") or {}).get("toolkit") in (".NET (CLR)",):
                break
            r = RB.run(cmd, exe, timeout=60)
            nr = RB.nr_of(r)
            if r["ok"] and nr and (nr.get("modules") or nr.get("compiler") or nr.get("dependencies") or nr.get("build")):
                res["kinds"].append(tag)
                res[tag] = {k: (v if not isinstance(v, (list, dict)) else (v[:30] if isinstance(v, list) else {kk: v[kk] for kk in list(v)[:20]})) for k, v in nr.items() if k in ("compiler", "go_version", "modules", "build", "dependencies", "main", "settings")}
                break
    if phase == "native" and exe and os.path.isfile(exe) and not res["kinds"] and os.path.getsize(exe) < 40e6:
        from core_organs import rea_native as RN
        g = RN.ghidra_strings(exe, 1800)
        res["kinds"].append("native/ghidra")
        res["ghidra"] = g
    res["seconds"] = round(time.time() - t0, 1)
    return res


def text_of(e: Dict[str, Any], r: Dict[str, Any]) -> str:
    L = [f"# {e['name']}: reverse engineered with REA (static; the program was never started)", ""]
    L.append("Kinds found: " + (", ".join(r["kinds"]) or "none beyond the static pass (see its imports / resources)") + ".")
    for it in r.get("js", []):
        m, rea = it.get("mined") or {}, it.get("rea") or {}
        pk = m.get("package") or {}
        L += ["", f"## Electron / JavaScript application ({os.path.basename(it['path'])})"]
        if pk:
            L.append(f"- package: {pk.get('productName') or pk.get('name')} {pk.get('version', '')} - {pk.get('description', '')}".strip())
        if rea.get("ok"):
            L.append(f"- REA graph: {rea.get('modules')} modules, {rea.get('browser_windows')} browser windows, {rea.get('preload_entrypoints')} preload entry points, {rea.get('ipc_channels')} literal IPC channels"
                     + (" (partial: REA reached its time limit)" if rea.get("partial") else ""))
        if m.get("menu"):
            L.append("- menu items with their shortcuts: " + "; ".join(f"{x['label']} = {x['accelerator']}" for x in m["menu"][:60]))
        if m.get("commands"):
            L.append("- declared commands: " + "; ".join(m["commands"][:80]))
        if m.get("keybindings"):
            L.append("- key bindings: " + "; ".join(f"{k['key']} -> {k['command']}" for k in m["keybindings"][:60]))
        if m.get("global_shortcuts"):
            L.append("- global shortcuts: " + ", ".join(m["global_shortcuts"]))
        if m.get("protocols"):
            L.append("- deep-link protocols: " + ", ".join(m["protocols"]))
        if m.get("ipc"):
            L.append(f"- internal IPC channels ({len(m['ipc'])}): " + ", ".join(m["ipc"][:120]))
        if m.get("hosts"):
            L.append("- hosts it talks to (from its code): " + ", ".join(list(m["hosts"])[:25]))
        if m.get("libraries"):
            L.append("- main libraries: " + ", ".join(m["libraries"][:30]))
        if m.get("locale_strings"):
            L.append(f"- interface wording from its English locale files ({len(m['locale_strings'])} strings): " + " | ".join(m["locale_strings"][:150]))
    for p in r.get("managed", []):
        if p.get("error"):
            continue
        L += ["", f"## .NET assembly {p.get('assembly')} {p.get('version')} ({os.path.basename(p['path'])})",
              f"- {p['types']} types, {p['methods']} methods, {p['user_strings_total']} string literals, {p['pinvoke']} P/Invoke boundaries; main namespaces: {', '.join(p['namespaces'][:10])}"]
        if p.get("chords"):
            L.append("- shortcuts found in its strings: " + ", ".join(p["chords"][:30]))
        if p.get("ui_strings"):
            L.append("- user-visible wording: " + " | ".join(p["ui_strings"][:120]))
    for k in ("go", "rust"):
        if r.get(k):
            L += ["", f"## {k} binary", json.dumps(r[k], default=str)[:1200]]
    g = r.get("ghidra")
    if g and g.get("ok"):
        L += ["", "## strings from the program (Ghidra)", f"- {g.get('strings_seen')} strings; flags {g.get('flags', [])[:20]}; hosts {g.get('urls', [])[:10]}; interface words: " + " | ".join(g.get("ui_words", [])[:100])]
    return "\n".join(L)


def file_into_rag(rag: Any, e: Dict[str, Any], r: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    from core_organs.harvest import bridge as BR, web_learn as WL
    key = e["rag_key"]
    res = {"document_chunks": 0, "commands": 0, "hotkeys": 0}
    rows, cmd_labels = [], []
    for it in r.get("js", []):
        m = it.get("mined") or {}
        for x in m.get("menu", []):
            chord = re.sub(r"CmdOrCtrl|CommandOrControl", "Ctrl", x["accelerator"]).replace("Control", "Ctrl").replace("Option", "Alt")
            if _CHORD.match(chord.replace("Ctrl+", "").replace("Alt+", "").replace("Shift+", "").replace("Super+", "").replace("Meta+", "")):
                rows.append((x["label"], chord, "menu of the app's own code"))
            cmd_labels.append(x["label"])
        for kb in m.get("keybindings", []):
            rows.append((kb["command"], kb["key"], "declared key binding"))
        cmd_labels += [c for c in m.get("commands", []) if len(c) < 80][:300]
    for p in r.get("managed", []):
        for c in p.get("chords", []):
            pass
    prs = []
    for label, chord, src in rows:
        kind, payload = BR.norm_keys(re.sub(r"\s*\+\s*", "+", chord.lower()))
        if payload:
            prs.append({"app_key": key, "kind": kind, "task_pattern": label[:80], "payload": payload, "source": "rea_static", "trust": "catalog", "verified": False,
                        "context": f"declared by the program itself ({src}); not yet pressed live", "params_schema_json": BR.infer_schema(payload)})
    with WL.rag_lock():
        with contextlib.suppress(Exception):
            rep = rag.proc.ingest_document(key, text_of(e, r), f"rea_sweep:{run_id}", kind="web_doc", title=f"{e['name']} (REA reverse engineering)", trust="catalog")
            res["document_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
        with contextlib.suppress(Exception):
            for lab in dict.fromkeys(cmd_labels):
                rag.lex.add_command(key, lab[:80], archetype="native", source="rea_static", trust="catalog")
                res["commands"] += 1
        with contextlib.suppress(Exception):
            fresh = [p for p in prs if not rag.fast.find(key, p["task_pattern"], p["payload"])]
            for p in fresh:
                p["command_id"] = rag.lex.add_command(key, p["task_pattern"], archetype="native", source="rea_static", trust="catalog")
            if fresh:
                rag.fast.upsert(fresh)
            res["hotkeys"] = len(fresh)
    return res


# ---- driver ---------------------------------------------------------------------------------------------------------------------------------------------------------
def run(workers: int = 3, only: str = "", limit: int = 0, phase: str = "fast", redo: bool = False) -> Dict[str, Any]:
    from core_organs import rag as R
    rag = R.get_rag()
    led = MS.load()
    run_id = time.strftime("rea_%Y%m%d_%H%M%S")
    want = {x.strip().lower() for x in only.split(",") if x.strip()}
    todo = []
    for k, e in led["entries"].items():
        if e.get("kind") != "app" or not e.get("rag_key"):
            continue
        if NEVER.search(e["name"]):
            e["rea"] = {"skipped": "security / anti-cheat / proctoring software is not analysed"}
            continue
        if want and e["name"].lower() not in want:
            continue
        done = (e.get("rea") or {}).get("phase_done", [])
        if not redo and phase in done:
            continue
        if not (e.get("exe_exists") or e.get("install_dir") or e.get("shortcut_target")):
            e["rea"] = {"skipped": "no readable program file or folder (packaged app whose files are not accessible)", "phase_done": done}
            continue
        todo.append(e)
    if limit:
        todo = todo[:limit]
    print(f"[rea-sweep] {len(todo)} applications, phase {phase}, {workers} at a time", flush=True)
    t0 = time.time()
    n = 0

    def job(e: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        try:
            return e["key"], analyze(e, phase)
        except Exception as ex:
            return e["key"], {"error": f"{type(ex).__name__}: {str(ex)[:160]}"}
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(job, e): e for e in todo}
        for fu in cf.as_completed(futs):
            e = futs[fu]
            key, r = fu.result()
            if r.get("error"):
                e["rea"] = {**(e.get("rea") or {}), "error": r["error"], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
                print(f"[rea-sweep] {e['name']}: ERROR {r['error']}", flush=True)
            else:
                filed = file_into_rag(rag, e, r, run_id) if r["kinds"] else {}
                slim = {k: v for k, v in r.items() if k not in ("js", "managed", "ghidra")}
                slim["filed"] = filed
                slim["phase_done"] = sorted(set((e.get("rea") or {}).get("phase_done", [])) | {phase})
                slim["summary"] = {"menu": sum(len((i.get("mined") or {}).get("menu", [])) for i in r.get("js", [])), "ipc": sum(len((i.get("mined") or {}).get("ipc", [])) for i in r.get("js", [])),
                                   "locale_strings": sum(len((i.get("mined") or {}).get("locale_strings", [])) for i in r.get("js", [])), "managed_ui_strings": sum(len(p.get("ui_strings", [])) for p in r.get("managed", [])),
                                   "js_modules": sum(((i.get("rea") or {}).get("modules") or 0) for i in r.get("js", []))}
                e["rea"] = slim
                print(f"[rea-sweep] {e['name']}: {slim['kinds']} {slim['summary']} filed={filed} {r['seconds']}s", flush=True)
            n += 1
            if n % 3 == 0:
                MS.save(led)
    MS.save(led)
    return {"done": n, "seconds": round(time.time() - t0)}


def report() -> str:
    led = MS.load()
    ent = [e for e in led["entries"].values() if e.get("rea")]
    kinds = collections.Counter(k for e in ent for k in (e["rea"].get("kinds") or []))
    skipped = [(e["name"], e["rea"]["skipped"]) for e in ent if e["rea"].get("skipped")]
    errs = [(e["name"], e["rea"]["error"]) for e in ent if e["rea"].get("error")]
    L = [f"# REA sweep - {len(ent)} applications touched", f"kinds: {dict(kinds)}", f"skipped: {len(skipped)}  errors: {len(errs)}", ""]
    for e in sorted(ent, key=lambda x: x["name"].lower()):
        r = e["rea"]
        if r.get("kinds"):
            L.append(f"- {e['name']}: {', '.join(r['kinds'])} {r.get('summary', {})} {r.get('seconds', '')}s")
    L += ["", "## skipped"] + [f"- {n}: {w}" for n, w in skipped] + ["", "## errors"] + [f"- {n}: {w}" for n, w in errs]
    txt = "\n".join(L)
    open(os.path.join(MS.OUT, "REA_REPORT.md"), "w", encoding="utf-8").write(txt)
    return txt


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--phase", default="fast", choices=["fast", "native"])
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        print(json.dumps(run(a.workers, a.only, a.limit, a.phase, a.redo)))
    print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
