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
  HV10 clips -> pairs batch driver: planning across videos, resumable, stops on failure streak / time budget, prunes unused frames, dataset report
  HV11 UI-frame gate: verdict parsing, cache, unverified fallback; no pair from a frame that is not a software UI
  HV12 step extraction on the phrasings that broke the first real run
  HV13 local recorder: containment grounding, change detection, a stand-in app driven into click / hotkey / type pairs in the video format
  HV14 captions through yt-dlp (paced, cookie-free, block = stop) + the local speech fallback
  HV15 keyframe pre-filter + normalized token-overlap target matcher
  HV16 the slow YouTube loop (per-app harvest then pairs; target / deadline / audio-refusal stops)
  HV17 failover on a caption refusal: static sources at once, no waiting, no speech recognition
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
            rep_b = M.run_harvester(max_apps=2, videos_per_app=2, net=net_b, root=root_b, delay_s=0, on_block="wait")
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
                  "no_match_is_none_not_a_guess": VE.match_element(fake, "Quit") is None and VE.match_element(fake, "") is None,
                  "a_label_that_is_only_part_of_the_spoken_target_does_not_match": VE.match_element({"elements": [{"id": 3, "label": "File", "role": "text", "box": [0, 0, 1, 1]}]}, "share file") is None,
                  "the_target_inside_a_longer_label_matches": VE.match_element({"elements": [{"id": 4, "label": "Save As...", "role": "text", "box": [0, 0, 1, 1]}]}, "save")["id"] == 4}
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
    said_after = [{"text": "now click the File menu", "start": 2.0, "duration": 1.0}, {"text": "then press Ctrl+S", "start": 3.5, "duration": 1.0}]
    with _Dir() as root3, _Env() as R3:
        VE.explain_video(R3, "calc", "vidJ", said_after, [kf[0]], out_jsonl=os.path.join(root3, "j.jsonl"), root=root3, som_fn=som, scan_delta=False, ingest=False)
        j = [json.loads(l) for l in open(os.path.join(root3, "j.jsonl"), encoding="utf-8")]
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
              "an_instruction_said_after_the_change_is_never_preferred_over_the_one_before": len(j) == 1 and json.loads(j[0]["messages"][2]["content"][0]["text"])[0]["action"] == "click",
              "ocr_debris_is_not_shown_as_what_appeared": junk == ["Calculator", "Programmer", "Date calculation"]}
    return _verdict(checks, f"statuses={st} dry={[o['video_id'] for o in dry['off_topic']]} purged={fixed['removed_chunks']} pairs={rep2['pairs']} junk_out={junk}")


def run_hv10() -> "TestOutcome":
    """HV10: the clips -> pairs batch driver: plans clips across videos, resumable, stops on a download-failure streak and on the time budget, prunes unused frames, reports dataset worth"""
    try:
        import cv2  # noqa: F401
        from core_organs.harvest import pairs_batch as PB
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    said = lambda base: [{"text": "welcome to this tutorial everybody", "start": base - 20.0, "duration": 3.0}, {"text": "now click the File menu", "start": base + 1.5, "duration": 2.0},
                         {"text": "and then it just does its thing", "start": base + 6.0, "duration": 2.0}]
    som = lambda image, region=None: {"elements": [{"id": 1, "label": "File", "role": "text", "box": [0, 0, 5, 5]}, {"id": 2, "label": "Open", "role": "text", "box": [0, 10, 5, 5]}], "seconds": 0.0,
                                      "size": [640, 360], "tiers_used": [], "tiers_skipped": []}
    made = []

    def good_download(vid, t0, t1, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, f"{vid}_{int(t0)}-{int(t1)}.mp4")
        _synthetic_video(p)
        made.append(p)
        return p

    def boom(vid, t0, t1, out_dir):
        raise RuntimeError("HTTP Error 429: Too Many Requests")
    with _Dir() as root:
        os.makedirs(os.path.join(root, "transcripts_json"))
        os.makedirs(os.path.join(root, "transcripts_json", "_off_topic"))
        for app, vid, base in (("alpha", "vidA", 100.0), ("beta", "vidB", 200.0), ("alpha", "vidC", 300.0)):
            json.dump(said(base), open(os.path.join(root, "transcripts_json", f"{app}__{vid}.json"), "w"))
        json.dump(said(50.0), open(os.path.join(root, "transcripts_json", "_off_topic", "gamma__vidD.json"), "w"))
        plan = PB.plan_clips(root)
        only_beta = PB.plan_clips(root, apps=["beta"])
        rep = PB.run_pairs_batch(None, root, max_clips=10, delay_s=0, download=good_download, som_fn=som, gate=None, prefilter=None, min_elements=1)
        jl = [json.loads(l) for l in open(os.path.join(root, "training", "ui_training_dataset.jsonl"), encoding="utf-8")]
        again = PB.run_pairs_batch(None, root, max_clips=10, delay_s=0, download=good_download, som_fn=som, gate=None, prefilter=None, min_elements=1)
        n_made_after_rerun = len(made)
        frames_left = [f for d, _, fs in os.walk(os.path.join(root, "frames")) for f in fs]
        referenced = {os.path.basename(m["meta"]["pre"]) for m in jl} | {os.path.basename(m["meta"]["post"]) for m in jl if m["meta"].get("post")}
        state = json.load(open(os.path.join(root, "training", "pairs_state.json")))
        report = PB.dataset_report(root)                           # these pairs were made with gate=None: NOT verified as UI, so not usable for training
        report_unchecked_ok = PB.dataset_report(root, require_ui=False)
    with _Dir() as root2:
        os.makedirs(os.path.join(root2, "transcripts_json"))
        for i in range(6):
            json.dump(said(100.0 + 100 * i), open(os.path.join(root2, "transcripts_json", f"app{i}__vid{i}.json"), "w"))
        calls = []

        def counting_boom(*a):
            calls.append(a)
            return boom(*a)
        rep_fail = PB.run_pairs_batch(None, root2, max_clips=6, delay_s=0, download=counting_boom, som_fn=som, max_fail_streak=3, gate=None, prefilter=None, min_elements=1)
        rep_budget = PB.run_pairs_batch(None, root2, max_clips=6, budget_s=0.0, delay_s=0, download=good_download, som_fn=som, gate=None, prefilter=None, min_elements=1)
    checks = {"plan_covers_every_on_topic_video_and_skips_the_quarantine": sorted({c["app"] for c in plan}) == ["alpha", "beta"] and len(plan) == 3 and not any(c["app"] == "gamma" for c in plan),
              "plan_can_be_limited_to_apps": [c["app"] for c in only_beta] == ["beta"],
              "clips_are_short": all(c["t1"] - c["t0"] <= 12.0 for c in plan),
              "downloads_and_makes_pairs": rep["downloaded"] == 3 and rep["pairs"] >= 3 and rep["grounded"] >= 3 and len(jl) == rep["pairs"],
              "pairs_split_across_apps": set(rep["by_app"]) == {"alpha", "beta"},
              "rerun_does_nothing_new": again["attempted"] == 0 and again["pairs"] == 0 and n_made_after_rerun == 3 and again["already_done"] == 3,
              "state_records_every_clip": len(state["clips"]) == 3 and all(v["status"].startswith("done") for v in state["clips"].values()),
              "unused_frames_pruned": rep["frames_pruned"] >= 1 and set(frames_left) <= referenced,
              "stops_on_a_failure_streak_without_retrying": rep_fail["download_failed"] == 3 and len(calls) == 3 and "in a row" in rep_fail["stopped"],
              "failures_are_remembered_not_retried_forever": rep_fail["attempted"] == 3,
              "stops_on_the_time_budget_without_fetching": rep_budget["stopped"] == "time budget spent" and rep_budget["pairs"] == 0 and len(made) == n_made_after_rerun,
              "dataset_report_refuses_to_count_unverified_frames": report["usable_for_training"] == 0 and report["frames_not_verified_as_ui"] == len(jl) and report["invalid"] == len(jl),
              "dataset_report_counts_them_when_asked": report_unchecked_ok["usable_for_training"] == len(jl) and report_unchecked_ok["by_action"].get("click") == len(jl)
                                                         and report_unchecked_ok["fraction_of_min"] == round(len(jl) / 200, 2)}
    return _verdict(checks, f"plan={len(plan)} pairs={rep['pairs']} pruned={rep['frames_pruned']} report={ {k: report_unchecked_ok[k] for k in ('usable_for_training', 'videos')} }")


def run_hv11() -> "TestOutcome":
    """HV11: the UI-frame gate -- verdict parsing, cache, unverified fallback, and no pair is made from a frame that is not a software UI"""
    import base64
    import io as _io
    from PIL import Image
    from core_organs.harvest import video_explain as VE
    from core_organs.harvest.frame_gate import UIFrameGate
    from si_tests_rag import _Env
    calls = []

    def fake_post(url, body, timeout):
        calls.append(body["model"])
        im = Image.open(_io.BytesIO(base64.b64decode(body["messages"][0]["images"][0]))).convert("L")
        mean = sum(im.getdata()) / (im.size[0] * im.size[1])
        return {"message": {"content": "YES" if mean > 150 else ("MAYBE" if mean < 40 else "no.")}}
    with _Dir() as root:
        light, mid, dark = (os.path.join(root, n) for n in ("light.jpg", "mid.jpg", "dark.jpg"))
        Image.new("RGB", (400, 300), (230, 230, 230)).save(light)
        Image.new("RGB", (400, 300), (90, 90, 90)).save(mid)
        Image.new("RGB", (400, 300), (10, 10, 10)).save(dark)
        gate = UIFrameGate(url="http://x", cache_path=os.path.join(root, "gate.json"), post=fake_post)
        v_ui, _ = gate.check(light)
        v_no, _ = gate.check(mid)
        v_unparse, why_unparse = gate.check(dark)
        n_before = len(calls)
        v_again, why_again = gate.check(light)
        calls_after_again = len(calls)
        gate2 = UIFrameGate(url="http://x", cache_path=os.path.join(root, "gate.json"), post=fake_post)               # a new process reads the persisted cache
        v_persist, why_persist = gate2.check(mid)
        down_calls = []

        def down_post(url, body, timeout):
            down_calls.append(1)
            raise ConnectionError("no ollama")
        gate3 = UIFrameGate(url="http://x", cache_path="", post=down_post)
        d1 = gate3.check(light)
        d2 = gate3.check(mid)
        down_after = len(down_calls)
        bad_path = gate.check(os.path.join(root, "nope.jpg"))
        # explain_video: the instruction waits for a change that actually shows the interface
        for n, shade in (("a_pre", 230), ("a_post", 230), ("b_pre", 10 + 80), ("b_post", 230), ("c_pre", 230), ("c_post", 230)):
            Image.new("RGB", (300, 200), (shade,) * 3).save(os.path.join(root, f"{n}.jpg"))
        P = lambda n: os.path.join(root, n + ".jpg")
        evs = [{"t": 3.0, "pre": P("b_pre"), "post": P("b_post"), "bbox": [0, 0, 5, 5]}, {"t": 4.0, "pre": P("c_pre"), "post": P("c_post"), "bbox": [0, 0, 5, 5]}]
        som = lambda image, region=None: {"elements": [{"id": 1, "label": "File", "role": "text", "box": [0, 0, 5, 5]}], "seconds": 0.0, "size": [300, 200], "tiers_used": [], "tiers_skipped": []}
        said = [{"text": "now click the File menu", "start": 2.0, "duration": 1.0}]
        g = UIFrameGate(url="http://x", cache_path="", post=fake_post)
        with _Env() as R:
            rep = VE.explain_video(R, "app", "vidG", said, evs, out_jsonl=os.path.join(root, "g.jsonl"), root=root, som_fn=som, scan_delta=False, ingest=False, gate=g)
            rows = [json.loads(l) for l in open(os.path.join(root, "g.jsonl"), encoding="utf-8")]
            h = UIFrameGate(url="http://x", cache_path="", post=down_post)
            rep_down = VE.explain_video(R, "app", "vidH", said, evs, out_jsonl=os.path.join(root, "h.jsonl"), root=root, som_fn=som, scan_delta=False, ingest=False, gate=h)
            rep_none = VE.explain_video(R, "app", "vidI", said, evs, out_jsonl=os.path.join(root, "i.jsonl"), root=root, som_fn=som, scan_delta=False, ingest=False, gate=None)
            none_rows = [json.loads(l) for l in open(os.path.join(root, "i.jsonl"), encoding="utf-8")]
        seq = iter(["8888", "YES"])                                            # degenerate tokens at the first size, a clean answer at another (measured on near-blank frames)
        g_retry = UIFrameGate(url="http://x", cache_path="", post=lambda u, b, t: {"message": {"content": next(seq)}})
        v_retry = g_retry.check(P("light"))
        seq_bad = iter(["8888", "8888", "8888"])
        g_bad = UIFrameGate(url="http://x", cache_path="", post=lambda u, b, t: {"message": {"content": next(seq_bad)}})
        v_bad = g_bad.check(P("mid"))
    checks = {"a_degenerate_answer_is_asked_again_at_another_size": v_retry[0] is True and g_retry.stats["asked"] == 2 and v_bad[0] is None and "unparseable" in v_bad[1] and g_bad.stats["asked"] == 3,
              "yes_means_ui_no_means_not": v_ui is True and v_no is False,
              "an_unparseable_answer_is_unverified_not_a_guess": v_unparse is None and "unparseable" in why_unparse,
              "a_frame_is_judged_once": v_again is True and why_again == "cached" and calls_after_again == n_before,
              "the_cache_survives_a_restart": v_persist is False and why_persist == "cached",
              "an_unreachable_model_is_unverified_and_backs_off": d1[0] is None and d2[0] is None and down_after == 1 and "backing off" in d2[1],
              "an_unreadable_image_is_rejected": bad_path[0] is False,
              "the_non_ui_change_makes_no_pair_and_the_step_waits": rep["not_ui_frame"] == 1 and rep["pairs"] == 1 and rows[0]["meta"]["t"] == 4.0 and rows[0]["meta"]["ui_frames"] is True,
              "an_unreachable_model_makes_no_pairs": rep_down["pairs"] == 0 and rep_down["unverified_frame"] >= 1,
              "gate_none_records_unchecked": rep_none["pairs"] == 1 and none_rows[0]["meta"]["ui_frames"] is None}
    return _verdict(checks, f"calls={len(calls)} rep={ {k: rep[k] for k in ('pairs', 'not_ui_frame', 'unverified_frame')} }")


def run_hv12() -> "TestOutcome":
    """HV12: step extraction on the phrasings that broke the first real run"""
    from core_organs.harvest import video_explain as VE
    from core_organs.rag.procedures import extract_steps
    cases = {"click the file menu click save as": [("click", "file"), ("click", "save as")],
             "You'll just wanna tap tools and then short link.": [("tap", "tools")],
             "just press enter and that person will get your message": [("press", "enter")],
             "to hit the m key in order to mute the VLC application": [("hit", "m key")],
             "click save to lock in your schedule": [("click", "save")],
             "select the cell and click Insert": [("select", "cell"), ("click", "Insert")],
             "press Ctrl+S to save": [("press", "Ctrl+S")],
             "okay now you press the Escape key to close it": [("press", "Escape key")],
             "all you need to do is click Save": [("click", "Save")],
             "so we gonna go to Preferences": [("go to", "Preferences")],
             "and that is the type of channel": [],
             "the type of channel it was in here": []}
    got = {t: [(s["verb"], s["target"]) for s in extract_steps(t)] for t in cases}
    concrete = {"click two more": False, "type of channel": False, "select this option": False, "press the": False, "click Save": True, "press Ctrl+S": True, "open Settings": True}
    cc = {}
    for t in concrete:
        st = extract_steps(t)
        cc[t] = VE.is_concrete(st[0]) if st else False
    segs = [{"text": "okay now you press the", "start": 10.0, "duration": 1.5}, {"text": "Escape key to close it.", "start": 11.6, "duration": 1.5}, {"text": "and that is it.", "start": 13.5, "duration": 1.0},
            {"text": "click Save", "start": 20.0, "duration": 1.0}, {"text": "much later", "start": 40.0, "duration": 1.0}]
    ut = VE.utterances(segs)
    checks = {"every_phrasing_extracts_exactly_what_was_asked": got == cases,
              "concreteness": cc == concrete,
              "caption_lines_are_rejoined_into_utterances": ut[0]["text"] == "okay now you press the Escape key to close it." and len(ut) >= 3,
              "a_rejoined_utterance_yields_the_step_its_halves_could_not": [(s["verb"], s["target"]) for s in extract_steps(ut[0]["text"])] == [("press", "Escape key")]
                                                                           and [s for s in extract_steps("okay now you press the") if VE.is_concrete(s)] == [],
              "sentence_end_stops_the_join": ut[1]["text"].startswith("and that is it.") and "click Save" not in ut[1]["text"],
              "steps_before_uses_utterances": any(s["target"] == "Escape key" for s in VE.steps_before(segs, 13.0))}
    bad = {t: (got[t], cases[t]) for t in cases if got[t] != cases[t]}
    return _verdict(checks, f"mismatches={bad}")


class _FakeCtl:
    def __init__(self, name):
        self.name = name


class _FakeApp:
    """Stands in for OwnedApp: a window that draws its state, with named controls. 'Seven' / 'Plus' change the picture, 'Inert' does not, 'Delete' must never be touched."""
    mode = "fake"
    LAYOUT = {"Seven": (10, 10, 100, 60), "Plus": (120, 10, 100, 60), "Inert": (230, 10, 100, 60), "Delete": (340, 10, 100, 60), "Menu": (10, 80, 100, 20)}
    ITEMS = {"Item A": (10, 105, 100, 20), "Item B": (10, 130, 100, 20), "Delete item": (10, 155, 100, 20)}

    def __init__(self):
        self.state, self.touched, self.typed, self.popups, self.menu_open, self.layers, self.anchor = 0, [], "", 0, False, [], None

    def grab(self, popups=False, stable=True):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (460, 200), (40, 40, 40))
        d = ImageDraw.Draw(im)
        for i, (n, b) in enumerate(self.LAYOUT.items()):
            d.rectangle([b[0], b[1], b[0] + b[2], b[1] + b[3]], fill=(90, 90, 90))
        d.rectangle([200, 100, 200 + 20 * (self.state + len(self.typed)), 150], fill=(250, 250, 250))
        if self.menu_open and popups:
            d.rectangle([10, 100, 112, 175], fill=(200, 200, 60))
            self.layers = [{"hwnd": 1, "origin": (0, 0), "paste": (10, 100), "size": (102, 75)}]
        else:
            self.layers = []
        return im, (0, 0)

    def controls(self, origin, size):
        out = [{"key": f"ButtonControl|{n}", "name": n, "type": "ButtonControl", "box": b, "ctl": _FakeCtl(n), "popup": False} for n, b in self.LAYOUT.items() if not (self.menu_open and n == "Inert")]
        if self.menu_open:
            out += [{"key": f"MenuItemControl|{n}", "name": n, "type": "MenuItemControl", "box": b, "ctl": _FakeCtl(n), "popup": True} for n, b in self.ITEMS.items()]
        return out

    def act(self, ctl):
        self.touched.append(ctl.name)
        if ctl.name in ("Seven", "Plus"):
            self.state += 1
        if ctl.name == "Menu":
            self.menu_open = True
        elif ctl.name in self.ITEMS:
            self.menu_open = False
            self.state += 2
        return "Invoke"

    def chord(self, combo):
        if combo == "ctrl+h":
            self.state += 2
        elif combo == "esc":
            self.menu_open = False
        return True

    def type_text(self, text):
        self.typed += text
        return True

    def clear_text(self):
        self.typed = ""

    def close_popups(self):
        self.popups += 1
        return 0


def run_hv13() -> "TestOutcome":
    """HV13: the local recorder -- target found by containment, change detection, and a driven stand-in app yields click / hotkey / type pairs in the video route's format, never touching an unsafe control"""
    from core_organs import train_qlora as TQ
    from core_organs.harvest import local_recorder as LR
    # containment, not IoU: the scanner finds the glyph INSIDE a key
    som = {"elements": [{"id": 1, "label": "", "box": [150, 30, 20, 20]}, {"id": 2, "label": "7", "box": [40, 30, 20, 20]}, {"id": 3, "label": "Calculator", "box": [0, 0, 460, 12]},
                        {"id": 4, "label": "", "box": [30, 25, 20, 20]}, {"id": 5, "label": "wide", "box": [0, 20, 300, 50]}]}
    pick = LR.element_at(som, (10, 10, 100, 60))
    el_none = LR.element_at(som, (300, 100, 50, 50))
    from PIL import Image, ImageDraw
    a_img = Image.new("RGB", (100, 100), (0, 0, 0))
    b_img = a_img.copy()
    ImageDraw.Draw(b_img).rectangle([20, 30, 49, 59], fill=(255, 255, 255))
    ok_ch, bbox = LR.changed(a_img, b_img)
    ok_same, _ = LR.changed(a_img, a_img.copy())
    LR.APPS["fake"] = {"launch": "x", "modes": [], "chords": [("ctrl+h", "Open the history panel", "esc")], "type": "hello", "menus": ["Menu"]}
    boxes = dict(_FakeApp.LAYOUT, **_FakeApp.ITEMS)
    fake_som = lambda image, region=None: {"elements": [{"id": i + 1, "label": n, "role": "button", "box": [b[0] + 30, b[1] + b[3] // 2 - 5, 30, 10]} for i, (n, b) in enumerate(boxes.items())],
                                          "seconds": 0.0, "size": [460, 200], "tiers_used": [], "tiers_skipped": []}
    try:
        with _Dir() as root:
            out = os.path.join(root, "t", "p.jsonl")
            app = _FakeApp()
            rep = LR.record_app("fake", max_actions=10, budget_s=60, root=root, out_jsonl=out, som_fn=fake_som, app=app, settle_s=0.0)
            rows = [json.loads(l) for l in open(out, encoding="utf-8")]
            acts = [json.loads(r["messages"][2]["content"][0]["text"])[0] for r in rows]
            rep2 = LR.record_app("fake", max_actions=10, budget_s=60, root=root, out_jsonl=out, som_fn=fake_som, app=_FakeApp(), settle_s=0.0)
            rows2 = [json.loads(l) for l in open(out, encoding="utf-8")]
            validated = [TQ.validate_pair(r, root) for r in rows]
            by_goal = {r["messages"][1]["content"][1]["text"].split("Goal: ")[1]: json.loads(r["messages"][2]["content"][0]["text"])[0] for r in rows}
    finally:
        LR.APPS.pop("fake", None)
    clicks = [a_ for a_ in acts if a_["action"] == "click"]
    seven = by_goal.get("Click the Seven button", {})
    checks = {"the_glyph_inside_a_key_is_its_element_and_a_label_beats_none": pick is not None and pick["id"] == 2,
              "nothing_inside_means_no_element": el_none is None,
              "change_detection_finds_the_region": ok_ch and bbox == (20, 30, 30, 30) and not ok_same,
              "click_pairs_for_controls_that_changed_the_picture": sorted(by_goal) == sorted(["Click the Seven button", "Click the Plus button", "Click the Menu button", "Click the Item A menu item", "Click the Item B menu item", "Open the history panel", "Type 'hello'"]) and len(clicks) == 8,          # two passes: empty page, then a page with text
              "target_is_the_overlapping_element": seven.get("action") == "click" and seven.get("target_id") == 1,
              "hotkey_and_type_pairs": by_goal["Open the history panel"]["hotkey"] == "ctrl+h" and by_goal["Type 'hello'"]["text"] == "hello",
              "unsafe_control_never_touched": "Delete" not in app.touched and "Delete item" not in app.touched and rep["skipped_unsafe"] == 2,
              "a_menu_is_opened_and_each_safe_item_in_it_is_a_pair": by_goal["Click the Item A menu item"]["action"] == "click" and by_goal["Click the Item B menu item"]["target_id"] is not None and "Item A" in app.touched and "Item B" in app.touched,
              "inert_control_is_not_a_pair": rep["no_change"] == 4 and app.touched.count("Inert") >= 2,
              "rows_are_the_video_format_and_pass_the_training_validator": all(r["meta"]["ui_frames"] is True and r["meta"]["source"] == "local_uia" and r["meta"]["grounded"] for r in rows) and not any(validated),
              "a_rerun_adds_nothing": rep2["pairs"] == 0 and rep2["duplicates"] >= 1 and len(rows2) == len(rows),
              "popups_are_tidied_after_every_action": app.popups >= rep["actions"]}
    return _verdict(checks, f"pairs={rep['pairs']} goals={sorted(by_goal)} rep={ {k: v for k, v in rep.items() if k not in ('jsonl',)} } validator={validated}")


def run_hv14() -> "TestOutcome":
    """HV14: captions through yt-dlp -- paced, cookie-free, block = stop, json3 parsing, and the local speech fallback only for a video with no captions at all"""
    import yt_dlp
    from core_organs.harvest import captions as CP, free_master_harvester as M
    json3 = {"events": [{"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "now click"}]}, {"tStartMs": 1000, "dDurationMs": 3000, "segs": [{"utf8": "now click the File menu"}]},
                        {"tStartMs": 9000, "dDurationMs": 1000, "segs": [{"utf8": "[Music]"}]}, {"tStartMs": 12000, "dDurationMs": 2000, "segs": [{"utf8": "then press Ctrl+S"}]}, {"aAppend": 1}]}
    parsed = CP.parse_json3(json3)
    seen_opts = {}

    class FakeYDL:
        def __init__(self, opts):
            seen_opts.update(opts)
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            vid = urls[0].rsplit("=", 1)[1]
            if vid == "blocked":
                raise Exception("ERROR: HTTP Error 429: Too Many Requests")
            if vid == "gone":
                raise Exception("ERROR: Video unavailable")
            if vid != "nocaps":
                d = os.path.dirname(self.opts["outtmpl"])
                json.dump(json3, open(os.path.join(d, f"{vid}.en.json3"), "w", encoding="utf-8"))
    real = yt_dlp.YoutubeDL
    yt_dlp.YoutubeDL = FakeYDL
    try:
        got = CP.ytdlp_transcript("abc", ["en"])
        errs = {}
        for vid in ("blocked", "gone", "nocaps"):
            try:
                CP.ytdlp_transcript(vid, ["en"])
                errs[vid] = "no error"
            except PermissionError:
                errs[vid] = "Blocked"
            except CP.TranscriptUnavailable as e:
                errs[vid] = str(e)
    finally:
        yt_dlp.YoutubeDL = real
    fetched = {"audio": 0}

    def fake_audio(vid, secs, d):
        fetched["audio"] += 1
        return os.path.join(d, "a.m4a")
    heard = CP.whisper_transcript("x", 120.0, fetch_audio=fake_audio, transcribe=lambda path, model: [{"text": "click File", "start": 1.0, "duration": 1.0}])

    def net_for(raises, whisper=None):
        def tr(vid, langs):
            raise raises
        return M.Net(http_get=lambda u: None, search=lambda q, n: [], transcript=tr, whisper=whisper, sleep=lambda s: None)
    one = lambda v: [{"text": "click File", "start": 0.0, "duration": 1.0}]
    with _Dir() as root:
        os.makedirs(os.path.join(root, "transcripts_json"))
        nocap = M.fetch_transcript(net_for(CP.TranscriptUnavailable("No_Subtitles")), root, "calc", "v1")
        wh = M.fetch_transcript(net_for(CP.TranscriptUnavailable("No_Subtitles"), whisper=one), root, "calc", "v2")
        other = M.fetch_transcript(net_for(CP.TranscriptUnavailable("other:hi"), whisper=one), root, "calc", "v3")
        gone = M.fetch_transcript(net_for(CP.TranscriptUnavailable("Video_Unavailable"), whisper=one), root, "calc", "v4")

        def blk(v):
            raise PermissionError("Blocked:429")
        blocked = M.fetch_transcript(net_for(CP.TranscriptUnavailable("No_Subtitles"), whisper=blk), root, "calc", "v5")
        wh_file = os.path.isfile(M.transcript_path(root, "calc", "v2"))
    import inspect
    queries = inspect.signature(M.run_harvester).parameters["queries"].default
    # a refusal is a rate limit: wait it out (longer each time), ask again; refused every time = stop
    waits, calls = [], {"n": 0}
    video = {"id": "v_cool", "title": "Notepad tutorial", "duration": 600, "view_count": 10}
    segs_ok = [{"text": "in notepad click File then notepad Save, notepad is simple", "start": 1.0, "duration": 2.0}] * 6

    def flaky(vid, langs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("Blocked:429")
        return segs_ok

    def always(vid, langs):
        raise PermissionError("Blocked:429")
    out = {}
    for tag, fn in (("clears", flaky), ("stays", always)):
        waits.clear()
        calls["n"] = 0
        net = M.Net(http_get=lambda u: WINGET_FIXTURE.encode("utf-8") if u == M.WINGET_CSV else None, search=lambda q, n: [video], transcript=fn, sleep=lambda x: waits.append(x))
        with _Dir() as r2:
            rep_c = M.run_harvester(max_apps=1, videos_per_app=1, net=net, root=r2, delay_s=0, write_workbook=False, only_apps=["Notepad"], block_cooldowns=(600, 1200), on_block="wait")
        out[tag] = (rep_c["blocked"], rep_c["stats"]["downloaded"], rep_c["stats"]["cooldowns"], [w for w in waits if w >= 600])
    # captions refused for good: after the cool-offs the caption endpoint is left alone for a while and on-topic videos are recognised locally; an off-topic title is not worth CPU time
    vids2 = [{"id": "w1", "title": "Notepad tutorial", "duration": 600, "view_count": 9}, {"id": "w2", "title": "Notepad tips", "duration": 600, "view_count": 8},
             {"id": "w3", "title": "Cooking pasta", "duration": 600, "view_count": 7}]
    cap_calls, heard_ids = [], []
    waits.clear()

    def refused(vid, langs):
        cap_calls.append(vid)
        raise PermissionError("Blocked:429")

    def speech(vid):
        heard_ids.append(vid)
        return segs_ok
    net2 = M.Net(http_get=lambda u: WINGET_FIXTURE.encode("utf-8") if u == M.WINGET_CSV else None, search=lambda q, n: vids2, transcript=refused, whisper=speech, sleep=lambda x: waits.append(x))
    with _Dir() as r3:
        rep_w = M.run_harvester(max_apps=1, videos_per_app=3, net=net2, root=r3, delay_s=0, write_workbook=False, only_apps=["Notepad"], block_cooldowns=(600, 1200), on_block="wait")
    # the refusal first lands on a video whose title is off-topic: that is not a block, the run goes on to the next video
    vids3 = [{"id": "x1", "title": "Cooking pasta", "duration": 600, "view_count": 9}, {"id": "x2", "title": "Notepad tips", "duration": 600, "view_count": 8}]
    heard3 = []
    net3 = M.Net(http_get=lambda u: WINGET_FIXTURE.encode("utf-8") if u == M.WINGET_CSV else None, search=lambda q, n: vids3, transcript=lambda v, l: (_ for _ in ()).throw(PermissionError("Blocked:429")),
                 whisper=lambda v: (heard3.append(v), segs_ok)[1], sleep=lambda x: None)
    with _Dir() as r4:
        rep_o = M.run_harvester(max_apps=1, videos_per_app=2, net=net3, root=r4, delay_s=0, write_workbook=False, only_apps=["Notepad"], block_cooldowns=(60,), on_block="wait")
    checks = {"rolling_auto_captions_merge_and_noise_is_dropped": [(s["text"], s["start"]) for s in parsed] == [("now click the File menu", 0.0), ("then press Ctrl+S", 12.0)],
              "captions_come_back_as_segments": [s["text"] for s in got] == [s["text"] for s in parsed],
              "paced_exactly_as_asked": seen_opts.get("sleep_interval_requests") == 1.5 and seen_opts.get("sleep_interval") == 2 and seen_opts.get("max_sleep_interval") == 5,
              "subtitles_only_no_video": seen_opts.get("skip_download") is True and seen_opts.get("writesubtitles") is True and seen_opts.get("writeautomaticsub") is True,
              "no_browser_cookies_are_read": not any(k in seen_opts for k in ("cookiesfrombrowser", "cookiefile")),
              "a_refusal_is_a_block_and_unavailable_and_no_caption_are_not": errs == {"blocked": "Blocked", "gone": "Video_Unavailable", "nocaps": "No_Subtitles"},
              "whisper_runs_on_the_audio_section": heard[0]["text"] == "click File" and fetched["audio"] == 1,
              "no_whisper_configured_means_no_subtitles": nocap["status"] == "No_Subtitles",
              "no_captions_falls_back_to_speech_recognition": wh["status"] == "Downloaded" and wh.get("via") == "whisper" and wh_file,
              "other_language_or_missing_video_never_triggers_it": other["status"].startswith("Other_Language") and gone["status"] == "Video_Unavailable",
              "a_block_during_the_fallback_is_a_block": blocked["status"].startswith("Blocked"),
              "queries_favour_screencasts": list(queries) == ["{app} tutorial step by step", "{app} how to use interface"],
              "a_refusal_that_clears_after_a_cool_off_is_harvested": out["clears"] == (False, 1, 2, [600, 1200]),
              "a_refusal_that_stays_stops_the_run_after_the_cool_offs": out["stays"] == (True, 0, 2, [600, 1200]),
              "captions_refused_for_good_means_local_speech_for_on_topic_videos": rep_w["stats"]["downloaded"] == 2 and rep_w["stats"]["via_whisper"] == 2 and heard_ids == ["w1", "w2"] and not rep_w["blocked"],
              "the_caption_endpoint_is_left_alone_after_that": cap_calls == ["w1", "w1", "w1"] and rep_w["stats"]["captions_down"] == 1 and rep_w["stats"]["cooldowns"] == 2,
              "an_off_topic_title_hit_by_the_refusal_is_not_a_block": not rep_o["blocked"] and rep_o["stats"]["off_topic"] == 1 and heard3 == ["x2"] and rep_o["stats"]["downloaded"] == 1,
              "an_off_topic_title_costs_no_speech_recognition": "w3" not in heard_ids and rep_w["stats"]["off_topic"] == 1}
    return _verdict(checks, f"errs={errs} queries={list(queries)} cooloff={out}")


def run_hv15() -> "TestOutcome":
    """HV15: the keyframe pre-filter (flat / skin-tone / face frames rejected before any OCR) and the normalized token-overlap target matcher"""
    from PIL import Image, ImageDraw
    from core_organs.harvest import frame_prefilter as FP, video_explain as VE, free_master_harvester as M2
    from si_tests_rag import _Env
    ui = Image.new("RGB", (800, 500), (245, 245, 245))
    d = ImageDraw.Draw(ui)
    for i in range(14):
        d.rectangle([20 + (i % 7) * 105, 40 + (i // 7) * 120, 110 + (i % 7) * 105, 130 + (i // 7) * 120], outline=(40, 40, 40), width=2)
        d.text((30 + (i % 7) * 105, 70 + (i // 7) * 120), f"Option {i}", fill=(0, 0, 0))
    flat = Image.new("RGB", (800, 500), (30, 60, 140))
    skin = Image.new("RGB", (800, 500), (224, 172, 105))
    keep_ui, _ = FP.looks_like_screencast(ui)
    keep_flat, why_flat = FP.looks_like_screencast(flat)
    keep_skin, why_skin = FP.looks_like_screencast(skin)
    keep_bad, why_bad = FP.looks_like_screencast("no/such/file.jpg")
    som = {"elements": [{"id": 1, "label": "Save Ctrl+S", "box": [0, 0, 5, 5]}, {"id": 2, "label": "File", "box": [0, 0, 5, 5]}, {"id": 3, "label": "Font size", "box": [0, 0, 5, 5]},
                        {"id": 4, "label": "Settings", "box": [0, 0, 5, 5]}, {"id": 5, "label": "New Tab", "box": [0, 0, 5, 5]}]}
    case = lambda t: (VE.match_element(som, t) or {}).get("id")
    matches = {"save": case("save"), "share file": case("share file"), "change font size": case("change font size"), "setting": case("setting"), "new tab": case("new tab"),
               "open file menu": case("open file menu"), "file": case("file")}
    # the pre-filter runs before any OCR and a rejected frame leaves the instruction available for a later change
    seen_som = []
    elements = [{"id": 1, "label": "File", "role": "text", "box": [0, 0, 5, 5]}] * 8

    def som_fn(image, region=None):
        seen_som.append(image)
        return {"elements": elements, "seconds": 0.0, "size": [100, 100], "tiers_used": [], "tiers_skipped": []}
    kf = [{"t": 3.0, "pre": "frames/a_pre.jpg", "post": "frames/a_post.jpg", "bbox": [0, 0, 50, 50]}, {"t": 3.5, "pre": "frames/b_pre.jpg", "post": "frames/b_post.jpg", "bbox": [0, 0, 60, 60]}]
    said = [{"text": "now click the File menu", "start": 2.5, "duration": 1.0}]
    with _Dir() as root, _Env() as R:
        rep = VE.explain_video(R, "calc", "vidP", said, kf, out_jsonl=os.path.join(root, "p.jsonl"), root=root, som_fn=som_fn, scan_delta=False, ingest=False, min_elements=1,
                               prefilter=lambda path: (("b_pre" in path), "presenter"))
    checks = {"a_ui_frame_is_kept": keep_ui,
              "a_flat_card_is_rejected": not keep_flat and "edges" in why_flat,
              "a_skin_tone_close_up_is_rejected": not keep_skin and "skin" in why_skin,
              "an_unreadable_frame_is_rejected": not keep_bad and "unreadable" in why_bad,
              "shortcut_hint_in_the_label_is_ignored": matches["save"] == 1,
              "a_plural_and_a_missing_word_still_match": matches["setting"] == 4 and matches["change font size"] == 3 and matches["new tab"] == 5,
              "one_shared_word_never_carries_a_multiword_target": matches["share file"] is None and matches["open file menu"] is None,
              "a_one_word_target_matches_its_label": matches["file"] == 2,
              "a_lookalike_program_is_not_the_app": not M2.on_topic("Notepad", "Notepad++ tutorial for beginners") and M2.on_topic("Notepad", "Windows Notepad tips") and M2.on_topic("Notepad++", "Notepad++ tutorial")
                                                    and not M2.on_topic("Notepad", "Tips", " ".join(["notepad++"] * 6 + ["notepad"] * 2)) and M2.on_topic("Notepad", "Tips", " ".join(["notepad"] * 6)),
              "prefilter_runs_before_ocr_and_the_step_waits": rep["prefiltered"] == 1 and rep["pairs"] == 1 and len(seen_som) == 1 and "b_pre" in seen_som[0]}
    return _verdict(checks, f"matches={matches} flat={why_flat!r} skin={why_skin!r} pairs={rep['pairs']} prefiltered={rep['prefiltered']}")


def run_hv16() -> "TestOutcome":
    """HV16: the slow YouTube loop -- per app harvest then that app's pairs, short cool-off + local speech recognition + no cookies, stops at the target / the deadline / an audio refusal"""
    from core_organs.harvest import free_master_harvester as M, pairs_batch as PB, youtube_loop as YL
    real_h, real_p, real_u = M.run_harvester, PB.run_pairs_batch, YL._usable
    calls, usable, block_on = [], {"n": 100}, {"app": ""}

    def fake_h(**kw):
        calls.append(("harvest", kw["only_apps"][0], kw["videos_per_app"], tuple(kw["block_cooldowns"]), kw["whisper_fallback"], sorted(kw), kw["on_block"]))
        return {"stats": {"downloaded": 1}, "blocked": kw["only_apps"][0] == block_on["app"]}

    def fake_p(rag, root, **kw):
        calls.append(("pairs", kw["apps"]))
        usable["n"] += 30
        return {"attempted": 5, "pairs": 30, "grounded": 30}
    M.run_harvester, PB.run_pairs_batch, YL._usable = fake_h, fake_p, lambda root: usable["n"]
    try:
        log = []
        r_default = YL.run_loop(hours=1.0, target=10 ** 6, videos_per_app=3, apps=["notepad"], log=log.append)
        default_call = calls[0]
        calls.clear()
        usable["n"] = 100
        r_target = YL.run_loop(hours=1.0, target=190, videos_per_app=3, apps=["notepad", "slack", "vlc"], whisper=True, log=log.append)
        first = list(calls[:3])
        harvested = [c[1] for c in calls if c[0] == "harvest"]
        calls.clear()
        usable["n"] = 0
        r_deadline = YL.run_loop(hours=0.0, target=10 ** 6, videos_per_app=3, apps=["notepad"], log=log.append)
        n_deadline = len(calls)
        calls.clear()
        usable["n"] = 0
        block_on["app"] = "Slack"
        r_block = YL.run_loop(hours=1.0, target=10 ** 6, videos_per_app=3, apps=["notepad", "slack", "vlc"], log=log.append)
        seq_block = [c[1] for c in calls if c[0] == "harvest"]
        pairs_after_block = [c for c in calls if c[0] == "pairs"]
    finally:
        M.run_harvester, PB.run_pairs_batch, YL._usable = real_h, real_p, real_u
    checks = {"stops_when_the_target_is_reached": r_target["stopped"] == "target reached" and r_target["rounds"][-1]["usable_now"] >= 190 and harvested == ["Notepad", "VLC Media Player", "Slack"][:len(harvested)],
              "each_app_is_harvested_then_only_its_own_clips_become_pairs": [c[0] for c in first[:2]] == ["harvest", "pairs"] and first[1][1] == ["notepad"] and first[2][0] == "harvest" and first[2][1] == "VLC Media Player",
              "the_default_fails_over_without_waiting_or_transcribing": default_call[3] == () and default_call[4] is False and default_call[6] == "failover",
              "a_short_cool_off_and_local_speech_recognition_no_cookies": first[0][3] == (60,) and first[0][4] is True and first[0][6] == "wait" and first[0][2] == 3 and not any("cookie" in k for k in first[0][5]),
              "a_passed_deadline_does_nothing": r_deadline["stopped"] == "deadline" and n_deadline == 0,
              "an_audio_refusal_stops_the_loop_after_that_apps_own_pairs": r_block["stopped"].startswith("blocked") and seq_block == ["Notepad", "VLC Media Player", "Slack"] and len(pairs_after_block) == 3,
              "every_round_is_logged": len(log) >= 5}
    return _verdict(checks, f"target={r_target['stopped']} harvested={harvested} deadline={r_deadline['stopped']} block={r_block['stopped']} seq={seq_block}")


def run_hv17() -> "TestOutcome":
    """HV17: failover on a caption refusal -- no sleeping, no speech recognition; the app goes to the static sources at once, the caption endpoint is left alone for the following apps"""
    from core_organs.harvest import free_master_harvester as M
    slept, static_calls, transcript_calls, heard = [], [], [], []
    vids = [{"id": "f1", "title": "Notepad tutorial", "duration": 600, "view_count": 9}, {"id": "f2", "title": "Notepad tips", "duration": 600, "view_count": 8}]

    def refused(vid, langs):
        transcript_calls.append(vid)
        raise PermissionError("Blocked:429")

    def static(app_name, root):
        static_calls.append(app_name)
        return {"ok": True}
    net = M.Net(http_get=lambda u: WINGET_FIXTURE.encode("utf-8") if u == M.WINGET_CSV else None, search=lambda q, n: vids, transcript=refused, whisper=lambda v: heard.append(v) or [], sleep=lambda x: slept.append(x))
    with _Dir() as root:
        rep = M.run_harvester(max_apps=2, videos_per_app=2, net=net, root=root, delay_s=0, write_workbook=False, static_source=static, only_apps=["Notepad", "Windows Calculator"])
        state = json.load(open(os.path.join(root, "harvest_state.json"), encoding="utf-8"))
    import inspect
    params = inspect.signature(M.run_harvester).parameters
    checks = {"a_refusal_costs_no_sleep_and_no_speech_recognition": all(w <= 0 for w in slept) and heard == [] and rep["stats"]["cooldowns"] == 0,
              "the_app_switches_to_static_sources_at_once": static_calls[:1] == ["Notepad"] and rep["stats"]["failover"] >= 1,
              "the_refused_video_is_not_retried_and_the_next_one_is_skipped": transcript_calls == ["f1"],
              "the_next_app_never_asks_the_caption_endpoint": static_calls == ["Notepad", "Windows Calculator"] and transcript_calls == ["f1"] and rep["stats"]["failover"] == 2,
              "nothing_is_reported_as_a_block_and_the_batch_finishes": not rep["blocked"] and rep["stats"]["apps_processed"] == 2 and rep["failed_over"] == ["notepad", "calculator"],
              "failed_over_apps_are_marked_done": all(state["done_apps"].get(k) for k in ("notepad", "calculator")),
              "defaults_are_failover_no_whisper_no_cool_off": params["on_block"].default == "failover" and params["whisper_fallback"].default is False and tuple(params["block_cooldowns"].default) == ()}
    return _verdict(checks, f"slept={slept} static={static_calls} captions_asked={transcript_calls} stats={ {k: rep['stats'][k] for k in ('failover', 'captions_down', 'static_ok')} }")


TESTS = [("HV1", run_hv1), ("HV2", run_hv2), ("HV3", run_hv3), ("HV4", run_hv4), ("HV5", run_hv5), ("HV6", run_hv6), ("HV7", run_hv7), ("HV8", run_hv8), ("HV9", run_hv9), ("HV10", run_hv10), ("HV11", run_hv11), ("HV12", run_hv12), ("HV13", run_hv13), ("HV14", run_hv14), ("HV15", run_hv15), ("HV16", run_hv16), ("HV17", run_hv17)]

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
