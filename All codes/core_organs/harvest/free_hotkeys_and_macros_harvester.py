"""
harvest.free_hotkeys_and_macros_harvester -- Sub-RAG 4 material: hotkeys and macros/scripts. $0.

  Layer 1  built-in seeds        the superhuman templates (Blender bpy, AutoCAD .scr, Excel/Word COM, OBS CLI) and the core hotkeys: trust 'seed'
  Layer 2  public shortcut pages HTML tables, ONLY where the site's robots.txt allows it, rate-limited, capped: trust 'web'
  Layer 3  tldr-pages            CLI syntax from the open tldr-pages repo: trust 'seed'
  Layer 4  local model fallback  OFF by default; whatever a model writes is trust 'llm' (always a probe, never executed unverified -- rag.fastpaths gate)

Output: workbook sheets 3_Hotkeys_Matrix / 4_Superhuman_Macros_CLI (merged with what is there) + sub_rag4_hotkeys_and_macros.jsonl. The RAG bridge (harvest.bridge) turns rows into fast_paths.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.robotparser
from typing import Any, Callable, Dict, List, Optional

from .free_master_harvester import Net, _merge, _save
from .paths import harvest_dir, workbook_path

SHEET_HOTKEYS, SHEET_MACROS = "3_Hotkeys_Matrix", "4_Superhuman_Macros_CLI"

SUPERHUMAN_MACROS_SEED: List[Dict[str, Any]] = [
    {"app_name": "Blender 3D", "tier": 3, "execution_type": "Headless_Python_bpy", "cli_trigger": 'blender --background --python "{script_path}"',
     "task_pattern": "Create a beveled cube of a given size, smooth shaded, and save it as a .blend file",
     "code_template": ("import bpy\nbpy.ops.wm.read_factory_settings(use_empty=True)\nbpy.ops.mesh.primitive_cube_add(size={size}, location=(0, 0, {size}/2))\nobj = bpy.context.active_object\n"
                       "mod = obj.modifiers.new(name='Bevel', type='BEVEL')\nmod.width = {bevel_width}\nmod.segments = 4\nbpy.ops.object.shade_smooth()\n"
                       "bpy.ops.wm.save_as_mainfile(filepath=r'{output_blend_path}')")},
    {"app_name": "AutoCAD", "tier": 3, "execution_type": "AutoCAD_Script_SCR", "cli_trigger": 'accoreconsole.exe /i "{input_dwg}" /s "{script_scr_path}"',
     "task_pattern": "Draw a rectangle and extrude the closed polyline into a 3D solid of a given height",
     "code_template": "_PLINE 0,0 {width},0 {width},{depth} 0,{depth} _C\n_EXTRUDE _L \n{height}\n_ZOOM _E\n_QSAVE\n"},
    {"app_name": "Microsoft Excel", "tier": 2, "execution_type": "Win32_COM_Automation", "cli_trigger": "python script.py",
     "task_pattern": "Create a sheet with a header row and a SUM formula under a column",
     "code_template": ("import win32com.client as win32\nexcel = win32.gencache.EnsureDispatch('Excel.Application')\nexcel.Visible = True\nwb = excel.Workbooks.Add()\nws = wb.ActiveSheet\n"
                       "ws.Range('A1:B1').Value = ['Metric', 'Revenue']\nws.Range('B{total_row}').Formula = '=SUM(B2:B{last_row})'\n")},
    {"app_name": "Microsoft Word", "tier": 2, "execution_type": "Win32_COM_Automation", "cli_trigger": "python script.py",
     "task_pattern": "Generate a document with a Heading 1 title",
     "code_template": ("import win32com.client as win32\nword = win32.gencache.EnsureDispatch('Word.Application')\nword.Visible = True\ndoc = word.Documents.Add()\n"
                       "rng = doc.Range(0, 0)\nrng.Text = '{title}\\n'\nrng.Style = 'Heading 1'\n")},
    {"app_name": "OBS Studio", "tier": 2, "execution_type": "WebSocket_And_CLI", "cli_trigger": "obs64.exe --startrecording --minimize-to-tray",
     "task_pattern": "Start recording without touching the UI", "code_template": "obs64.exe --startrecording --minimize-to-tray"},
]

CORE_HOTKEYS_SEED: List[Dict[str, Any]] = [
    {"app_name": "Blender 3D", "shortcut": "G then Z then {distance}", "action": "Move the selection along Z by an exact distance", "category": "3D Transform"},
    {"app_name": "Blender 3D", "shortcut": "E", "action": "Extrude selected mesh region in Edit Mode", "category": "Modeling"},
    {"app_name": "Blender 3D", "shortcut": "Ctrl+B", "action": "Bevel selected edges or vertices", "category": "Modeling"},
    {"app_name": "Blender 3D", "shortcut": "Tab", "action": "Toggle between Object Mode and Edit Mode", "category": "Mode Switch"},
    {"app_name": "Blender 3D", "shortcut": "Shift+A", "action": "Open the Add menu (Mesh, Curve, Light, Camera)", "category": "Creation"},
    {"app_name": "Blender 3D", "shortcut": "F12", "action": "Render the active camera frame", "category": "Render"},
    {"app_name": "AutoCAD", "shortcut": "L then Enter", "action": "Activate the LINE drawing tool", "category": "Draw"},
    {"app_name": "AutoCAD", "shortcut": "EXT then Enter", "action": "EXTRUDE a 2D closed object into a 3D solid", "category": "3D Modeling"},
    {"app_name": "AutoCAD", "shortcut": "TR then Enter then Enter", "action": "TRIM intersecting geometry", "category": "Modify"},
    {"app_name": "AutoCAD", "shortcut": "F8", "action": "Toggle Ortho Mode (lock the cursor to 90-degree angles)", "category": "Precision"},
    {"app_name": "AutoCAD", "shortcut": "F3", "action": "Toggle Object Snap for exact endpoints and midpoints", "category": "Precision"},
    {"app_name": "WhatsApp Desktop", "shortcut": "Ctrl+N", "action": "Start a new chat", "category": "Navigation"},
    {"app_name": "WhatsApp Desktop", "shortcut": "Ctrl+F", "action": "Search chats and messages", "category": "Search"},
    {"app_name": "WhatsApp Desktop", "shortcut": "Ctrl+Shift+M", "action": "Mute the selected conversation", "category": "Chat Actions"},
    {"app_name": "OBS Studio", "shortcut": "Ctrl+,", "action": "Open OBS Settings", "category": "Configuration"},
    {"app_name": "Visual Studio Code", "shortcut": "Ctrl+Shift+P", "action": "Open the Command Palette (run any command by name)", "category": "Master Control"},
]

_ROBOTS: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
UA = "HoJaiga-harvester/1.0"


def allowed_by_robots(url: str, net: Net) -> bool:
    """True only when the site's robots.txt is readable and permits this path (an unreadable robots.txt is treated as 'not allowed': be conservative with other people's sites)."""
    p = urllib.parse.urlparse(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in _ROBOTS:
        raw = net.http_get(host + "/robots.txt")
        if raw is None:
            _ROBOTS[host] = None
        else:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(raw.decode("utf-8", "replace").splitlines())
            _ROBOTS[host] = rp
    rp = _ROBOTS[host]
    return bool(rp and rp.can_fetch(UA, url))


_MODS = {"ctrl", "control", "alt", "shift", "win", "windows", "cmd", "command", "option", "opt", "altgr", "fn", "meta"}
_NAMED = {"enter", "return", "esc", "escape", "tab", "space", "spacebar", "home", "end", "pgup", "pgdn", "pageup", "pagedown", "page", "up", "down", "left", "right", "del", "delete", "backspace", "bksp",
          "insert", "ins", "capslock", "prtsc", "printscreen", "pause", "numlock", "scrolllock", "menu", "plus", "minus", "equals", "comma", "period", "slash", "backslash", "click", "scroll", "wheel"}
_ARROWS = set("\u2191\u2193\u2190\u2192")


def _is_key_token(tok: str) -> bool:
    t = tok.strip().lower()
    return bool(t) and (t in _MODS or t in _NAMED or bool(re.fullmatch(r"f([1-9]|1\d|2[0-4])", t)) or (len(t) == 1 and (t.isalnum() or t in ",./;'[]\\`-=<>?!@#$%^&*()_~" or t in _ARROWS)))


def _is_special(tok: str) -> bool:
    t = tok.strip().lower()
    return t in _MODS or t in _NAMED or bool(re.fullmatch(r"f([1-9]|1\d|2[0-4])", t)) or t in _ARROWS


def is_key_combo(text: str) -> bool:
    """'Ctrl + Shift + D', 'F12', 'Alt + 1', 'Ctrl + \u2191': tokens joined by '+' (or spaces), every one a modifier, named key, F-key or single character, at least one token."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s or len(s) > 45:
        return False
    toks = [t for t in re.split(r"\s*\+\s*|\s+", s) if t]
    return bool(toks) and all(_is_key_token(t) for t in toks) and (len(toks) > 1 or len(toks[0]) > 1 or toks[0].isalpha() or toks[0].isdigit())


def parse_shortcut_table(table) -> List[Dict[str, str]]:
    """[{shortcut, action}] from one HTML table, whatever its column layout (votes | keys | action | ... or keys | action): the key-combo column is found by CONTENT, the action is the longest
    descriptive cell. Mnemonic underlines (<u>m</u>emory) are joined, not split into 'm emory'. Rows without both are dropped, never guessed."""
    out = []
    for row in table.find_all("tr"):
        for br in row.find_all("br"):
            br.replace_with(" ")
        cells = [re.sub(r"\s+", " ", c.get_text("", strip=False)).strip() for c in row.find_all(["td", "th"])]
        cands = [c for c in cells if is_key_combo(c)]
        # rank: a combo with a modifier / named key / F-key beats a bare character; a bare number (a votes column) is the last resort
        cands.sort(key=lambda c: (not any(_is_special(t) for t in re.split(r"\s*\+\s*|\s+", c) if t), c.strip().isdigit() or bool(re.fullmatch(r"-?\d+", c.strip()))))
        keys = cands[0] if cands else None
        if keys is not None and re.fullmatch(r"-?\d+", keys.strip()) and len([c for c in cells if c]) >= 3:
            continue                                                  # a bare number in a 3+ cell row is the votes column, and the real key was a glyph we do not recognise: drop, never guess
        if keys is None:
            continue
        desc = [c for c in cells if c and c != keys and re.search(r"[A-Za-z]{2,}", c) and not is_key_combo(c)]
        if not desc:
            continue
        action = max(desc, key=len)
        if len(action) < 4 or action.lower() in ("shortcut", "action", "description", "command"):
            continue
        # alternatives: separated by 'or' or '/', or run together ("Ctrl + ↑ Shift + D" = Ctrl+↑ and Shift+D): a modifier that follows a finished combo without a '+' starts a new one
        parts = re.split(r"\s+or\s+|\s*/\s*|(?<![+\s])\s+(?=(?:ctrl|alt|shift|win|cmd|option)\b)", keys, flags=re.I)
        for alt in [a.strip() for a in parts if a and a.strip()] or [keys]:
            if is_key_combo(alt):
                out.append({"shortcut": alt, "action": action})
    return out


def scrape_public_shortcuts(app_name: str, net: Net, max_rows: int = 400, delay_s: float = 1.0) -> List[Dict[str, Any]]:
    from bs4 import BeautifulSoup
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-")
    out: List[Dict[str, Any]] = []
    for url in (f"https://www.shortcutworld.com/{slug}/win/{slug}_shortcuts", f"https://defkey.com/{slug}-shortcuts"):
        if not allowed_by_robots(url, net):
            continue
        raw = net.http_get(url)
        net.sleep(delay_s)
        if not raw:
            continue
        soup = BeautifulSoup(raw, "lxml")
        for table in soup.find_all("table"):
            for r in parse_shortcut_table(table):
                out.append({"app_name": app_name, "shortcut": r["shortcut"], "action": r["action"], "category": "Scraped_Web_Table", "source": "web_table", "source_url": url})
                if len(out) >= max_rows:
                    return out
        if out:
            break
    return out


def fetch_tldr(app_name: str, net: Net, delay_s: float = 0.5) -> List[Dict[str, Any]]:
    toks = re.sub(r"[^a-z0-9 ]+", " ", app_name.lower()).split()
    cands = []
    for c in ["".join(toks), toks[0] if toks else "", toks[-1] if toks else ""]:
        if c and c not in cands and c not in ("windows", "microsoft", "adobe", "desktop", "studio", "editor"):
            cands.append(c)
    out: List[Dict[str, Any]] = []
    for slug in cands[:3]:
        for plat in ("windows", "common"):
            raw = net.http_get(f"https://raw.githubusercontent.com/tldr-pages/tldr/main/pages/{plat}/{slug}.md")
            net.sleep(delay_s)
            if not raw:
                continue
            desc = ""
            for line in raw.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if line.startswith("- "):
                    desc = line[2:].rstrip(":")
                elif line.startswith("`") and line.endswith("`") and desc:
                    cmd = line.strip("`")
                    out.append({"app_name": app_name, "tier": 1, "execution_type": "CLI_Command", "cli_trigger": cmd, "task_pattern": desc, "code_template": cmd, "source": "tldr"})
                    desc = ""
            if out:
                return out
    return out


def ollama_shortcuts(app_name: str, model: str = "qwen3-vl:8b", url: str = "http://127.0.0.1:11434") -> List[Dict[str, Any]]:
    """Layer 4 (opt-in). Output is trust 'llm': a probe candidate, never a direct step."""
    import requests
    prompt = f"List the 10 most important Windows keyboard shortcuts for '{app_name}'. Return ONLY a JSON list of objects with keys 'shortcut' and 'action'."
    try:
        r = requests.post(url + "/api/generate", json={"model": model, "prompt": prompt, "stream": False, "format": "json"}, timeout=40)
        raw = json.loads(r.json().get("response", "[]"))
        items = raw if isinstance(raw, list) else raw.get("shortcuts", [])
        return [{"app_name": app_name, "shortcut": str(i["shortcut"]), "action": str(i["action"]), "category": "Local_Model_Synthesized", "source": "llm"} for i in items if "shortcut" in i and "action" in i]
    except Exception:
        return []


def run_hotkeys_and_macros_harvester(app_names: Optional[List[str]] = None, max_apps: int = 5, scrape: bool = True, tldr: bool = True, use_model: bool = False, net: Optional[Net] = None,
                                     root: str = "", delay_s: float = 1.0, write_workbook: bool = True) -> Dict[str, Any]:
    net = net or Net()
    root = root or harvest_dir()[0]
    if app_names is None:
        try:
            import pandas as pd
            app_names = pd.read_excel(workbook_path(root), sheet_name="1_Master_1000_Apps")["app_name"].dropna().unique().tolist()
        except Exception:
            app_names = sorted({a["app_name"] for a in SUPERHUMAN_MACROS_SEED + CORE_HOTKEYS_SEED})
    hotkeys = [dict(h, source="seed") for h in CORE_HOTKEYS_SEED]
    macros = [dict(m, source="seed") for m in SUPERHUMAN_MACROS_SEED]
    stats = {"apps": 0, "scraped_rows": 0, "tldr_rows": 0, "model_rows": 0}
    for name in app_names[:max_apps]:
        stats["apps"] += 1
        got = scrape_public_shortcuts(name, net, delay_s=delay_s) if scrape else []
        hotkeys += got
        stats["scraped_rows"] += len(got)
        if not got and use_model:
            m = ollama_shortcuts(name)
            hotkeys += m
            stats["model_rows"] += len(m)
        if tldr:
            t = fetch_tldr(name, net, delay_s=delay_s / 2)
            macros += t
            stats["tldr_rows"] += len(t)
    out: Dict[str, Any] = {"root": root, "stats": stats, "hotkeys": len(hotkeys), "macros": len(macros)}
    jl = os.path.join(root, "sub_rag4_hotkeys_and_macros.jsonl")
    with open(jl, "w", encoding="utf-8") as f:
        for r in hotkeys:
            f.write(json.dumps(dict(r, rag_sub_table="sub_rag4_hotkeys"), ensure_ascii=False) + "\n")
        for r in macros:
            f.write(json.dumps(dict(r, rag_sub_table="sub_rag4_superhuman_macros"), ensure_ascii=False) + "\n")
    out["jsonl"] = jl
    if write_workbook:
        import pandas as pd
        path = workbook_path(root)
        existing = pd.read_excel(path, sheet_name=None) if os.path.isfile(path) else {}
        sheets = dict(existing)
        old_hot = existing.get(SHEET_HOTKEYS)
        if old_hot is not None and len(old_hot) and "source" in old_hot.columns:
            old_hot = old_hot[~((old_hot["source"] == "web_table") & old_hot["app_name"].isin(app_names[:max_apps]))]
        sheets[SHEET_HOTKEYS] = _merge(old_hot, pd.DataFrame(hotkeys), ["app_name", "shortcut"])
        sheets[SHEET_MACROS] = _merge(existing.get(SHEET_MACROS), pd.DataFrame(macros), ["app_name", "task_pattern"])
        _save(path, sheets)
        out["workbook"] = path
    return out


if __name__ == "__main__":
    print(json.dumps(run_hotkeys_and_macros_harvester(), indent=2, default=str))
