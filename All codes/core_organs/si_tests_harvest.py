"""
si_tests_harvest -- tests for Checkpoint 3 (harvest/): the data pipeline that feeds the RAG. All offline: the network is injected (fake Net), videos are synthetic, roots are temp dirs.

  HV1  master harvester: seeds first and matched to Winget ids, the REAL index schema (no Tags column), recent-first extras with junk excluded, honest per-video statuses, cache, resume, stop on block, workbook merge
  HV2  hotkeys / macros harvester: robots.txt respected (denied or unreadable = not fetched), table parsing, tldr parsing, model fallback off by default, sheets 3-4 + JSONL
  HV3  bridge: shortcut normalisation, trust by source (never verified), command_ids only where the lexicon knows, script/com/cli rows with inferred slots and the sandbox, idempotent
  HV4  bridge: transcripts + sheet-2 titles -> Sub-RAG 3 with citations, grounded steps, idempotent
  HV5  video pipeline: scene changes at the right seconds, delta boxes over what changed, pre/post frames saved, nothing detected in a still video, action moments from the transcript only
  HV6  SoM + explain: numbered elements read from a real frame, the delta-box rescan finds the new menu in full-frame coordinates, training pairs are well-formed, grounded only when the target matches, dedup
  HV7  paths: HOJAIGA_HARVEST_DIR wins; an unmounted storage root falls back and says so
  HV8  shortcut-table parsing finds the key column by content (regression for the votes-column bug found in the first live scrape)
  HV9  data-quality gates found on real footage: off-topic videos quarantined, loose verbs are not UI actions, audit + purge, one instruction labels one change
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore

WINGET_FIXTURE = ('\ufeff"PackageId","Version","Name","LastUpdate"\n'
                  '"Notepad.Plus","1","Notepad","2020-01-01 00:00:00Z"\n'
                  '"Obsproject.OBSStudio","30","OBS Studio","2026-10-01 00:00:00Z"\n'
                  '"Acme.Newest","1","Acme Draw Pro","2026-10-14 00:00:00Z"\n'
                  '"Acme.Older","1","Acme Paint Studio","2026-05-01 00:00:00Z"\n'
                  '"Microsoft.VCRedist","14","Microsoft Visual C++ Redistributable","2026-10-15 00:00:00Z"\n'
                  '"Foo.Font","1","Fancy Font Pack","2026-10-13 00:00:00Z"\n'
                  '"Z.Tiny","1","ab","2026-10-12 00:00:00Z"\n')


class _Dir:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="hv_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def fake_net(pages=None, transcripts=None, searches=None):
    """A Net whose every call is recorded. pages: url -> bytes; transcripts: video_id -> segments | Exception; searches: substring -> [videos]."""
    from core_organs.harvest.free_master_harvester import Net
    log = {"http": [], "search": [], "transcript": [], "sleep": 0}
    pages = pages or {}
    transcripts = transcripts or {}

    def http_get(url):
        log["http"].append(url)
        return pages.get(url)

    def search(q, n):
        log["search"].append(q)
        for k, v in (searches or {}).items():
            if k.lower() in q.lower():
                return v
        return []

    def transcript(vid, langs):
        log["transcript"].append(vid)
        t = transcripts.get(vid)
        if isinstance(t, Exception):
            raise t
        return t or []

    def sleep(s):
        log["sleep"] += 1
    return Net(http_get, search, transcript, sleep), log


def run_hv1() -> "TestOutcome":
    """HV1: master harvester against fixtures"""
    import pandas as pd
    from core_organs.harvest import free_master_harvester as M
    vids = [{"id": "v_short", "title": "too short", "duration": 30, "view_count": 999999, "uploader": "x"}, {"id": "v_ok1", "title": "Notepad tutorial", "duration": 600, "view_count": 500, "uploader": "a"},
            {"id": "v_ok2", "title": "Notepad tips", "duration": 900, "view_count": 900, "uploader": "b"}, {"id": "v_nosub", "title": "no captions", "duration": 700, "view_count": 100, "uploader": "c"}]
    segs = [{"text": "click File", "start": 1.0, "duration": 2.0}, {"text": "press Ctrl+S", "start": 4.0, "duration": 2.0}]
    with _Dir() as root:
        net, log = fake_net({M.WINGET_CSV: WINGET_FIXTURE.encode("utf-8")}, {"v_ok1": segs, "v_ok2": segs, "v_nosub": M.TranscriptUnavailable("NoTranscriptFound")}, {"notepad": vids})
        net_lang, _ = fake_net({M.WINGET_CSV: WINGET_FIXTURE.encode("utf-8")}, {"hi_only": M.TranscriptUnavailable("other:hi,ta")})
        lang = M.fetch_transcript(net_lang, root, "notepad", "hi_only")
        plan = M.build_app_list(net, limit=40)
        names = [a["app_name"] for a in plan["apps"]]
        extras = [a for a in plan["apps"] if a["source"] == "winget"]
        np_row = next(a for a in plan["apps"] if a["app_name"] == "Notepad")
        obs_row = next(a for a in plan["apps"] if a["app_name"] == "OBS Studio")
        rep = M.run_harvester(max_apps=1, videos_per_app=3, net=net, root=root, delay_s=0)
        rows = pd.read_excel(M.workbook_path(root), sheet_name=M.SHEET_VIDEOS)
        st = dict(zip(rows["video_id"], rows["transcript_status"]))
        files = sorted(os.listdir(os.path.join(root, "transcripts_json")))
        n_t = len(log["transcript"])
        rep2 = M.run_harvester(max_apps=1, videos_per_app=3, net=net, root=root, delay_s=0)             # same batch again: the app is done, nothing is fetched
        n_after_rerun = len(log["transcript"])
        rep3 = M.run_harvester(max_apps=1, videos_per_app=3, net=net, root=root, delay_s=0, only_apps=["Notepad"], start=0)
        n_before_state_loss = len(log["transcript"])
        os.remove(os.path.join(root, "harvest_state.json"))
        rep4 = M.run_harvester(max_apps=1, videos_per_app=3, net=net, root=root, delay_s=0)             # state lost, files kept: transcripts come from cache, no new fetches
        rows4 = pd.read_excel(M.workbook_path(root), sheet_name=M.SHEET_VIDEOS)
        apps_sheet = pd.read_excel(M.workbook_path(root), sheet_name=M.SHEET_APPS)
        # a blocked address stops the run instead of hammering
        net_b, log_b = fake_net({M.WINGET_CSV: WINGET_FIXTURE.encode("utf-8")}, {"v_ok1": PermissionError("RequestBlocked"), "v_ok2": segs}, {"notepad": vids, "obs": [{"id": "v_ok2", "title": "x", "duration": 600, "view_count": 1}]})
        with _Dir() as root_b:
            rep_b = M.run_harvester(max_apps=2, videos_per_app=2, net=net_b, root=root_b, delay_s=0)
        # winget unreachable: only the seed apps, and it SAYS so
        net_n, _ = fake_net({})
        plan_n = M.build_app_list(net_n, limit=40)
        checks = {"seed_apps_come_first": names[:len(M.CORE_APPS)] == [a["app_name"] for a in M.CORE_APPS],
                  "seed_matched_to_winget_ids": np_row["package_id"] == "Notepad.Plus" and obs_row["package_id"] == "Obsproject.OBSStudio",
                  "real_index_schema_parsed_without_tags": plan["winget_ok"] and plan["winget_rows"] == 7,
                  "extras_newest_first": [a["app_name"] for a in extras][:2] == ["Acme Draw Pro", "Acme Paint Studio"],
                  "junk_excluded": not any(x in names for x in ("Microsoft Visual C++ Redistributable", "Fancy Font Pack", "ab")),
                  "extras_are_unclassified_tier": all(a["tier"] == -1 for a in extras),
                  "short_video_filtered_and_statuses_honest": "v_short" not in st and st.get("v_ok1") == "Downloaded" and st.get("v_nosub") == "No_Subtitles",
                  "other_language_is_named_not_hidden": lang["status"] == "Other_Language:hi,ta" and lang["segments"] == 0,
                  "transcripts_on_disk": files == ["notepad__v_ok1.json", "notepad__v_ok2.json"],
                  "done_apps_are_skipped": rep2["stats"]["apps_skipped_done"] == 1 and n_after_rerun == n_t and n_before_state_loss == n_t,
                  "cache_used_after_state_loss": rep4["stats"]["cached"] == 2 and len(log["transcript"]) == n_before_state_loss + 1,       # only the no-subtitles video is tried again
                  "workbook_merged_not_duplicated": len(rows4) == 3 and len(apps_sheet) == len(plan["apps"]),
                  "block_stops_the_run": rep_b["blocked"] and rep_b["stats"]["blocked"] == 1 and rep_b["stats"]["apps_processed"] == 0 and "obs" not in " ".join(log_b["search"]).lower(),
                  "winget_down_is_reported": not plan_n["winget_ok"] and len(plan_n["apps"]) == len(M.CORE_APPS)}
        return _verdict(checks, f"statuses={st} extras={[a['app_name'] for a in extras]}")


def run_hv2() -> "TestOutcome":
    """HV2: hotkeys and macros harvester"""
    import pandas as pd
    from core_organs.harvest import free_hotkeys_and_macros_harvester as K
    K._ROBOTS.clear()
    html = b"<html><body><table><tr><th>Shortcut</th><th>Action</th></tr><tr><td>Ctrl+B</td><td>Bold the selection</td></tr><tr><td>Ctrl+I</td><td>Italicise the selection</td></tr><tr><td>x</td><td>no</td></tr></table></body></html>"
    allow = b"User-agent: *\nAllow: /\n"
    deny = b"User-agent: *\nDisallow: /\n"
    tldr = b"# tar\n\n- Create an archive:\n\n`tar cf {{target.tar}} {{file}}`\n\n- Extract an archive:\n\n`tar xf {{source.tar}}`\n"
    with _Dir() as root:
        net_ok, log_ok = fake_net({"https://defkey.com/robots.txt": allow, "https://defkey.com/notepad-shortcuts": html, "https://www.shortcutworld.com/robots.txt": deny,
                                   "https://raw.githubusercontent.com/tldr-pages/tldr/main/pages/common/notepad.md": tldr})
        got = K.scrape_public_shortcuts("Notepad", net_ok, delay_s=0)
        shortcutworld_fetched = any("shortcutworld.com/notepad" in u for u in log_ok["http"])
        K._ROBOTS.clear()
        net_deny, log_deny = fake_net({"https://defkey.com/robots.txt": deny, "https://defkey.com/notepad-shortcuts": html})
        denied = K.scrape_public_shortcuts("Notepad", net_deny, delay_s=0)
        page_fetched_when_denied = any(u.endswith("notepad-shortcuts") for u in log_deny["http"])
        K._ROBOTS.clear()
        net_none, log_none = fake_net({"https://defkey.com/notepad-shortcuts": html})                      # robots.txt unreadable -> conservative
        unreadable = K.scrape_public_shortcuts("Notepad", net_none, delay_s=0)
        tl = K.fetch_tldr("Notepad", net_ok, delay_s=0)
        K._ROBOTS.clear()
        rep = K.run_hotkeys_and_macros_harvester(["Notepad"], net=net_ok, root=root, delay_s=0)
        sheets = pd.read_excel(K.workbook_path(root), sheet_name=None)
        jl = [json.loads(l) for l in open(rep["jsonl"], encoding="utf-8")]
        called_model = []
        orig = K.ollama_shortcuts
        K.ollama_shortcuts = lambda *a, **k: called_model.append(1) or []
        K._ROBOTS.clear()
        K.run_hotkeys_and_macros_harvester(["Notepad"], net=net_none, root=root, delay_s=0, write_workbook=False)
        K.ollama_shortcuts = orig
        checks = {"allowed_site_parsed": [g["shortcut"] for g in got] == ["Ctrl+B", "Ctrl+I"] and all(g["source"] == "web_table" for g in got),
                  "disallowed_site_never_fetched": denied == [] and not page_fetched_when_denied and not shortcutworld_fetched,
                  "unreadable_robots_means_not_allowed": unreadable == [],
                  "tldr_commands_parsed": [t["task_pattern"] for t in tl] == ["Create an archive", "Extract an archive"] and tl[0]["source"] == "tldr",
                  "seeds_present": {"Blender 3D", "AutoCAD"} <= set(sheets["3_Hotkeys_Matrix"]["app_name"]) and len(sheets["4_Superhuman_Macros_CLI"]) >= 5,
                  "sheets_and_jsonl_agree": len(jl) == rep["hotkeys"] + rep["macros"] and {r["rag_sub_table"] for r in jl} == {"sub_rag4_hotkeys", "sub_rag4_superhuman_macros"},
                  "model_fallback_is_off_by_default": called_model == []}
        return _verdict(checks, f"scraped={len(got)} tldr={len(tl)} jsonl={len(jl)}")


def run_hv3() -> "TestOutcome":
    """HV3: hotkeys and macros -> fast_paths"""
    from core_organs.harvest import bridge as B
    from core_organs.harvest.free_master_harvester import app_key_of
    from core_organs.rag.types import Query
    from si_tests_rag import _Env
    kind_b, pay_b = B.norm_keys("Ctrl + B")
    kind_g, pay_g = B.norm_keys("G then Z then {distance}")
    kind_l, pay_l = B.norm_keys("L + Enter")
    kind_f, pay_f = B.norm_keys("F12")
    blender = app_key_of("Blender 3D")
    with _Env() as R:
        R.lex.add_command(blender, "Extrude Region")
        rows = [{"app_name": "Blender 3D", "shortcut": "E", "action": "Extrude Region", "category": "Modeling", "source": "seed"},
                {"app_name": "Blender 3D", "shortcut": "G then Z then {distance}", "action": "Move the selection along Z by an exact distance", "category": "3D", "source": "seed"},
                {"app_name": "Blender 3D", "shortcut": "Ctrl+Q", "action": "Quit without asking", "category": "x", "source": "web_table"},
                {"app_name": "Blender 3D", "shortcut": "Ctrl+Alt+Z", "action": "Undo history", "category": "x", "source": "llm"},
                {"app_name": "Blender 3D", "shortcut": "", "action": "no key", "source": "seed"}]
        hrep = B.ingest_hotkeys(R, rows)
        from core_organs.harvest.free_hotkeys_and_macros_harvester import SUPERHUMAN_MACROS_SEED
        mrep = B.ingest_macros(R, SUPERHUMAN_MACROS_SEED)
        again = B.ingest_hotkeys(R, rows)
        n_rows = R.st.count("fast_paths")
        e = R.fast.by_command(blender, f"{blender}:extrude region")
        move = R.fast.by_goal(blender, "move the selection along Z by an exact distance 4")
        web = [x for x in R.fast.by_goal(blender, "quit without asking") if x.trust == "web"]
        llm = [x for x in R.fast.by_goal(blender, "undo history") if x.trust == "llm"]
        cube = R.fast.by_goal(blender, "Create a beveled cube of a given size, smooth shaded, and save it as a .blend file size 3 bevel_width 0.1")
        script = next((x for x in cube if x.kind == "script"), None)
        ac = app_key_of("AutoCAD")
        scr = next((x for x in R.fast.by_goal(ac, "Draw a rectangle and extrude the closed polyline into a 3D solid height 300 width 1000 depth 800") if x.kind == "script"), None)
        com = [x for x in R.fast.by_goal(app_key_of("Microsoft Excel"), "Create a sheet with a header row and a SUM formula") if x.kind == "com"]
        checks = {"shortcut_normalisation": (kind_b, pay_b) == ("hotkey", "ctrl+b") and (kind_g, pay_g) == ("chord_seq", "g z {distance}") and (kind_l, pay_l) == ("chord_seq", "l enter") and (kind_f, pay_f) == ("hotkey", "f12"),
                  "rows_without_a_key_are_skipped": hrep["rows"] == 4,
                  "commands_from_published_tables_only": hrep["with_command"] == 3 and hrep.get("commands_created") == 2 and bool(e) and e[0].payload["payload"] == "e",
                  "model_written_rows_create_no_command": R.lex.best(blender, "Undo history") is None and bool(llm) and not llm[0].command_ids,
                  "seed_hotkey_is_a_probe_not_verified": e[0].payload["probe"] and not e[0].payload["verified"],
                  "web_and_llm_rows_carry_their_trust": bool(web) and web[0].payload["probe"] and bool(llm) and llm[0].payload["probe"],
                  "chord_sequence_with_a_slot": bool(move) and move[0].kind == "chord_seq" and "distance" in move[0].payload["missing"] or bool(move) and move[0].payload["payload"].startswith("g z"),
                  "macros_become_scripts_with_a_sandbox": mrep["rows"] == 5 and script is not None and script.payload["sandbox"] == "scripting_route",
                  "slots_inferred_and_reported_not_guessed": script is not None and "output_blend_path" in script.payload["missing"] and script.payload["probe"],
                  "autocad_scr_template_filled": scr is not None and "300" in scr.payload["payload"] and "1000" in scr.payload["payload"],
                  "com_template_is_kind_com": bool(com),
                  "re_ingest_is_idempotent": again["rows"] == 4 and R.st.count("fast_paths") == n_rows}
        return _verdict(checks, f"fast_paths={n_rows} script_missing={script.payload['missing'] if script else None}")


def run_hv4() -> "TestOutcome":
    """HV4: transcripts -> Sub-RAG 3"""
    import pandas as pd
    from core_organs.harvest import bridge as B, free_master_harvester as M
    from core_organs.rag.types import Query
    from si_tests_rag import _Env
    segs = [{"text": "now click the File menu", "start": 1.0, "duration": 3.0}, {"text": "then choose Save As", "start": 5.0, "duration": 3.0}, {"text": "and press Ctrl+S to save", "start": 9.0, "duration": 3.0}]
    with _Dir() as root, _Env() as R:
        os.makedirs(os.path.join(root, "transcripts_json"))
        json.dump(segs, open(os.path.join(root, "transcripts_json", "notepad__vidA.json"), "w"))
        open(os.path.join(root, "transcripts_json", "garbage.json"), "w").write("{}")
        open(os.path.join(root, "transcripts_json", "notepad__bad.json"), "w").write("not json")
        M.write_sheets(root, [{"app_name": "Notepad", "app_key": "notepad", "tier": 0}], [{"app_name": "Notepad", "app_key": "notepad", "video_id": "vidA", "title": "Notepad basics", "transcript_status": "Downloaded"}])
        for n in ("File", "Save As", "Save"):
            R.lex.add_command("notepad", n)
        rep = B.ingest_transcripts(R, root)
        rep2 = B.ingest_transcripts(R, root)
        n_chunks = R.st.count("knowledge_chunks")
        ev = R.proc.query("notepad", "how do I save as", k=3)
        procs = R.proc.find_procedures("notepad", "Notepad basics")
        checks = {"files_ingested_and_junk_skipped": rep["files"] == 1 and rep["skipped"] == 2,
                  "citation_is_video_and_span": bool(ev) and ev[0].citation.startswith("vidA@"),
                  "steps_grounded_to_known_commands": bool(procs) and {"notepad:file", "notepad:save as"} <= set(procs[0].command_ids),
                  "title_from_sheet_2": bool(procs) and procs[0].text == "Notepad basics",
                  "reingest_is_idempotent": rep2["files"] == 1 and R.st.count("knowledge_chunks") == n_chunks}
        return _verdict(checks, f"chunks={n_chunks} procs={[(p.text, p.command_ids) for p in procs]}")


def _synthetic_video(path: str):
    import cv2
    import numpy as np

    def frame(t):
        f = np.full((360, 640, 3), 255, np.uint8)
        cv2.rectangle(f, (0, 0), (640, 70), (235, 235, 235), -1)
        for x, name in ((20, "File"), (140, "Edit"), (260, "View")):
            cv2.putText(f, name, (x, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
        if 3.0 <= t < 6.0:
            cv2.rectangle(f, (10, 75), (230, 215), (250, 250, 250), -1)
            cv2.rectangle(f, (10, 75), (230, 215), (60, 60, 60), 2)
            for i, name in enumerate(("New", "Open", "Save")):
                cv2.putText(f, name, (25, 112 + i * 44), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        if t >= 6.0:
            cv2.rectangle(f, (170, 100), (470, 270), (245, 245, 245), -1)
            cv2.rectangle(f, (170, 100), (470, 270), (40, 40, 40), 2)
            cv2.putText(f, "Save As", (200, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
        return f
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    if not w.isOpened():
        return False
    for i in range(90):
        w.write(frame(i / 10))
    w.release()
    return True


def run_hv5() -> "TestOutcome":
    """HV5: video pipeline -- scene changes, delta boxes, keyframes, action moments"""
    try:
        import cv2
        import numpy as np
        from core_organs.harvest import video_pipeline as VP
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    with _Dir() as d:
        p = os.path.join(d, "v.mp4")
        if not _synthetic_video(p):
            return TestOutcome(False, "ENV-BLOCKED: no mp4v video writer")
        ev = VP.scene_changes(p)
        kf = VP.extract_keyframes(p, os.path.join(d, "frames"), "vid")
        # a video in which nothing happens has no events
        q = os.path.join(d, "still.mp4")
        w = cv2.VideoWriter(q, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
        for _ in range(50):
            w.write(np.full((180, 320, 3), 200, np.uint8))
        w.release()
        still = VP.scene_changes(q)
        a = np.full((100, 100, 3), 255, np.uint8)
        b = a.copy()
        b[20:40, 30:70] = 0
        box = VP.changed_region(a, b)
        none = VP.changed_region(a, a)
        segs = [{"text": "hi everyone welcome back to the channel", "start": 0.0, "duration": 3.0}, {"text": "now click the File menu", "start": 10.0, "duration": 2.0},
                {"text": "and choose Save As", "start": 12.0, "duration": 2.0}, {"text": "this is a nice feature really", "start": 30.0, "duration": 3.0}, {"text": "press Ctrl+S", "start": 60.0, "duration": 2.0}]
        moments = VP.action_moments(segs)
        e0 = ev[0] if ev else {"bbox": None}
        bb = e0["bbox"] or [0, 0, 0, 0]
        checks = {"two_changes_at_three_and_six_seconds": [round(e["t"]) for e in ev] == [3, 6],
                  "delta_box_covers_the_menu_that_opened": bb[0] <= 12 and bb[1] <= 80 and bb[0] + bb[2] >= 225 and bb[1] + bb[3] >= 210,
                  "pre_and_post_frames_saved": len(kf) == 2 and all(os.path.isfile(k["pre"]) and os.path.isfile(k["post"]) for k in kf),
                  "still_video_has_no_events": still == [],
                  "changed_region_boxes_the_change": box is not None and 25 <= box[0] <= 32 and 15 <= box[1] <= 22 and box[2] >= 40 and none is None,
                  "action_moments_only_where_something_is_done": len(moments) == 2 and "File" in moments[0]["text"] and "Ctrl+S" in moments[1]["text"] and moments[0]["t0"] <= 8.0 and moments[0]["t1"] >= 14.0}
        return _verdict(checks, f"events={[(e['t'], e['bbox']) for e in ev]} moments={[(m['t0'], m['t1']) for m in moments]}")


def run_hv6() -> "TestOutcome":
    """HV6: Set-of-Marks of real frames + training pairs"""
    try:
        import cv2
        from core_organs.harvest import video_pipeline as VP, video_explain as VE
        from core_organs.professor.candidates import tesseract_ok
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    if not tesseract_ok():
        return TestOutcome(False, "ENV-BLOCKED: Tesseract not installed")
    from si_tests_rag import _Env
    segs = [{"text": "now click the File menu", "start": 0.5, "duration": 2.0}, {"text": "this is just talking about nothing important at all", "start": 4.0, "duration": 1.0},
            {"text": "then press Ctrl+Shift+S", "start": 5.0, "duration": 0.8}]
    with _Dir() as d, _Env() as R:
        p = os.path.join(d, "v.mp4")
        if not _synthetic_video(p):
            return TestOutcome(False, "ENV-BLOCKED: no mp4v video writer")
        kf = VP.extract_keyframes(p, os.path.join(d, "frames"), "vid")
        som = VP.som_of_frame(kf[0]["pre"])
        labels = [e["label"].lower() for e in som["elements"]]
        sub = VP.som_of_frame(kf[0]["post"], region=tuple(kf[0]["bbox"]))
        sub_labels = {e["label"].lower(): e["box"] for e in sub["elements"]}
        out = os.path.join(d, "pairs.jsonl")
        rep = VE.explain_video(R, "notepad", "vid", segs, kf, out_jsonl=out, root=d)
        rows = [json.loads(l) for l in open(out, encoding="utf-8")]
        rep2 = VE.explain_video(R, "notepad", "vid", segs, kf, out_jsonl=out, root=d)
        rows2 = [json.loads(l) for l in open(out, encoding="utf-8")]
        first = rows[0] if rows else {"messages": [{}, {"content": [{}]}, {"content": [{"text": "[]"}]}], "meta": {}}
        act = json.loads(first["messages"][2]["content"][0]["text"])[0] if rows else {}
        file_el = next((e for e in som["elements"] if e["label"].lower() == "file"), None)
        # deterministic matching logic with a fake SoM (independent of OCR quality)
        fake = {"elements": [{"id": 7, "label": "File", "role": "text", "box": [0, 0, 1, 1]}, {"id": 8, "label": "Save As...", "role": "text", "box": [0, 0, 1, 1]}, {"id": 9, "label": "", "role": "icon", "box": [0, 0, 1, 1]}]}
        checks = {"elements_are_numbered_and_named": len(som["elements"]) >= 3 and {"file", "edit", "view"} <= set(labels) and "capture:provided" in som["tiers_used"],
                  "no_model_or_gpu_used": all("vlm" not in t.lower() for t in som["tiers_used"]),
                  "delta_rescan_finds_the_new_menu": {"new", "open", "save"} <= set(sub_labels) and sub_labels["open"][0] < 120 and 90 <= sub_labels["open"][1] <= 190,
                  "pairs_written_one_per_step_with_a_step_nearby": rep["pairs"] == 2 and rep["no_step_nearby"] == 0 and len(rows) == 2,
                  "click_pair_targets_the_file_element": file_el is not None and act.get("action") == "click" and act.get("target_id") == file_el["id"] and first["meta"]["grounded"],
                  "hotkey_pair_carries_the_chord": json.loads(rows[1]["messages"][2]["content"][0]["text"])[0].get("hotkey") == "ctrl+shift+s",
                  "expectation_comes_from_the_delta_scan": "new on screen" in act.get("verify_expectation", "") and "Open" in act.get("verify_expectation", ""),
                  "record_is_unsloth_shaped": [m["role"] for m in first["messages"]] == ["system", "user", "assistant"] and first["messages"][1]["content"][0]["type"] == "image" and "Elements:" in first["messages"][1]["content"][1]["text"],
                  "rerun_adds_nothing": rep2["duplicates"] == 2 and rep2["pairs"] == 0 and len(rows2) == len(rows),
                  "transcript_went_to_the_rag_too": rep.get("rag_chunks", 0) >= 1 and R.st.count("knowledge_chunks") >= 1,
                  "match_exact_label": VE.match_element(fake, "file")["id"] == 7,
                  "match_contained_words": VE.match_element(fake, "Save As")["id"] == 8,
                  "no_match_is_none_not_a_guess": VE.match_element(fake, "Quit") is None and VE.match_element(fake, "") is None}
        return _verdict(checks, f"som={len(som['elements'])} labels={labels[:6]} seconds={som['seconds']} pairs={rep['pairs']}")


def run_hv7() -> "TestOutcome":
    """HV7: harvest directory resolution"""
    from core_organs.harvest import paths
    from core_organs.rag import storage as ST
    old = {k: os.environ.get(k) for k in ("HOJAIGA_HARVEST_DIR", "AI_STORAGE_ROOT")}
    fb = tempfile.mkdtemp(prefix="hv_fb_")
    old_def = ST.DEFAULT_ROOT
    try:
        os.environ["HOJAIGA_HARVEST_DIR"] = os.path.join(fb, "explicit")
        d1, deg1 = paths.harvest_dir()
        os.environ.pop("HOJAIGA_HARVEST_DIR")
        from si_tests_rag import _free_drive
        os.environ["AI_STORAGE_ROOT"] = _free_drive()
        ST.DEFAULT_ROOT = os.path.join(fb, "default")
        d2, deg2 = paths.harvest_dir()
        checks = {"explicit_dir_wins": d1.endswith("explicit") and deg1 == [] and os.path.isdir(os.path.join(d1, "transcripts_json")),
                  "unmounted_root_falls_back_under_the_default": d2.startswith(os.path.join(fb, "default")) and d2.endswith("harvest") and os.path.isdir(os.path.join(d2, "frames")),
                  "fallback_is_reported": any(x.startswith("storage_root_missing:") for x in deg2)}
        return _verdict(checks, f"{d2} {deg2}")
    finally:
        ST.DEFAULT_ROOT = old_def
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(fb, ignore_errors=True)


def run_hv8() -> "TestOutcome":
    """HV8: shortcut-table parsing finds the key column by CONTENT (regression: a votes column was stored as the shortcut and the keys as its action)"""
    from bs4 import BeautifulSoup
    from core_organs.harvest import free_hotkeys_and_macros_harvester as K
    html = ("<table class='shortcutTable'>"
            "<tr><td>5</td><td>Alt + 1</td><td>Switch to Standard mode</td><td></td></tr>"
            "<tr><td>0</td><td>Ctrl + M</td><td>Store in <u>m</u>emory</td><td></td></tr>"
            "<tr><td>-1</td><td>F3</td><td>Select DEG</td><td></td></tr>"
            "<tr><td>2</td><td>Ctrl + ↑  Shift + D</td><td>Move up or duplicate</td><td></td></tr>"
            "<tr><td>0</td><td>E</td><td>Extrude region</td><td></td></tr>"
            "<tr><td>1</td><td>⌥⌃</td><td>Select Xor</td><td></td></tr>"
            "<tr><th>Keys</th><th>Action</th></tr><tr><td>nothing here</td><td>just words about the application</td></tr></table>"
            "<table><tr><th>Shortcut</th><th>Description</th></tr><tr><td>Ctrl+Shift+Esc</td><td>Open Task Manager</td></tr><tr><td>Win+D</td><td>Show the desktop</td></tr></table>")
    soup = BeautifulSoup(html, "lxml")
    t1, t2 = soup.find_all("table")
    r1, r2 = K.parse_shortcut_table(t1), K.parse_shortcut_table(t2)
    pairs1 = {(r["shortcut"], r["action"]) for r in r1}
    combos = {t: K.is_key_combo(t) for t in ("5", "-1", "Switch to Standard mode", "just words", "Alt + 1", "F12", "Ctrl+Shift+Esc", "Win + D", "E")}
    checks = {"votes_column_is_not_the_shortcut": ("5", "Alt + 1") not in pairs1 and ("Alt + 1", "Switch to Standard mode") in pairs1,
              "mnemonic_underline_joined": ("Ctrl + M", "Store in memory") in pairs1,
              "function_key_and_bare_letter": ("F3", "Select DEG") in pairs1 and ("E", "Extrude region") in pairs1,
              "alternatives_split_into_rows": ("Ctrl + ↑", "Move up or duplicate") in pairs1 and ("Shift + D", "Move up or duplicate") in pairs1,
              "prose_row_and_header_row_dropped": not any("nothing" in r["shortcut"] or r["shortcut"] == "Keys" for r in r1) and len(r1) == 6,
              "votes_row_with_an_unrecognised_key_glyph_is_dropped_not_guessed": not any(r["action"] == "Select Xor" for r in r1),
              "plain_two_column_table_still_works": [(r["shortcut"], r["action"]) for r in r2] == [("Ctrl+Shift+Esc", "Open Task Manager"), ("Win+D", "Show the desktop")],
              "key_combo_predicate": combos == {"5": True, "-1": False, "Switch to Standard mode": False, "just words": False, "Alt + 1": True, "F12": True, "Ctrl+Shift+Esc": True, "Win + D": True, "E": True}
                                     or (not combos["Switch to Standard mode"] and not combos["just words"] and combos["Alt + 1"] and combos["F12"] and combos["Ctrl+Shift+Esc"])}
    return _verdict(checks, f"rows={sorted(pairs1)[:4]}")


def run_hv9() -> "TestOutcome":
    """HV9: data-quality gates found on real footage -- off-topic videos, loose action verbs, audit + purge, one instruction labels one change"""
    import pandas as pd
    from core_organs.harvest import bridge as B, free_master_harvester as M, video_explain as VE, video_pipeline as VP
    from si_tests_rag import _Env
    on = M.on_topic
    mentions = " ".join(["so open the calculator and press the button"] * 6)
    # a harvester run with one on-topic title, one off-topic video, and one whose title is vague but whose speaker keeps naming the app
    segs_plain = [{"text": "click File", "start": 1.0, "duration": 2.0}, {"text": "press Ctrl+S", "start": 4.0, "duration": 2.0}]
    segs_calc = [{"text": "now in the calculator we press the calculator memory button", "start": float(i * 3), "duration": 2.0} for i in range(6)]
    vids = [{"id": "v_title", "title": "Windows Calculator basics", "duration": 600, "view_count": 900, "uploader": "a"},
            {"id": "v_off", "title": "15 Amazing Shortcuts You Aren't Using", "duration": 700, "view_count": 800, "uploader": "b"},
            {"id": "v_vague", "title": "Tips and tricks everyone should know", "duration": 650, "view_count": 700, "uploader": "c"}]
    with _Dir() as root:
        net, _ = fake_net({M.WINGET_CSV: WINGET_FIXTURE.encode("utf-8")}, {"v_title": segs_plain, "v_off": segs_plain, "v_vague": segs_calc}, {"calculator": vids})
        rep = M.run_harvester(max_apps=1, videos_per_app=3, net=net, root=root, delay_s=0, only_apps=["Windows Calculator"])
        rows = pd.read_excel(M.workbook_path(root), sheet_name=M.SHEET_VIDEOS)
        st = dict(zip(rows["video_id"], rows["transcript_status"]))
        kept = sorted(f for f in os.listdir(os.path.join(root, "transcripts_json")) if f.endswith(".json"))
        quarantined = sorted(os.listdir(os.path.join(root, "transcripts_json", "_off_topic"))) if os.path.isdir(os.path.join(root, "transcripts_json", "_off_topic")) else []
    # action moments
    acts = {"use this, but it can come in handy.": False, "use a mac": False, "press Ctrl+S": True, "click the File menu": True, "select it": False, "so you can just type your name": True, "hit M+": False}
    got = {t: VP.is_ui_action(__import__("core_organs.rag.procedures", fromlist=["x"]).extract_steps(t, [t])[0]) if __import__("core_organs.rag.procedures", fromlist=["x"]).extract_steps(t, [t]) else False for t in acts}
    moments = VP.action_moments([{"text": "use this, but it can come in handy", "start": 5.0, "duration": 2.0}, {"text": "now click the File menu", "start": 30.0, "duration": 2.0}, {"text": "use a mac", "start": 60.0, "duration": 1.0}])
    # audit + purge against a RAG that already holds an off-topic video
    with _Dir() as root, _Env() as R:
        os.makedirs(os.path.join(root, "transcripts_json"))
        calc_ok = [{"text": "in the calculator press the calculator memory button to store the value", "start": float(i * 4), "duration": 3.0} for i in range(8)]
        for vid, segs in (("v_good", calc_ok), ("v_bad", [{"text": f"press Windows plus V to open the clipboard {i}", "start": float(i * 4), "duration": 3.0} for i in range(8)])):
            json.dump(segs, open(os.path.join(root, "transcripts_json", f"calculator__{vid}.json"), "w"))
            R.proc.ingest_transcript("calculator", segs, vid, "t")
        M.write_sheets(root, [{"app_name": "Windows Calculator", "app_key": "calculator", "tier": 1}],
                       [{"app_name": "Windows Calculator", "app_key": "calculator", "video_id": "v_good", "title": "Windows Calculator tips", "transcript_status": "Downloaded"},
                        {"app_name": "Windows Calculator", "app_key": "calculator", "video_id": "v_bad", "title": "10 Windows shortcuts", "transcript_status": "Downloaded"}])
        before = R.proc.stats("calculator")["chunks"]
        dry = B.audit_topics(None, root, fix=False)
        still_there = sorted(os.listdir(os.path.join(root, "transcripts_json")))
        fixed = B.audit_topics(R, root, fix=True)
        after = R.proc.stats("calculator")["chunks"]
        gone = R.proc.query("calculator", "open the clipboard windows plus v", k=5)
        kept_q = R.proc.query("calculator", "calculator memory button store the value", k=5)
        synced = R.st.text.count("knowledge_chunks") == R.st.count("knowledge_chunks")
        moved = os.path.isfile(os.path.join(root, "transcripts_json", "_off_topic", "calculator__v_bad.json"))
    # one instruction labels the FIRST change it causes
    som = lambda image, region=None: {"elements": [{"id": 1, "label": "File", "role": "text", "box": [0, 0, 5, 5]}], "seconds": 0.0, "size": [100, 100], "tiers_used": [], "tiers_skipped": []}
    kf = [{"t": 3.0, "pre": "frames/a_pre.jpg", "post": "frames/a_post.jpg", "bbox": [0, 0, 50, 50]}, {"t": 4.0, "pre": "frames/b_pre.jpg", "post": "frames/b_post.jpg", "bbox": [0, 0, 60, 60]},
          {"t": 9.0, "pre": "frames/c_pre.jpg", "post": "frames/c_post.jpg", "bbox": [0, 0, 10, 10]}]
    said = [{"text": "now click the File menu", "start": 2.5, "duration": 1.0}]
    with _Dir() as root, _Env() as R2:
        rep2 = VE.explain_video(R2, "calc", "vidX", said, kf, out_jsonl=os.path.join(root, "p.jsonl"), root=root, som_fn=som, scan_delta=False, ingest=False)
    junk = VE.clean_labels([{"label": l} for l in ("McC", "|||", "a", "Calculator", "calculator", "Programmer", "x1", "Date calculation", "ynVerter", "")])
    checks = {"title_naming_the_app_is_on_topic": on("Windows Calculator", "Secrets of The Windows Calculator") and on("MS Paint", "Intro to Paint for kids"),
              "generic_title_is_off_topic": not on("Windows Calculator", "15 Amazing Shortcuts You Aren't Using") and not on("Windows Calculator", "Stop Using Your Mouse"),
              "a_speaker_who_keeps_naming_the_app_counts": on("Windows Calculator", "Tips", mentions) and not on("Windows Calculator", "Tips", "open the thing and press a button"),
              "app_tokens_drop_generic_words": M.app_tokens("Windows Calculator") == ["calculator"] and M.app_tokens("MS Paint") == ["paint"],
              "harvester_keeps_on_topic_and_quarantines_the_rest": st.get("v_title") == "Downloaded" and st.get("v_off") == "Off_Topic" and st.get("v_vague") == "Downloaded"
                                                                   and kept == ["calculator__v_title.json", "calculator__v_vague.json"] and quarantined == ["calculator__v_off.json"] and rep["stats"]["off_topic"] == 1,
              "loose_verbs_are_not_ui_actions": got == acts,
              "action_moments_skip_ordinary_speech": len(moments) == 1 and "File" in moments[0]["text"],
              "audit_dry_run_changes_nothing": [o["video_id"] for o in dry["off_topic"]] == ["v_bad"] and still_there == ["calculator__v_bad.json", "calculator__v_good.json"],
              "audit_fix_quarantines_and_purges_the_rag": moved and fixed["removed_chunks"] >= 1 and after < before and not any(e.citation.startswith("v_bad") for e in gone),
              "audit_keeps_the_good_video": any(e.citation.startswith("v_good") for e in kept_q),
              "text_and_vector_indexes_stay_in_sync": synced,
              "one_instruction_labels_one_change": rep2["pairs"] == 1 and rep2["step_already_used"] == 1 and rep2["no_step_nearby"] == 1,
              "ocr_debris_is_not_shown_as_what_appeared": junk == ["Calculator", "Programmer", "Date calculation"]}
    return _verdict(checks, f"statuses={st} dry={[o['video_id'] for o in dry['off_topic']]} purged={fixed['removed_chunks']} pairs={rep2['pairs']} junk_out={junk}")


TESTS = [("HV1", run_hv1), ("HV2", run_hv2), ("HV3", run_hv3), ("HV4", run_hv4), ("HV5", run_hv5), ("HV6", run_hv6), ("HV7", run_hv7), ("HV8", run_hv8), ("HV9", run_hv9)]

if __name__ == "__main__":
    only = [a.upper() for a in sys.argv[1:]]
    rc = 0
    for name, fn in TESTS:
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            r = fn()
        except Exception:
            import traceback
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-1500:])
        print(f"[{'PASS' if r.passed else 'FAIL'}] {name} {time.time() - t0:5.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:90]}\n        {r.evidence[:1600]}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
