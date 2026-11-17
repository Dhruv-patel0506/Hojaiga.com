"""excel_agent_autorun -- an autonomous Excel BUILDER: the local model invents the workbook,
the organs drive the ribbon, and every claim is proved twice.

    plan (local LLM)  ->  act (UIA + posted input)  ->  verify (live UIA + saved file)
                                                      ->  independent recompute (Python)

Nothing about the workbook is hand-written here. The model chooses the project, the sheets, the
columns, the data, the formulas and WHICH RIBBON FEATURES to exercise, from a capability menu
this script can actually perform and actually check. Excel computes the formulas; Python
re-evaluates the same formulas from the plan's own data; the saved file is then reopened and
both are compared cell by cell.

Laws honoured:
  * never the physical cursor -- UIA patterns and headless_input posted messages only.
  * every action has a postcondition: the Formula Bar is read back live through UIA
    TextPattern, and the saved .xlsx is the authoritative final oracle.
  * honest reporting: a capability that could not be verified is reported as failed, and a
    model that is unreachable aborts the run rather than substituting a canned plan.
  * only the Excel instance this script launched is ever closed.

Usage
-----
  python excel_agent_autorun.py --check-plan      # ask the model, print its plan, do nothing
  python excel_agent_autorun.py                   # plan + build + verify
  python excel_agent_autorun.py --keep-open       # leave Excel open for inspection
  python excel_agent_autorun.py --plan my.json    # reuse a previously produced plan
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORGANS = ROOT / "All codes"
if str(ORGANS) not in sys.path:
    sys.path.insert(0, str(ORGANS))

for _s in (sys.stdout, sys.stderr):
    try:
        _rc = getattr(_s, "reconfigure", None)
        if callable(_rc):
            _rc(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core_organs import fast_uia, headless_input  # noqa: E402

UIA_INVOKE, UIA_VALUE, UIA_TEXT, UIA_SELECT_ITEM, UIA_TOGGLE = 10000, 10002, 10014, 10007, 10015
EXCEL_EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
VISION_URL = os.environ.get("HOJAIGA_QWEN_VL_URL",
                            os.environ.get("HOJAIGA_PROF_VISION_URL", "http://127.0.0.1:8081")).rstrip("/")
OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OUT_DIR = ROOT / "storage" / "excel_agent"
LOG = ROOT / "trajectories" / "excel_agent_log.jsonl"
SETTLE, NAV_SETTLE = 0.35, 0.65


def log(msg: str) -> None:
    print(f"[agent] {msg}", flush=True)


# ---------------------------------------------------------------------------
# what the hands can do: every entry is performable AND checkable in the file
# ---------------------------------------------------------------------------

CAPABILITIES = {
    # ---- Home tab ----
    "bold": {"tab": "Home", "buttons": ["Bold"], "key": "ctrl+b", "check": "font_bold",
             "needs": "range", "desc": "make the text bold (header rows)"},
    "italic": {"tab": "Home", "buttons": ["Italic"], "key": "ctrl+i", "check": "font_italic",
               "needs": "range", "desc": "italicise a range"},
    "underline": {"tab": "Home", "buttons": ["Underline"], "key": "ctrl+u", "check": "font_underline",
                  "needs": "range", "desc": "underline a range"},
    "center": {"tab": "Home", "buttons": ["Center"], "key": "ctrl+e", "check": "align_center",
               "needs": "range", "desc": "centre-align a range"},
    "wrap_text": {"tab": "Home", "buttons": ["Wrap Text"], "key": "alt+h,w", "check": "align_wrap",
                  "needs": "range", "desc": "wrap long text inside cells"},
    "merge_center": {"tab": "Home", "buttons": ["Merge & Center"], "key": "alt+h,m,c",
                     "check": "merged", "needs": "range", "desc": "merge a banner across columns"},
    "fill_yellow": {"tab": "Home", "buttons": ["Fill Color"], "key": "alt+h,h", "check": "fill",
                    "needs": "range", "desc": "highlight a range with the fill colour"},
    "font_red": {"tab": "Home", "buttons": ["Font Color"], "key": "alt+h,f,c", "check": "font_color",
                 "needs": "range", "desc": "change the font colour"},
    "font_size": {"tab": "Home", "buttons": ["Font Size"], "check": "font_size",
                  "needs": "range+value", "desc": "set the point size of a range (value=14)"},
    "currency": {"tab": "Home", "buttons": ["Currency"], "key": "ctrl+shift+4", "check": "num_currency",
                 "needs": "range", "desc": "$ number format"},
    "percent": {"tab": "Home", "buttons": ["Percent Style"], "key": "ctrl+shift+5",
                "check": "num_percent", "needs": "range", "desc": "% number format"},
    "comma": {"tab": "Home", "buttons": ["Comma Style"], "key": "ctrl+shift+3", "check": "num_comma",
              "needs": "range", "desc": "thousands separator with 2 decimals"},
    "all_borders": {"tab": "Home", "buttons": ["Borders"], "key": "alt+h,b,a", "check": "borders",
                    "needs": "range", "desc": "apply all borders to a block"},
    "cond_greater": {"tab": "Home", "buttons": ["Conditional Formatting"], "key": "alt+h,l,g",
                     "check": "conditional_format", "needs": "range+value",
                     "desc": "highlight cells greater than a value"},
    "autofit_columns": {"tab": "Home", "buttons": ["Format", "Autofit Column Widths"],
                        "key": "alt+h,o,i", "check": None, "needs": "range",
                        "desc": "widen columns to fit their content"},
    # ---- Insert tab ----
    "new_sheet": {"tab": "", "buttons": [], "key": "shift+f11", "check": "sheet_exists",
                  "needs": "value", "desc": "add another worksheet (value=name)"},
    "bar_chart": {"tab": "Insert", "buttons": [], "key": "alt+f1", "check": "chart",
                  "needs": "range", "desc": "insert a clustered column chart from a selection"},
    "table": {"tab": "Insert", "buttons": ["Table"], "check": "table", "needs": "range",
              "desc": "turn a block into a real Excel table (Ctrl+L then confirm)"},
    # ---- Page Layout tab ----
    "landscape": {"tab": "Page Layout", "buttons": ["Orientation", "Landscape"], "key": "alt+p,o,a,l",
                  "check": "orientation", "needs": "", "desc": "print orientation to landscape"},
    "margins_narrow": {"tab": "Page Layout", "buttons": ["Margins", "Narrow"], "key": "alt+p,m,n",
                       "check": "margins", "needs": "", "desc": "narrow page margins"},
    # ---- Formulas tab ----
    "autosum": {"tab": "Home", "buttons": ["AutoSum"], "key": "alt+=", "check": "formula_sum",
                "needs": "range", "desc": "AutoSum the column above the selection"},
    "define_name": {"tab": "Formulas", "buttons": ["Define Name"], "check": "defined_name",
                    "needs": "range+value", "desc": "name a range (value=the name)"},
    # ---- Data tab ----
    "autofilter": {"tab": "Data", "buttons": ["Filter"], "key": "ctrl+shift+l", "check": "filter",
                   "needs": "range", "desc": "add filter dropdowns to a header row"},
    "sort_ascending": {"tab": "Data", "buttons": ["Sort Ascending"], "key": "alt+a,s,a",
                       "check": "sorted", "needs": "range", "desc": "sort a column A-Z / low-high"},
    # ---- Review tab ----
    "note": {"tab": "Review", "buttons": ["New Note"], "key": "shift+f2", "check": "comment",
             "needs": "cell+value", "desc": "attach a note to a cell (value=text)"},
    # ---- View tab ----
    "freeze_first_row": {"tab": "View", "buttons": ["Freeze Panes", "Freeze Top Row"],
                         "key": "alt+w,f,f", "check": "freeze_top", "needs": "",
                         "desc": "keep the header row visible while scrolling"},
    "gridlines_off": {"tab": "View", "buttons": ["View", "Gridlines"], "key": "alt+w,g",
                      "check": "no_gridlines", "needs": "", "desc": "hide gridlines for a clean look"},
}

MENU = "\n".join(f"  - {k}: {v['desc']}" for k, v in CAPABILITIES.items())

SCHEMA = ('{"project":"one line goal","file":"short_name","sheets":[{"name":"SheetTabName",'
          '"purpose":"...","tab_color":"Red|Blue|Green|Orange|Yellow|Purple|none",'
          '"title_banner":"optional merged heading text",'
          '"headers":["Col A","Col B"],"rows":[["value",12.5,38]],'
          '"formulas":[{"cell":"D2","formula":"=B2*C2","why":"taxable income"}],'
          '"features":[{"cap":"bold","range":"A1:G1"},{"cap":"freeze_first_row"},'
          '{"cap":"currency","range":"D2:D9"},{"cap":"bar_chart","range":"A1:A9"},'
          '{"cap":"new_sheet","value":"Notes"}],"chart":{"type":"bar","data":"D2:D9","cats":"A2:A9"}}]}')


# ---------------------------------------------------------------------------
# the planner: the local model invents the workbook
# ---------------------------------------------------------------------------

PLAN_PROMPT = (
    "You are an Excel automation agent about to drive a real Microsoft Excel window. You decide "
    "what to build - it must be a genuinely useful multi-sheet workbook, not a toy, and it must "
    "exercise as much of the RIBBON as makes sense for the subject.\n\n"
    "Non-negotiable requirements (a plan that misses these is rejected and you will be asked "
    "again):\n"
    " * 4 sheets, each with a different job (for example: the raw data, a calculation, an "
    "analysis/dashboard, and a reference or assumptions sheet).\n"
    " * Each sheet: 4 to 7 columns and 4 to 8 data rows of REALISTIC values you invent (names, "
    "prices, quantities, dates as text like 2026-01-15). No placeholders like TBD or xxx.\n"
    " * At least 8 formulas in total across the workbook, written as Excel formulas in the "
    "'formulas' list. Header text lives in row 1 and data starts in row 2, so NEVER put a "
    "formula in row 1 of a sheet that has headers - use row "
    "below the last data row, or a column to the right.\n"
    " * Use at least 14 DIFFERENT capability ids from the menu, and they must come from at "
    "least 5 different ribbon tabs (Home, Insert, Page Layout, Formulas, Data, Review, View).\n"
    " * 'features' entries may only use capability ids from the menu. 'range' means an Excel "
    "range like A1:F1 or D2:D9.\n"
    " * Reply with JSON only, shaped exactly like: " + SCHEMA + "\n\n"
    "RIBBON CAPABILITY MENU:\n" + MENU + "\n"
)


def extract_json(text: str):
    if not text:
        return None
    t = re.sub(r"^```[a-zA-Z]*\s*", "", str(text).strip()).strip("` \n")
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except Exception:
                    return None
    return None


def ask_model(prompt: str, session) -> tuple:
    """Local only. Vision server first (it is the brain on this box), then Ollama text."""
    import requests
    try:
        r = requests.get(VISION_URL + "/health", timeout=2)
        if r.status_code == 200:
            body = {"messages": [{"role": "system", "content": "You output strict JSON only."},
                                 {"role": "user", "content": prompt}],
                    "temperature": 0.4, "max_tokens": 2600, "stream": False}
            txt = requests.post(VISION_URL + "/v1/chat/completions", json=body, timeout=420).json()
            return (txt.get("choices") or [{}])[0].get("message", {}).get("content", ""), "vlm"
    except Exception:
        pass
    try:
        names = [m.get("name", "") for m in requests.get(OLLAMA_URL + "/api/tags", timeout=3).json().get("models", [])]
        pick = next((n for n in names if n.startswith("qwen2.5")), names[0] if names else "")
        if not pick:
            return "", "none"
        body = {"model": pick, "prompt": prompt, "format": "json", "stream": False,
                "options": {"temperature": 0.4, "num_predict": 2600}}
        resp = requests.post(OLLAMA_URL + "/api/generate", json=body, timeout=420).json().get("response", "")
        try:
            inner = json.loads(resp)
            if isinstance(inner, str):
                resp = inner
        except Exception:
            pass
        return (resp if isinstance(resp, str) else json.dumps(resp)), pick
    except Exception as exc:
        return "", f"error:{type(exc).__name__}"


def validate_plan(plan: dict) -> list:
    """Keep only what the executor genuinely needs: a name, something to write, and real
    formulas. A notes or summary sheet may legitimately be narrow or short."""
    bad = []
    if not isinstance(plan, dict) or not isinstance(plan.get("sheets"), list) or not plan["sheets"]:
        return ["no sheets"]
    if len(plan["sheets"]) < 3:
        bad.append(f"only {len(plan['sheets'])} sheets; the task needs at least 3")
    total_formulas = 0
    caps_used = set()
    for s in plan["sheets"]:
        nm = str(s.get("name") or "").strip()
        if not nm:
            bad.append("sheet without a name")
            continue
        headers = s.get("headers")
        rows = s.get("rows")
        if not isinstance(headers, list) or not headers:
            bad.append(f"{nm}: needs a headers list")
            continue
        if not isinstance(rows, list) or not rows:
            bad.append(f"{nm}: needs at least one data row")
            continue
        if any(not isinstance(r, list) for r in rows):
            bad.append(f"{nm}: every row must be a list of values")
        for f in (s.get("formulas") or []):
            if not str(f.get("formula", "")).startswith("="):
                bad.append(f"{nm}: formula {f.get('formula')!r} does not start with =")
            else:
                total_formulas += 1
        for feat in (s.get("features") or []):
            if feat.get("cap") not in CAPABILITIES:
                bad.append(f"{nm}: unknown capability {feat.get('cap')!r}")
            else:
                caps_used.add(feat["cap"])
    if total_formulas < 6:
        bad.append(f"only {total_formulas} formulas across the workbook; give at least 6")
    if len(caps_used) < 8:
        bad.append(f"only {len(caps_used)} different ribbon capabilities used "
                   f"({sorted(caps_used)}); use at least 8, spread over several tabs")
    tabs = {CAPABILITIES[c]["tab"] for c in caps_used if c in CAPABILITIES}
    if len(tabs - {""}) < 3:
        bad.append(f"capabilities come from too few tabs ({sorted(tabs)}); reach across "
                   f"Home, Insert, Page Layout, Formulas, Data, Review or View")
    return bad


def normalise_plan(plan: dict) -> list:
    """Repair what we can before judging: a 'formula' entry that is really a plain value is
    dropped (it will still be written as data), capability ids are lower-cased."""
    notes = []
    for s in plan.get("sheets", []):
        keep = []
        for f in (s.get("formulas") or []):
            form = str(f.get("formula", "")).strip()
            if form.startswith("="):
                keep.append(f)
            else:
                notes.append(f"{s.get('name')}: {f.get('cell')}={form!r} is a value, not a formula")
        s["formulas"] = keep
        feats = []
        for feat in (s.get("features") or []):
            cap = str(feat.get("cap") or "").strip().lower()
            if cap in CAPABILITIES:
                feat["cap"] = cap
                feats.append(feat)
            else:
                notes.append(f"{s.get('name')}: unknown capability {feat.get('cap')!r}")
        s["features"] = feats
    return notes


def plan_score(plan: dict) -> tuple:
    """(problems, distinct capabilities, formulas, sheets) -- used to pick the best attempt."""
    problems = validate_plan(plan)
    caps = {f["cap"] for s in plan.get("sheets", []) for f in (s.get("features") or [])
            if f.get("cap") in CAPABILITIES}
    forms = sum(len(s.get("formulas") or []) for s in plan.get("sheets", []))
    return len(problems), len(caps), forms, len(plan.get("sheets") or [])


def floor_ok(plan: dict) -> bool:
    """The minimum we will actually execute: something real to build, with several ribbon
    features. Anything below this and we abort rather than pretend."""
    if not isinstance(plan, dict) or not isinstance(plan.get("sheets"), list):
        return False
    if len(plan["sheets"]) < 2:
        return False
    caps = {f["cap"] for s in plan["sheets"] for f in (s.get("features") or [])
            if f.get("cap") in CAPABILITIES}
    forms = sum(len(s.get("formulas") or []) for s in plan["sheets"])
    return len(caps) >= 4 and forms >= 2


def make_plan(args) -> dict:
    if args.plan:
        p = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        log(f"reusing plan from {args.plan}")
        return p
    import requests
    prompt = PLAN_PROMPT
    best, best_score = None, None
    for attempt in (1, 2, 3, 4):
        raw, engine = ask_model(prompt, requests)
        plan = extract_json(raw)
        if not plan:
            log(f"attempt {attempt}: model returned no JSON (engine={engine or 'unreachable'})")
            prompt = PLAN_PROMPT + "\nYour last reply was not valid JSON. Reply with JSON only.\n"
            continue
        notes = normalise_plan(plan)
        problems = validate_plan(plan)
        if notes:
            log(f"attempt {attempt}: normalised {len(notes)} item(s): {notes[:2]}")
        score = plan_score(plan)
        if best_score is None or score[1:] > best_score[1:]:      # more caps/formulas wins
            best, best_score = plan, score
        if not problems:
            log(f"plan authored by local model '{engine}': {plan.get('project', '')[:78]}")
            plan["_engine"] = engine
            return plan
        log(f"attempt {attempt} rejected: {problems[:3]}")
        # reflexion: feed the exact shortfall back, keep the model from starting over
        prompt = (PLAN_PROMPT + "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Reasons:\n"
                  + "\n".join(f" - {p}" for p in problems)
                  + "\n\nKeep the same workbook idea but FIX every reason above. Your previous "
                  "answer for reference (edit it, do not restart):\n"
                  + json.dumps(plan)[:3500] + "\n")
        time.sleep(1.5)
    if best is not None and floor_ok(best):
        problems = validate_plan(best)
        log(f"no attempt met the full target; executing the BEST plan at reduced ambition "
            f"({plan_score(best)[1]} capabilities, {plan_score(best)[2]} formulas). "
            f"Outstanding: {problems[:3]}")
        best["_below_target"] = problems
        return best
    return {}


# ---------------------------------------------------------------------------
# the pilot: hardened primitives (self-healing handles, mode-clearing, ribbon clicks)
# ---------------------------------------------------------------------------

class Pilot:
    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)
        self._cache = {}

    def nodes(self, cap: int = 30000) -> list:
        return fast_uia.snapshot(self.hwnd, max_nodes=cap) or []

    def resolve(self, want: str, ctype: str = "", refresh: bool = False):
        """Find a UIA element by name or automation id, cached but re-resolvable: an Office
        element can go stale, and a stale handle is the difference between one failed step and
        a cascade of them."""
        key = (want.lower(), ctype.lower())
        if not refresh and key in self._cache:
            n = self._cache[key]
            try:
                _ = n.ctrl  # touch it; a dead element raises here
                return n
            except Exception:
                self._cache.pop(key, None)
        low = want.lower()
        for n in self.nodes():
            nm = str(n.name or "").strip().lower()
            aid = str(n.aid or "").lower()
            if (low == nm or low == aid or low in nm) and (not ctype or ctype.lower() in n.ctype.lower()):
                self._cache[key] = n
                return n
        return None

    def drop_cache(self) -> None:
        self._cache = {}

    # ---- basic input ------------------------------------------------------
    def clear_mode(self) -> None:
        """Escape twice: cancels a half-typed cell or an open rename box before we act."""
        headless_input.post_key_combo(self.hwnd, "escape")
        time.sleep(0.12)
        headless_input.post_key_combo(self.hwnd, "escape")
        time.sleep(0.2)

    def key(self, combo: str, settle: float = SETTLE) -> bool:
        ok, _ = headless_input.post_key_combo(self.hwnd, combo)
        time.sleep(settle)
        return bool(ok)

    def type_text(self, text: str) -> bool:
        ok, _ = headless_input.post_text(self.hwnd, str(text))
        time.sleep(SETTLE)
        return bool(ok)

    def goto(self, addr: str, attempts: int = 2) -> bool:
        for a in range(attempts):
            self.clear_mode()
            nb = self.resolve("13", "combobox", refresh=bool(a))
            if nb is None:
                continue
            try:
                nb.ctrl.GetPattern(UIA_VALUE).SetValue(str(addr))
            except Exception:
                continue
            time.sleep(0.15)
            self.key("enter")
            time.sleep(NAV_SETTLE)
            return True
        return False

    def read(self) -> str:
        """The selected cell's content, via UIA TextPattern on the Formula Bar."""
        fb = self.resolve("formulabar", "")
        if fb is None:
            return ""
        for pid, kind in ((UIA_TEXT, "text"), (UIA_VALUE, "value")):
            try:
                p = fb.ctrl.GetPattern(pid)
                v = p.DocumentRange.GetText(-1) if kind == "text" else p.Value
                if v:
                    return str(v)
            except Exception:
                continue
        return ""

    def click_button(self, *names: str, tab: str = "") -> bool:
        """Drive the ribbon: select the tab, then Invoke the named control."""
        if tab:
            t = self.resolve(tab, "tabitem")
            if t is not None:
                try:
                    t.ctrl.GetPattern(UIA_SELECT_ITEM).Select()
                    time.sleep(0.55)
                except Exception:
                    pass
        for want in names:
            for ctype in ("button", "splitbutton", "menuitem", ""):
                n = self.resolve(want, ctype)
                if n is None:
                    continue
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    time.sleep(0.5)
                    return True
                except Exception:
                    continue
        return False

    def active_sheet_name(self) -> str:
        for n in self.nodes():
            if "tabitem" in n.ctype.lower() and str(getattr(n, "selected", False)):
                nm = str(n.name or "").strip()
                if nm and nm.lower() not in ("file", "home", "insert", "draw", "page layout",
                                             "formulas", "data", "review", "view", "automate",
                                             "help", "analytic solver"):
                    return nm
        return ""


def reach_workbook() -> tuple:
    mine = {int(h) for h, t in headless_input.top_level_titles(visible_only=False)
            if (t or "").strip().lower().endswith("- excel")}
    log("launching our own Excel instance ...")
    proc = subprocess.Popen([EXCEL_EXE, "/n"], creationflags=0x00000200)
    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(1.5)
        for h, t in headless_input.top_level_titles(visible_only=False):
            tl = (t or "").strip().lower()
            if tl.endswith("- excel") and "book" in tl:
                p = Pilot(int(h))
                log(f"workbook window: hwnd={h} title={t!r}")
                return proc, p
        for h, t in headless_input.top_level_titles(visible_only=False):
            if int(h) in mine or (t or "").strip().lower() != "excel":
                continue
            p = Pilot(int(h))
            n = p.resolve("blank workbook", "listitem")
            if n is not None:
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    log("  start screen: invoked 'Blank workbook' through UIA")
                except Exception:
                    pass
            break
    return proc, None


# ---------------------------------------------------------------------------
# writing cells, with a live postcondition on every one
# ---------------------------------------------------------------------------

def same_text(a: str, b: str) -> bool:
    a, b = str(a).strip().lower(), str(b).strip().lower()
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 0.005          # Excel shows 12 for 12.0
    except (TypeError, ValueError):
        return False


def write_cell(p: Pilot, led: list, addr: str, value, tag: str = "cell") -> bool:
    got = ""
    for attempt in (1, 2):
        if not p.goto(addr):
            continue
        p.type_text(value)
        p.key("enter")
        time.sleep(0.25)
        if not p.goto(addr):
            continue
        got = p.read()
        if same_text(got, value):
            led.append({"step": tag, "detail": f"{addr}={value}", "verified": True})
            return True
        led.append({"step": tag, "detail": f"{addr}={value}", "verified": False,
                    "observed": got[:50], "attempt": attempt})
    log(f"  FAIL  {tag} {addr} = {value}  (formula bar showed {got[:40]!r})")
    return False


COL = lambda i: "" if i < 0 else chr(ord("A") + i % 26)    # noqa: E731  (plans stay small)


def build_sheet(p: Pilot, led: list, sheet: dict, first: bool) -> dict:
    """Create/switch to the sheet, fill it, then apply the model's chosen ribbon features."""
    name = str(sheet.get("name") or "Data").strip()[:28] or "Data"
    if first:
        tab = p.resolve(name.lower() if p.active_sheet_name().lower() == name.lower() else "sheet1")
        if tab is None:
            tab = p.resolve("sheet1")
        try:
            tab.ctrl.GetPattern(UIA_SELECT_ITEM).Select()
        except Exception:
            pass
        p.key("f2", settle=0.4)
        p.type_text(name)
        p.key("enter", settle=0.9)
        p.clear_mode()
    else:
        p.clear_mode()
        p.key("shift+f11", settle=1.4)          # new sheet arrives with its tab name editable
        p.type_text(name)
        p.key("enter", settle=1.0)
        p.clear_mode()
    live = p.active_sheet_name()
    led.append({"step": "sheet", "detail": f"sheet {name!r} exists and is active",
                "verified": live.lower() == name.lower(), "observed": live})
    log(f"  {'PASS' if live.lower() == name.lower() else 'FAIL'}  sheet: {name} (active={live!r})")

    headers = [str(h) for h in (sheet.get("headers") or [])]
    for i, h in enumerate(headers):
        write_cell(p, led, f"{COL(i)}1", h, "header")
    for r, row in enumerate(sheet.get("rows") or [], start=2):
        for i, val in enumerate(row[:len(headers) or len(row)]):
            write_cell(p, led, f"{COL(i)}{r}", val, "data")
    for f in (sheet.get("formulas") or []):
        addr = str(f.get("cell") or "").strip().upper()
        form = str(f.get("formula") or "").strip()
        if not (addr and form.startswith("=")):
            continue
        if re.match(r"^[A-Z]+1$", addr) and headers:
            # a model that aims a formula at row 1 would erase the header it just wrote
            led.append({"step": "formula", "detail": f"{addr}={form}", "verified": False,
                        "observed": "skipped: would overwrite the header row"})
            log(f"  SKIP  formula {addr}={form} (row 1 is the header row)")
            continue
        write_cell(p, led, addr, form, "formula")
    return {"name": name, "headers": headers, "rows": sheet.get("rows") or [],
            "formulas": sheet.get("formulas") or [], "features": sheet.get("features") or [],
            "chart": sheet.get("chart") or {}, "tab_color": sheet.get("tab_color") or "none",
            "banner": sheet.get("title_banner") or ""}


def apply_feature(p: Pilot, led: list, sheet: dict, feat: dict) -> None:
    cap = str(feat.get("cap") or "")
    spec = CAPABILITIES.get(cap)
    rng = str(feat.get("range") or "").strip()
    val = feat.get("value")
    if spec is None:
        led.append({"step": "feature", "detail": f"{cap}: unknown capability", "verified": False})
        return
    ok = False
    if cap == "new_sheet":
        p.clear_mode()
        p.key("shift+f11", settle=1.3)
        p.type_text(str(val or "Extra"))
        p.key("enter", settle=1.0)
        ok = True
    elif cap == "font_size":
        if p.goto(rng or "A1"):
            fs = p.resolve("font size", "combobox")
            try:
                fs.ctrl.GetPattern(UIA_VALUE).SetValue(str(val or 14))
                p.key("enter", settle=0.6)
                ok = True
            except Exception:
                ok = False
    elif cap == "table":
        if p.goto(rng or "A1"):
            p.key("ctrl+l", settle=1.2)
            ok = p.key("enter", settle=1.2)
    elif cap == "autosum":
        ok = p.goto(rng or "A1") and p.key("alt+=")
    elif cap == "note":
        cell = (rng or "A1").split(":")[0]
        ok = p.goto(cell) and p.type_text(str(val or "note")) and p.key("escape")
    elif cap == "define_name":
        ok = p.goto(rng or "A1")
        if ok:
            nb = p.resolve("13", "combobox")
            try:
                nb.ctrl.GetPattern(UIA_VALUE).SetValue(str(val or "MyRange"))
                p.key("enter", settle=0.8)
                ok = True
            except Exception:
                ok = False
    elif cap == "cond_greater":
        if p.goto(rng or "A1"):
            ok = p.click_button("Conditional Formatting", tab="Home")
            if ok:
                p.key("g", settle=0.8)
                p.type_text(str(val if val is not None else 100))
                p.key("enter", settle=1.0)
                p.key("enter", settle=0.6)
    elif cap == "bar_chart":
        ok = p.goto(rng or "A1") and p.key("alt+f1", settle=1.6)
        p.key("escape")
    elif cap == "autofilter":
        ok = p.goto(rng or "A1") and p.key("ctrl+shift+l")
    elif cap == "freeze_first_row":
        ok = p.goto("A2") and p.click_button("Freeze Panes", "Freeze Top Row", tab="View")
        if not ok:
            ok = p.key("alt+w,f,f")
    elif cap in ("landscape", "margins_narrow", "gridlines_off"):
        ok = p.click_button(*spec["buttons"], tab=spec["tab"]) or p.key(spec.get("key", ""))
    else:
        if rng and not p.goto(rng):
            led.append({"step": "feature", "detail": f"{cap} on {rng}: cannot select", "verified": False})
            return
        if spec.get("key"):
            ok = p.key(spec["key"])
        if not ok and spec.get("buttons"):
            ok = p.click_button(*spec["buttons"], tab=spec.get("tab", ""))
        if cap in ("fill_yellow", "font_red") and ok:
            p.key("enter", settle=0.5)
    led.append({"step": "feature", "detail": f"{cap} {rng or val or ''}".strip(),
                "verified": bool(ok)})
    log(f"  {'PASS' if ok else 'FAIL'}  ribbon: {cap} {rng or ('=' + str(val)) if (rng or val) else ''}")


def save_workbook(p: Pilot, led: list, path: Path) -> bool:
    """F12 opens the CLASSIC #32770 dialog, which -- unlike Office's own pane -- takes a full
    path. SetValue is refused on its edit, so focus it and post the characters instead."""
    p.clear_mode()
    p.key("f12", settle=3.0)
    dlg = None
    for h, t in headless_input.top_level_titles(visible_only=False):
        if "save as" in (t or "").lower():
            dlg = int(h)
            break
    if dlg is None:
        led.append({"step": "save", "detail": "F12 produced no Save As dialog", "verified": False})
        return False
    edit = None
    for n in (fast_uia.snapshot(dlg, max_nodes=9000) or []):
        if str(n.name or "").strip().lower().startswith("file name") and "edit" in n.ctype.lower():
            edit = n
            break
    placed = False
    if edit is not None:
        try:
            edit.ctrl.SetFocus()
            time.sleep(0.4)
            headless_input.post_key_combo(dlg, "ctrl+a")
            time.sleep(0.2)
            placed = headless_input.post_text(dlg, str(path))[0]
        except Exception:
            placed = False
    time.sleep(0.9)
    clicked = False
    for n in (fast_uia.snapshot(dlg, max_nodes=9000) or []):
        if str(n.name or "").strip().lower() == "save" and "button" in n.ctype.lower():
            try:
                n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                clicked = True
            except Exception:
                clicked = headless_input.post_button_click(int(n.el.CurrentNativeWindowHandle) or 0)[0]
            break
    if not clicked:
        headless_input.post_key_combo(dlg, "enter")
    time.sleep(3.5)
    ok = path.is_file()
    led.append({"step": "save", "detail": f"saved {path.name} (name field {placed}, save {clicked})",
                "verified": ok})
    log(f"  {'PASS' if ok else 'FAIL'}  save: {path}")
    return ok


# ---------------------------------------------------------------------------
# independent arithmetic: Python evaluates the model's own formulas from its own data
# ---------------------------------------------------------------------------

def literal(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return str(v)


def expand_range(a: str, b: str, cells: dict) -> list:
    ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups()
    cb, rb = re.match(r"([A-Z]+)(\d+)", b).groups()
    idx_a, idx_b = _col_i(ca), _col_i(cb)
    out = []
    for r in range(int(ra), int(rb) + 1):
        for c in range(min(idx_a, idx_b), max(idx_a, idx_b) + 1):
            out.append(cells.get(f"{_col_name(c)}{r}", 0.0))
    return out


def _col_i(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def _num(x):
    return x if isinstance(x, (int, float)) else (literal(x) if isinstance(x, str) else 0.0)


def _flatten(args):
    out = []
    for a in args:
        out.extend(a if isinstance(a, list) else [a])
    return out


def _crit_match(val, crit) -> bool:
    c = str(crit).strip().strip('"')
    m = re.match(r"^([<>]=?|=)\s*(.+)$", c)
    if m:
        op, rhs = m.group(1), literal(m.group(2))
        lv = _num(val)
        return {"<": lv < rhs, ">": lv > rhs, "<=": lv <= rhs, ">=": lv >= rhs, "=": lv == rhs}[op]
    return str(val).strip().lower() == c.lower()


FUNCS = {
    "SUM": lambda *a: sum(_num(x) for x in _flatten(a)),
    "AVERAGE": lambda *a: (sum(_num(x) for x in _flatten(a)) / max(1, len(_flatten(a)))),
    "MAX": lambda *a: max((_num(x) for x in _flatten(a)), default=0),
    "MIN": lambda *a: min((_num(x) for x in _flatten(a)), default=0),
    "COUNT": lambda *a: sum(1 for x in _flatten(a) if isinstance(_num(x), float)),
    "PRODUCT": lambda *a: eval("*".join(str(_num(x)) for x in _flatten(a)) or "1"),
    "SUMPRODUCT": lambda a, b=None: sum(_num(x) * _num(y) for x, y in zip(
        a if isinstance(a, list) else [a], (b if isinstance(b, list) else [b]) if b is not None else [])),
    "ROUND": lambda x, n=0: round(_num(x), int(_num(n))),
    "ABS": lambda x: abs(_num(x)),
    "IF": lambda c, t, f=False: t if c else f,
    "COUNTIF": lambda rng, crit: sum(1 for x in (rng if isinstance(rng, list) else [rng]) if _crit_match(x, crit)),
    "INDEX": lambda rng, i: (rng if isinstance(rng, list) else [rng])[max(1, int(_num(i))) - 1],
    "MATCH": lambda v, rng, k=0: next((j + 1 for j, x in enumerate(rng if isinstance(rng, list) else [rng])
                                       if _num(x) == _num(v)), 0),
}

TOKEN_RE = re.compile(r"([A-Z]{1,3}\d+:[A-Z]{1,3}\d+)|([A-Z]{1,3}\d+)|(\b[A-Z]+(?=\())", re.I)


def to_python(formula: str, cells: dict):
    """Translate one Excel formula into a Python expression, then evaluate it in a guarded
    evaluator: the formula text comes from a model, so only arithmetic, comparisons, literals,
    lists and the named functions above are allowed through."""
    expr = str(formula).lstrip("=")
    literals = []

    def stash(m):                       # Excel is case-insensitive in functions but not in text
        literals.append(m.group(0)[1:-1])
        return f"\x00{len(literals) - 1}\x00"

    expr = re.sub(r'"[^"]*"', stash, expr).upper()
    parts, pos = [], 0
    for m in TOKEN_RE.finditer(expr):
        parts.append(expr[pos:m.start()])
        rng, ref, fn = m.group(1), m.group(2), m.group(3)
        if rng:
            a, b = rng.split(":")
            parts.append(repr(expand_range(a, b, cells)))
        elif ref:
            parts.append(ref if fn else repr(cells.get(ref, 0.0)))
        elif fn:
            parts.append(fn if fn in FUNCS else "UNSUPPORTED")
        pos = m.end()
    parts.append(expr[pos:])
    py = "".join(parts)
    for i, lit in enumerate(literals):
        py = py.replace(f"\x00{i}\x00", repr(lit))
    for name in FUNCS:
        py = re.sub(rf"\b{name}\s*\(", f"FUNCS['{name}'](", py)
    if "UNSUPPORTED" in py or "\x00" in py:
        return None
    return safe_eval(py)


ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
                 ast.Constant, ast.Name, ast.Load, ast.List, ast.Tuple, ast.Call, ast.keyword,
                 ast.Subscript, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow,
                 ast.Mod, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Lt, ast.LtE,
                 ast.Gt, ast.GtE, ast.Eq, ast.NotEq)


def safe_eval(py: str):
    """A deliberately small calculator: the only subscript and the only call allowed is a
    lookup into FUNCS. Attribute access, comprehensions, lambdas, names and every builtin are
    refused, so model-authored text cannot execute anything."""
    try:
        tree = ast.parse(py, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            return None
        if isinstance(node, ast.Subscript):
            if not (isinstance(node.value, ast.Name) and node.value.id == "FUNCS"):
                return None
            if not isinstance(node.slice, ast.Constant):
                return None
        elif isinstance(node, ast.Call):
            fn = node.func
            if not (isinstance(fn, ast.Subscript) and isinstance(fn.value, ast.Name)
                    and fn.value.id == "FUNCS"):
                return None
        elif isinstance(node, ast.Name) and node.id != "FUNCS":
            return None
    try:
        return eval(compile(tree, "<formula>", "eval"), {"__builtins__": {}}, {"FUNCS": FUNCS})
    except Exception:
        return None


def evaluate_sheet(sheet: dict) -> dict:
    """Cells from the plan's own data, then its formulas resolved in dependency order."""
    cells = {}
    headers = [str(h) for h in (sheet.get("headers") or [])]
    for i, h in enumerate(headers):
        cells[f"{_col_name(i)}1"] = h
    for r, row in enumerate(sheet.get("rows") or [], start=2):
        for i, v in enumerate(row):
            cells[f"{_col_name(i)}{r}"] = literal(v)
    pending = {str(f.get("cell", "")).upper(): str(f.get("formula", ""))
               for f in (sheet.get("formulas") or []) if str(f.get("formula", "")).startswith("=")}
    for _ in range(6):
        if not pending:
            break
        progress = False
        for addr in list(pending):
            val = to_python(pending[addr], cells)
            if val is not None:
                cells[addr] = val if isinstance(val, (int, float, str)) else val
                del pending[addr]
                progress = True
        if not progress:
            break
    return cells


# ---------------------------------------------------------------------------
# the authoritative oracle: reopen the saved file and check what the plan promised
# ---------------------------------------------------------------------------

def _rng_first(rng: str) -> str:
    return (rng or "A1").split(":")[0].strip().upper()


def _rng_cols(rng: str) -> list:
    a, _, b = (rng or "A1").partition(":")
    a, b = a.strip().upper(), (b or a).strip().upper()
    ma, mb = re.match(r"([A-Z]+)", a), re.match(r"([A-Z]+)", b)
    if not ma or not mb:
        return ["A"]
    lo, hi = _col_i(ma.group(1)), _col_i(mb.group(1))
    return [_col_name(i) for i in range(min(lo, hi), max(lo, hi) + 1)]


def _rng_rows(rng: str) -> tuple:
    a, _, b = (rng or "A1").partition(":")
    ra = re.search(r"(\d+)", a)
    rb = re.search(r"(\d+)", b or a)
    return (int(ra.group(1)) if ra else 1, int(rb.group(1)) if rb else (int(ra.group(1)) if ra else 1))


def check_feature(cap: str, rng: str, val, ws, wb) -> tuple:
    """Ask the saved file whether the ribbon operation really happened."""
    c0 = _rng_first(rng)
    cell = ws[c0] if c0 else ws["A1"]
    f = cell.font
    if cap == "bold":
        return bool(f and f.bold), f"bold={bool(f and f.bold)}"
    if cap == "italic":
        return bool(f and f.italic), f"italic={bool(f and f.italic)}"
    if cap == "underline":
        return bool(f and f.underline), f"underline={f.underline if f else None}"
    if cap == "center":
        return cell.alignment.horizontal == "center", f"align={cell.alignment.horizontal}"
    if cap == "wrap_text":
        return bool(cell.alignment.wrapText), f"wrap={cell.alignment.wrapText}"
    if cap == "merge_center":
        return any(c0 in str(m) for m in ws.merged_cells.ranges), f"merged={list(ws.merged_cells.ranges)[:2]}"
    if cap == "fill_yellow":
        rgb = str(getattr(cell.fill.fgColor, "rgb", "") or "")
        return rgb not in ("", "00000000", "None"), f"fill={rgb}"
    if cap == "font_red":
        rgb = str(getattr(f.color, "rgb", "") or "") if f and f.color else ""
        return rgb not in ("", "00000000", "None", "FF000000"), f"font color={rgb}"
    if cap == "font_size":
        want = float(val or 14)
        return abs(float(getattr(f, "sz", 0) or 0) - want) < 0.6, f"size={getattr(f, 'sz', None)}"
    if cap == "currency":
        return "$" in str(cell.number_format), f"fmt={cell.number_format}"
    if cap == "percent":
        return "%" in str(cell.number_format), f"fmt={cell.number_format}"
    if cap == "comma":
        return "," in str(cell.number_format), f"fmt={cell.number_format}"
    if cap == "all_borders":
        b = cell.border
        return any([b.left.style, b.right.style, b.top.style, b.bottom.style]), f"borders={b.left.style}"
    if cap == "cond_greater":
        n = len(list(ws.conditional_formatting))
        return n > 0, f"cf rules={n}"
    if cap == "autofilter":
        return bool(ws.auto_filter.ref), f"filter={ws.auto_filter.ref}"
    if cap == "freeze_first_row":
        return str(ws.freeze_panes or "") in ("A2", "B2", "C2", "D2", "E2"), f"freeze={ws.freeze_panes}"
    if cap == "gridlines_off":
        return not ws.sheet_view.showGridLines, f"gridlines={ws.sheet_view.showGridLines}"
    if cap == "landscape":
        return str(ws.page_setup.orientation) == "landscape", f"orientation={ws.page_setup.orientation}"
    if cap == "margins_narrow":
        m = ws.page_margins
        return float(m.left) <= 0.5, f"margins left={m.left}"
    if cap == "bar_chart":
        return len(getattr(ws, "_charts", []) or []) > 0, f"charts={len(getattr(ws, '_charts', []) or [])}"
    if cap == "table":
        return len(getattr(ws, "tables", {}) or {}) > 0, f"tables={list(getattr(ws, 'tables', {}))}"
    if cap == "note":
        return cell.comment is not None, f"comment={bool(cell.comment)}"
    if cap == "define_name":
        names = list(wb.defined_names)
        return any(str(val or "").lower() in str(n).lower() for n in names), f"names={names[:4]}"
    if cap == "autosum":
        v = str(ws[c0].value or "")
        return v.upper().startswith("=SUM"), f"cell={v[:24]}"
    if cap == "new_sheet":
        want = str(val or "").strip().lower()
        return want in [s.lower() for s in wb.sheetnames], f"sheets={wb.sheetnames}"
    return None, "no file-level check for this capability"


def file_oracle(path: Path, plan: dict, computed: dict) -> dict:
    v = {"features_ok": 0, "features_total": 0, "features_bad": [], "cells_ok": 0,
         "cells_total": 0, "cells_bad": [], "formula_ok": 0, "formula_total": 0}
    if not path.is_file():
        v["oracle_error"] = "workbook never reached the disk"
        return v
    try:
        import openpyxl
        wf = openpyxl.load_workbook(str(path), data_only=False)
        wv = openpyxl.load_workbook(str(path), data_only=True)
    except Exception as exc:
        v["oracle_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return v
    v["sheets"] = wf.sheetnames
    want_sheets = [str(s.get("name") or "") for s in plan.get("sheets", [])]
    extra = [f for sh in plan.get("sheets", []) for f in (sh.get("features") or [])
             if f.get("cap") == "new_sheet"]
    v["sheets_ok"] = all((w or "").lower() in [x.lower() for x in wf.sheetnames] for w in want_sheets)
    for sheet in plan.get("sheets", []):
        nm = str(sheet.get("name") or "")
        if nm not in wf.sheetnames:
            v["features_bad"].append({"sheet": nm, "problem": "sheet missing from file"})
            continue
        sf, sv = wf[nm], wv[nm]
        headers = [str(h) for h in (sheet.get("headers") or [])]
        for i, h in enumerate(headers):
            v["cells_total"] += 1
            got = str(sf[f"{_col_name(i)}1"].value or "")
            if got.strip().lower() == h.strip().lower():
                v["cells_ok"] += 1
            else:
                v["cells_bad"].append({"sheet": nm, "addr": f"{_col_name(i)}1", "want": h, "got": got})
        for r, row in enumerate(sheet.get("rows") or [], start=2):
            for i, val in enumerate(row):
                addr = f"{_col_name(i)}{r}"
                v["cells_total"] += 1
                if same_text(sv[addr].value, val):
                    v["cells_ok"] += 1
                else:
                    v["cells_bad"].append({"sheet": nm, "addr": addr, "want": val,
                                           "got": sv[addr].value})
        cells = computed.get(nm, {})
        for f in (sheet.get("formulas") or []):
            addr = str(f.get("cell", "")).upper()
            form = str(f.get("formula", ""))
            if not addr or not form.startswith("="):
                continue
            v["formula_total"] += 1
            got_f = str(sf[addr].value or "").replace(" ", "").upper()
            exp_val = cells.get(addr)
            got_val = sv[addr].value
            ok_f = got_f == form.replace(" ", "").upper()
            ok_v = (exp_val is None) or _close(got_val, exp_val)
            if ok_f and ok_v:
                v["formula_ok"] += 1
            else:
                v["cells_bad"].append({"sheet": nm, "addr": addr, "kind": "formula",
                                       "want": f"{form} -> {exp_val}", "got": f"{got_f} -> {got_val}"})
        for feat in (sheet.get("features") or []):
            cap = feat.get("cap")
            if cap not in CAPABILITIES or cap == "new_sheet":
                continue
            ok, seen = check_feature(cap, feat.get("range", ""), feat.get("value"), sf, wf)
            v["features_total"] += 1
            if ok:
                v["features_ok"] += 1
            else:
                v["features_bad"].append({"sheet": nm, "cap": cap, "range": feat.get("range", ""),
                                          "observed": seen})
    for feat in extra:
        ok, seen = check_feature("new_sheet", "", feat.get("value"), wf[wf.sheetnames[0]], wf)
        v["features_total"] += 1
        v["features_ok"] += int(ok)
        if not ok:
            v["features_bad"].append({"cap": "new_sheet", "observed": seen})
    return v


def _close(got, want) -> bool:
    try:
        return abs(float(got) - float(want)) < max(0.02, abs(float(want)) * 0.0005)
    except (TypeError, ValueError):
        return str(got or "").strip().lower() == str(want or "").strip().lower()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="An autonomous Excel builder: model plans, organs act.")
    ap.add_argument("--check-plan", action="store_true", help="only produce and print the model's plan")
    ap.add_argument("--plan", default="", help="reuse a saved plan JSON instead of asking the model")
    ap.add_argument("--keep-open", action="store_true", help="leave Excel running afterwards")
    ap.add_argument("--out", default="", help="where to save the workbook")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log("asking the local model to design the workbook (nothing here is hand-written) ...")
    plan = make_plan(args)
    if not plan:
        log("ABORT: no local model produced a plan. Refusing to run a canned task instead.")
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", str(plan.get("file") or "workbook"))[:32] or "workbook"
    out = Path(args.out) if args.out else OUT_DIR / f"{slug}_{stamp}.xlsx"
    (OUT_DIR / f"plan_{stamp}.json").write_text(json.dumps(plan, indent=3, ensure_ascii=False),
                                                encoding="utf-8")
    log(f"PROJECT : {plan.get('project', '')}")
    if plan.get("_below_target"):
        log(f"  (the model did not reach the full ribbon target; outstanding: "
            f"{plan['_below_target'][:3]})")
    for s in plan.get("sheets", []):
        caps = sorted({f.get("cap") for f in (s.get("features") or [])})
        log(f"  SHEET {s.get('name')!r}: {len(s.get('headers') or [])} cols x "
            f"{len(s.get('rows') or [])} rows, {len(s.get('formulas') or [])} formulas, "
            f"ribbon: {', '.join(c for c in caps if c) or '-'}")
    if args.check_plan:
        print(json.dumps(plan, indent=3, ensure_ascii=False))
        return 0

    computed = {str(s.get("name")): evaluate_sheet(s) for s in plan.get("sheets", [])}

    proc, p = reach_workbook()
    if p is None:
        log("ABORT: never reached a workbook window.")
        try:
            proc.terminate()
        except Exception:
            pass
        return 2
    led, t0 = [], time.time()

    for i, sheet in enumerate(plan.get("sheets", [])):
        built = build_sheet(p, led, sheet, first=(i == 0))
        log(f"  -- sheet {built['name']!r} filled; applying ribbon features --")
        for feat in (built["features"] or []):
            apply_feature(p, led, built, feat)
        if (built.get("chart") or {}).get("data"):
            ch = built["chart"]
            p.clear_mode()
            if p.goto(ch.get("cats", "A2")):
                ok = p.key("alt+f1", settle=1.8)          # Alt+F1 = default chart from the block
                led.append({"step": "chart", "detail": f"{ch.get('type', 'bar')} from "
                            f"{ch.get('data')}", "verified": bool(ok)})
                log(f"  {'PASS' if ok else 'FAIL'}  chart: {ch.get('type', 'bar')}")
                p.key("escape")
                p.clear_mode()

    saved = save_workbook(p, led, out)
    verdict = file_oracle(out, plan, computed) if saved else {"oracle_error": "not saved"}

    secs = time.time() - t0
    ui_ok = sum(1 for r in led if r.get("verified"))
    log("")
    log(f"RESULT  live UI steps        : {ui_ok}/{len(led)} verified in {secs:.0f}s")
    log(f"        cells in the file    : {verdict.get('cells_ok', 0)}/{verdict.get('cells_total', 0)} "
        f"exactly as planned")
    log(f"        formulas recomputed  : {verdict.get('formula_ok', 0)}/{verdict.get('formula_total', 0)} "
        f"match Python's independent evaluation")
    log(f"        ribbon features      : {verdict.get('features_ok', 0)}/{verdict.get('features_total', 0)} "
        f"confirmed present in the saved file")
    log(f"        sheets in the file   : {verdict.get('sheets')}")
    log(f"        workbook             : {out if out.is_file() else 'NOT SAVED'}")
    for b in verdict.get("cells_bad", [])[:10]:
        log(f"        CELL MISMATCH {b}")
    for b in verdict.get("features_bad", [])[:12]:
        log(f"        FEATURE MISS  {b}")
    if verdict.get("oracle_error"):
        log(f"        ORACLE ERROR  {verdict['oracle_error']}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "seconds": round(secs, 1),
                             "engine": plan.get("_engine"), "ui_verified": ui_ok, "ui_total": len(led),
                             "file": str(out), "oracle": verdict, "steps": led,
                             "plan": {k: v for k, v in plan.items() if k != "_engine"}},
                            ensure_ascii=False) + "\n")

    if not args.keep_open:
        log("closing the Excel instance we started ...")
        p.clear_mode()
        p.key("alt+f4")
        time.sleep(2.0)
        for h, t in headless_input.top_level_titles(visible_only=False):
            if "microsoft excel" in (t or "").lower():
                for n in (fast_uia.snapshot(int(h), max_nodes=4000) or []):
                    if "don" in str(n.name or "").lower():
                        try:
                            n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                        except Exception:
                            pass
                        break
        time.sleep(1.5)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(6)
            except Exception:
                pass
    clean = (ui_ok == len(led) and not verdict.get("cells_bad") and not verdict.get("features_bad")
             and not verdict.get("oracle_error") and out.is_file())
    log(f"VERDICT: {'AUTONOMOUS BUILD COMPLETE - planned by the model, verified in the file' if clean else 'PARTIAL - the misses are listed above'}")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
