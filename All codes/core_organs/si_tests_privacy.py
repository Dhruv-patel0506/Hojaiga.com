"""AR21: nothing personal in a frame or a launch (kept apart from si_tests_artist so its paths stay readable)."""
from __future__ import annotations

import json
import os
import tempfile


def run_ar21(verdict):
    """AR21: nothing personal in a frame or a launch -- account badges are masked, a document app is started on the sandbox, and the scrub quarantines a frame that shows the person's identifiers"""
    from PIL import Image, ImageDraw
    from core_organs.harvest import privacy as PV, sandbox as SB
    img = Image.new("RGB", (400, 120), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([330, 10, 370, 40], fill=(180, 0, 120))
    me = (PV.personal_terms() or ["zzzz"])[0]
    ctrls = [{"name": "PD", "box": [330, 10, 40, 30], "type": "ButtonControl"}, {"name": "Account", "box": [10, 60, 50, 20], "type": "ButtonControl"},
             {"name": "Folder of " + me, "box": [100, 60, 80, 20], "type": "ListItemControl"}, {"name": "Bold", "box": [200, 60, 30, 20], "type": "ButtonControl"}]
    m = PV.mask_personal(img, ctrls)
    with tempfile.TemporaryDirectory() as d:
        ws = SB.ensure_workspace(os.path.join(d, "ws"))
        w_args = SB.args_for(os.path.join("C:", os.sep, "Program Files", "Microsoft Office", "root", "Office16", "WINWORD.EXE"), ws)
        z_args = SB.args_for(os.path.join("C:", os.sep, "Program Files", "7-Zip", "7zFM.exe"), ws)
        o_args = SB.args_for(os.path.join("C:", os.sep, "Windows", "notepad.exe"), ws)
        files = sorted(os.listdir(ws))
        root = os.path.join(d, "h")
        os.makedirs(os.path.join(root, "training"))
        os.makedirs(os.path.join(root, "frames", "local_x"))
        bad = Image.new("RGB", (900, 160), (255, 255, 255))
        ImageDraw.Draw(bad).text((20, 40), "C:" + chr(92) + "Users" + chr(92) + me + chr(92) + "Downloads    " + me, fill=(0, 0, 0))
        good = Image.new("RGB", (900, 160), (255, 255, 255))
        ImageDraw.Draw(good).text((20, 40), "File Edit View Help Bold Italic", fill=(0, 0, 0))
        bad = bad.resize((1800, 320))
        good = good.resize((1800, 320))
        bad.save(os.path.join(root, "frames", "local_x", "bad_pre.png"))
        good.save(os.path.join(root, "frames", "local_x", "good_pre.png"))
        rows = [{"messages": [{}, {"content": []}], "meta": {"pair_id": "b", "app_key": "x", "source": "local_uia", "pre": "frames/local_x/bad_pre.png", "post": ""}},
                {"messages": [{}, {"content": []}], "meta": {"pair_id": "g", "app_key": "x", "source": "local_uia", "pre": "frames/local_x/good_pre.png", "post": ""}}]
        ds = os.path.join(root, "training", "ui_training_dataset.jsonl")
        with open(ds, "w") as f:
            f.write("\n".join(json.dumps(r) for r in rows) + "\n")
        rep = PV.scrub(root, 0.0, progress=False)
        left = [json.loads(line)["meta"]["pair_id"] for line in open(ds)]
        quar = os.path.isfile(ds.replace(".jsonl", "_quarantine.jsonl"))
        gone = not os.path.isfile(os.path.join(root, "frames", "local_x", "bad_pre.png"))
        pr = PV.purge_app(root, "x")
    checks = {"the_initials_badge_is_painted_over": m.getpixel((350, 25)) == (128, 128, 128) and img.getpixel((350, 25)) == (180, 0, 120),
              "an_account_button_and_a_control_named_like_the_person_are_masked": m.getpixel((30, 70)) == (128, 128, 128) and m.getpixel((140, 70)) == (128, 128, 128),
              "an_ordinary_control_is_left_alone": m.getpixel((215, 70)) == (255, 255, 255),
              "word_is_started_on_a_blank_document_in_the_sandbox": bool(w_args) and w_args[0] == "/q" and w_args[-1].endswith("blank.docx") and SB.sandbox_path(w_args[-1], ws),
              "a_file_manager_is_started_on_the_sandbox_folder": bool(z_args) and SB.sandbox_path(z_args[-1], ws),
              "a_program_with_no_entry_gets_no_arguments": o_args == [],
              "the_workspace_has_blank_files": {"blank.docx", "blank.pptx", "blank.xlsx"} <= set(files),
              "a_frame_showing_the_person_is_quarantined_and_deleted": rep["pairs_quarantined"] == 1 and left == ["g"] and quar and gone,
              "purge_removes_an_app_entirely": pr["rows"] == 1}
    return verdict(checks, "terms=%s rep=%s w=%s z=%s files=%s" % (PV.personal_terms(), rep, w_args, z_args, files))
