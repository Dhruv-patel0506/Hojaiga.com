"""
test_youtube_seeder_tagger.py -- offline tests of youtube_app_seeder.py and youtube_pattern_mix_tagger.py. No network, no GPU, temp folders only.

    python test_youtube_seeder_tagger.py            (or: python -m unittest test_youtube_seeder_tagger -v)

  S1 filter   concept pages ("Foundation", "Online marketplace") are dropped, products ("Trello", "Google Docs") kept; no control character hides in a regex (the \\b -> backspace mangling)
  S2 wiki 429 a Wikipedia refusal ends that source cleanly and keeps what was found
  S3 order    the shuffle is deterministic and de-duplicates by normalised name
  S4 files    a run with fewer sources never shrinks an earlier list; names are written one per line
  S5 mix      first pattern = raw winner; a second needs >= 60% of the first AND >= 1.5 x its mean; too little text is reported, not guessed
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import youtube_app_seeder as S              # noqa: E402
import youtube_pattern_mix_tagger as T      # noqa: E402


class SeederTests(unittest.TestCase):
    def test_s1_filter(self):
        for bad in ("Foundation", "Employment website", "Online marketplace", "Foundation 6"):
            self.assertTrue(S._CONCEPT.search(bad), bad)
        for good in ("Trello", "Google Docs", "Notion", "Blender"):
            self.assertFalse(S._CONCEPT.search(good), good)
        for rx in (S._CONCEPT, S._NOISE, S._INFRA, S._NAME_OK):
            self.assertIsNone(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", rx.pattern), rx.pattern[:40])

    def test_s2_wiki_429(self):
        calls = []

        def fake(params):
            calls.append(params["cmtitle"])
            if len(calls) == 1:
                return {"query": {"categorymembers": [{"title": "Trello"}, {"title": "List of web apps"}, {"title": "Notion (software)"}, {"title": "Foundation"}]}}
            raise S.WikiBlocked("30")
        old = S._wiki_json
        S._wiki_json = fake
        try:
            out = S.seed_wikipedia("web_app", 100, 1)
        finally:
            S._wiki_json = old
        self.assertEqual(out, ["Trello", "Notion"])
        self.assertLessEqual(len(calls), 2)                              # it did not keep asking

    def test_s3_order(self):
        names = ["Blender", "blender", "GIMP", "Audacity", "Blender "]
        a, b = S.stable_shuffle(names), S.stable_shuffle(list(reversed(names)))
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)

    def test_s4_files_are_additive(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "apps_app.txt").write_text("Blender\nGIMP\nFoundation\n", encoding="utf-8")
            rc = S.main(["--sources", "none", "--out-dir", d, "--per-kind", "50"])
            self.assertEqual(rc, 0)
            names = (out / "apps_app.txt").read_text(encoding="utf-8").split()
            self.assertIn("Blender", names)
            self.assertIn("GIMP", names)
            self.assertNotIn("Foundation", names)                        # an old concept page is filtered out on the next run
            self.assertTrue((out / "apps_web_app.txt").is_file())


class TaggerTests(unittest.TestCase):
    BASE = {"file_manager": 0.8, "raster_editor": 0.2, "vector_editor": 0.2, "terminal": 0.3}

    def test_s5_single_and_hybrid(self):
        single = T.mix_from({"raster_editor": 1.5, "file_manager": 0.8, "vector_editor": 0.3}, self.BASE)
        self.assertEqual(single["ranked"][0][0], "raster_editor")
        self.assertFalse(single["hybrid"])                              # file_manager is its usual self (0.8 < 1.5 x 0.8)
        hyb = T.mix_from({"raster_editor": 1.5, "file_manager": 0.8, "vector_editor": 1.0}, self.BASE)
        self.assertTrue(hyb["hybrid"])
        self.assertEqual([a for a, _ in hyb["ranked"]], ["raster_editor", "vector_editor"])

    def test_s5_too_little_text_is_reported(self):
        self.assertEqual(T.mix_from(None, self.BASE)["status"], "too_little_text")
        self.assertEqual(T.mix_from({}, self.BASE)["status"], "no_signal")

    def test_s5_tag_all_on_temp_transcripts(self):
        with tempfile.TemporaryDirectory() as d:
            h = Path(d)
            (h / "transcripts_json").mkdir()
            seg = [{"text": "now click the layer panel and pick the brush tool on the canvas to paint " * 4, "start": 0, "duration": 5}] * 6
            (h / "transcripts_json" / "demo__abc.json").write_text(json.dumps(seg), encoding="utf-8")
            rep = T.tag_all(h)
            self.assertEqual(rep["apps"], 1)
            row = json.loads((h / "youtube_rag" / "app_pattern_mix.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["app_key"], "demo")
            self.assertIn(row["status"], ("ok", "no_signal"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
