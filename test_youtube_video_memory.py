"""
test_youtube_video_memory.py -- offline, CPU-only tests of youtube_video_memory.py. No network (sockets are blocked while the tests run), no GPU, no model download, no window; the staging database and the RAG
are temporary and the real master RAG is only checked for being left alone. The video is the synthetic screencast from test_youtube_video_rag_harvester (menu bar, a pointer, a menu that opens at 4 s,
a Save As dialog at 9 s); the Whisper step is a stub (the real one is exercised separately, see the `--whisper` check in the report).

    python test_youtube_video_memory.py            (or: python -m unittest test_youtube_video_memory -v)

  M1 speech       windows from caption lines; .srt / .json3 transcripts
  M2 alignment    a spoken UI step lands on the element it names (with a box and the frame time); a spoken word that is also on screen is recorded with its place; a spoken thing that is NOT on screen is not
  M3 store        moments + FTS + vectors written once (re-adding is a no-op); search finds the right moment, honours the app filter, returns a time link
  M4 embedder     a memory built with one embedder refuses to be searched with another; the semantic embedder (bge, local cache) ranks a paraphrase first (skipped if not cached)
  M5 rag          to_rag refuses without confirm; with it the transcript reaches a TEMP federated RAG and is retrievable
  M6 offline      CUDA hidden, torch not loaded by the hash path, the master RAG file untouched, a real OCR pass finds the menu labels of the synthetic frame
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import youtube_video_memory as VM                       # noqa: E402
import test_youtube_video_rag_harvester as TH           # noqa: E402

MASTER = ROOT / "data" / "hojaiga_master_rag.db"
MASTER_STAT = (MASTER.stat().st_size, MASTER.stat().st_mtime) if MASTER.exists() else None

SEGS = [{"text": "Now click File to open the menu.", "start": 2.0, "duration": 2.0},
        {"text": "Then click New Project from the list.", "start": 5.0, "duration": 2.0},
        {"text": "Adjust the layer settings on the left.", "start": 7.5, "duration": 2.0},
        {"text": "Finally press Ctrl+S and the Save As dialog appears.", "start": 9.6, "duration": 2.0}]
MENU = [("File", 8), ("Edit", 60), ("View", 112), ("Help", 164)]


def stub_screen(path: str):
    """What the scanner would read on the synthetic frames, by the frame's second (the file name ends with it)."""
    t = int(os.path.splitext(os.path.basename(path))[0].rsplit("_", 1)[1])
    els = [{"label": n, "role": "text", "box": [x - 2, 6, 40, 22], "conf": 0.9} for n, x in MENU] + [{"label": "Layer 0 settings", "role": "text", "box": [10, 208, 150, 16], "conf": 0.8}]
    if 4 <= t < 9:
        els += [{"label": "New Project", "role": "text", "box": [30, 40, 100, 20], "conf": 0.9}, {"label": "Open", "role": "text", "box": [30, 70, 60, 20], "conf": 0.9}]
    if t >= 9:
        els += [{"label": "Save As", "role": "text", "box": [200, 110, 90, 24], "conf": 0.9}]
    for i, e in enumerate(els, 1):
        e["id"] = i
    return {"size": [640, 360], "elements": els}


@contextlib.contextmanager
def memory(embedder: str = "hash"):
    td = tempfile.mkdtemp(prefix="vmem_t_")
    clip = os.path.join(td, "clip.mp4")
    TH.make_clip(clip)
    mem = VM.VideoMemory(os.path.join(td, "mem.db"), embedder)
    old = VM.WINDOW
    VM.WINDOW = (3.0, 5.0)
    try:
        yield td, clip, mem
    finally:
        VM.WINDOW = old
        mem.close()
        shutil.rmtree(td, ignore_errors=True)


def add(mem, clip, app="TestApp", video_id="vid1", **kw):
    return VM.ingest_file(mem, clip, app, "Saving a project", screen_fn=stub_screen, transcribe_fn=lambda p, m: list(SEGS), video_id=video_id, source="youtube", **kw)


class Offline(unittest.TestCase):
    """Every test runs with the network closed."""

    def setUp(self):
        self._real = socket.socket.connect
        socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(OSError("network blocked in tests"))

    def tearDown(self):
        socket.socket.connect = self._real


class M1Speech(Offline):
    def test_windows_and_transcript_files(self):
        old = VM.WINDOW
        VM.WINDOW = (3.0, 5.0)
        try:
            w = VM.windows(SEGS)
        finally:
            VM.WINDOW = old
        self.assertEqual(len(w), 2)
        self.assertIn("New Project", w[0]["text"])
        self.assertIn("Ctrl+S", w[1]["text"])
        with tempfile.TemporaryDirectory() as td:
            srt = Path(td) / "a.srt"
            srt.write_text("1\n00:00:01,000 --> 00:00:03,500\nClick File.\n\n2\n00:00:04,000 --> 00:00:06,000\nThen save.\n", encoding="utf-8")
            segs = VM.read_transcript(str(srt))
            self.assertEqual([(s["text"], s["start"]) for s in segs], [("Click File.", 1.0), ("Then save.", 4.0)])
            j3 = Path(td) / "a.en.json3"
            j3.write_text(json.dumps({"events": [{"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "Open the menu"}]}]}), encoding="utf-8")
            self.assertEqual(VM.read_transcript(str(j3))[0]["text"], "Open the menu")


class M2Alignment(Offline):
    def test_step_and_word_alignment(self):
        with memory() as (td, clip, mem):
            r = add(mem, clip)
            self.assertEqual(r["moments"], 2)
            m = mem.c.execute("SELECT * FROM moments ORDER BY t0").fetchall()
            al = json.loads(m[0]["aligned_json"])
            by = {a["label"]: a for a in al if a["label"]}
            self.assertEqual(set(by), {"File", "New Project"})                                     # click File (menu bar) and click New Project (only on the later frame)
            self.assertEqual(by["File"]["box"], [6, 6, 40, 22])
            self.assertGreater(by["New Project"]["t"], by["File"]["t"])
            al2 = json.loads(m[1]["aligned_json"])
            self.assertEqual([a["hotkey"] for a in al2], ["ctrl+s"])
            words = {w["word"]: w for w in json.loads(m[1]["words_json"])}
            self.assertIn("layer", words)                                                          # spoken AND on screen, with its place
            self.assertEqual(words["layer"]["box"], [10, 208, 150, 16])
            self.assertIn("save", words)
            self.assertNotIn("left", words)                                                        # spoken but not on screen: not aligned

    def test_unseen_spoken_target_is_not_invented(self):
        with memory() as (td, clip, mem):
            segs = [{"text": "Click the Frobnicator button.", "start": 2.0, "duration": 2.0}]
            VM.ingest_file(mem, clip, "TestApp", "x", screen_fn=stub_screen, transcribe_fn=lambda p, m: segs, video_id="v2")
            row = mem.c.execute("SELECT aligned_json FROM moments").fetchone()
            self.assertEqual(json.loads(row[0]), [])

    def test_dots_frame_is_saved_when_asked(self):
        with memory() as (td, clip, mem):
            add(mem, clip, dots=True)
            frames = [r[0] for r in mem.c.execute("SELECT frame FROM moments")]
            self.assertTrue(any(f.endswith("_dots.jpg") and os.path.isfile(f) for f in frames), frames)


class M3Store(Offline):
    def test_store_and_search(self):
        with memory() as (td, clip, mem):
            add(mem, clip)
            n = mem.stats()
            self.assertEqual((n["videos"], n["moments"], n["with_aligned_steps"], n["with_words_on_screen"]), (1, 2, 2, 2))
            again = add(mem, clip)
            self.assertEqual((again["new"], again["skipped"]), (0, 2))                           # idempotent
            self.assertEqual(mem.stats()["moments"], 2)
            top = mem.search("where does he click the new project item")[0]
            self.assertEqual(top["t0"], 2.0)
            self.assertIn("watch?v=vid1&t=2s", top["link"])
            self.assertTrue(top["in_fts"] and top["in_vector_top"])
            top2 = mem.search("save the file shortcut dialog")[0]
            self.assertEqual(top2["t0"], 7.5)
            self.assertEqual(mem.search("save", app="OtherApp"), [])                             # app filter
            self.assertEqual(mem.search("zzzzzz qqqqq", k=1)[0]["video_id"], "vid1")             # vector side still answers when words do not match


class M4Embedder(Offline):
    def test_embedder_mismatch_refused(self):
        with memory() as (td, clip, mem):
            add(mem, clip)
            path = mem.path
            mem.close()
            with self.assertRaises(ValueError):
                VM.VideoMemory(path, "bge")
            VM.VideoMemory(path, "hash").close()
            mem.c = VM.sqlite3.connect(path)                                                      # for the context manager's close()

    @unittest.skipUnless(os.path.isdir(os.path.expanduser("~/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5")), "bge-small not in the local cache")
    def test_bge_ranks_a_paraphrase(self):
        with memory("bge") as (td, clip, mem):
            add(mem, clip)
            top = mem.search("how do I store my work with a keyboard shortcut")[0]
            self.assertEqual(top["t0"], 7.5)                                                      # no shared word with 'Ctrl+S ... Save As dialog' except meaning


class M5Rag(Offline):
    def test_to_rag_needs_confirm_and_reaches_a_temp_rag(self):
        from core_organs.rag import embed as E, storage as ST
        from core_organs.rag.router import Rag
        from core_organs.rag.types import Query
        with memory() as (td, clip, mem):
            add(mem, clip, app="testapp")
            rag = Rag(ST.Storage(os.path.join(td, "ragroot"), E.HashEmbedder()), icons=False)
            self.assertFalse(mem.to_rag(rag)["ingested"])
            self.assertEqual(rag.st.count("knowledge_chunks"), 0)
            r = mem.to_rag(rag, confirm=True)
            self.assertTrue(r["ingested"])
            self.assertGreater(rag.st.count("knowledge_chunks"), 0)
            got = rag.retrieve(Query(text="click new project from the list", app_key="testapp", mode="tutor"))
            self.assertTrue(got.evidence or got.plans)


class M6Offline(Offline):
    def test_gpu_hidden_torch_not_loaded_master_untouched(self):
        out = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0]=[r'%s', r'%s']; import youtube_video_memory as m, os; mem=m.VideoMemory(os.path.join(__import__('tempfile').mkdtemp(),'x.db')); "
                              "print(os.environ['CUDA_VISIBLE_DEVICES'], 'torch' in sys.modules)" % (ROOT, ROOT / "All codes")], capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["-1", "False"])
        if MASTER.exists():
            self.assertEqual((MASTER.stat().st_size, MASTER.stat().st_mtime), MASTER_STAT)

    def test_real_ocr_reads_the_menu(self):
        with tempfile.TemporaryDirectory() as td:
            import cv2
            p = os.path.join(td, "f_3.jpg")
            cv2.imwrite(p, TH._frame(3.0, (300, 200), False, False))
            labels = {e["label"] for e in VM.screen_ocr(p)["elements"]}
            self.assertTrue({"File", "Edit", "View", "Help"} & labels, labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
