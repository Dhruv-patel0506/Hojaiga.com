"""
test_youtube_video_rag_harvester.py -- offline, CPU-only tests of youtube_video_rag_harvester.py. No network, no yt-dlp call, no GPU, no window; every database / folder is temporary and the real master RAG is only
checked for being left alone. A small synthetic screencast (a menu bar, a moving pointer, a menu that opens, a dialog that opens) stands in for the downloaded clip; the Set-of-Marks scan is a stub.

    python test_youtube_video_rag_harvester.py            (or: python -m unittest test_youtube_video_rag_harvester -v)

  H1 search      flat-search JSON -> candidates; short / live / off-topic videos are dropped; a 429 is Blocked
  H2 parts       transcript -> parts named by chapter
  H3 end to end  index -> captions -> clip -> keyframes -> dots -> JSONL pair + chain in causal_procedures_fts (FTS finds it); label / chord grounding; dots drawn on the picture; cursor_like activity found
  H4 cursor      no label matches -> the pointer's resting element grounds the step and the row says `cursor`
  H5 block       a refusal writes a doubling cool-down, stops the run, and nothing is requested during it
  H6 lock        a locked database spools the chains; they are flushed later, once
  H7 safety      credential-looking speech is dropped; destructive verbs mark the chain HITL_REQUIRED
  H8 resources   CUDA hidden, torch never loaded, subprocesses windowless with stdin closed, the master RAG file untouched
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402

import youtube_video_rag_harvester as H     # noqa: E402

MASTER = ROOT / "data" / "hojaiga_master_rag.db"
MASTER_STAT = (MASTER.stat().st_size, MASTER.stat().st_mtime) if MASTER.exists() else None

MENU = [("File", 8), ("Edit", 60), ("View", 112), ("Help", 164)]


def _frame(t: float, cursor, dropdown: bool, dialog: bool) -> np.ndarray:
    f = np.full((360, 640, 3), (48, 44, 40), np.uint8)
    cv2.rectangle(f, (0, 0), (640, 30), (30, 28, 26), -1)
    for name, x in MENU:
        cv2.putText(f, name, (x, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
    for i in range(8):
        cv2.putText(f, f"Layer {i} settings", (14, 220 + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.rectangle(f, (200, 60), (620, 330), (90, 90, 96), 2)
    cv2.line(f, (200, 60), (620, 330), (70, 70, 80), 1)
    if dropdown:
        cv2.rectangle(f, (20, 30), (180, 170), (70, 70, 80), -1)
        for j, lab in enumerate(("New Project", "Open", "Save")):
            cv2.putText(f, lab, (30, 56 + j * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    if dialog:
        cv2.rectangle(f, (170, 90), (470, 270), (110, 110, 120), -1)
        cv2.putText(f, "Save As", (200, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.rectangle(f, (380, 230), (450, 255), (60, 120, 200), -1)
    cx, cy = cursor
    f[cy:cy + 9, cx:cx + 9] = 255
    return f


def make_clip(path: str, fps: int = 10, seconds: int = 12) -> None:
    """Pointer travels to the File menu (t 2.0-3.5 s), the menu opens at 4.0 s, the Save As dialog opens at 9.0 s."""
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 360))
    for i in range(fps * seconds):
        t = i / fps
        k = min(1.0, max(0.0, (t - 2.0) / 1.5))
        cur = (int(300 + (24 - 300) * k), int(200 + (12 - 200) * k))
        vw.write(_frame(t, cur, 4.0 <= t < 9.0, t >= 9.0))
    vw.release()


def som_stub(image, region=None):
    if region:
        els = [{"id": 1, "label": "New Project", "role": "menuitem", "box": [30, 40, 100, 20], "conf": 0.9},
               {"id": 2, "label": "Open", "role": "menuitem", "box": [30, 70, 60, 20], "conf": 0.9}]
    else:
        els = [{"id": i + 1, "label": n, "role": "menuitem", "box": [x - 2, 6, 40, 22], "conf": 0.9} for i, (n, x) in enumerate(MENU)]
        els.append({"id": 5, "label": "Layer 0 settings", "role": "text", "box": [10, 208, 150, 16], "conf": 0.8})
    return {"size": [640, 360], "elements": els, "tiers_used": ["stub"], "tiers_skipped": [], "seconds": 0.0}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def seg(text, start, dur=2.0):
    return {"text": text, "start": start, "duration": dur}


def build(td: str, segments, ingest=True, chapter="Saving a project"):
    """A Harvester wired to fakes: captions from `segments`, the clip is the synthetic screencast, the scan is the stub."""
    clip_src = os.path.join(td, "src.mp4")
    make_clip(clip_src)
    h = H.Harvester(root=os.path.join(td, "root"), db=os.path.join(td, "rag.db"), ingest=ingest, pace=(0, 0))
    h.sleep_fn = lambda s: None
    h.log = lambda m: None
    h.som_fn = som_stub
    h.captions_fn = lambda vid: {"segments": segments, "chapters": [{"t0": 10.0, "t1": 30.0, "title": chapter}], "duration": 300, "title": "t", "caption_kind": "manual"}

    def clip_fn(vid, t0, t1, out_dir, **kw):
        dst = os.path.join(out_dir, f"{vid}_clip.mp4")
        with open(clip_src, "rb") as a, open(dst, "wb") as b:
            b.write(a.read())
        return dst
    h.clip_fn = clip_fn
    h.search_fn = lambda q, n: [{"id": "abcdefghijk", "title": "TestApp full tutorial", "channel": "c", "duration": 600}]
    return h


@contextlib.contextmanager
def harness(segments, **kw):
    td = tempfile.mkdtemp(prefix="ythv_")
    h = build(td, segments, **kw)
    try:
        yield td, h
    finally:
        h.close()
        shutil.rmtree(td, ignore_errors=True)


class H1Search(unittest.TestCase):
    def test_search_parse_and_filter(self):
        payload = {"entries": [{"id": "a" * 11, "title": "Blender Tutorial for Beginners", "channel": "X", "duration": 900},
                               {"id": "b" * 11, "title": "Blender in 30 seconds", "duration": 30},
                               {"id": "c" * 11, "title": "Blender live now", "duration": 5000, "live_status": "is_live"},
                               {"id": "d" * 11, "title": "Maya modelling", "duration": 900},
                               {"id": "short", "title": "bad id", "duration": 900}]}
        runner = lambda args, timeout=0: (0, json.dumps(payload), "")
        got = H.search_youtube("Blender tutorial", 5, runner)
        self.assertEqual(len(got), 4)
        kept = [e["id"] for e in got if H.relevant(e, "Blender")]
        self.assertEqual(kept, ["a" * 11])
        self.assertEqual(H.app_of_query("FL Studio beginner"), "FL Studio")
        self.assertEqual(H.app_of_query("VS Code walkthrough"), "VS Code")

    def test_429_is_blocked(self):
        runner = lambda args, timeout=0: (1, "", "ERROR: HTTP Error 429: Too Many Requests")
        with self.assertRaises(H.Blocked):
            H.search_youtube("x tutorial", 3, runner)


class H2Parts(unittest.TestCase):
    def test_parts_named_by_chapter(self):
        segs = [seg("Now click File to open the menu.", 13.0), seg("Then press Ctrl+S to save your project.", 18.0), seg("And that is it for today, thanks.", 60.0)]
        parts = H.make_parts(segs, [{"t0": 10.0, "t1": 30.0, "title": "Saving"}])
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["chapter"], "Saving")
        self.assertEqual(parts[0]["idx"], 0)
        self.assertLessEqual(parts[0]["t1"] - parts[0]["t0"], 90.0)


SEGS = [seg("Now click File to open the menu.", 13.0), seg("Then press Ctrl+S to save your project.", 18.0)]


class H3EndToEnd(unittest.TestCase):
    def test_pipeline(self):
        with harness(SEGS) as (td, h):
            self.assertEqual(h.index([("TestApp", "app", "TestApp tutorial")], 3)["videos"], 1)
            self.assertEqual(h.index([("TestApp", "app", "TestApp tutorial")], 3)["skipped_done"], 1)          # resumable
            tot = h.process(5)
            self.assertEqual((tot["done"], tot["pairs"], tot["chains"]), (1, 2, 1), tot)
            rows = read_jsonl(h.out_jsonl)
            by = {r["meta"]["grounding"]: r for r in rows}
            self.assertEqual(set(by), {"label", "chord"})
            lab = by["label"]
            act = json.loads(lab["messages"][2]["content"][0]["text"])[0]
            self.assertEqual((act["action"], act["target_id"]), ("click", 1))                           # File -> dot 1
            self.assertIn("new on screen: New Project", act["verify_expectation"])
            self.assertIn("● [1]", lab["messages"][1]["content"][1]["text"])
            self.assertEqual(lab["meta"]["provenance"], "youtube_real_frame")
            self.assertIn("t=", lab["meta"]["url"])
            dotted = cv2.imread(os.path.join(h.root, lab["meta"]["dotted"]))
            clean = cv2.imread(os.path.join(h.root, lab["meta"]["pre"]))
            self.assertIsNotNone(dotted)
            self.assertGreater(int(np.abs(dotted.astype(int) - clean.astype(int)).sum()), 5000)        # dots really drawn
            self.assertTrue(any(r["kind"] == "cursor_like" and abs(r["box"][0] - 28) < 60 and r["box"][1] < 60 for r in lab["meta"]["activity"]), lab["meta"]["activity"])
            self.assertEqual(json.loads(by["chord"]["messages"][2]["content"][0]["text"])[0]["hotkey"], "ctrl+s")
            # the RAG got the chain: findable, Precondition -> Action -> Delta
            c = sqlite3.connect(h.db)
            hit = c.execute("SELECT arch_id, domain, goal, steps_json, trap_guard FROM causal_procedures_fts WHERE causal_procedures_fts MATCH 'Saving'").fetchall()
            self.assertEqual(len(hit), 1)
            arch, dom, goal, steps_json, guard = hit[0]
            steps = json.loads(steps_json)
            self.assertEqual((arch, dom, goal), ("VIDEO_VIDEO", "desktop_app", "Saving a project in TestApp"))
            self.assertEqual(len(steps), 2)
            self.assertTrue(steps[0]["precondition"]["frame"] and "File" in steps[0]["precondition"]["visible"])
            self.assertTrue(steps[0]["expected_delta"])
            self.assertIn("UNVERIFIED", guard)
            # idempotent
            ch = read_jsonl(h.chains_jsonl)[0]
            self.assertEqual(H.ingest_chains(h.db, [ch], h.spool)["skipped"], 1)
            self.assertEqual(c.execute("SELECT count(*) FROM causal_procedures_fts").fetchone()[0], 1)
            c.close()
            self.assertEqual(h.ledger.stats()["videos_by_status"], {"done": 1})
            self.assertEqual(os.listdir(os.path.join(h.work, "clips")), [])                              # clips deleted
            self.assertNotIn("torch", sys.modules)

    def test_captions_only_tier(self):
        with harness(SEGS) as (td, h):
            h.frames = False
            h.index([("TestApp", "web_app", "TestApp tutorial")], 3)
            tot = h.process(5)
            self.assertEqual((tot["pairs"], tot["chains"]), (0, 1))
            c = sqlite3.connect(h.db)
            arch, dom, steps = c.execute("SELECT arch_id, domain, steps_json FROM causal_procedures_fts").fetchone()
            c.close()
            self.assertEqual((arch, dom), ("VIDEO_TRANSCRIPT", "web_app"))
            self.assertIn("not observed", json.loads(steps)[0]["precondition"]["note"])
            self.assertFalse(os.path.exists(h.out_jsonl))


class H4Cursor(unittest.TestCase):
    def test_pointer_grounds_when_no_label_matches(self):
        with harness([seg("Click the icon at the top left.", 13.0)]) as (td, h):
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            rows = read_jsonl(h.out_jsonl)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["meta"]["grounding"], "cursor")
            self.assertEqual(json.loads(rows[0]["messages"][2]["content"][0]["text"])[0]["target_id"], 1)

    def test_unlocatable_step_writes_nothing(self):
        with harness([seg("Click the Frobnicator tab.", 13.0)]) as (td, h):
            h.som_fn = lambda image, region=None: {"size": [640, 360], "elements": [{"id": 1, "label": "Zzz", "role": "text", "box": [400, 300, 30, 20], "conf": 0.9}], "tiers_used": [], "tiers_skipped": [], "seconds": 0}
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            self.assertFalse(os.path.exists(h.out_jsonl) and os.path.getsize(h.out_jsonl) > 0)


class H5Block(unittest.TestCase):
    def test_cooldown_doubles_and_stops_everything(self):
        with harness(SEGS) as (td, h):
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            calls = []

            def refuse(vid):
                calls.append(vid)
                raise H.Blocked("HTTP Error 429")
            h.captions_fn = refuse
            tot = h.process(5)
            self.assertTrue(tot.get("blocked"))
            first = h.ledger.blocked_until()
            self.assertGreater(first - time.time(), 1700)
            self.assertEqual(h.ledger.stats()["videos_by_status"], {"indexed": 1})                       # not marked failed: it can be retried after the cool-down
            tot2 = h.process(5)                                                                          # still cooling down: no call at all
            self.assertTrue(tot2.get("blocked"))
            self.assertEqual(len(calls), 1)
            with self.assertRaises(H.Blocked):
                h.index([("Other", "app", "Other tutorial")], 3)
            self.assertGreater(h.ledger.block() - time.time(), 3500)                                     # the next refusal doubles it


class H6Lock(unittest.TestCase):
    def test_locked_db_spools_then_flushes(self):
        with tempfile.TemporaryDirectory() as td:
            db, spool = os.path.join(td, "rag.db"), os.path.join(td, "spool.jsonl")
            ch = {"chain_id": "c1", "arch_id": "VIDEO_VIDEO", "domain": "desktop_app", "goal": "Do a thing in App", "trap_guard": "g", "video_id": "v", "steps": [{"step": 1}]}
            H.ingest_chains(db, [dict(ch, chain_id="seed")], spool)
            blocker = sqlite3.connect(db, timeout=1)
            blocker.execute("BEGIN EXCLUSIVE")
            t0 = time.time()
            r = H.ingest_chains(db, [ch], spool, busy_ms=200)
            self.assertEqual(r["spooled"], 1)
            self.assertLess(time.time() - t0, 5)
            blocker.rollback()
            blocker.close()
            self.assertEqual(H.flush_spool(db, spool)["inserted"], 1)
            self.assertFalse(os.path.exists(spool))
            self.assertEqual(H.flush_spool(db, spool)["inserted"], 0)
            c = sqlite3.connect(db)
            self.assertEqual(c.execute("SELECT count(*) FROM causal_procedures_fts").fetchone()[0], 2)
            c.close()


class H7Safety(unittest.TestCase):
    def test_credentials_dropped_and_destructive_flagged(self):
        with harness([seg("Click the password field and type your password.", 13.0), seg("Then click Delete to remove it.", 18.0)]) as (td, h):
            h.frames = False
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            c = sqlite3.connect(h.db)
            goal, steps, guard = c.execute("SELECT goal, steps_json, trap_guard FROM causal_procedures_fts").fetchone()
            c.close()
            self.assertNotIn("password", steps.lower())
            self.assertIn("HITL_REQUIRED", guard)


class H8Resources(unittest.TestCase):
    def test_gpu_hidden_and_torch_not_loaded(self):
        out = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0]=[r'%s', r'%s']; import youtube_video_rag_harvester as h, os; print(os.environ['CUDA_VISIBLE_DEVICES'], 'torch' in sys.modules)" % (ROOT, ROOT / "All codes")],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["-1", "False"])

    def test_subprocess_is_windowless_and_stdin_closed(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        real = subprocess.run
        subprocess.run = fake_run
        try:
            H.run_ytdlp(["--version"])
        finally:
            subprocess.run = real
        self.assertEqual(seen["stdin"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertEqual(seen["creationflags"], subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(MASTER.exists(), "master RAG not present")
    def test_seed_is_read_only_and_clean(self):
        names = H.seed_names("app", str(MASTER), limit=0)
        self.assertGreater(len(names), 50)
        self.assertFalse([n for n in names if "#" in n or "'" in n])
        self.assertEqual((MASTER.stat().st_size, MASTER.stat().st_mtime), MASTER_STAT)


class H9ActionKinds(unittest.TestCase):
    """Found in the first live run (Blender): 'scroll wheel' / 'drag around' were written as clicks, 'press shift A' as a click, vague steps grounded by the pointer."""

    def test_spoken_chord_without_plus(self):
        self.assertEqual(H.step_chord({"verb": "press", "target": "shift A"}), "shift+a")
        self.assertEqual(H.step_chord({"verb": "press", "target": "Control Shift Z"}), "ctrl+shift+z")
        self.assertEqual(H.step_chord({"verb": "press", "target": "the Save button"}), "")
        self.assertEqual(H.step_chord({"verb": "click", "target": "shift A"}), "")
        self.assertEqual(H.step_chord({"verb": "press", "target": "Ctrl+S", "chord": "ctrl+s"}), "ctrl+s")

    def test_scroll_and_drag_make_no_pair_and_no_click_chain(self):
        with harness([seg("Scroll the mouse wheel to zoom in on the canvas.", 13.0), seg("Then drag the layers panel to the right.", 18.0)]) as (td, h):
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            self.assertFalse(os.path.exists(h.out_jsonl) and os.path.getsize(h.out_jsonl) > 0)

    def test_spoken_shift_a_becomes_a_hotkey_pair(self):
        with harness([seg("Now press shift A to add something.", 13.0)]) as (td, h):
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            rows = read_jsonl(h.out_jsonl)
            act = json.loads(rows[0]["messages"][2]["content"][0]["text"])[0]
            self.assertEqual((act["action"], act["hotkey"]), ("hotkey", "shift+a"))

    def test_pointer_does_not_ground_a_non_pointing_verb(self):
        with harness([seg("Add a plane at the top left.", 13.0)]) as (td, h):
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            h.process(5)
            self.assertFalse(os.path.exists(h.out_jsonl) and os.path.getsize(h.out_jsonl) > 0)


class H10WhisperFirst(unittest.TestCase):
    def test_never_calls_captions_and_reports_timing(self):
        with harness([]) as (td, h):
            def no_captions(vid):
                raise AssertionError("the caption endpoint must not be called in whisper-first mode")
            h.captions_fn = no_captions
            h.whisper_first, h.frames = True, False
            seen = {}
            h.audio_fn = lambda vid, secs, d: seen.update(secs=secs) or os.path.join(d, "a.m4a")
            h.transcribe_fn = lambda path, model: [seg("Now click File to open the menu.", 13.0), seg("Then press Ctrl+S to save your project.", 18.0)] and \
                [seg("Now click File to open the menu.", 13.0), seg("Then press Ctrl+S to save your project.", 18.0)]
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            tot = h.process(5)
            self.assertEqual((tot["done"], tot["chains"]), (1, 1), tot)
            self.assertEqual(seen["secs"], 240.0)
            self.assertEqual(set(h.timing), {"audio_download_s", "transcribe_s", "speech_s"})
            self.assertAlmostEqual(h.timing["speech_s"], 20.0, places=1)

    def test_blocked_audio_download_stops_and_sets_cooldown(self):
        with harness([]) as (td, h):
            def refused(vid, secs, d):
                raise H.Blocked("HTTP Error 429")
            h.audio_fn = refused
            h.whisper_first, h.frames = True, False
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            tot = h.process(5)
            self.assertTrue(tot.get("blocked"))
            self.assertGreater(h.ledger.blocked_until(), time.time())

    def test_silence_gives_a_skip_not_a_chain(self):
        with harness([]) as (td, h):
            h.whisper_first, h.frames = True, False
            h.audio_fn = lambda vid, secs, d: os.path.join(d, "a.m4a")
            h.transcribe_fn = lambda path, model: []
            h.index([("TestApp", "app", "TestApp tutorial")], 3)
            tot = h.process(5)
            self.assertEqual((tot["done"], tot["skipped"], tot["chains"]), (0, 1, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
