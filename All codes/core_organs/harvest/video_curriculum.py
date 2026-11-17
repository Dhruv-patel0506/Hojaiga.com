"""
harvest.video_curriculum -- the always-on pipeline that turns public tutorial videos of MANY apps into knowledge in the local RAG, climbing from easy to complex in every category at once.

    python -m core_organs.harvest.video_curriculum plan                      the ladders (data file: data/video_graph/curriculum.json, edit it freely) and what is done
    python -m core_organs.harvest.video_curriculum run [--hours 12] [--tier 1 2 3] [--only "Blender" ...] [--no-rag]
    python -m core_organs.harvest.video_curriculum status | growth | rollback --run <stamp>

LADDERS. Every category (writing, spreadsheets, drawing, code, system, communication, video, audio, 3D / CAD ...) is an ordered ladder from the simplest app to the most complex
(writing: Notepad -> WordPad -> Notepad++ -> Google Docs -> Word -> Notion -> Obsidian -> Overleaf). The run takes RUNG 0 of every category, then rung 1 of every category, and so on: breadth
before depth, and each category keeps climbing. Each app carries the archetype a person would give it, which is training data for the profile model (never the model's own guess).

TWO STAGES, ALWAYS OVERLAPPED (a queue of one app between them):
    ACQUIRE   fetch up to N tutorial videos (polite, one at a time, a pause between, stop at the first HTTP 429 and wait; titles that are reviews / versus / news / cracks / downloads are
              skipped) and transcribe their audio locally (faster-whisper, CPU)                                              - network + CPU, while the previous app is being learned
    LEARN     cut each video into action events (webcam masked, scene cuts dropped, moving objects TRACED as vector paths), merge the videos into one graph of the app, read the text of the
              menus / panels that appear (OCR, voted at the fact level across videos), read the shortcuts and modifier gestures that were SPOKEN, clean and de-duplicate the names (fact_cleaner),
              write only NEW shortcuts into the RAG (screen facts as trust 'web', spoken ones as 'transcript', verified False: a shortcut the RAG already knows is corroborated or reported as a
              conflict, never duplicated or overwritten), profile the app as a MIXTURE of the 25 archetypes (app_profile), index its gestures in the vector store (drag_trace.GestureIndex),
              write a picture report and a growth-ledger line + chart.
So the RAG is fed after EVERY app, while the next one is already downloading. Nothing needs an API key, a model server or the GPU (yt-dlp on public pages, OpenCV, Tesseract, faster-whisper,
SQLite / LanceDB); it never opens an application on the screen. It asks Windows not to idle-sleep for its own lifetime and runs at below-normal priority.

Honest scope: this grows the pool's KNOWLEDGE of applications. Nothing becomes 'verified' here (that needs a live test, harvest.shortcut_verify) and no Qwen weights are trained.
Stop it by creating  data/video_graph/STOP  (it finishes the step it is on). Resume = run again: finished apps are skipped.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from core_organs.harvest import consolidate as C

DATA = C.DATA
ROOT = os.path.dirname(DATA)
CURRICULUM_PATH = os.path.join(C.GRAPH_DIR, "curriculum.json")
STATE_PATH = os.path.join(C.GRAPH_DIR, "curriculum_state.json")
STOP_PATH = os.path.join(C.GRAPH_DIR, "STOP")
GESTURES_PATH = os.path.join(C.GRAPH_DIR, "gestures.npz")
OUT_ROOT = os.path.join(ROOT, "reports", "video_curriculum")
MIN_FREE_GB = 30.0
MAX_CONSECUTIVE_FAILURES = 3
RATE_LIMIT_WAIT_S = 900
EXCLUDE = ["review", " vs ", "versus", "alternative", "news", "reaction", "podcast", "livestream", "live stream", "shorts", "trailer", "crack", "keygen", "free download", "activation",
           "patch", "torrent", "giveaway", "mod apk", "interview", "unboxing", "top 10", "top 5"]
GENERIC = {"microsoft", "windows", "adobe", "google", "the", "pro", "app", "editor", "studio", "11", "10"}

# category -> [(name, search phrase, kind, host (web only), archetype id or ''), ...] from the simplest app to the most complex
LADDERS: Dict[str, List[tuple]] = {
    "writing": [("Notepad", "Windows 11 Notepad", "desktop", "", "text_editor"), ("WordPad", "Windows WordPad", "desktop", "", "word_processor"), ("Notepad++", "Notepad++", "desktop", "", "text_editor"),
                ("Google Docs", "Google Docs", "web", "docs.google.com", "word_processor"), ("Microsoft Word", "Microsoft Word", "desktop", "", "word_processor"),
                ("Notion", "Notion", "web", "notion.so", "note_taking"), ("Obsidian", "Obsidian notes", "desktop", "", "note_taking"), ("Overleaf", "Overleaf LaTeX", "web", "overleaf.com", "text_editor")],
    "spreadsheets": [("Google Sheets", "Google Sheets", "web", "sheets.google.com", "spreadsheet"), ("Microsoft Excel", "Microsoft Excel", "desktop", "", "spreadsheet"),
                     ("Airtable", "Airtable", "web", "airtable.com", "database_client"), ("Power BI", "Power BI Desktop", "desktop", "", "database_client")],
    "presentations": [("Google Slides", "Google Slides", "web", "slides.google.com", "presentation"), ("Microsoft PowerPoint", "Microsoft PowerPoint", "desktop", "", "presentation"),
                      ("Canva", "Canva", "web", "canva.com", "vector_editor")],
    "drawing": [("Microsoft Paint", "Microsoft Paint", "desktop", "", "raster_editor"), ("Excalidraw", "Excalidraw", "web", "excalidraw.com", "diagram_whiteboard"),
                ("draw.io", "draw.io diagrams.net", "web", "app.diagrams.net", "diagram_whiteboard"), ("Photopea", "Photopea", "web", "photopea.com", "raster_editor"),
                ("GIMP", "GIMP", "desktop", "", "raster_editor"), ("Inkscape", "Inkscape", "desktop", "", "vector_editor"), ("Figma", "Figma", "web", "figma.com", "vector_editor"),
                ("Krita", "Krita", "desktop", "", "raster_editor"), ("Adobe Photoshop", "Adobe Photoshop", "desktop", "", "raster_editor"),
                ("Adobe Illustrator", "Adobe Illustrator", "desktop", "", "vector_editor")],
    "code": [("Visual Studio Code", "Visual Studio Code", "desktop", "", "code_ide"), ("Jupyter Notebook", "Jupyter Notebook", "desktop", "", "code_ide"), ("Postman", "Postman API", "desktop", "", "code_ide"),
             ("GitHub Desktop", "GitHub Desktop", "desktop", "", "code_ide"), ("PyCharm", "PyCharm", "desktop", "", "code_ide"), ("Visual Studio", "Visual Studio 2022", "desktop", "", "code_ide"),
             ("Docker Desktop", "Docker Desktop", "desktop", "", "system_utility")],
    "system": [("Windows Calculator", "Windows Calculator", "desktop", "", "calculator"), ("File Explorer", "Windows 11 File Explorer", "desktop", "", "file_manager"),
               ("Task Manager", "Windows Task Manager", "desktop", "", "system_utility"), ("Windows Settings", "Windows 11 Settings", "desktop", "", "settings_panel"),
               ("7-Zip", "7-Zip", "desktop", "", "file_manager"), ("Windows Terminal", "Windows Terminal", "desktop", "", "terminal")],
    "communication": [("Gmail", "Gmail", "web", "mail.google.com", "email_client"), ("Outlook", "Microsoft Outlook", "desktop", "", "email_client"), ("Zoom", "Zoom meetings", "desktop", "", "chat_messenger"),
                      ("Slack", "Slack", "desktop", "", "chat_messenger"), ("Discord", "Discord", "desktop", "", "chat_messenger"), ("Microsoft Teams", "Microsoft Teams", "desktop", "", "chat_messenger")],
    "projects": [("Trello", "Trello", "web", "trello.com", ""), ("Asana", "Asana", "web", "asana.com", ""), ("ClickUp", "ClickUp", "web", "clickup.com", ""), ("Jira", "Jira", "web", "jira.atlassian.com", "")],
    "video": [("Clipchamp", "Clipchamp", "web", "clipchamp.com", "video_editor"), ("OBS Studio", "OBS Studio", "desktop", "", "screen_capture_stream"), ("CapCut", "CapCut", "desktop", "", "video_editor"),
              ("DaVinci Resolve", "DaVinci Resolve", "desktop", "", "video_editor"), ("Adobe Premiere Pro", "Adobe Premiere Pro", "desktop", "", "video_editor"),
              ("Adobe After Effects", "Adobe After Effects", "desktop", "", "video_editor")],
    "audio": [("Audacity", "Audacity", "desktop", "", "audio_daw"), ("FL Studio", "FL Studio", "desktop", "", "audio_daw"), ("Ableton Live", "Ableton Live", "desktop", "", "audio_daw")],
    "media": [("VLC", "VLC media player", "desktop", "", "media_player"), ("Spotify", "Spotify desktop", "desktop", "", "media_player")],
    "modeling": [("Tinkercad", "Tinkercad", "web", "tinkercad.com", "3d_modeler"), ("SketchUp", "SketchUp", "desktop", "", "3d_modeler"), ("Blender", "Blender 3D", "desktop", "", "3d_modeler"),
                 ("Fusion 360", "Autodesk Fusion 360", "desktop", "", "cad_engineering"), ("AutoCAD", "AutoCAD", "desktop", "", "cad_engineering"), ("SolidWorks", "SolidWorks", "desktop", "", "cad_engineering")],
    "documents": [("Adobe Acrobat", "Adobe Acrobat", "desktop", "", "pdf_reader")],
    "data": [("DBeaver", "DBeaver", "desktop", "", "database_client"), ("Tableau", "Tableau", "desktop", "", "database_client")],
    "gamedev": [("Scratch", "Scratch programming", "web", "scratch.mit.edu", ""), ("Unity", "Unity editor", "desktop", "", "3d_modeler"), ("Unreal Engine", "Unreal Engine 5", "desktop", "", "3d_modeler")],
    "browser": [("Google Chrome", "Google Chrome", "desktop", "", "browser")],
}


def slug(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_")


def app_key(entry: Dict[str, Any]) -> str:
    if entry["kind"] == "web":
        return f"webapp:{entry['host']}"
    from core_organs.harvest import bridge as BR
    return BR.app_key_of(re.sub(r"\++", lambda m: " plus " * len(m.group(0)), entry["name"]))      # 'Notepad++' must not collapse into 'Notepad'


def default_rows() -> List[Dict[str, Any]]:
    rows = []
    for cat, ladder in LADDERS.items():
        for rung, (name, search, kind, host, arch) in enumerate(ladder):
            rows.append({"name": name, "search": search, "kind": kind, "host": host, "category": cat, "archetype": arch, "rung": rung, "tier": 1 + rung // 3, "videos": 4 + min(2, rung // 2),
                         "min_min": 3 + min(rung, 5), "max_min": min(25, 10 + 2 * rung)})
    return rows


def load_curriculum() -> List[Dict[str, Any]]:
    """The ladders as rows. Written from LADDERS the first time and then owned by the user (add, remove, reorder, change counts)."""
    if os.path.isfile(CURRICULUM_PATH):
        with contextlib.suppress(Exception):
            rows = json.load(open(CURRICULUM_PATH, encoding="utf-8"))
            if rows and "rung" in rows[0]:
                return rows
            os.replace(CURRICULUM_PATH, CURRICULUM_PATH + ".v1")                    # the first, tier-only version is kept aside; the ladder version replaces it
    rows = default_rows()
    os.makedirs(os.path.dirname(CURRICULUM_PATH), exist_ok=True)
    json.dump(rows, open(CURRICULUM_PATH, "w", encoding="utf-8"), indent=1)
    return rows


def ordered(rows: Sequence[Dict[str, Any]], tiers: Sequence[int] = (), only: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Rung by rung: the simplest app of EVERY category, then the second of every category, and so on (categories in a fixed order inside a rung). Rows without a rung use tier - 1."""
    pick = [r for r in rows if (not tiers or r["tier"] in tiers) and (not only or any(o.lower() == r["name"].lower() for o in only))]
    rung = lambda r: r.get("rung", r["tier"] - 1)
    cats = list(dict.fromkeys(r["category"] for r in pick))
    out: List[Dict[str, Any]] = []
    for k in sorted({rung(r) for r in pick}):
        for c in cats:
            out += [r for r in pick if rung(r) == k and r["category"] == c]
    return out


def load_state() -> Dict[str, Any]:
    if os.path.isfile(STATE_PATH):
        with contextlib.suppress(Exception):
            return json.load(open(STATE_PATH, encoding="utf-8"))
    return {"apps": {}}


def save_state(st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, STATE_PATH)


def keep_awake_and_nice() -> Dict[str, bool]:
    """Per-process only: Windows does not idle-sleep while this process runs (ES_CONTINUOUS | ES_SYSTEM_REQUIRED), and it runs below normal priority."""
    res = {"awake": False, "nice": False}
    with contextlib.suppress(Exception):
        import ctypes
        res["awake"] = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001))
    with contextlib.suppress(Exception):
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        res["nice"] = True
    return res


def free_gb(path: str = DATA) -> float:
    with contextlib.suppress(Exception):
        return shutil.disk_usage(path).free / 1e9
    return 1e9


def backup_rag(stamp: str, log: Callable[[str], None]) -> str:
    src = os.path.join(DATA, "ai_root", "rag")
    dst = os.path.join(DATA, "backups", f"rag_before_curriculum_{stamp}")
    if not os.path.isdir(src) or os.path.isdir(dst):
        return dst if os.path.isdir(dst) else ""
    os.makedirs(dst, exist_ok=True)
    log(f"backing up the RAG folder to {dst}")
    subprocess.run(["robocopy", src, dst, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NP"], capture_output=True)           # robocopy exits 1..7 on success
    return dst


def required_words(name: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9.]+", name.lower()) if w not in GENERIC and len(w) >= 3] or [name.lower()]


# ------------------------------------------------------------------------------------------------------------------ stage A: acquire
def acquire(entry: Dict[str, Any], log: Callable[[str], None] = print, stop: Callable[[], bool] = lambda: False, transcribe: bool = True) -> Dict[str, Any]:
    """Videos on disk (downloaded if missing) and their transcripts (made locally if missing)."""
    t0 = time.time()
    out_dir = os.path.join(C.GRAPH_DIR, "_downloads", slug(entry["name"]))
    os.makedirs(out_dir, exist_ok=True)
    acq: Dict[str, Any] = {"out_dir": out_dir, "rate_limited": False, "transcribed": 0, "transcript_errors": []}
    have = sorted(glob.glob(os.path.join(out_dir, "*.mp4")))
    need = max(0, int(entry["videos"]) - len(have))
    if need and not stop():
        C.fetch_videos(entry["search"], need, out_dir=out_dir, min_s=int(entry["min_min"] * 60), max_s=int(entry["max_min"] * 60), sleep_s=6.0, exclude=EXCLUDE,
                       require=required_words(entry["search"] if entry["kind"] == "desktop" else entry["name"]), log=log)
        acq["rate_limited"] = bool(C.LAST_FETCH.get("rate_limited"))
    acq["paths"] = sorted(glob.glob(os.path.join(out_dir, "*.mp4")))
    acq["segments"] = {}
    if transcribe:
        C._CAPTIONS_BLOCKED["yes"] = True                       # the caption endpoint answers 429 for this machine: straight to the audio track, never hammering
        for p in acq["paths"]:
            if stop():
                break
            try:
                tr = C.fetch_transcript(p, log=log)
                acq["segments"][p] = tr["segments"]
                acq["transcribed"] += 1
            except Exception as exc:
                acq["transcript_errors"].append(f"{os.path.basename(p)}: {type(exc).__name__}: {str(exc)[:100]}")
    acq["seconds"] = round(time.time() - t0, 1)
    return acq


# ------------------------------------------------------------------------------------------------------------------ stage B: learn
def rag_totals(rag: Any) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with contextlib.suppress(Exception):
        out["fast_paths"] = int(rag.st.count("fast_paths"))
        out["procedures"] = int(rag.st.count("procedures"))
    with contextlib.suppress(Exception):
        db = sqlite3.connect(f"file:{os.path.join(DATA, 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        out["lexicon_commands"] = int(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0])
        out["lexicon_apps"] = int(db.execute("SELECT COUNT(DISTINCT app_key) FROM commands").fetchone()[0])
        db.close()
    return out


def learn(entry: Dict[str, Any], acq: Dict[str, Any], rag: Any, log: Callable[[str], None] = print, write_rag: bool = True, stop: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
    t0 = time.time()
    key = app_key(entry)
    res: Dict[str, Any] = {"name": entry["name"], "key": key, "tier": entry["tier"], "category": entry["category"], "status": "ok", "rate_limited": acq.get("rate_limited", False),
                           "videos_downloaded": len(acq.get("paths", [])), "transcribed": acq.get("transcribed", 0)}
    paths = list(acq.get("paths", []))
    if len(paths) < 2:
        res["status"] = "too_few_videos"
        res["seconds"] = round(time.time() - t0, 1)
        return res
    g = C.AppGraph.load(key)
    ingest_errors = []
    for p in paths:
        if stop():
            res["status"] = "stopped"
            break
        try:
            segs = (acq.get("segments") or {}).get(p)
            vid = os.path.splitext(os.path.basename(p))[0]
            if vid in g.videos:                                                       # already ingested on an earlier run: its SPEECH (not yet read then) is still recorded
                if segs and not any(vid in v.get("videos", []) for v in (g.extra.get("spoken_votes") or {}).values()):
                    C.record_speech(g, vid, segs)
                    g.save()
            else:
                C.ingest_video(g, p, segments=segs)
        except Exception as exc:                                                      # one bad video must not lose the others
            ingest_errors.append(f"{os.path.basename(p)}: {type(exc).__name__}: {str(exc)[:120]}")
            log(f"  ingest failed {os.path.basename(p)}: {str(exc)[:120]}")
    res["ingest_errors"] = ingest_errors
    res["videos_ingested"] = len(g.videos)
    res["edges"], res["shared_edges"] = len(g.edges), len(g.baseline())
    if len(g.videos) < 2 or res["status"] == "stopped":
        res["seconds"] = round(time.time() - t0, 1)
        return res
    with contextlib.suppress(Exception):
        res["ocr_events"] = C.ocr_observations(g).get("ocr_calls")
    with contextlib.suppress(Exception):
        res["ocr_calls"] = C.ocr_edges(g).get("ocr_calls")
    priors, arch = None, entry.get("archetype") or ""
    with contextlib.suppress(Exception):                                              # what the pool already knows about apps like this one
        from core_organs.harvest import transfer_priors as TP, app_profile as AP0
        priors = TP.Priors.from_rag(rag) if rag is not None else None
        if not arch:
            arch = AP0.profile(g, entry["name"])["primary"]
    accept = (lambda f: (lambda s: (s[0] if s[0] >= 2 else s[1]) if priors.accept(arch, f["action"], f["windows"], key) else 0)(priors.strength(arch, f["action"], f["windows"], key))) if priors else None
    facts = g.facts(min_videos=1 if priors else 2)
    facts = [f for f in facts if f["videos"] >= 2 or f.get("source") == "speech" or (accept and accept(f))]
    if priors:
        with contextlib.suppress(Exception):
            res["transfer"] = {"archetype": arch, "accepted_by_prior": sum(1 for f in facts if f["videos"] < 2 and f.get("source") != "speech"),
                               "expected_not_seen": priors.expectations(arch, key, [(f["action"], f["windows"]) for f in facts], top=8)}
    res["shortcut_facts"] = len(facts)
    res["facts_by_source"] = {s: sum(1 for f in facts if f.get("source") == s) for s in ("screen", "speech")}
    res["top_facts"] = [(f["action"], f["windows"], f["videos"]) for f in facts[:8]]
    with contextlib.suppress(Exception):
        res["gestures"] = [(x["modifier"], x["gesture"], x["effect"]) for x in g.gestures()[:6]]
    if write_rag and rag is not None and facts:
        try:
            ex = C.export_facts_rag(g, rag, entry["name"], min_videos=2, only_new=True, accept_single=accept)
            res["rag"] = {"written": ex.get("written", 0), "corroborated": len(ex.get("corroborated", [])), "conflicts": ex.get("conflicts", []), "rows": ex.get("rows", []),
                          "cleaned": len((ex.get("cleaning") or {}).get("renamed", []))}
        except Exception as exc:
            res["rag"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    with contextlib.suppress(Exception):                                              # what KIND of app: a mixture; the labelled apps feed the profile model's training set
        from core_organs.harvest import app_profile as AP
        prof = AP.profile(g, entry["name"])
        AP.save(g, prof)
        res["profile"] = {"primary": prof["primary"], "share": prof["share"], "secondary": prof["secondary"], "hybrid": prof["hybrid"], "status": prof["status"]}
        if write_rag and rag is not None:
            res["profile"]["written"] = AP.apply_to_rag(rag, key, prof)
        if entry.get("archetype"):
            res["profile"]["labelled_example_added"] = AP.add_example(entry["archetype"], AP.signature_of(g), key)
            res["profile"]["model_gate"] = AP.fit_and_gate().get("why")
    with contextlib.suppress(Exception):                                              # the traced drags go into the shared gesture vector index
        from core_organs.harvest import drag_trace as DT
        drags = g.drags()
        idx = DT.GestureIndex(GESTURES_PATH)
        seen = {(m.get("app"), m.get("video"), m.get("t")) for m in idx.meta}
        new = [d for d in drags if (key, d["video"], d["t"]) not in seen]
        for d in new:
            idx.add(d["points"], {"app": key, "name": entry["name"], "video": d["video"], "t": d["t"], "kind": d["kind"], "length": d["length"]})
        if new:
            idx.save()
        res["drags"] = {"traced": len(drags), "added_to_index": len(new), "index_size": len(idx.vecs)}
    with contextlib.suppress(Exception):
        C.understanding_report(g, os.path.join(ROOT, "reports", "video_understanding", slug(entry["name"])), top=10)
    res["seconds"] = round(time.time() - t0, 1)
    return res


def run_app(entry: Dict[str, Any], rag: Any, log: Callable[[str], None] = print, write_rag: bool = True, stop: Callable[[], bool] = lambda: False, transcribe: bool = False) -> Dict[str, Any]:
    """Both stages in sequence (the single-function form; the pipeline overlaps them)."""
    return learn(entry, acquire(entry, log, stop, transcribe=transcribe), rag, log, write_rag, stop)


# ------------------------------------------------------------------------------------------------------------------ the ledger of the pool's growth
def write_summary(st: Dict[str, Any], stamp: str) -> str:
    os.makedirs(OUT_ROOT, exist_ok=True)
    md = ["# Video curriculum: what the pool learned", "", f"Updated {time.strftime('%Y-%m-%d %H:%M:%S')} (run {stamp}). Leads only: nothing here is verified until it is tested live.", "",
          "| rung | app | category | videos | edges (shared) | facts (screen/speech) | written to RAG | known | conflicts | profile | drags | status |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in sorted(st["apps"].items(), key=lambda kv: (kv[1].get("tier", 9), kv[1].get("category", ""), kv[0])):
        rg, pf, fs = r.get("rag") or {}, r.get("profile") or {}, r.get("facts_by_source") or {}
        prof = f"{pf.get('primary', '')} {int(100 * pf.get('share', 0))}%" + (" +" + "+".join(k for k, _ in pf.get("secondary", [])) if pf.get("secondary") else "") if pf else ""
        md.append(f"| {r.get('tier')} | {name} | {r.get('category')} | {r.get('videos_ingested', r.get('videos_downloaded', 0))} | {r.get('edges', 0)} ({r.get('shared_edges', 0)}) | "
                  f"{r.get('shortcut_facts', 0)} ({fs.get('screen', 0)}/{fs.get('speech', 0)}) | {rg.get('written', 0)} | {rg.get('corroborated', 0)} | {len(rg.get('conflicts', []))} | {prof} | "
                  f"{(r.get('drags') or {}).get('traced', 0)} | {r.get('status')} |")
    md += ["", "## Newest shortcut facts per app", ""]
    for name, r in sorted(st["apps"].items(), key=lambda kv: (kv[1].get("tier", 9), kv[0])):
        if r.get("top_facts"):
            md.append(f"- **{name}**: " + "; ".join(f"{a} = {w.upper()} ({v} videos)" for a, w, v in r["top_facts"]))
    gl = [f"- **{n}**: " + "; ".join(f"hold {m.upper()} while {g_} to {e_}" for m, g_, e_ in r["gestures"][:3]) for n, r in st["apps"].items() if r.get("gestures")]
    if gl:
        md += ["", "## Modifier gestures presenters described", ""] + gl
    path = os.path.join(OUT_ROOT, "SUMMARY.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    return path


def growth_snapshot(rag: Any, st: Dict[str, Any], stamp: str) -> Dict[str, Any]:
    """One line of the pool's volume: what the RAG holds and what the curriculum has taken in so far. Also redraws growth.png."""
    apps = st["apps"]
    snap = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "run": stamp, "apps_done": sum(1 for r in apps.values() if r.get("status") in ("ok", "no_new_knowledge", "ok_no_rag")),
            "videos": sum(r.get("videos_ingested", 0) for r in apps.values()), "events": sum(r.get("edges", 0) for r in apps.values()),
            "facts_found": sum(r.get("shortcut_facts", 0) for r in apps.values()), "facts_written": sum((r.get("rag") or {}).get("written", 0) for r in apps.values()),
            "categories": sorted({r.get("category") for r in apps.values() if r.get("category")}), "rag": rag_totals(rag) if rag is not None else {}}
    with contextlib.suppress(Exception):
        from core_organs.harvest import drag_trace as DT
        snap["gestures_indexed"] = len(DT.GestureIndex(GESTURES_PATH).vecs)
    with contextlib.suppress(Exception):
        from core_organs.harvest import app_profile as AP
        snap["labelled_apps_for_profile_model"] = len(AP.examples())
    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(os.path.join(OUT_ROOT, "growth.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(snap) + "\n")
    with contextlib.suppress(Exception):
        draw_growth_chart()
    return snap


def draw_growth_chart(path: str = "") -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = [json.loads(l) for l in open(os.path.join(OUT_ROOT, "growth.jsonl"), encoding="utf-8") if l.strip()]
    if not rows:
        return ""
    xs = list(range(len(rows)))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].plot(xs, [r["apps_done"] for r in rows], label="apps learned", marker="o")
    ax[0].plot(xs, [r["videos"] for r in rows], label="videos", marker="s")
    ax[0].plot(xs, [r["facts_found"] for r in rows], label="shortcut facts found", marker="^")
    ax[0].set_title("What the curriculum has taken in (one point per finished app)")
    ax[0].legend()
    ax[0].set_xlabel("apps finished")
    if rows[-1].get("rag"):
        for k in ("fast_paths", "procedures", "lexicon_commands"):
            ax[1].plot(xs, [r.get("rag", {}).get(k, 0) for r in rows], label=k, marker=".")
        ax[1].set_title("The RAG's volume")
        ax[1].legend()
        ax[1].set_xlabel("apps finished")
    fig.tight_layout()
    path = path or os.path.join(OUT_ROOT, "growth.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


# ------------------------------------------------------------------------------------------------------------------ the run
def run_curriculum(hours: float = 12.0, tiers: Sequence[int] = (), only: Sequence[str] = (), write_rag: bool = True, rag: Any = None, app_runner: Optional[Callable[..., Dict[str, Any]]] = None,
                   log: Callable[[str], None] = lambda s: print(s, flush=True), sleep: Callable[[float], None] = time.sleep, rows: Optional[Sequence[Dict[str, Any]]] = None,
                   acquire_fn: Optional[Callable[..., Dict[str, Any]]] = None, learn_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """With `app_runner` (tests, one-function form) the apps run one after another. Otherwise the two stages run as a pipeline: a producer thread acquires app k+1 while app k is learned."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    t_start = time.time()
    st = load_state()
    todo = [e for e in ordered(rows if rows is not None else load_curriculum(), tiers, only) if st["apps"].get(e["name"], {}).get("status") not in ("ok", "no_new_knowledge")]
    log(f"RUN {stamp}: {len(todo)} apps to do, budget {hours} h, rag writes {'on' if write_rag else 'off'}, {'sequential' if app_runner else 'pipelined'}")
    os.makedirs(OUT_ROOT, exist_ok=True)
    stop = lambda: os.path.isfile(STOP_PATH)
    state = {"fails": 0, "rate_waits": 0, "done": []}

    def why_stop() -> str:
        if stop():
            return "STOP file present"
        if (time.time() - t_start) / 3600.0 >= hours:
            return f"time budget of {hours} h used"
        if free_gb() < MIN_FREE_GB:
            return f"free disk below {MIN_FREE_GB} GB"
        if state["fails"] >= MAX_CONSECUTIVE_FAILURES:
            return f"{state['fails']} apps in a row failed"
        return ""

    def finish(entry: Dict[str, Any], r: Dict[str, Any]) -> None:
        r["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
        wrote = (r.get("rag") or {}).get("written", 0)
        if r["status"] == "ok":
            if (r.get("rag") or {}).get("error"):
                r["status"] = "rag_error"                                              # the write failed: retried on the next run
            elif not write_rag:
                r["status"] = "ok_no_rag"                                              # looked at, not written: a later run WITH writes picks it up again
            elif not wrote:
                r["status"] = "no_new_knowledge"                                       # nothing new two authors agree on (or it is all already known): not retried unless videos are added
        st["apps"][entry["name"]] = r
        save_state(st)
        with open(os.path.join(OUT_ROOT, "progress.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(r, run=stamp), default=str) + "\n")
        if wrote:
            with open(os.path.join(OUT_ROOT, "rag_writes.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"run": stamp, "app": entry["name"], "key": r.get("key"), "rows": (r.get("rag") or {}).get("rows", [])}) + "\n")
        write_summary(st, stamp)
        with contextlib.suppress(Exception):
            growth_snapshot(rag, st, stamp)
        log(f"APPDONE {entry['name']} status={r['status']} videos={r.get('videos_ingested', r.get('videos_downloaded', 0))} edges={r.get('edges', 0)} facts={r.get('shortcut_facts', 0)} "
            f"written={wrote} seconds={r.get('seconds')}")
        state["done"].append(entry["name"])
        state["fails"] = state["fails"] + 1 if r["status"] == "error" else 0

    if app_runner is not None:
        for entry in todo:
            why = why_stop()
            if why:
                log(f"STOPPING: {why}")
                break
            log(f"APPSTART {entry['name']} (rung {entry.get('rung', entry['tier'] - 1)}, {entry['category']})")
            try:
                r = app_runner(entry, rag, log, write_rag=write_rag, stop=stop) if app_runner is run_app else app_runner(entry, rag, log)
            except Exception as exc:
                r = {"name": entry["name"], "tier": entry["tier"], "category": entry["category"], "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            finish(entry, r)
            if r.get("rate_limited") and state["rate_waits"] < 3:
                state["rate_waits"] += 1
                log(f"RATELIMITED: waiting {RATE_LIMIT_WAIT_S // 60} min (no retries, no rotation)")
                sleep(RATE_LIMIT_WAIT_S)
    else:
        acq_fn, learn_f = acquire_fn or acquire, learn_fn or learn
        q: "queue.Queue" = queue.Queue(maxsize=1)

        def producer() -> None:
            waits = 0
            for entry in todo:
                if why_stop():
                    break
                log(f"FETCHSTART {entry['name']}")
                try:
                    acq = acq_fn(entry, log, stop)
                except Exception as exc:
                    acq = {"error": f"{type(exc).__name__}: {str(exc)[:200]}", "paths": []}
                log(f"FETCHDONE {entry['name']} videos={len(acq.get('paths', []))} transcribed={acq.get('transcribed', 0)} seconds={acq.get('seconds')}")
                q.put((entry, acq))                                                    # blocks while the consumer is still learning the previous app and one is already waiting
                if acq.get("rate_limited") and waits < 3:
                    waits += 1
                    log(f"RATELIMITED: fetching pauses {RATE_LIMIT_WAIT_S // 60} min (learning goes on)")
                    sleep(RATE_LIMIT_WAIT_S)
            q.put(None)

        th = threading.Thread(target=producer, daemon=True, name="acquire")
        th.start()
        while True:
            item = q.get()
            if item is None:
                break
            entry, acq = item
            why = why_stop()
            if why:
                log(f"STOPPING: {why}")
                while q.get() is not None:                                             # let the producer finish its put
                    pass
                break
            log(f"APPSTART {entry['name']} (rung {entry.get('rung', entry['tier'] - 1)}, {entry['category']})")
            try:
                r = acq.get("error") and {"name": entry["name"], "tier": entry["tier"], "category": entry["category"], "status": "error", "error": acq["error"]} or learn_f(entry, acq, rag, log, write_rag, stop)
            except Exception as exc:
                r = {"name": entry["name"], "tier": entry["tier"], "category": entry["category"], "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            finish(entry, r)
    path = write_summary(st, stamp)
    log(f"RUNDONE {stamp}: {len(state['done'])} apps this run, summary {path}")
    return {"stamp": stamp, "apps": state["done"], "summary": path}


def rollback(stamp: str, rag: Any) -> Dict[str, Any]:
    """Forget the RAG rows a run wrote (from rag_writes.jsonl), row by row."""
    n, apps = 0, 0
    path = os.path.join(OUT_ROOT, "rag_writes.jsonl")
    for line in open(path, encoding="utf-8") if os.path.isfile(path) else []:
        j = json.loads(line)
        if j["run"] != stamp:
            continue
        ids = []
        for action, payload in j["rows"]:
            row = rag.fast.find(j["key"], action, payload)
            if row and not row.get("verified"):                                       # a row that was proven since is never forgotten here
                ids.append(row["fast_id"])
        n += rag.fast.forget_rows(ids)
        apps += 1
    return {"apps": apps, "rows_forgotten": n}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="video_curriculum")
    ap.add_argument("cmd", choices=["plan", "run", "status", "growth", "rollback"])
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--tier", type=int, nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--no-rag", action="store_true")
    ap.add_argument("--run", default="")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        st = load_state()
        for i, e in enumerate(ordered(load_curriculum(), a.tier, a.only), 1):
            s = st["apps"].get(e["name"], {}).get("status", "todo")
            print(f"{i:>2}. rung {e.get('rung', e['tier'] - 1)} {e['category']:<14} {e['name']:<22} {e['kind']:<7} {e['videos']} videos {e['min_min']}-{e['max_min']} min  [{s}]  key={app_key(e)}")
        return 0
    if a.cmd == "status":
        for n, r in load_state()["apps"].items():
            print(f"{n:<22} {r.get('status'):<17} videos={r.get('videos_ingested', r.get('videos_downloaded', 0))} edges={r.get('edges', 0)} facts={r.get('shortcut_facts', 0)} written={(r.get('rag') or {}).get('written', 0)}")
        return 0
    if a.cmd == "growth":
        print(draw_growth_chart() or "no growth data yet")
        return 0
    from core_organs import rag as R
    if a.cmd == "rollback":
        print(json.dumps(rollback(a.run, R.get_rag()), indent=1))
        return 0
    print(json.dumps(keep_awake_and_nice()), flush=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    rag = None if a.no_rag else R.get_rag()
    if rag is not None:
        backup_rag(stamp, lambda s: print(s, flush=True))
    r = run_curriculum(a.hours, a.tier, a.only, not a.no_rag, rag)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
