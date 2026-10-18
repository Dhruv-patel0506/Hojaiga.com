"""
harvest.rag_feed -- WORKFLOW KNOWLEDGE for the RAG from open datasets and documentation, in our own structure.

The RAG should know HOW PEOPLE GET THINGS DONE in many programs and sites before it ever meets one: which control, which key, in what order, what follows. Three sources of that, all permissively licensed,
all read as TEXT only (no pictures are downloaded):

    agentnet    gui-wm/agentnet-success-v1 (Apache-2.0): desktop workflows by program (browser, image editor, office suite, media player, code editor): an instruction and the ordered steps
                that completed it, each step with the control it landed on and the keys it pressed.
    mind2web    osunlp/Multimodal-Mind2Web (text columns only): web tasks on real sites: task and the ordered '[element] label -> CLICK / TYPE / SELECT' steps.
    repos       a list of documentation repositories (data file, licence recorded per entry): headings, numbered / imperative steps, key combinations.

What is stored is a DERIVED structure, not a copy of anyone's prose: each step becomes a logic chain (precondition -> action {click control | press keys | type} -> expected -> if blocked) written
through rag.logic_chains into the stores that hold that kind of knowledge, filed under the program (desktop_app) or the site (website) with the source and licence on the entry. Task titles are shortened;
fall-back sentences are never copied from the source.

    python -m core_organs.harvest.rag_feed agentnet --tasks-per-app 80
    python -m core_organs.harvest.rag_feed mind2web --tasks 300
    python -m core_organs.harvest.rag_feed repos --file D:/new_automation/data/feeds/repos.json
"""
from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core_organs.rag import logic_chains as LC

AGENTNET = "gui-wm/agentnet-success-v1"
MIND2WEB = "osunlp/Multimodal-Mind2Web"
PROGRAM = {"chrome": "Google Chrome", "gimp": "GIMP", "libreoffice_calc": "LibreOffice Calc", "libreoffice_writer": "LibreOffice Writer", "libreoffice_impress": "LibreOffice Impress",
           "vlc": "VLC media player", "vs_code": "Visual Studio Code"}
KEYNAME = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "command": "Cmd", "enter": "Enter", "return": "Enter", "esc": "Esc", "escape": "Esc", "tab": "Tab",
           "space": "Space", "delete": "Delete", "backspace": "Backspace", "pageup": "PageUp", "pagedown": "PageDown", "home": "Home", "end": "End", "up": "Up", "down": "Down", "left": "Left", "right": "Right"}


def _key_label(k: str) -> str:
    k = k.strip().strip("'\"").lower()
    return KEYNAME.get(k) or (k.upper() if len(k) == 1 else k.upper() if re.fullmatch(r"f\d{1,2}", k) else k.title())


def parse_pyautogui(code: str) -> Dict[str, Any]:
    """What a recorded pyautogui snippet DID: {'kind': click | double_click | right_click | hotkey | type | press | scroll | other, 'keys': 'Ctrl+S', 'text': '...'}"""
    c = code or ""
    m = re.search(r"hotkey\(([^)]*)\)", c)
    if m:
        ks = [_key_label(x) for x in m.group(1).split(",") if x.strip()]
        return {"kind": "hotkey", "keys": "+".join(ks), "text": ""}
    m = re.search(r"(?:typewrite|write)\(\s*(?:message\s*=\s*)?(['\"])(.*?)\1", c, re.S)
    if m:
        return {"kind": "type", "keys": "", "text": m.group(2)[:60]}
    m = re.search(r"press\(\s*(['\"])(.*?)\1", c)
    if m:
        return {"kind": "press", "keys": _key_label(m.group(2)), "text": ""}
    for pat, kind in (("doubleClick", "double_click"), ("rightClick", "right_click"), ("click", "click"), ("scroll", "scroll")):
        if pat in c:
            return {"kind": kind, "keys": "", "text": ""}
    return {"kind": "other", "keys": "", "text": ""}


def target_name(action_target: Any, action_nl: str) -> str:
    """The control a step landed on: the accessibility name when the recording has one, else a quoted name in the step's own sentence."""
    with contextlib.suppress(Exception):
        t = json.loads(action_target) if isinstance(action_target, str) else (action_target or {})
        n = str((t or {}).get("name") or "").strip()
        if n and len(n) <= 60:
            return n
    m = re.search(r"[\"“‘']([^\"”’']{2,40})[\"”’']", action_nl or "")
    return m.group(1).strip() if m else ""


def steps_from_trace(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordered recorded steps -> the step dicts the chain builder reads: {text, names, keys}. Typed text is dropped (it is the person's content, not the workflow)."""
    steps: List[Dict[str, Any]] = []
    for r in rows:
        act = parse_pyautogui(str(r.get("action_pyautogui") or ""))
        nm = target_name(r.get("action_target"), str(r.get("action_nl") or ""))
        text = str(r.get("action_nl") or "").strip()
        if act["kind"] == "type":
            text = "Type the text into the active field." if not nm else f"Type into {nm}."
        if not text:
            continue
        steps.append({"text": text[:200], "names": [nm] if nm and act["kind"] in ("click", "double_click", "right_click") else [], "keys": [act["keys"]] if act["keys"] else [], "imgs": [], "verbatim": True})
    return steps


def mind2web_steps(reprs: Any) -> List[Dict[str, Any]]:
    """'[button] Search -> CLICK', '[textbox] From -> TYPE: ...', '[select] Sort -> SELECT: ...' -> steps. The typed / chosen value is not kept."""
    import ast
    items = reprs
    if isinstance(reprs, str):
        with contextlib.suppress(Exception):
            items = ast.literal_eval(reprs)                                        # a Python-style list of strings
    out: List[Dict[str, Any]] = []
    for it in items or []:
        m = re.match(r"\[(\w+)\]\s*(.*?)\s*->\s*(CLICK|TYPE|SELECT|HOVER|ENTER)", str(it))
        if not m:
            continue
        tag, label, op = m.group(1), m.group(2).strip(), m.group(3)
        label = re.sub(r"\s+", " ", label)[:60]
        verb = {"CLICK": "Click", "TYPE": "Type into", "SELECT": "Choose from", "HOVER": "Point at", "ENTER": "Press Enter in"}[op]
        out.append({"text": f"{verb} the {label or tag} {tag}.", "names": [label] if label else [], "keys": ["Enter"] if op == "ENTER" else [], "imgs": []})
    return out


def write_workflow(rag: Any, app_key: str, app_name: str, title: str, steps: Sequence[Dict[str, Any]], source: str) -> Dict[str, int]:
    """One workflow -> chains -> the stores. The source (dataset or repo, with its licence) goes on the entry."""
    if len(steps) < 2:
        return {}
    chains = LC.build_chains(steps, [[] for _ in steps], "")
    for c in chains:
        c["fallback"] = []                                                   # never copy a source's troubleshooting prose
    return LC.write(rag, app_key, app_name, chains, [[] for _ in steps], source, title[:110])


# ------------------------------------------------------------------------------------------------------------------------------------------------ sources
def _hf():
    from huggingface_hub import HfFileSystem
    import pyarrow.parquet as pq
    return HfFileSystem(), pq


def feed_agentnet(rag: Any, tasks_per_app: int = 80, shards_per_app: int = 3, log: Any = print) -> Dict[str, Any]:
    from core_organs.rag import domains as DM
    fs, pq = _hf()
    files = fs.ls(f"datasets/{AGENTNET}/data", detail=False)
    rep: Dict[str, Any] = {"source": AGENTNET + " (apache-2.0)", "apps": {}}
    for grp, name in PROGRAM.items():
        shards = sorted(f for f in files if f"/{grp}-part-" in f)
        if not shards:
            continue
        pick = [shards[int(i * len(shards) / max(shards_per_app, 1))] for i in range(min(shards_per_app, len(shards)))]
        key = DM.key_for(DM.DESKTOP, name)
        DM.register(rag, key, DM.DESKTOP, {"why": f"workflows from {AGENTNET}"})
        done_tasks, n_steps, tot = set(), 0, {"procedures": 0, "edges": 0, "hotkeys": 0}
        for sh in pick:
            if len(done_tasks) >= tasks_per_app:
                break
            try:
                tb = pq.ParquetFile(fs.open(sh)).read(columns=["task_id", "instruction", "step", "action_nl", "action_pyautogui", "action_target", "transition_role", "judged_outcome"]).to_pylist()
            except Exception as exc:
                log(f"[feed] {sh.split('/')[-1]}: {type(exc).__name__}")
                continue
            by: Dict[str, List[Dict[str, Any]]] = {}
            for r in tb:
                if r.get("transition_role") == "main" and r.get("judged_outcome") in ("success", None):
                    by.setdefault(str(r["task_id"]), []).append(r)
            for tid, rows in by.items():
                if tid in done_tasks or len(done_tasks) >= tasks_per_app:
                    continue
                rows.sort(key=lambda r: r.get("step") or 0)
                steps = steps_from_trace(rows)
                w = write_workflow(rag, key, name, str(rows[0].get("instruction") or "")[:110], steps, f"hf:{AGENTNET}")
                if w:
                    done_tasks.add(tid)
                    n_steps += len(steps)
                    for k in tot:
                        tot[k] += w.get(k, 0)
        rep["apps"][name] = {"key": key, "tasks": len(done_tasks), "steps": n_steps, **tot}
        log(f"[feed] {name}: {rep['apps'][name]}")
    return rep


def feed_mind2web(rag: Any, tasks: int = 300, shards: int = 6, log: Any = print) -> Dict[str, Any]:
    from core_organs.rag import domains as DM
    fs, pq = _hf()
    files = sorted(fs.ls(f"datasets/{MIND2WEB}/data", detail=False))
    pick = [files[int(i * len(files) / max(shards, 1))] for i in range(min(shards, len(files)))]
    seen, rep = set(), {"source": MIND2WEB + " (text columns; see the dataset card for its licence terms)", "tasks": 0, "sites": {}}
    for sh in pick:
        if rep["tasks"] >= tasks:
            break
        try:
            pf = pq.ParquetFile(fs.open(sh))
            tb = pf.read(columns=["annotation_id", "website", "domain", "confirmed_task", "action_reprs"]).to_pylist()
        except Exception as exc:
            log(f"[feed] {sh.split('/')[-1]}: {type(exc).__name__}: {str(exc)[:60]}")
            continue
        for r in tb:
            aid = r["annotation_id"]
            if aid in seen or rep["tasks"] >= tasks:
                continue
            seen.add(aid)
            steps = mind2web_steps(r.get("action_reprs"))
            site = re.sub(r"[^a-z0-9]+", "", str(r.get("website") or "").lower())
            if not site or len(steps) < 2:
                continue
            host = f"{site}.com"
            key = DM.key_for(DM.WEBSITE, f"https://www.{host}")
            DM.register(rag, key, DM.WEBSITE, {"why": f"web workflows from {MIND2WEB}"})
            w = write_workflow(rag, key, host, str(r.get("confirmed_task") or "")[:110], steps, f"hf:{MIND2WEB}")
            if w:
                rep["tasks"] += 1
                rep["sites"][host] = rep["sites"].get(host, 0) + 1
    log(f"[feed] mind2web: {rep['tasks']} tasks over {len(rep['sites'])} sites")
    return rep


def md_steps(text: str) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Documentation (markdown or reStructuredText) -> [(heading, steps)]: the numbered / imperative lines under each heading, with key combinations and quoted control names found in them."""
    imperative = re.compile(r"(?:^|[,:;]\s*|\bthen\s+)(?:click|select|choose|open|press|go to|navigate|use|type|enter|drag|right-click|double-click|hold|toggle|set|add|insert|save|export)\b", re.I)
    text = re.sub(r"^(.+)" + chr(10) + r"([=\-~^]{3,})[ \t]*$", chr(35) + r" \1", text, flags=re.M)                    # reStructuredText headings (a line underlined with = - ~ ^)
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    head, steps = "", []
    for ln in text.splitlines():
        h = re.match(r"^\s*#{1,4}\s+(.+?)\s*#*\s*$", ln)
        if h:
            if len(steps) >= 2:
                out.append((head, steps))
            head, steps = re.sub(r"[*_`\[\]]", "", h.group(1))[:90], []
            continue
        s = re.sub(r"^\s*(?:\d+[.)]|[-*+])\s+", "", ln).strip()
        s = re.sub(r"\*\*|__|`", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
        if 14 <= len(s) <= 300 and (imperative.search(s) or LC.KEY_RX.search(s)):
            names = [a or b for a, b in re.findall(r"[\"“‘]([^\"”’]{2,32})[\"”’]|\*\*([^*]{2,32})\*\*", ln)]
            steps.append({"text": s[:200], "names": names[:3], "keys": [k if isinstance(k, str) else k[0] for k in LC.KEY_RX.findall(s)][:2], "imgs": []})
    if len(steps) >= 2:
        out.append((head, steps))
    return out


def feed_repos(rag: Any, repos_file: str, max_files: int = 25, log: Any = print) -> Dict[str, Any]:
    import requests
    from core_organs.rag import domains as DM
    cfg = json.load(open(repos_file, encoding="utf-8"))
    rep: Dict[str, Any] = {"repos": {}}
    for r in cfg:
        repo, app, lic = r["repo"], r["app"], r.get("license", "")
        try:
            info = requests.get(f"https://api.github.com/repos/{repo}", timeout=20).json()
            branch = info.get("default_branch", "main")
            tree = requests.get(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1", timeout=40).json().get("tree", [])
        except Exception as exc:
            rep["repos"][repo] = {"error": f"{type(exc).__name__}"}
            continue
        pats = [re.compile(p, re.I) for p in r.get("paths", [r"\.(md|rst)$"])]
        files = [t["path"] for t in tree if t.get("type") == "blob" and any(p.search(t["path"]) for p in pats)][:max_files]
        key = DM.key_for(DM.DESKTOP, app)
        DM.register(rag, key, DM.DESKTOP, {"why": f"documentation in {repo}"})
        n_w = n_s = 0
        for path in files:
            try:
                txt = requests.get(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}", timeout=30).text
            except Exception:
                continue
            for head, steps in md_steps(txt)[:6]:
                if write_workflow(rag, key, app, head or path.split("/")[-1], steps, f"github:{repo}/{path} ({lic or info.get('license', {}) and info['license'].get('spdx_id', '')})"):
                    n_w += 1
                    n_s += len(steps)
        rep["repos"][repo] = {"app": app, "files": len(files), "workflows": n_w, "steps": n_s, "license": lic}
        log(f"[feed] {repo}: {rep['repos'][repo]}")
    return rep


def feed_browser(rag: Any, engine: str = "google", apps: int = 12, minutes: float = 90.0, log: Any = print) -> Dict[str, Any]:
    """Programs picked by category from the Start menu (so a short run still covers many kinds of software), each looked up in a throw-away browser: the engine's synthesized answer, its illustrated tutorials,
    the Images and Videos tabs. ONE session, no account. When the engine answers with a challenge instead of results (a CAPTCHA), that engine is dropped for the rest of the run and the next engine is used;
    the challenge is never answered."""
    from core_organs.harvest import catalogue as C, search_browser as SBR
    from core_organs.rag import domains as DM
    from core_organs.professor.adapters.cdp import CdpBrowser  # noqa: F401  (imported so a missing browser fails here, not mid-run)
    names = [e["name"] for e in C.select(limit=apps, per_category=3)]
    t0 = time.time()
    rep: Dict[str, Any] = {"engine_start": engine, "apps": {}, "dropped_engines": []}
    cur = engine
    for nm in names:
        if (time.time() - t0) / 60.0 > minutes:
            break
        base = re.sub(r"\s+(?:v?\d[\d.]*|\(.*?\))\s*$", "", nm).strip() or nm
        key = DM.key_for(DM.DESKTOP, base)
        DM.register(rag, key, DM.DESKTOP, {"why": "learned from search-engine tutorials in a browser"})
        try:
            r = SBR.run([base], max_tutorials=2, log=log, app_keys={base: key}, engine=cur)
            row = (r.get("apps") or [{}])[0]
        except Exception as exc:
            row = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
        if SBR.BLOCKED.get("google") and cur == "google":
            rep["dropped_engines"].append("google")
            cur = "bing"
            log("[feed] google answered with a challenge: dropped for this run, continuing with bing")
        rep["apps"][base] = {k: row.get(k) for k in ("tutorials", "steps", "chains", "procedures", "hotkeys", "pairs", "ai_summaries", "ai_chains", "error")}
        log(f"[feed] {base}: {rep['apps'][base]}")
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    from core_organs import rag as R
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["agentnet", "mind2web", "repos", "browser", "all"])
    ap.add_argument("--engine", default="google")
    ap.add_argument("--apps", type=int, default=12)
    ap.add_argument("--minutes", type=float, default=90.0)
    ap.add_argument("--tasks-per-app", type=int, default=80)
    ap.add_argument("--tasks", type=int, default=300)
    ap.add_argument("--shards", type=int, default=15)
    ap.add_argument("--file", default=r"D:\new_automation\data\feeds\repos.json")
    a = ap.parse_args(argv)
    rag = R.get_rag()
    out: Dict[str, Any] = {}
    t0 = time.time()
    if a.what in ("agentnet", "all"):
        out["agentnet"] = feed_agentnet(rag, a.tasks_per_app, a.shards)
    if a.what in ("mind2web", "all"):
        out["mind2web"] = feed_mind2web(rag, a.tasks)
    if a.what in ("repos", "all"):
        out["repos"] = feed_repos(rag, a.file)
    if a.what == "browser":
        out["browser"] = feed_browser(rag, a.engine, a.apps, a.minutes)
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
