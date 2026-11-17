"""Hojaiga 4B dataset builder + trainer launcher (v2, Oct-29).

Why v2: the first build put 544,590 rows into training, but most of them taught template copies, not skills.
  - 386k Quick, Draw! rows had no strokes in the answer.
  - Every non-click job was wrapped as "type it into element #1", with a made-up "#1 window '... Context'" added to the prompt.
  - Question-answer sets became "click the button named after the question".
  - The plan rows had no plan in them.
  - Most `verified_by` labels were stamped on, not earned.
  - The best sources gave 0 rows, and the WebSRC images were lost: they are base64 text, which the old reader skipped.

This version:
  - Each source has its own converter, keeping that job's real answer format and the EXACT system prompts Hojaiga sends at run time.
    The prompts are read from loop_first / hojaiga_run / gestures / app_qa, so they stay in step with the code.
  - Every row carries an honest `verified_by`, and each source has a cap (`CAPS`, overridable with HOJAIGA_CAP_<SOURCE>=n).
  - One 95/5 split by `split_group`; the eval set is capped and spread across the jobs.
  - Every row passes train_qlora's own job-aware check before it is written.
  - A fresh run folder. train_qlora resumes it by itself: same folder, same max_steps.

Usage (Python 3.13 with the training packages):
    python train_full_uncapped_4b.py build      # shards -> train.jsonl / eval.jsonl + data_summary.json + samples.md
    python train_full_uncapped_4b.py sample     # 3 rows per job printed (no build)
    python train_full_uncapped_4b.py train      # start or resume training on the built set
    python train_full_uncapped_4b.py dry        # 3 training steps on a tiny slice (memory/speed check)
"""
import ast
import base64
import collections
import glob
import hashlib
import io
import json
import os
import pathlib
import random
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SEED = 100
ROOT = pathlib.Path(r"D:\new_automation")
ALL_CODES = ROOT / "All codes"
INBOX = ROOT / "data" / "inbox"
HARVEST = ROOT / "data" / "ai_root" / "harvest"          # train_qlora's image root: image paths are relative to it
TRAIN_DIR = HARVEST / "training"
OUT = TRAIN_DIR / "hojaiga_4b_v2"
SHARDS = OUT / "shards"
IMG_DIR_REL = "hf_unpacked_images_v2"
IMG_DIR = HARVEST / IMG_DIR_REL
MODEL_4B = "Qwen/Qwen3-VL-4B-Instruct"
for d in (OUT, SHARDS, IMG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# rows per source. Real, proven data is kept whole; public sets and generated sets are capped so none dominates (no job above ~25 %)
CAPS = {"real_ui": 0, "decide_web": 0, "safety_traps": 2000, "waveui_point": 0, "websrc": 15000, "squad": 8000, "vba_teach": 6000,
        "agentnet_plan": 8000, "mind2web_plan": 6000, "odyssey_route": 2000, "quickdraw": 3000, "office_exact": 4000}
for k in CAPS:
    CAPS[k] = int(os.environ.get(f"HOJAIGA_CAP_{k.upper()}", CAPS[k]))
EVAL_MAX = 3000


# ---- the run-time prompts, read from the code -------------------------------------------------------------------------------------------------------
def _const(path: pathlib.Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{name} not found in {path}")


CO = ALL_CODES / "core_organs"
STEP_SYSTEM = _const(CO / "loop_first.py", "STEP_SYSTEM")
ITEMS_SYSTEM = _const(CO / "hojaiga_run.py", "ITEMS_SYSTEM")
CHECK_SYSTEM = _const(CO / "hojaiga_run.py", "CHECK_SYSTEM")
DESCRIBE_SCREEN = _const(CO / "hojaiga_run.py", "DESCRIBE_SCREEN")
SKETCH_SYSTEM = _const(CO / "professor" / "gestures.py", "SKETCH_SYSTEM")
TEACH_SYSTEM = _const(CO / "mind" / "app_qa.py", "SYSTEM")
SCREEN_QA_SYSTEM = ("You answer a question about the screenshot you are shown, from what is visible on it. Reply with the answer only, as short as the screen states it.")
POINT_SYSTEM = ("You find one control on a screenshot. Reply JSON only: {\"point\": [x, y]} with x and y from 0 to 1000 across the picture's width and height, "
                "at the centre of the control the request describes.")
ROUTE_APPS_SYSTEM = ("You plan which apps a multi-app task needs, in the order it uses them. Reply JSON only: {\"parts\": [{\"app\": \"...\", \"does\": \"...\"}]}.")


def rec(job, system, user_text, answer, verified_by, group, source, image=None, app_key=""):
    content = ([{"type": "image", "image": image}] if image else []) + [{"type": "text", "text": user_text}]
    return {"messages": [{"role": "system", "content": [{"type": "text", "text": system}]},
                         {"role": "user", "content": content},
                         {"role": "assistant", "content": [{"type": "text", "text": answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)}]}],
            "meta": {"job": job, "source": source, "verified_by": verified_by, "split_group": group, "app_key": app_key, "ui_frames": True, "lang": "en"}}


def save_img(data: bytes, name: str, max_side: int = 1280) -> str:
    from PIL import Image
    rel = f"{IMG_DIR_REL}/{name}.jpg"
    path = HARVEST / rel
    if not (path.exists() and path.stat().st_size > 400):
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(path, "JPEG", quality=88)
    return rel


# ---- sources ------------------------------------------------------------------------------------------------------------------------------------------
def src_real_ui():
    """Hojaiga's own harvested grounding pairs with real screenshots (local UIA recorder, web DOM, Wave UI): kept as they are, job = ground."""
    seen = set()
    for name in ("ui_training_dataset_v2_all.jsonl", "ui_training_dataset.jsonl"):
        for line in open(TRAIN_DIR / name, encoding="utf-8", errors="ignore"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            key = hashlib.md5(json.dumps(r["messages"][1:], sort_keys=True).encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            m = r.setdefault("meta", {})
            src = m.get("source") or "harvest"
            m.update(job="ground", verified_by={"local_uia": "uia_name", "web_dom": "dom", "web_steps": "dom", "hf_waveui": "public_label"}.get(src, "harvest"),
                     split_group=f"ui::{m.get('app_key', '')}::{m.get('uia_name') or m.get('video_id') or key[:8]}", source=src)
            yield r


def src_decide_web():
    """The round-3 decision rows (real elements from real sites + rule-made confirm / replan cases): one action, confirm or replan. job = decide."""
    seen = set()
    for p in (TRAIN_DIR / "runs" / "run_20261027_mind" / "train.jsonl", TRAIN_DIR / "runs" / "run_20261027_mind" / "eval.jsonl", TRAIN_DIR / "web_action_rows.jsonl"):
        if not p.exists():
            continue
        for line in open(p, encoding="utf-8", errors="ignore"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            key = hashlib.md5(json.dumps(r["messages"][1:], sort_keys=True).encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            m = r.setdefault("meta", {})
            src = m.get("source") or "web-explore"
            m.update(job="decide", verified_by="dom" if src == "web-explore" else "rule", source=src,
                     split_group=f"decide::{m.get('app_key') or m.get('site') or ''}::{m.get('goal', '')[:40] or key[:8]}")
            yield r


def src_safety_traps():
    """Rule-labelled 'do the safe one, not the destructive one' rows (text only). Rows whose target is not in their own element list are dropped by the check."""
    p = TRAIN_DIR / "master_4b_seed100_pipeline" / "synthetic_4modality_and_traps_4000.jsonl"
    if not p.exists():
        return
    for i, line in enumerate(open(p, encoding="utf-8", errors="ignore")):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        r["meta"] = {"job": "decide", "verified_by": "rule", "source": "safety_traps", "split_group": f"traps::{i // 4}", "ui_frames": True}
        yield r


def src_waveui_point():
    """Wave UI screens: 'find the control' -> its centre as 0-1000 coordinates (the ScreenSpot style of grounding)."""
    import pyarrow.parquet as pq
    for f in sorted(glob.glob(str(INBOX / "10_wave_ui_25k" / "data" / "*.parquet"))):
        for i, it in enumerate(pq.read_table(f).to_pylist()):
            img, bbox, res = it.get("image"), it.get("bbox"), it.get("resolution")
            if not (img and bbox and res and (it.get("name") or it.get("description"))):
                continue
            data = img.get("bytes") if isinstance(img, dict) else img
            if not data:
                continue
            w, h = float(res[0]), float(res[1])
            x, y = (bbox[0] + bbox[2]) / 2 / w * 1000, (bbox[1] + bbox[3]) / 2 / h * 1000
            name, purpose = str(it.get("name") or "").strip(), str(it.get("purpose") or "").strip()
            ask = (name + (f", used {purpose}" if purpose.lower().startswith("to ") else "")) if name else str(it.get("description") or "")
            yield rec("point", POINT_SYSTEM, f"Find: {ask}\nJSON:", {"point": [round(x), round(y)]}, "public_label", f"waveui::{os.path.basename(f)}::{i // 5}",
                      "waveui", save_img(data, f"waveui_{os.path.basename(f)[:12]}_{i:05d}"), it.get("platform", ""))


def src_websrc():
    """WebSRC: a real web page screenshot + a question -> the short answer read off the page (job = see)."""
    import pyarrow.parquet as pq
    for f in sorted(glob.glob(str(INBOX / "16_websrc_screenqa" / "data" / "*.parquet"))):
        for i, it in enumerate(pq.read_table(f).to_pylist()):
            q, a, img = str(it.get("question") or "").strip(), str(it.get("answer") or "").strip(), it.get("image")
            if not (q and a and img):
                continue
            data = base64.b64decode(img) if isinstance(img, str) else (img.get("bytes") if isinstance(img, dict) else img)
            pid = f"{it.get('domain', '')}_{it.get('page_id', i)}"
            yield rec("see", SCREEN_QA_SYSTEM, q, a, "public_label", f"websrc::{pid}", "websrc", save_img(data, f"websrc_{pid}"), it.get("domain", ""))


def src_squad():
    """SQuAD v2 as evidence-grounded answering (Hojaiga's teach format): the paragraph is evidence [1] (with a distractor [2] half the time); an unanswerable
    question must be 'NOT IN EVIDENCE: ...'."""
    import pyarrow.parquet as pq
    rows = pq.read_table(str(INBOX / "17_squad_v2_chartqa" / "squad_v2" / "train-00000-of-00001.parquet")).to_pylist()
    rng = random.Random(SEED)
    for i, it in enumerate(rows):
        ctx, q, ans = it["context"], it["question"].strip(), (it.get("answers") or {}).get("text") or []
        ev = [ctx]
        if rng.random() < 0.5:
            other = rows[rng.randrange(len(rows))]["context"]
            if other != ctx:
                ev.append(other)
        rng.shuffle(ev)
        n = ev.index(ctx) + 1
        evidence = "\n".join(f"[{k + 1}] {e[:900]}" for k, e in enumerate(ev))
        answer = f"{ans[0]} [{n}]" if ans else f"NOT IN EVIDENCE: the evidence does not say {q[0].lower() + q[1:].rstrip('?')}."
        yield rec("teach", TEACH_SYSTEM, f"Question: {q}\n\nEvidence:\n{evidence}", answer, "public_label", f"squad::{it.get('title', '')}::{i // 40}", "squad_v2")


def src_vba_teach():
    """Office VBA reference pages as evidence: the right page among two others (or absent: NOT IN EVIDENCE), the answer is the page's own first sentence with its citation."""
    z = INBOX / "3_1_office_vba_docs" / "VBA-Docs-main.zip"
    if not z.exists():
        return
    pages = []
    with zipfile.ZipFile(z) as zf:
        for name in zf.namelist():
            if not name.endswith(".md") or "/api/" not in name.lower():
                continue
            md = zf.read(name).decode("utf-8", "ignore")
            title = (re.search(r"^title:\s*(.+)$", md, re.M) or re.search(r"^#\s+(.+)$", md, re.M))
            body = re.sub(r"^---.*?---", "", md, flags=re.S)
            body = re.sub(r"^#.*$", "", body, flags=re.M).strip()
            first = re.split(r"(?<=[.!?])\s", re.sub(r"\s+", " ", body), maxsplit=1)[0].strip()
            if title and 30 <= len(first) <= 400:
                pages.append((title.group(1).strip().strip('"'), first, re.sub(r"\s+", " ", body)[:700], name.split("/")[2] if len(name.split("/")) > 2 else "office"))
    rng = random.Random(SEED)
    rng.shuffle(pages)
    for i, (title, first, body, app) in enumerate(pages):
        trick = rng.random() < 0.2
        others = [rng.choice(pages) for _ in range(2)]
        ev = [(o[0], o[2]) for o in others] + ([] if trick else [(title, body)])
        rng.shuffle(ev)
        evidence = "\n".join(f"[{k + 1}] {t}: {b}" for k, (t, b) in enumerate(ev))
        q = f"In {app.split('-')[0].title()}, what does {re.sub(r'\s*\(.*\)$', '', title)} do?"
        answer = f"NOT IN EVIDENCE: none of the pages describes {re.sub(r'\s*\(.*\)$', '', title)}." if trick else f"{first} [{[t for t, _ in ev].index(title) + 1}]"
        yield rec("teach", TEACH_SYSTEM, f"Question: {q}\n\nEvidence:\n{evidence}", answer, "public_label", f"vba::{app}::{i // 30}", "vba_docs", app_key=app)


_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s'\"<>|?*]+")


def _shown(text: str):
    """The planner sees paths as PATH1, PATH2 (loop_first.model_steps does this at run time)."""
    paths = {}
    for p in dict.fromkeys(_PATH.findall(text)):
        paths[p] = f"PATH{len(paths) + 1}"
        text = text.replace(p, paths[p])
    return text, paths


def _agentnet_steps(traj):
    steps = []
    for st in traj:
        v = st.get("value") or {}
        code, act = (v.get("code") or "").strip(), re.sub(r"\s+", " ", (v.get("action") or "").strip())
        if code.startswith("computer.terminate"):
            break
        target = re.split(r"(?<=[.!?])\s", act, maxsplit=1)[0]                          # 'Click on the "Carrier Deals" link in the menu to learn ...' -> 'the "Carrier Deals" link in the menu'
        target = re.sub(r"^(?:double-click|right-click|triple-click|click|tap|press|select|drag|move)\s+(?:on|at|in)?\s*", "", target, flags=re.I)
        target = re.split(r"\s+(?:to|in order to|so that|which|that will|and then|, then)\s+", target, maxsplit=1)[0].strip(" .,")[:80]
        for ln in code.splitlines():
            ln = ln.strip()
            m = re.match(r"pyautogui\.write\(message=(['\"])(.*)\1\)", ln)
            if m:
                if m.group(2):
                    steps.append({"do": "type", "text": m.group(2), "target": "", "format": ""})
                continue
            m = re.match(r"pyautogui\.(?:hotkey|press)\((.*)\)", ln)
            if m:
                keys = re.findall(r"'([^']+)'", m.group(1).split("presses")[0])
                if keys:
                    steps.append({"do": "press", "text": "+".join(keys), "target": "", "format": ""})
                continue
            if re.match(r"(?:pyautogui|computer)\.(?:click|doubleClick|rightClick|tripleClick)\(", ln):
                steps.append({"do": "click", "text": "", "target": target, "format": ""})
            elif ln.startswith("pyautogui.dragTo"):
                steps.append({"do": "select", "text": "", "target": target, "format": ""})
    return steps


def src_agentnet_plan():
    """AgentNet / OpenCUA: tasks people actually completed on Windows / macOS / Ubuntu, as Hojaiga's step plan (the real step kinds, the real typed text)."""
    for fn in ("agentnet_win_mac_18k.jsonl", "agentnet_ubuntu_5k.jsonl"):
        p = INBOX / "13_agentnet_opencua" / fn
        if not p.exists():
            continue
        for line in open(p, encoding="utf-8", errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not d.get("task_completed") or int(d.get("alignment_score") or 0) < 7:
                continue
            steps = _agentnet_steps(d.get("traj") or [])
            if not 2 <= len(steps) <= 25:
                continue
            app = re.search(r"\b(excel|word|powerpoint|chrome|edge|firefox|vs ?code|notepad|outlook|wps|photoshop|gimp|libreoffice \w+|terminal|finder|explorer)\b",
                            (d.get("actual_task") or "") + " " + d["instruction"], re.I)
            app = app.group(1).lower() if app else "the app on screen"
            shown, paths = _shown(d["instruction"])
            for s in steps:
                for pth, k in paths.items():
                    s["text"] = s["text"].replace(pth, k)
            yield rec("plan", STEP_SYSTEM.replace("APP", app), f"Instruction: \"{shown}\"\nJSON:", {"steps": steps}, "public_label", f"agentnet::{d['task_id']}", "agentnet", app_key=app)


def src_mind2web_plan():
    """Mind2Web: real web tasks and the actions people took on the real page ('[link] NFL -> CLICK', '[textbox] From -> TYPE: New York')."""
    head = re.compile(r'"website":\s*"((?:[^"\\]|\\.)*)".{0,400}?"annotation_id":\s*"((?:[^"\\]|\\.)*)",\s*"confirmed_task":\s*"((?:[^"\\]|\\.)*)",\s*"action_reprs":\s*(\[(?:[^\]"\\]|"(?:[^"\\]|\\.)*")*\])', re.S)
    def tasks_of(path):                                                       # the files are 500-600 MB (raw HTML of every step): read in chunks, keep only each task's header
        buf = ""
        with open(path, encoding="utf-8", errors="ignore") as fh:
            while True:
                chunk = fh.read(8 << 20)
                buf += chunk
                end = 0
                for m in head.finditer(buf):
                    end = m.end()
                    with_reprs = json.loads(m.group(4))
                    yield {"website": json.loads(f'"{m.group(1)}"'), "annotation_id": m.group(2), "confirmed_task": json.loads(f'"{m.group(3)}"'), "action_reprs": with_reprs}
                buf = buf[max(end, len(buf) - 200_000):]
                if not chunk:
                    break
    for f in sorted(glob.glob(str(INBOX / "12_mind2web" / "data" / "train" / "*.json")), key=os.path.getsize):
        for t in tasks_of(f):
            steps = []
            for a in t.get("action_reprs") or []:
                m = re.match(r"\s*\[(\w+)\]\s*(.*?)\s*->\s*(CLICK|TYPE|SELECT|HOVER|ENTER)(?::\s*(.*))?$", a)
                if not m:
                    continue
                role, label, op, val = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(" .")[:90], m.group(3), (m.group(4) or "").strip()
                target = f"{label} ({role})" if label else role
                steps.append({"do": {"CLICK": "click", "HOVER": "click", "ENTER": "press", "TYPE": "type", "SELECT": "select"}[op],
                              "text": val if op in ("TYPE", "SELECT") else ("enter" if op == "ENTER" else ""), "target": target, "format": ""})
            if 2 <= len(steps) <= 20:
                yield rec("plan", STEP_SYSTEM.replace("APP", "the web browser"), f"Instruction: \"{t['confirmed_task']} (on {t.get('website', 'the site')})\"\nJSON:",
                          {"steps": steps}, "public_label", f"mind2web::{t.get('annotation_id')}", "mind2web", app_key=f"web:{t.get('website', '')}")


def src_odyssey_route():
    """GUI-Odyssey: cross-app tasks -> which apps, in which order (the multi-app pattern; its phone screenshots are not used)."""
    for f in sorted(glob.glob(str(INBOX / "9_gui_odyssey" / "annotations" / "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except ValueError:
            continue
        ti = d.get("task_info") or {}
        low = str(ti.get("instruction") or "").lower()
        pos = {a: low.find(a.lower().split(" - ")[0]) for a in ti.get("app") or [] if a}
        apps = sorted((a for a, p in pos.items() if p >= 0), key=pos.get)       # in the order the task USES them (the dataset's list is not in that order)
        if len(apps) >= 2 and len(apps) == len(pos) and ti.get("instruction"):
            yield rec("route", ROUTE_APPS_SYSTEM, f"Task: {ti['instruction']}\nJSON:", {"parts": [{"app": a, "does": ""} for a in apps]}, "public_label",
                      f"odyssey::{ti.get('meta_task', '')[:40]}", "gui_odyssey")


def src_quickdraw():
    """Quick, Draw!: real human sketches the game recognised, as the drawing engine's own stroke format (0..100, at most 8 strokes, at most 24 points each)."""
    files = sorted(glob.glob(str(INBOX / "6_1_quickdraw" / "*.ndjson")))
    per = max(1, CAPS["quickdraw"] // max(1, len(files)) + 1) if CAPS["quickdraw"] else 10 ** 9
    for f in files:
        n = 0
        for line in open(f, encoding="utf-8"):
            if n >= per:
                break
            d = json.loads(line)
            if not d.get("recognized"):
                continue
            strokes = [s for s in d["drawing"] if len(s[0]) >= 2][:8]
            xs = [x for s in strokes for x in s[0]]
            ys = [y for s in strokes for y in s[1]]
            if not xs:
                continue
            side = max(max(xs) - min(xs), max(ys) - min(ys), 1)
            out = []
            for sx, sy in strokes:
                k = max(1, len(sx) // 24 + (len(sx) % 24 > 0))
                pts = list(zip(sx, sy))[::k] + ([(sx[-1], sy[-1])] if (len(sx) - 1) % k else [])
                out.append([[round(100 * (x - min(xs)) / side), round(100 * (y - min(ys)) / side)] for x, y in pts])
            n += 1
            yield rec("draw", SKETCH_SYSTEM, f"Draw: a {d['word']}\nJSON:", {"strokes": out}, "public_label", f"quickdraw::{d['word']}::{n // 10}", "quickdraw")


def src_office_exact():
    """Exact-label Office rows aimed at the run-time prompts, built by code from random values: the planner's step plan (no format words in the text, the
    named save always there, a kept table inserted once), the proof judge's item list, and its yes/no check on a read-back that is right or broken on purpose."""
    rng = random.Random(SEED)
    items = ["Milk", "Bread", "Eggs", "Rice", "Tea", "Apples", "Butter", "Paper", "Pens", "Soap", "Salt", "Coffee"]
    titles = ["Largest cities", "Quarterly Plan", "Sales Report", "Team Update", "Budget 2027", "Project Status", "Weekly Summary", "Travel Plan"]
    fmts = ["bold", "italic", "underline"]
    for i in range(CAPS["office_exact"] or 4000):
        kind = i % 4
        path = rf"D:\work\{rng.choice(['report', 'notes', 'prices', 'deck', 'plan'])}_{i}.{['xlsx', 'docx', 'pptx', 'xlsx'][kind]}"
        if kind in (0, 3):                                                   # Excel cells
            n = rng.randint(1, 3)
            picks = rng.sample(items, n)
            vals = [rng.randint(5, 500) for _ in picks]
            hdr = rng.random() < 0.6
            f = rng.choice(fmts)
            words = ", ".join(f"{p} in A{k + 2} and {v} in B{k + 2}" for k, (p, v) in enumerate(zip(picks, vals)))
            task = f"open Excel, type Item in A1 and Price in B1, {words}" + (f", make A1 and B1 {f}" if hdr else "") + f" and save it as {path}"
            steps = [{"do": "new_document", "text": "", "target": "", "format": ""}, {"do": "type", "text": "Item", "target": "A1", "format": ""},
                     {"do": "type", "text": "Price", "target": "B1", "format": ""}]
            for k, (p, v) in enumerate(zip(picks, vals)):
                steps += [{"do": "type", "text": p, "target": f"A{k + 2}", "format": ""}, {"do": "type", "text": str(v), "target": f"B{k + 2}", "format": ""}]
            if hdr:
                steps += [{"do": "format", "text": "", "target": "A1", "format": f}, {"do": "format", "text": "", "target": "B1", "format": f}]
            want = [{"content": "Item", "where": "A1", "format": f if hdr else ""}, {"content": "Price", "where": "B1", "format": f if hdr else ""}] + \
                   [x for k, (p, v) in enumerate(zip(picks, vals)) for x in ({"content": p, "where": f"A{k + 2}", "format": ""}, {"content": str(v), "where": f"B{k + 2}", "format": ""})]
            cells = {"A1": ("'Item'", hdr and f), "B1": ("'Price'", hdr and f)}
            for k, (p, v) in enumerate(zip(picks, vals)):
                cells[f"A{k + 2}"], cells[f"B{k + 2}"] = (f"'{p}'", None), (str(v), None)
            app = "excel"
        elif kind == 1:                                                      # Word: title + optional kept table
            t, f = rng.choice(titles), rng.choice(fmts)
            table = rng.random() < 0.5
            task = f"open Word, write the title {t} in {f}" + (", insert the cities table below it" if table else "") + f" and save it as {path}"
            steps = [{"do": "new_document", "text": "", "target": "", "format": ""}, {"do": "type", "text": t, "target": "title", "format": ""},
                     {"do": "format", "text": t, "target": "title", "format": f}] + ([{"do": "insert_table", "text": "cities", "target": "", "format": ""}] if table else [])
            want = [{"content": t, "where": "title", "format": f}] + ([{"content": "the cities table", "where": "below the title", "format": ""}] if table else [])
            cells = None
            app = "word"
        else:                                                                # PowerPoint: title slide + a table slide
            t = rng.choice(titles)
            task = f"open PowerPoint, make a title slide {t}, add a slide with the cities table and save it as {path}"
            steps = [{"do": "new_document", "text": "", "target": "", "format": ""}, {"do": "type", "text": t, "target": "title", "format": ""},
                     {"do": "add_slide", "text": "", "target": "", "format": ""}, {"do": "insert_table", "text": "cities", "target": "", "format": ""}]
            want = [{"content": t, "where": "slide 1 title", "format": ""}, {"content": "the cities table", "where": "slide 2", "format": ""}]
            cells = None
            app = "powerpoint"
        steps.append({"do": "save_as", "text": path, "target": "", "format": ""})
        shown, paths = _shown(task.split(", ", 1)[1] if task.startswith("open ") else task)
        for s in steps:
            s["text"] = paths.get(s["text"], s["text"])
        ctx = "Kept by the apps before this one (use these names in read / insert / paste steps):\n- table 'cities' (A1:C11) from excel\n" if "cities table" in task else ""
        g = f"office::{i // 4}"
        yield rec("plan", STEP_SYSTEM.replace("APP", app), f"{ctx}Instruction: \"{shown}\"\nJSON:", {"steps": steps}, "constructed_exact", g, "office_exact", app_key=app)
        yield rec("judge", ITEMS_SYSTEM, f"Task: \"{re.sub(r'(?:,?\s*and)?\s*save it as .*$', '', task)}\"\nJSON:", {"items": want}, "constructed_exact", g, "office_exact", app_key=app)
        if cells:                                                            # the yes/no check on a read-back, right or broken on purpose (half each)
            broken = rng.random() < 0.5
            what = dict(cells)
            target = rng.choice(list(cells))
            how = ""
            if broken:
                how = rng.choice(["value", "format", "move"] if cells[target][1] else ["value", "move"])
                val, fm = what[target]
                if how == "value":
                    what[target] = ("'" + val.strip("'") + " total'" if val.startswith("'") else str(int(val) + rng.randint(1, 9)), fm)
                elif how == "format":
                    what[target] = (val, None)
                else:
                    what.pop(target)
                    what[target[0] + str(int(target[1:]) + 5)] = (val, fm)
            readback = "\n".join(f"Sheet1!{c} = {v}" + (f" [{fm}]" if fm else "") for c, (v, fm) in sorted(what.items(), key=lambda x: (int(x[0][1:]), x[0][0])))
            it = next(x for x in want if x["where"] == target)
            q = f"does it contain {it['content']!r} at/in {it['where']}" + (f", formatted {it['format']}" if it["format"] else "") + ", exactly that and in that place?"
            yield rec("check", CHECK_SYSTEM, f"The result:\n\"\"\"\n{readback}\n\"\"\"\nQuestion: {q}\nAnswer:", "no" if broken else "yes", "constructed_exact", g,
                      "office_exact", app_key=app)


SOURCES = {"real_ui": src_real_ui, "decide_web": src_decide_web, "safety_traps": src_safety_traps, "waveui_point": src_waveui_point, "websrc": src_websrc,
           "squad": src_squad, "vba_teach": src_vba_teach, "agentnet_plan": src_agentnet_plan, "mind2web_plan": src_mind2web_plan, "odyssey_route": src_odyssey_route,
           "quickdraw": src_quickdraw, "office_exact": src_office_exact}


# ---- build ----------------------------------------------------------------------------------------------------------------------------------------------
def _checker():
    sys.path.insert(0, str(ALL_CODES))
    from core_organs import train_qlora as TQ
    return lambda r: TQ.validate_pair(r, str(HARVEST), (r.get("meta") or {}).get("job") == "ground")


def build(only=None):
    check = _checker()
    report = {}
    for name, fn in SOURCES.items():
        if only and name not in only:
            continue
        shard = SHARDS / f"{name}.jsonl"
        done = SHARDS / f"{name}.done.json"
        if done.exists() and not only:
            report[name] = json.loads(done.read_text())
            print(f"[skip] {name}: {report[name]['kept']} rows already built")
            continue
        cap = CAPS[name]
        kept, rejected, reasons, seen = 0, 0, collections.Counter(), set()
        rows = []
        try:
            for r in fn():
                h = hashlib.md5(json.dumps(r["messages"][1:], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                probs = check(r)
                if probs:
                    rejected += 1
                    reasons[probs[0].split(":")[0][:70]] += 1
                    continue
                rows.append(r)
        except Exception as exc:
            print(f"[warn] {name} stopped early: {type(exc).__name__}: {str(exc)[:160]}")
        if cap and len(rows) > cap:                                        # cap by whole groups chosen at random, so near-duplicates do not crowd the sample
            groups = collections.defaultdict(list)
            for r in rows:
                groups[r["meta"]["split_group"]].append(r)
            keys = sorted(groups)
            random.Random(SEED).shuffle(keys)
            picked = []
            for k in keys:
                if len(picked) >= cap:
                    break
                picked += groups[k][: max(1, cap - len(picked))]
            rows = picked[:cap]
        with open(shard, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        kept = len(rows)
        report[name] = {"kept": kept, "rejected": rejected, "reasons": dict(reasons.most_common(5)), "jobs": dict(collections.Counter(r["meta"]["job"] for r in rows))}
        done.write_text(json.dumps(report[name], indent=1))
        print(f"[built] {name}: kept {kept}, rejected {rejected} {dict(reasons.most_common(3))}", flush=True)
    split(report)


def split(report):
    rows = []
    for name in SOURCES:
        p = SHARDS / f"{name}.jsonl"
        if p.exists():
            rows += [json.loads(l) for l in open(p, encoding="utf-8")]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r["meta"]["split_group"]].append(r)
    keys = sorted(groups)
    random.Random(SEED).shuffle(keys)
    by_job = collections.defaultdict(list)                                   # eval: about 5 %, capped, spread across jobs
    for k in keys:
        by_job[groups[k][0]["meta"]["job"]].append(k)
    eval_keys = set()
    total = len(rows)
    for job, ks in by_job.items():
        n_job = sum(len(groups[k]) for k in ks)
        want = max(30, int(EVAL_MAX * n_job / max(1, total)))
        got = 0
        for k in ks:
            if got >= want or got >= 0.1 * n_job:
                break
            eval_keys.add(k)
            got += len(groups[k])
    train = [r for k in keys if k not in eval_keys for r in groups[k]]
    ev = [r for k in keys if k in eval_keys for r in groups[k]]
    random.Random(SEED).shuffle(train)
    for name, part in (("train", train), ("eval", ev)):
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    jobs = collections.Counter(r["meta"]["job"] for r in train)
    summary = {"seed": SEED, "train": len(train), "eval": len(ev), "train_by_job": dict(jobs), "train_by_job_pct": {j: round(100 * n / max(1, len(train)), 1) for j, n in jobs.items()},
               "train_by_verified_by": dict(collections.Counter(r["meta"]["verified_by"] for r in train)), "train_with_image": sum(1 for r in train if any(c.get("type") == "image" for c in r["messages"][1]["content"])),
               "sources": report, "caps": CAPS, "steps_for_one_epoch_at_8_rows": -(-len(train) // 8)}
    (OUT / "data_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("train", "eval", "train_by_job_pct", "train_with_image", "steps_for_one_epoch_at_8_rows")}, indent=1))
    sample()


def sample(n=3):
    """3 rows of each job written to samples.md (and the start printed) so the set can be read before hours of training."""
    p = OUT / "train.jsonl"
    if not p.exists():
        print("build first")
        return
    seen = collections.defaultdict(list)
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        j = r["meta"]["job"]
        if len(seen[j]) < n:
            seen[j].append(r)
    out = []
    for j, rs in sorted(seen.items()):
        out.append(f"## {j}\n")
        for r in rs:
            img = [c["image"] for c in r["messages"][1]["content"] if c.get("type") == "image"]
            u = " ".join(c.get("text", "") for c in r["messages"][1]["content"] if c.get("type") == "text")
            out.append(f"- source `{r['meta']['source']}` verified_by `{r['meta']['verified_by']}`" + (f" image `{img[0]}`" if img else "") +
                       f"\n  - USER: {u[-500:]!r}\n  - ANSWER: {r['messages'][2]['content'][0]['text'][:500]!r}\n")
    (OUT / "samples.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out)[:12000])


# ---- train ----------------------------------------------------------------------------------------------------------------------------------------------
def train(dry=False):
    summary = json.loads((OUT / "data_summary.json").read_text())
    local = INBOX / "1_model_qwen3_vl_4b"
    model = str(local) if (local / "config.json").exists() else MODEL_4B
    pre = OUT
    steps = int(os.environ.get("HOJAIGA_STEPS", summary["steps_for_one_epoch_at_8_rows"]))
    if dry:                                                                  # a tiny slice: does it fit and how fast is a step
        pre = OUT / "dry"
        pre.mkdir(exist_ok=True)
        rows = [json.loads(l) for l in open(OUT / "train.jsonl", encoding="utf-8")]
        rng = random.Random(SEED)
        pick = rng.sample(rows, 64)                                          # a random slice: the same mix of image / text rows as the real set
        for name in ("train", "eval"):
            with open(pre / f"{name}.jsonl", "w", encoding="utf-8") as f:
                for r in (pick if name == "train" else pick[:4]):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        steps = int(os.environ.get("HOJAIGA_DRY_STEPS", "6"))
    os.chdir(str(ALL_CODES))
    sys.path.insert(0, str(ALL_CODES))
    from core_organs import train_qlora as TQ
    argv = ["train", "--model", model, "--presplit", str(pre), "--steps", str(steps), "--seq", os.environ.get("HOJAIGA_SEQ", "1536"),
            "--max-pixels", os.environ.get("HOJAIGA_MAX_PIXELS", str(768 * 768)),     # measured Oct-29 on the RTX 3050: 1024x768 / 2048 needs 5.09 GiB of 5.03 free (44 s/step, spills);
                                                                                     # 768x768 / 1536 fits (4.92 GiB), ~27 s/step, drops 1.5 % of rows for length; 448x448 / 1024: 21 s but drops 11 % "--rank", os.environ.get("HOJAIGA_RANK", "16"),
            "--alpha", os.environ.get("HOJAIGA_ALPHA", "32"), "--warmup", os.environ.get("HOJAIGA_WARMUP", "100"), "--min-examples", "8" if dry else "200", "--force"]
    if os.environ.get("HOJAIGA_VISION", "1") == "1":
        argv.append("--vision")
    print("train_qlora", " ".join(argv), flush=True)
    return TQ.main(argv)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build(sys.argv[2:] or None)
    elif cmd == "split":
        split({})
    elif cmd == "sample":
        sample()
    elif cmd == "dry":
        sys.exit(train(dry=True))
    else:
        sys.exit(train())
