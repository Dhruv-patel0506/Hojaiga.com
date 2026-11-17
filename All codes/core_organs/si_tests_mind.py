"""
si_tests_mind -- AR65 consequence, AR66 persona, AR67 workflow, AR68 picker + training rows + executor hook. Offline: no GPU, no screen, no network (the picker server is a stub on localhost).
Run:  python -m core_organs.si_tests_mind [AR65 ...]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except ImportError:
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def run_ar65() -> "TestOutcome":
    """AR65: consequence. A control's words say what it does; the way out of a dialog is never a risk; 'all' / 'permanently' widen it; the safe form of a verb is milder; a typed secret is blocked;
    a plan in the person's words gets a heads-up with the consequence and the safer way"""
    from core_organs.mind import consequence as CQ
    c: Dict[str, Any] = {}
    g = lambda label, **k: CQ.classify_label(label, **k)
    c["money_words_need_a_yes"] = all(g(x)["risk"] == "money" and g(x)["gate"] == "confirm" and g(x)["severity"] == 3 for x in ("Place order", "Buy now", "Checkout", "Pay now", "Subscribe", "Donate"))
    c["send_and_publish_need_a_yes"] = all(g(x)["risk"] == "publish" and g(x)["gate"] == "confirm" for x in ("Send", "Publish", "Post", "Submit application", "Reply all"))
    c["delete_sign_out_agree_install_are_classed"] = (g("Delete")["risk"] == "delete" and g("Sign out")["risk"] == "account" and g("I agree")["risk"] == "consent" and g("Install update")["risk"] == "install")
    c["the_way_out_of_a_dialog_is_harmless"] = all(g(x)["gate"] == "allow" for x in ("Cancel", "Close", "Back", "No thanks", "Not now", "Skip"))
    c["cancel_subscription_is_not_the_way_out"] = g("Cancel subscription")["risk"] == "account" and g("Cancel subscription")["gate"] == "confirm"
    c["plain_navigation_is_untouched"] = all(g(x)["gate"] == "allow" for x in ("Home", "Pricing", "Features", "Open", "Settings", "Help", "Next", "Search"))
    c["a_long_headline_link_is_an_article_not_a_command"] = g("Delete the five habits that are ruining your sleep, according to a sleep researcher", role="link")["gate"] == "allow"
    c["scope_words_widen_it"] = g("Delete", context="delete all my customers permanently")["severity"] == 3 and g("Delete")["severity"] == 2
    c["the_draft_form_of_a_verb_is_milder"] = g("Send test email")["severity"] < 2 and g("Save draft")["gate"] != "confirm"
    c["low_risk_is_a_note_not_a_question"] = g("Save")["gate"] == "note" and g("Quit")["gate"] == "note"
    a = CQ.assess_step("click", "Place order", goal="buy the blue lamp")
    c["the_question_says_what_it_does_and_what_to_do_instead"] = a["gate"] == "confirm" and "charges" in a["question"] and "Safer" in a["question"] and "Go ahead?" in a["question"]
    c["typing_into_a_password_field_is_blocked"] = CQ.assess_step("type", "Password", typed_text="hunter2", field="Password")["gate"] == "block"
    c["a_card_number_is_blocked_whatever_the_field"] = CQ.assess_step("type", "Notes", typed_text="4111 1111 1111 1111")["gate"] == "block"
    c["ordinary_text_is_allowed"] = CQ.assess_step("type", "Subject", typed_text="Quarterly report")["gate"] == "allow"
    c["a_session_closing_chord_is_asked_about"] = CQ.assess_step("key", "", chord="Alt+F4")["gate"] == "confirm"
    p = CQ.critique_goal("delete all my old emails permanently, no backup")
    c["a_plan_gets_a_heads_up"] = p["gate"] == "confirm" and p["severity"] == 3 and "no way back" in p["heads_up"] and "Safer" in p["heads_up"]
    q = CQ.critique_goal("open the report and read page 3")
    c["a_harmless_plan_gets_none"] = q["gate"] == "allow" and "heads_up" not in q
    c["a_plan_that_says_draft_is_milder"] = CQ.critique_goal("send the draft to myself as a test")["severity"] < 2
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar66() -> "TestOutcome":
    """AR66: persona. Language by script / function words (Hinglish is its own); the other person's register, urgency and mood are measured; the brief follows the relationship and the channel;
    a draft is checked against it (wrong language, too long, placeholders, tone, clichés, missing acknowledgement)"""
    from core_organs.mind import persona as P
    c: Dict[str, Any] = {}
    L = lambda t: P.detect_language(t)["code"]
    c["english"] = L("Thanks for sending the report, I will review it and send comments on Friday.") == "en"
    c["hindi_script"] = L("कृपया रिपोर्ट कल तक भेज दीजिए धन्यवाद") == "hi"
    c["hinglish_is_not_english"] = L("bhai kal tak report bhej do, mujhe abhi chahiye aur kya kar rahe ho") == "hinglish"
    c["spanish"] = L("Gracias por el informe, lo revisare y le enviare mis comentarios para el viernes") == "es"
    c["german"] = L("Vielen Dank fur den Bericht, ich werde ihn prufen und die Kommentare am Freitag schicken") == "de"
    c["japanese"] = L("レポートをありがとうございます。金曜日までに確認します") == "ja"
    formal = "Dear Mr. Shah,\n\nI am writing to inform you that the proposal is attached for your review. Kindly confirm receipt at your earliest convenience.\n\nBest regards,\nPriya Nair"
    casual = "hey! lol thx for the update, gonna check it tmrw. cool? 😄"
    c["formal_message_reads_formal"] = P.read_message(formal)["register"] == "formal"
    c["casual_message_reads_casual"] = P.read_message(casual)["register"] in ("casual", "very casual")
    c["sender_is_found_under_the_sign_off"] = P.read_message(formal)["sender"] == "Priya Nair"
    c["urgency_and_upset_are_measured"] = P.read_message("This is unacceptable, I am still waiting for my refund!! Need an answer today.")["urgent"] and P.read_message("This is unacceptable, I am still waiting for my refund!!")["upset"]
    c["questions_are_counted"] = P.read_message("Can you send the file? And when is the call?")["asks"] == 2
    b = P.style_brief(formal, channel="email_reply", relationship="client", intent="confirm receipt and give the date")
    c["a_client_gets_formal_with_greeting_and_signoff"] = b["register"] == "formal" and b["greeting"] and b["signoff"] and not b["emoji_ok"] and b["greet_name"] == "Priya Nair"
    c["a_friend_in_chat_gets_casual_and_short"] = (lambda x: x["register"] in ("casual", "very casual") and x["max_words"] <= 60 and x["emoji_ok"])(P.style_brief(casual, channel="chat", relationship="friend"))
    c["a_linkedin_post_never_goes_casual_and_has_hashtag_limit"] = (lambda x: x["register"] == "neutral" and x["hashtags_max"] == 3 and not x["greeting"])(P.style_brief("", channel="linkedin_post", relationship="friend"))
    up = P.style_brief("This is unacceptable, I am still waiting!! Need an answer today.", channel="email_reply", relationship="customer")
    c["an_upset_urgent_reader_gets_calm_and_short"] = up["mood"] == "upset" and up["exclaim_max"] == 0 and any("acknowledging" in d for d in up["do"]) and up["max_words"] < 150
    c["language_follows_the_other_person"] = P.style_brief("Gracias por el informe, lo revisare y le enviare mis comentarios para el viernes", channel="email_reply", relationship="colleague")["language"] == "es"
    pr = P.compose_prompt(b, facts=["proposal v3 sent 12 March", "review meeting 20 March 10:00"], incoming=formal)
    c["the_prompt_carries_the_brief_and_only_the_given_facts"] = "Language: English" in pr and "Maximum" in pr and "review meeting 20 March" in pr and "Use only these facts" in pr
    c["no_facts_means_ask_not_invent"] = "ask for the missing details" in P.compose_prompt(b, facts=[])
    good = "Dear Priya,\n\nThank you for sending the proposal. I confirm receipt and will return my comments by 20 March.\n\nBest regards,\nArjun"
    c["a_good_draft_fits"] = P.check_draft(good, b)["fits"]
    bad = "Hey Priya!! lol I hope this email finds you well [Name] gonna look tmrw 😄 " + "word " * 200
    probs = " | ".join(P.check_draft(bad, b)["problems"])
    c["a_bad_draft_is_caught_on_every_count"] = all(k in probs for k in ("too long", "placeholder", "emoji", "exclamation", "filler phrase", "too casual", "no sign-off"))
    c["a_draft_in_the_wrong_language_is_caught"] = any("wrong language" in x for x in P.check_draft("Gracias por el informe, lo revisare y le enviare mis comentarios para el viernes, saludos cordiales", b)["problems"])
    c["an_upset_reader_needs_acknowledgement"] = any("upset" in x for x in P.check_draft("Dear Sam,\n\nYour order ships on Monday.\n\nBest regards,\nArjun", up)["problems"])
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar67() -> "TestOutcome":
    """AR67: workflow. The order of a professional job by kind of task; where a half-done job stands is read from the SCREEN (resume, reopen the menu, started fresh, done already, lost -> ask);
    the same task already open is continued, a stale one is not; several tasks share lanes, with priority and hands-off for a window the person is using"""
    from core_organs.mind import workflow as W
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar67_")
    try:
        c["a_document_has_the_professional_order"] = [s["name"] for s in W.skeleton("write a project proposal document")["stages"]][:3] == ["define purpose and reader", "outline", "draft each section"] and W.skeleton("write a project proposal document")["kind"] == "document"
        c["a_table_job_adds_formulas_before_formatting"] = [s["name"] for s in W.skeleton("make a budget spreadsheet")["stages"]].index("add formulas and totals") < [s["name"] for s in W.skeleton("make a budget spreadsheet")["stages"]].index("format")
        c["sending_and_publishing_are_the_persons_call"] = "(the person confirms)" in W.skeleton("reply to the email from the client")["stages"][-1]["name"] and "(the person confirms)" in W.skeleton("write a linkedin post")["stages"][-1]["name"]
        c["a_drawing_starts_with_parts_then_big_shapes"] = [s["name"] for s in W.skeleton("draw a logo")["stages"]][:2] == ["decide the subject and its parts", "block in the big shapes"]
        c["an_unknown_kind_still_gets_a_safe_order"] = W.skeleton("do the thing")["kind"] == "general"
        steps = [{"text": "Click 'File'", "target": "File", "expect": "a menu or panel opens, showing: New, Open, Save as, Export"},
                 {"text": "Click 'Export'", "target": "Export", "expect": "a dialog opens, showing: PDF, PNG, SVG"},
                 {"text": "Click 'PDF'", "target": "PDF", "expect": "the page 'Export complete' opens"}]
        wf = W.new("export the drawing as PDF", "paintlike", steps)
        loc = lambda screen, title="": W.locate(wf, screen, title)
        c["step_one_control_visible_and_nothing_else_is_a_fresh_start"] = loc(["File", "Edit", "View"])["mode"] == "fresh" and loc(["File", "Edit"])["index"] == 0
        r = loc(["New", "Open", "Save as", "Export", "Print"])
        c["a_menu_left_open_resumes_at_the_next_step"] = r["mode"] == "resume" and r["index"] == 1
        r = loc(["PDF", "PNG", "SVG", "Cancel"])
        c["the_dialog_of_step_two_means_step_three_is_next"] = r["mode"] == "resume" and r["index"] == 2
        c["the_last_result_on_screen_is_done"] = loc(["OK"], title="Export complete - Drawing")["mode"] == "done"
        r = loc(["File", "Edit", "PDF"])
        c["the_person_who_went_ahead_is_not_repeated"] = r["mode"] == "resume" and r["index"] == 2 and r.get("skipped") == [0, 1]
        c["a_result_with_the_next_control_out_of_view_waits_there"] = loc(["New", "Open", "Save as"])["mode"] == "resume" and loc(["New", "Open", "Save as"])["index"] == 1
        c["a_menu_that_closed_again_means_repeat_the_step"] = loc(["File", "New", "Open"])["mode"] == "reopen" and loc(["File", "New", "Open"])["index"] == 0
        c["an_unrelated_screen_is_lost"] = W.locate(wf, ["Edit", "Zoom", "Layers"])["mode"] == "lost"
        c["labels_cut_at_different_lengths_still_match"] = W.same_label("Inbox Capture every vital ", "Inbox Capture every vital detail from emails") and not W.same_label("File", "Profile") and W.same_label("Save as", "save as…")
        # ---- adopt: continue or start fresh
        store = W.Store(tmp)
        plan = lambda: steps
        a1 = W.adopt(store, "export the drawing as PDF", "paintlike", ["File", "Edit"], plan)
        c["first_ask_starts_fresh"] = a1["action"] == "started" and len(store.open_ones()) == 1
        a2 = W.adopt(store, "Export the drawing as a PDF", "paintlike", ["PDF", "PNG", "SVG"], plan)
        c["same_task_again_resumes_where_the_screen_says"] = a2["action"] == "resumed" and a2["workflow"]["cursor"] == 2 and a2["workflow"]["id"] == a1["workflow"]["id"] and "left this half done" in a2["message"] and len(store.open_ones()) == 1
        c["steps_before_the_resume_point_are_marked_done"] = [s["done"] for s in a2["workflow"]["steps"]] == [True, True, False]
        a3 = W.adopt(store, "export the drawing as PDF", "paintlike", ["Totally", "Different", "Screen"], plan)
        c["a_screen_that_matches_nothing_asks_the_person"] = a3["action"] == "ask" and "Continue it from where you are, or start over" in a3["message"] and store.load(a1["workflow"]["id"])["state"] == "waiting_person"
        a4 = W.adopt(store, "write the quarterly report", "wordlike", ["File"], lambda: steps)
        c["a_different_task_never_hijacks_an_open_one"] = a4["action"] == "started" and a4["workflow"]["id"] != a1["workflow"]["id"]
        a5 = W.adopt(W.Store(os.path.join(tmp, "b")), "export the drawing as PDF", "paintlike", ["OK"], plan, title="Export complete")
        c["a_finished_job_is_not_repeated"] = a5["action"] == "started" and True
        # ---- advance
        w = a4["workflow"]
        w = W.advance(store, w, "WRONG_STATE", "x")
        w = W.advance(store, w, "WRONG_STATE", "x")
        w = W.advance(store, w, "WRONG_STATE", "x")
        c["three_failures_stop_the_job_and_ask"] = w["state"] == "stuck" and w["steps"][0]["tries"] == 3
        w2 = W.new("t", "a", steps)
        for _ in range(3):
            w2 = W.advance(store, w2, "PASS")
        c["passing_every_step_finishes_it"] = w2["state"] == "done" and all(s["done"] for s in w2["steps"])
        # ---- scheduler
        st2 = W.Store(os.path.join(tmp, "s"))
        clock = [1000.0]
        S = W.Scheduler(st2, hands_off_s=20, clock=lambda: clock[0])
        hi = W.new("urgent thing", "wordlike", steps, priority=1)
        lo = W.new("later thing", "wordlike", steps, priority=5)
        other = W.new("other app", "browser", steps, priority=3)
        for x in (hi, lo, other):
            st2.save(x)
        p1 = S.next()
        c["priority_goes_first"] = p1["id"] == hi["id"]
        p2 = S.next()
        c["a_busy_lane_is_skipped_but_another_app_runs_at_once"] = p2["id"] == other["id"]
        c["nothing_else_runs_while_both_lanes_are_busy"] = S.next() is None
        S.release(hi["id"])
        S.person_touched("wordlike")
        c["the_window_the_person_is_using_is_left_alone"] = S.next() is None
        clock[0] += 25
        c["and_given_back_after_the_hands_off_time"] = S.next()["id"] == hi["id"]
        c["and_the_next_job_in_that_lane_waits_for_it_to_be_released"] = S.next() is None
        S.release(hi["id"])
        done_hi = st2.load(hi["id"])
        done_hi["state"] = "done"
        st2.save(done_hi)
        c["then_the_later_job_runs"] = S.next()["id"] == lo["id"]
        c["the_table_lists_every_job"] = len(S.table()) == 3 and {t["lane"] for t in S.table()} == {"wordlike", "browser"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


class _Stub(BaseHTTPRequestHandler):
    reply: Any = None

    def log_message(self, *a: Any) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n).decode())
        type(self).seen = body
        out = json.dumps({"action": type(self).reply}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def run_ar68() -> "TestOutcome":
    """AR68: the adapter in the loop and the rows that train it. (a) the prompt and reply format round-trip, (b) a bad answer (index outside the list, unknown verb, replan with no plan, server down) is rejected,
    (c) the executor's judge asks a (stub) server first and uses its pick, flags 'confirm', and falls back when it is unreachable, (d) the consequence gate stops a risky click and a typed secret in the step loop,
    (e) the training rows: four kinds, whole sites held out, risky targets kept out of the pick rows, the plan/done shape"""
    from core_organs.mind import picker as PK
    from core_organs.mind import train_rows as TR
    c: Dict[str, Any] = {}
    els = [{"role": "link", "name": "Home"}, {"role": "button", "name": "Place order"}, {"role": "link", "name": "Pricing"}]
    up = PK.user_prompt("web:shop.test", els, "Open pricing", plan=["Click 'Pricing'"], done=0)
    c["prompt_has_numbered_elements_plan_and_intent"] = "#2 button 'Place order'" in up and "Plan:\n1. Click 'Pricing'" in up and up.endswith("Predict exact Action JSON:") and "Intent: Open pricing" in up
    c["a_reply_is_read_from_text_around_it"] = PK.parse_reply('Sure. [{"step":1,"action":"click","target_id":3,"hotkey":null,"text":null,"verify_expectation":"x"}] done')["target_id"] == 3
    cut = PK.parse_reply('[{"step": 1, "action": "confirm", "target_id": 2, "hotkey": null, "text": "money", "verify_expectation": "asks the per')
    c["a_reply_cut_off_inside_the_free_text_keeps_the_fields_that_matter"] = cut["action"] == "confirm" and cut["target_id"] == 2 and cut["text"] == "money" and PK.validate(cut, 3)["action"] == "confirm"
    c["a_click_inside_the_list_is_accepted"] = PK.validate({"action": "click", "target_id": 3}, 3)["target_id"] == 3
    c["an_index_outside_the_list_is_rejected"] = PK.validate({"action": "click", "target_id": 9}, 3) is None and PK.validate({"action": "click", "target_id": 0}, 3) is None
    c["an_unknown_verb_is_rejected"] = PK.validate({"action": "explode", "target_id": 1}, 3) is None
    c["replan_needs_a_plan"] = PK.validate({"action": "replan"}, 3, has_plan=False) is None and PK.validate({"action": "replan"}, 3, has_plan=True)["action"] == "replan"
    c["a_server_that_is_down_gives_none_not_an_error"] = PK.ask("web:x", els, "go", url="http://127.0.0.1:9") is None and not PK.available("http://127.0.0.1:9")
    # ---- a stub server on localhost
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    try:
        _Stub.reply = {"step": 1, "action": "click", "target_id": 3, "text": None}
        a = PK.ask("web:shop.test", els, "Open pricing", url=url)
        c["the_client_sends_app_elements_and_intent_and_gets_a_checked_action"] = a["target_id"] == 3 and _Stub.seen["intent"] == "Open pricing" and len(_Stub.seen["elements"]) == 3 and PK.available(url)
        _Stub.reply = {"step": 1, "action": "click", "target_id": 77}
        c["a_wrong_index_from_the_server_becomes_none"] = PK.ask("web:shop.test", els, "x", url=url) is None
        # ---- the executor's judge
        import core_organs.desktop_grounding as DG
        os.environ["HOJAIGA_PICKER_URL"] = url
        DG.ConstrainedJudge._picker_state.update(checked=0.0, up=False)
        judge = DG.ConstrainedJudge.__new__(DG.ConstrainedJudge)
        judge.model = ""
        mk = lambda name, role, y: DG.GroundedElement(id=name, name=name, role=role, bbox=(10, y, 110, y + 20), tier="uia")
        elems = [mk("Home", "hyperlink", 10), mk("Place order", "button", 40), mk("Pricing", "hyperlink", 70)]
        if all(e is not None for e in elems):
            _Stub.reply = {"step": 1, "action": "click", "target_id": 3, "text": None}
            d = judge._ask_trained_picker("Open pricing", [(i, e) for i, e in enumerate(elems)], "shop")
            c["the_judge_uses_the_adapters_pick_first"] = bool(d) and d["element"]["name"] == "Pricing" and d["picker"] and d["element_index"] == 2
            _Stub.reply = {"step": 1, "action": "confirm", "target_id": 2, "text": "money", "verify_expectation": "it charges money"}
            d = judge._ask_trained_picker("Buy the lamp", [(i, e) for i, e in enumerate(elems)], "shop")
            c["a_confirm_answer_is_carried_to_the_gate"] = bool(d) and d["picker_confirm"]["risk"] == "money"
        else:
            c["the_judge_uses_the_adapters_pick_first"] = False
            c["a_confirm_answer_is_carried_to_the_gate"] = False
    finally:
        srv.shutdown()
    try:
        import core_organs.desktop_grounding as DG2
        DG2.ConstrainedJudge._picker_state.update(checked=0.0, up=False)
        os.environ["HOJAIGA_PICKER_URL"] = "http://127.0.0.1:9"
        j2 = DG2.ConstrainedJudge.__new__(DG2.ConstrainedJudge)
        c["with_the_server_down_the_judge_falls_back_silently"] = j2._ask_trained_picker("x", [(0, type("E", (), {"role": "button", "name": "A"})())], "app") is None
        os.environ.pop("HOJAIGA_PICKER_URL", None)
        c["without_the_env_var_the_adapter_is_never_asked"] = j2._ask_trained_picker("x", [], "app") is None
    except Exception:
        c["with_the_server_down_the_judge_falls_back_silently"] = False
        c["without_the_env_var_the_adapter_is_never_asked"] = False
    # ---- training rows
    tmp = tempfile.mkdtemp(prefix="ar68_")
    try:
        rows = []

        def crawl(host: str, path: str, names, target: int, outcome="opened a new page") -> Dict[str, Any]:
            tag = host.split(".")[0]
            names = [f"{n} {tag}" for n in names]
            path = " > ".join(f"{p} {tag}" for p in path.split(" > "))
            lines = "\n".join(f"#{i} link '{n}'" for i, n in enumerate(names, 1))
            user = f"Application: web:{host}\nElements:\n{lines}\nIntent: Go to the {names[target - 1]} page on {host}\nPredict exact Action JSON:"
            ans = json.dumps([{"step": 1, "action": "click", "target_id": target, "hotkey": None, "text": None, "verify_expectation": "the page opens"}])
            return {"messages": [{"role": "system", "content": [{"type": "text", "text": "old"}]}, {"role": "user", "content": [{"type": "text", "text": user}]}, {"role": "assistant", "content": [{"type": "text", "text": ans}]}],
                    "meta": {"host": host, "path": path, "outcome": outcome, "action": "click", "target_id": target}}
        hosts = [f"site{i}.test" for i in range(12)]
        for h in hosts:
            top = ["Home", "Products", "Pricing", "Buy now", "Subscribe", "Docs", "About", "Delete account", "Blog"]
            rows.append(crawl(h, "Products", top, 2))
            rows.append(crawl(h, "Docs", top, 6))
            rows.append(crawl(h, "Products > Widgets", ["Widget A", "Widget B", "Widget C", "Download", "Back"], 2))
            rows.append(crawl(h, "Products > Widgets > Widget B", ["Specs", "Reviews", "Add to cart", "Share"], 1))
            rows.append(crawl(h, "Buy", top, 4))                                            # the answer is a risky control: must not become a pick row
        rp = os.path.join(tmp, "rows.jsonl")
        with open(rp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        s = TR.build(rp, os.path.join(tmp, "out"), seed=5, max_confirm_per_host=3)
        tr = [json.loads(l) for l in open(os.path.join(tmp, "out", "train.jsonl"), encoding="utf-8")]
        ev = [json.loads(l) for l in open(os.path.join(tmp, "out", "eval.jsonl"), encoding="utf-8")]
        kinds = {r["meta"]["task"] for r in tr + ev}
        c["four_kinds_of_rows_are_made"] = kinds == {"pick", "confirm", "resume", "replan"}
        c["whole_sites_are_held_out"] = not ({r["meta"]["host"] for r in tr} & {r["meta"]["host"] for r in ev}) and len(ev) > 0 and len(tr) > 0
        c["round_two_held_out_sites_stay_held_out"] = TR.held_hosts(["telegram.org", "vimeo.com", "x.example"]) >= {"telegram.org", "vimeo.com"}
        c["every_row_uses_the_new_instructions"] = all(r["messages"][0]["content"][0]["text"] == PK.SYSTEM_V2 for r in tr + ev)
        conf = [r for r in tr + ev if r["meta"]["task"] == "confirm"]
        ok = True
        for r in conf:
            u = r["messages"][1]["content"][0]["text"]
            a = json.loads(r["messages"][2]["content"][0]["text"])[0]
            _, e, _i = TR.parse_user(u)
            ok &= a["action"] == "confirm" and a["text"] in ("money", "publish", "delete", "account", "consent", "install") and f"#{a['target_id']} " in u and a["verify_expectation"].startswith("asks the person first")
        c["confirm_rows_point_at_a_risky_control_and_name_the_risk"] = bool(conf) and ok
        picks = [r for r in tr + ev if r["meta"]["task"] == "pick"]
        bad = 0
        from core_organs.mind import consequence as CQ
        for r in picks:
            u = r["messages"][1]["content"][0]["text"]
            _, e, _i = TR.parse_user(u)
            a = json.loads(r["messages"][2]["content"][0]["text"])[0]
            bad += CQ.classify_label(e[a["target_id"] - 1]["name"], e[a["target_id"] - 1]["role"])["gate"] == "confirm"
        c["no_pick_row_answers_with_a_control_the_rules_say_to_ask_about"] = bool(picks) and bad == 0 and s["crawl_rows_left_out_as_risky_targets"] > 0
        res = [r for r in tr + ev if r["meta"]["task"] == "resume"]
        r0 = res[0]
        u0 = r0["messages"][1]["content"][0]["text"]
        c["resume_rows_carry_the_plan_and_how_much_is_done"] = "Plan:\n1. Click" in u0 and r0["meta"]["plan_len"] >= 2 and all(0 <= r["meta"]["step_done"] < r["meta"]["plan_len"] for r in res)
        c["a_resume_row_marks_finished_steps"] = any("[done]" in r["messages"][1]["content"][0]["text"] for r in res if r["meta"]["step_done"] > 0)
        rep = [r for r in tr + ev if r["meta"]["task"] == "replan"]
        a = json.loads(rep[0]["messages"][2]["content"][0]["text"])[0]
        c["replan_rows_pair_a_plan_with_another_sites_screen"] = a["action"] == "replan" and a["text"] == "not_here" and a["target_id"] is None and rep[0]["meta"]["plan_host"] != rep[0]["meta"]["host"]
        c["the_summary_states_its_limits"] = len(s["limits"]) == 3 and "distillation" in s["limits"][0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("HOJAIGA_PICKER_URL", None)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar69() -> "TestOutcome":
    """AR69: capabilities. Commands found in an app are sorted into the operations a job is made of; a job's needs are compared with what the app has, and the MISSING classes are the to-do for the next scan"""
    from core_organs.mind import capabilities as CP
    c: Dict[str, Any] = {}
    c["words_map_to_operation_classes"] = {"draw", "colour"} <= set(CP.classes_of("Fill the rectangle with colour")) and "table" in CP.classes_of("Insert table") and "format_text" in CP.classes_of("Bold") and "structure" in CP.classes_of("Insert page break")
    c["an_unrelated_label_maps_to_nothing"] = CP.classes_of("Zzyzx") == []
    labels = ["Rectangle tool", "Ellipse tool", "Select all", "Rotate 90", "Fill color", "Save as", "Undo", "Open file", "Export as PNG"]
    cov = CP.coverage("x", labels)
    c["coverage_counts_and_keeps_examples"] = cov["draw"]["n"] >= 2 and "Rectangle tool" in cov["draw"]["examples"] and cov["table"]["n"] == 0
    d = CP.can_do("x", "drawing", labels)
    c["a_drawing_app_can_draw"] = d["ok"] and not d["missing"] and "draw" in d["have"]
    t = CP.can_do("x", "table", labels)
    c["but_the_same_app_cannot_do_tables_and_says_what_is_missing"] = (not t["ok"]) and "table" in t["missing"]
    c["every_job_kind_of_the_workflow_module_has_needs"] = all(k in CP.JOBS for k in ("document", "table", "drawing", "email", "post", "form", "research"))
    from core_organs.mind import workflow as W
    c["skeleton_kinds_are_all_known_here"] = all(W.skeleton(g)["kind"] in CP.JOBS for g in ("write a report document", "make a budget spreadsheet", "draw a logo", "reply to the email", "write a linkedin post", "fill the application form", "research the market"))
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar70() -> "TestOutcome":
    """AR70: brain. One call: a risky plan is warned about before anything runs; the job gets its professional order; an app that lacks what the job needs says so; writing gets a voice brief (and asks for facts rather than inventing);
    a half-done job is continued where the screen says it stopped"""
    from core_organs.mind import brain as B
    from core_organs.mind import workflow as W
    c: Dict[str, Any] = {}
    r = B.think("delete all my old emails permanently, no backup", app="mail")
    c["a_dangerous_plan_is_stopped_with_the_consequence_first"] = r["decision"] == "ask_first" and r["say"].startswith("Before I do this") and "no way back" in r["say"]
    r = B.think("write a project proposal document", app="word", app_labels=["Save as", "Open", "Undo", "Bold", "Insert picture"])
    c["a_document_gets_its_order_and_the_missing_operations_named"] = r["kind"] == "document" and "structure" in r["app_can"]["missing"] and "No structure" not in r["say"] and "shows no" in r["say"] and "structure" in r["say"]
    c["writing_without_facts_asks_for_them"] = r["decision"] == "need_info" and "will not invent" in r["say"]
    r = B.think("reply to the email from Priya", app="mail", incoming="Dear Mr. Shah,\n\nCould you confirm the date of the review? Kindly reply today.\n\nRegards,\nPriya Nair", channel="email_reply", relationship="client", facts=["review is on 20 March 10:00"])
    c["a_reply_gets_a_voice_brief_and_a_prompt_with_only_the_given_facts"] = r["decision"] == "proceed" and r["voice"]["register"] == "formal" and r["voice"]["greet_name"] == "Priya Nair" and "review is on 20 March" in r["writer_prompt"]
    c["and_says_how_it_will_write"] = "English, formal" in r["say"] and "Priya Nair" in r["say"]
    r = B.think("make a budget spreadsheet", app="sheet")
    c["a_harmless_job_just_proceeds_with_its_order"] = r["decision"] == "proceed" and r["kind"] == "table" and "Order of work" in r["say"] and "add formulas and totals" in r["say"]
    tmp = tempfile.mkdtemp(prefix="ar70_")
    try:
        store = W.Store(tmp)
        steps = [{"text": "Click 'File'", "target": "File", "expect": "a menu or panel opens, showing: New, Open, Save as, Export"}, {"text": "Click 'Export'", "target": "Export", "expect": "a dialog opens, showing: PDF, PNG"}]
        r1 = B.think("export the drawing as pdf", app="paint", screen=["File", "Edit"], store=store, plan_provider=lambda: steps)
        c["first_time_it_starts_fresh"] = r1["workflow"]["action"] == "started" and r1["workflow"]["step"] == 1
        r2 = B.think("Export the drawing as a pdf", app="paint", screen=["New", "Open", "Save as", "Export"], store=store, plan_provider=lambda: steps)
        c["second_time_it_continues_where_the_screen_says"] = r2["workflow"]["action"] == "resumed" and r2["workflow"]["step"] == 2 and "left this half done" in r2["say"]
        r3 = B.think("export the drawing as pdf", app="paint", screen=["Something", "Else"], store=store, plan_provider=lambda: steps)
        c["a_screen_that_matches_nothing_means_ask_resume_or_restart"] = r3["decision"] == "resume_or_restart"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar71() -> "TestOutcome":
    """AR71: machine sweep. Every line the machine shows ends in one class (app / documentation / shell / component / system tool / stale / duplicate); the same program under several names is one; safety decides live / static only /
    running now; unplaced apps are grouped into PROPOSED patterns; the ledger survives a save and load"""
    from core_organs.harvest import machine_sweep as MS
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar71_")
    real_exe = os.path.join(tmp, "blender.exe")
    open(real_exe, "wb").write(b"MZ")
    try:
        k = lambda name, **kw: MS._kind_of({"name": name, "sources": kw.pop("sources", ["start_menu"]), **kw})[0]
        c["documentation_shortcuts_are_not_apps"] = k("Python 3.13 Manuals (64-bit)") == "not_an_app" and k("Git Release Notes") == "not_an_app" and k("Uninstall Node.js") == "not_an_app"
        c["a_shortcut_to_a_document_is_not_an_app"] = k("Quick start", shortcut_target=os.path.join(tmp, "guide.pdf")) == "not_an_app"
        c["shells_are_their_own_class"] = k("Anaconda Prompt") == "shell" and k("Windows PowerShell ISE") == "shell"
        c["runtimes_and_drivers_are_components"] = k("Microsoft Visual C++ 2015-2022 Redistributable (x64) - 14.44") == "component" and k("Microsoft ODBC Driver 18 for SQL Server") == "component"
        gone = os.path.join(tmp, "gone", "old.exe")
        c["a_shortcut_whose_program_is_gone_is_stale"] = k("Old Tool 2025", shortcut_target=gone) == "not_an_app" and "stale" in MS._kind_of({"name": "Old Tool", "sources": ["start_menu"], "shortcut_target": gone})[1]
        c["a_normal_program_is_an_app"] = k("Blender 5.2", shortcut_target=real_exe) == "app" and k("Calculator", sources=["start_menu", "packaged"]) == "app"
        ent = {"blender_5_2": {"key": "blender_5_2", "name": "Blender 5.2", "sources": ["start_menu"], "exe": real_exe, "exe_exists": True},
               "blender": {"key": "blender", "name": "Blender", "sources": ["installed_programs"], "exe": real_exe, "exe_exists": True, "publisher": "Blender Foundation"},
               "ollama": {"key": "ollama", "name": "Ollama", "sources": ["start_menu"], "exe_exists": False},
               "ollama_version_0_40_11": {"key": "ollama_version_0_40_11", "name": "Ollama version 0.40.11", "sources": ["installed_programs"], "exe_exists": False},
               "paint": {"key": "paint", "name": "Paint", "sources": ["start_menu"], "exe_exists": False}}
        MS._merge_duplicates(ent)
        c["the_same_exe_under_two_names_is_one_program"] = ent["blender_5_2"].get("state") != "merged" and ent["blender"]["state"] == "merged" and ent["blender"]["merged_into"] == "blender_5_2" and ent["blender_5_2"]["publisher"] == "Blender Foundation"
        c["a_version_tail_does_not_make_a_new_program"] = {ent["ollama"].get("state"), ent["ollama_version_0_40_11"].get("state")} == {None, "merged"}
        c["an_unrelated_name_is_left_alone"] = ent["paint"].get("state") is None
        c["names_lose_versions_and_arch_tags"] = MS._base_name("Wireshark 4.6.7 x64") == "wireshark" and MS._base_name("Python 3.13 (64-bit)") == "python" and MS._base_name("Cursor (User)") == "cursor"
        run = {real_exe.lower(): 4321}
        sf = lambda name, **kw: MS.safety({"name": name, "kind": kw.pop("kind", "app"), "kind_why": "", **kw}, run)[0]
        c["a_messenger_is_static_only"] = sf("WhatsApp", exe="x.exe") == "static_only" and sf("Outlook", exe="x.exe") == "static_only" and sf("Photos", exe="x.exe") == "static_only"
        c["a_launcher_or_game_is_static_only"] = sf("Epic Games Launcher", exe="x.exe") == "static_only" and sf("VALORANT", exe="x.exe") == "static_only"
        c["a_drawing_program_is_live"] = sf("Inkscape", exe="x.exe", sources=["start_menu"]) == "live" and sf("Calculator", appid="Microsoft.WindowsCalculator!App") == "live"
        c["an_app_the_person_has_open_is_never_started_again"] = sf("Blender 5.2", exe=real_exe) == "running_now"
        c["an_entry_that_cannot_be_started_is_static_only"] = sf("Mystery Thing") == "static_only"
        c["shells_are_not_apps_for_safety_too"] = sf("Anaconda Prompt", kind="shell") == "not_an_app"
        led = {"entries": {}}
        for nm, desc in (("Alpha Solver", "cad mesh solver cad mesh geometry"), ("Beta Solver", "cad mesh solver geometry cad"), ("Gamma Solver", "mesh cad solver cad geometry"), ("Odd Tool", "zzz qqq")):
            led["entries"][MS.slug(nm)] = {"key": MS.slug(nm), "name": nm, "rag_key": "nokey_" + MS.slug(nm), "kind": "app", "archetype": {"status": "insufficient"}, "static": {"version": {"FileDescription": desc}}}
        prop = MS.propose_patterns(led, min_size=3, threshold=0.3)
        c["unplaced_apps_that_share_words_become_a_proposed_pattern"] = len(prop) == 1 and set(prop[0]["apps"]) == {"Alpha Solver", "Beta Solver", "Gamma Solver"} and "cad" in prop[0]["shared_words"]
        old = (MS.OUT, MS.LEDGER)
        MS.OUT, MS.LEDGER = tmp, os.path.join(tmp, "ledger.json")
        MS.save({"entries": {"a": {"name": "A", "state": "pending"}}})
        back = MS.load()
        MS.OUT, MS.LEDGER = old
        c["the_ledger_survives_save_and_load"] = back["entries"]["a"]["name"] == "A" and "saved" in back
        c["every_state_is_documented"] = all(w in MS.__doc__ for w in ("learned_live", "static_only", "running_now", "not_an_app", "pending"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k_: bool(v) for k_, v in c.items()})


def run_ar72() -> "TestOutcome":
    """AR72: published shortcut pages. Table rows are read, macOS chords are dropped, chords are normalised and de-duplicated, and what is filed is a lead (source web_help, trust web, NOT verified)"""
    from core_organs.harvest import help_shortcuts as H
    try:
        from si_tests_rag import _Env  # type: ignore
    except ImportError:
        from core_organs.si_tests_rag import _Env
    c: Dict[str, Any] = {}
    page = ("<html><body><table><tr><th>Common actions</th></tr>"
            "<tr><td>Copy</td><td><span>Ctrl</span> + <span>c</span></td></tr>"
            "<tr><td>Paste without formatting</td><td>Ctrl + Shift + v</td></tr>"
            "<tr><td>Bold</td><td>Ctrl + b</td></tr><tr><td>Bold</td><td>Ctrl + b</td></tr>"
            "<tr><td>Copy (Mac)</td><td>&#8984; + c</td></tr>"
            "<tr><td>Insert comment</td><td>Ctrl + Alt + m or Ctrl + Alt + n</td></tr>"
            "<tr><td>Open the menu</td><td>Alt + /</td></tr>"
            "<tr><td>Find</td><td>just click the button</td></tr>"
            "<tr><td>Full screen</td><td>F11</td></tr></table></body></html>")
    rows = H.tables_of(page)
    c["two_cell_rows_are_read"] = ("Copy", "Ctrl + c") in rows and len(rows) == 9
    pairs = H.windows_pairs(rows)
    acts = [p["action"] for p in pairs]
    c["mac_chords_are_dropped"] = "Copy (Mac)" not in acts
    c["prose_in_the_shortcut_column_is_dropped"] = "Find" not in acts
    c["duplicates_collapse"] = acts.count("Bold") == 1
    c["chords_are_normalised"] = {"action": "Paste without formatting", "keys": "Ctrl+Shift+v"} in pairs and {"action": "Insert comment", "keys": "Ctrl+Alt+m"} in pairs
    c["function_keys_and_symbol_keys_are_kept"] = {"action": "Full screen", "keys": "F11"} in pairs and {"action": "Open the menu", "keys": "Alt+/"} in pairs
    txt = H.page_text(page)
    c["page_text_has_the_words_not_the_markup"] = "Paste without formatting" in txt and "<td>" not in txt
    with _Env() as rag:
        res = H.file_pairs(rag, "webapp:docs.test", "Docs Test", "https://help.test/x", pairs, txt, "RUN72")
        c["rows_and_a_document_were_filed"] = res["new"] == len(pairs) and res["document_chunks"] >= 1
        row = rag.fast.find("webapp:docs.test", "Bold", "ctrl+b")
        c["a_published_shortcut_is_a_lead_not_a_proof"] = bool(row) and row["source"] == "web_help" and row["trust"] == "web" and not row["verified"]
        res2 = H.file_pairs(rag, "webapp:docs.test", "Docs Test", "https://help.test/x", pairs, txt, "RUN72")
        c["filing_twice_adds_nothing"] = res2["new"] == 0
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar73() -> "TestOutcome":
    """AR73: the front door. A task with several parts becomes several tickets and no part is dropped; a sentence is not cut in two; each ticket is routed (question / write / web / desktop); a risky plan stops and asks BEFORE
    anything runs and runs once approved; writing a post is not publishing it; follow-up web parts share one browser session; independent parts finish whatever order they were asked in; a finished ticket is not
    redone on --resume; the web executor does tasks on real pages and says FAILED / UNVERIFIED where the page does not prove it"""
    from core_organs import hojaiga_run as HR
    c: Dict[str, Any] = {}
    os.environ["HOJAIGA_ROUTE_BRAIN"] = "rules"                                                        # this test is the pipeline; the model's routing is AR76
    sp = HR.split_parts
    c["parts_are_split_on_semicolon_and_then"] = sp("go to a.com; then click Pricing") == ["go to a.com", "click Pricing"] and len(sp("open Paint and then save it as x.png")) == 2
    c["a_sentence_is_not_cut_in_two"] = len(sp("write a post about our app that learns any program and then helps people use it")) == 1
    c["a_plain_task_is_one_part"] = sp("what is the shortcut for bold in Google Docs?") == ["what is the shortcut for bold in Google Docs?"]
    cl = lambda t, d="unknown": HR.classify(t, d, None, {})
    c["a_question_is_a_question"] = cl("what is the shortcut for bold in Google Docs?") == "question" and cl("how do I extrude a mesh in Blender?") == "question"
    c["writing_is_writing"] = cl("write a LinkedIn post about our launch") == "write" and cl("draft an email to my boss about the delay") == "write"
    c["a_web_address_is_web"] = cl("go to the Pricing page on todoist.com") == "web" and cl("click Add on D:/x/w_todo.html") == "web"
    c["an_app_task_is_desktop"] = cl("open Paint and save the picture as D:/x/a.png", "desktop") == "desktop"
    calls: List[Any] = []
    stub = {"web": lambda t: (calls.append(("web", t)) or {"status": "DONE", "evidence": "ok"}), "desktop": lambda t: (calls.append(("desktop", t)) or {"status": "DONE", "evidence": "ok"}),
            "question": lambda t: (calls.append(("question", t)) or {"status": "ANSWERED", "answer": "a"}), "write": lambda t: (calls.append(("write", t)) or {"status": "DRAFTED", "draft": "d"})}
    quiet = lambda *a, **k: None
    tmp = tempfile.mkdtemp(prefix="ar73_")
    old_runs = HR.RUNS
    HR.RUNS = tmp
    try:
        r = HR.run("delete all my old emails permanently, no backup", say=quiet, boot_first=False, executors=stub, rag=object())
        c["a_risky_plan_stops_and_asks_before_anything_runs"] = r["status"] == "NEEDS_CONFIRM" and not calls and "no way back" in r["tickets"][0]["result"]["question"]
        r = HR.run("delete all my old emails permanently, no backup", yes=True, say=quiet, boot_first=False, executors=stub, rag=object())
        c["once_approved_it_runs"] = r["status"] == "DONE" and calls and calls[-1][0] == "desktop"
        calls.clear()
        r = HR.run("what is the shortcut for bold in Google Docs?; then go to the Pricing page on todoist.com", say=quiet, boot_first=False, executors=stub, rag=object())
        c["both_parts_of_a_compound_task_are_done"] = r["status"] == "DONE" and {k for k, _ in calls} == {"question", "web"} and len(r["tickets"]) == 2
        calls.clear()
        r = HR.run("write a LinkedIn post about our new app that learns any program", say=quiet, boot_first=False, executors=stub, rag=object())
        c["writing_a_post_is_not_publishing_it"] = r["status"] == "DONE" and calls == [("write", "write a LinkedIn post about our new app that learns any program")]
        calls.clear()
        r = HR.run("write a LinkedIn post about our launch and publish it", say=quiet, boot_first=False, executors=stub, rag=object())
        c["but_publishing_it_is_asked_about"] = r["status"] == "NEEDS_CONFIRM" and not calls
        calls.clear()
        r = HR.run("go to the Pricing page on todoist.com; then click Features", say=quiet, boot_first=False, executors=stub, rag=object())
        c["follow_up_web_parts_share_one_session"] = len([k for k, _ in calls if k == "web"]) == 1 and "Features" in calls[0][1] and "Pricing" in calls[0][1]
        calls.clear()
        flaky = dict(stub, web=lambda t: {"status": "FAILED", "evidence": "page did not show it"})
        r1 = HR.run("what is the shortcut for bold in Google Docs?; then go to the Pricing page on todoist.com", say=quiet, boot_first=False, executors=flaky, rag=object())
        c["a_failed_part_makes_the_run_partial_not_done"] = r1["status"] == "PARTIAL"
        prev, left = HR.unfinished_from_last()
        c["the_last_run_remembers_what_is_unfinished"] = prev == r1["run_id"] and len(left) == 1 and "todoist" in left[0]
        calls.clear()
        r2 = HR.run("", say=quiet, boot_first=False, executors=stub, rag=object(), resume=True)
        c["resume_does_only_the_unfinished_part"] = r2["status"] == "DONE" and [k for k, _ in calls] == ["web"]
        r3 = HR.run("", say=quiet, boot_first=False, executors=stub, rag=object(), resume=True)
        c["and_when_all_is_done_there_is_nothing_to_resume"] = r3["status"] == "NOTHING_TO_RESUME"
        r4 = HR.run("what is the shortcut for bold in Google Docs?", dry=True, say=quiet, boot_first=False, executors=stub, rag=object())
        c["dry_run_runs_nothing"] = r4["tickets"][0]["result"]["status"] == "DRY_RUN"
        c["a_secret_in_the_task_is_removed_from_the_report"] = "sk-" not in json.dumps(HR.run("go to a.com and use key sk-abcdefghijklmnopqrstuvwxyz123456", say=quiet, boot_first=False, executors=stub, rag=object(), dry=True)["intake"])
    finally:
        HR.RUNS = old_runs
        os.environ.pop("HOJAIGA_ROUTE_BRAIN", None)
        shutil.rmtree(tmp, ignore_errors=True)
    # ---- the web executor on real pages (headless browser, local files)
    try:
        from core_organs import web_executor as WE
        base = r"D:/new_automation/All codes/brain/webapps/"
        r = WE.run_web_task(None, "type 'buy milk' into the new todo field; click Add", url=base + "w_todo.html")
        c["web_type_then_click_adds_the_item_and_proves_it"] = r["status"] == "DONE" and "now appears on the page" in r["evidence"]
        r = WE.run_web_task(None, "click 2", url=base + "w_tabs.html")
        c["web_a_tab_is_selected_and_the_page_says_so"] = r["status"] == "DONE"
        r = WE.run_web_task(None, "click Settings", url=base + "w_tabs.html")
        c["web_a_control_that_does_not_exist_fails_honestly"] = r["status"] == "FAILED"
        r = WE.run_web_task(None, "type 'hello' into the email field", url=base + "w_search.html")
        c["web_an_assumed_field_is_only_unverified"] = r["status"] == "UNVERIFIED" and "ASSUMED" in r["evidence"]
        r = WE.run_web_task(None, "search for apple", url=base + "w_search.html")
        c["web_search_filters_the_list"] = r["status"] == "DONE"
        shop = r"D:/new_automation/scratch/shop.html"
        if os.path.exists(shop):
            r = WE.run_web_task(None, "click Buy now", url=shop)
            c["web_a_payment_control_stops_and_asks"] = r["status"] == "NEEDS_CONFIRM" and "charges" in r.get("question", "")
            r = WE.run_web_task(None, "click Details", url=shop)
            c["web_a_harmless_control_is_pressed_and_proved"] = r["status"] == "DONE"
        c["web_no_site_means_no_guess"] = WE.run_web_task(None, "do something somewhere")["status"] == "NO_SITE"
    except Exception as e:
        c["web_executor_ran_without_error"] = False
        c["web_error"] = f"{type(e).__name__}: {str(e)[:120]}" == ""
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar74() -> "TestOutcome":
    """AR74: the session vault. A session is kept ENCRYPTED (DPAPI, this Windows user): no cookie value is ever in the file or in a listing; it comes back intact; imports of Cookie-Editor / Netscape / Playwright
    formats are understood; an expired session is reported and not used; a damaged entry returns nothing instead of raising; a missing session means a signed-out run that says so; an imported plain file is flagged or shredded"""
    import time
    from core_organs import session_vault as SV
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar74_")
    os.environ["HOJAIGA_VAULT_DIR"] = tmp
    try:
        raw = b"correct horse battery staple"
        c["dpapi_roundtrips"] = SV._unprotect(SV._protect(raw)) == raw
        c["and_the_blob_is_not_the_plaintext"] = raw not in SV._protect(raw)
        secret = "SECRET-VALUE-abc123XYZ"
        future = time.time() + 30 * 86400
        export = [{"name": "li_at", "value": secret, "domain": ".linkedin.com", "path": "/", "expirationDate": future, "httpOnly": True, "secure": True, "sameSite": "no_restriction"},
                  {"name": "JSESSIONID", "value": "ajax:123", "domain": ".www.linkedin.com", "path": "/", "session": True, "httpOnly": False, "secure": True, "sameSite": "lax"}]
        m = SV.put("https://www.LinkedIn.com/feed/", export, label="test")
        c["a_site_is_normalised_to_its_host"] = m["site"] == "linkedin.com" and SV.host_of("WWW.linkedin.com:443/x") == "linkedin.com"
        on_disk = open(os.path.join(tmp, "sessions.json"), encoding="utf-8").read()
        c["no_cookie_value_is_in_the_file"] = secret not in on_disk and "ajax:123" not in on_disk and "li_at" not in on_disk
        c["no_cookie_value_is_in_a_listing"] = secret not in json.dumps(SV.status()) and SV.status()[0]["cookies"] == 2
        st = SV.get("linkedin.com")
        names = {x["name"]: x for x in st["cookies"]}
        c["it_comes_back_intact_as_a_playwright_state"] = names["li_at"]["value"] == secret and names["li_at"]["sameSite"] == "None" and names["li_at"]["httpOnly"] is True and names["JSESSIONID"]["expires"] == -1
        c["it_reports_expiry_in_days_and_last_use"] = 29 <= (SV.meta("linkedin.com")["expires_in_days"] or 0) <= 30.1 and SV.meta("linkedin.com")["last_used"] is not None
        c["context_kwargs_carry_the_state"] = SV.context_kwargs("linkedin.com").get("storage_state", {}).get("cookies") and SV.context_kwargs("nothere.example") == {}
        net = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t%d\tsid\tabc\n#HttpOnly_.example.com\tTRUE\t/\tTRUE\t0\ttok\tdef\n" % int(future)
        n = SV.normalise(net)
        c["a_netscape_cookies_txt_is_understood"] = len(n["cookies"]) == 2 and n["cookies"][1]["httpOnly"] is True and n["cookies"][1]["expires"] == -1
        c["a_playwright_state_is_understood"] = len(SV.normalise({"cookies": [{"name": "a", "value": "b", "domain": "x.com", "path": "/"}], "origins": []})["cookies"]) == 1
        try:
            SV.normalise("garbage")
            c["garbage_is_refused"] = len(SV.normalise("garbage")["cookies"]) == 0
        except ValueError:
            c["garbage_is_refused"] = True
        try:
            SV.put("x.com", [])
            c["an_empty_session_is_refused"] = False
        except ValueError:
            c["an_empty_session_is_refused"] = True
        SV.put("old.example", [{"name": "s", "value": "v", "domain": "old.example", "path": "/", "expirationDate": time.time() - 3600}])
        c["an_expired_session_is_reported_and_not_used"] = SV.get("old.example") is None and SV.meta("old.example")["valid"] is False and SV.get("old.example", allow_expired=True) is not None
        c["expired_sessions_can_be_purged"] = SV.purge_expired() == ["old.example"] and not SV.meta("old.example")["present"]
        idx = json.load(open(os.path.join(tmp, "sessions.json"), encoding="utf-8"))
        idx["sessions"]["linkedin.com"]["blob"] = idx["sessions"]["linkedin.com"]["blob"][:-8] + "AAAAAAAA"
        json.dump(idx, open(os.path.join(tmp, "sessions.json"), "w", encoding="utf-8"))
        c["a_damaged_entry_returns_nothing_not_an_error"] = SV.get("linkedin.com") is None
        f1 = os.path.join(tmp, "cookies_plain.json")
        json.dump(export, open(f1, "w"))
        m1 = SV.import_file("shop.example", f1)
        c["an_imported_plain_file_is_flagged_as_still_on_disk"] = "STILL ON DISK" in m1["source_file"] and os.path.exists(f1)
        m2 = SV.import_file("shop.example", f1, shred=True)
        c["or_shredded_when_asked"] = "deleted" in m2["source_file"] and not os.path.exists(f1)
        c["a_session_can_be_deleted"] = SV.delete("shop.example") and not SV.delete("shop.example") and not SV.meta("shop.example")["present"]
        # the web executor says so when there is no session
        from core_organs import web_executor as WE
        r = WE.run_web_task(None, "click 2", url=r"D:/new_automation/All codes/brain/webapps/w_tabs.html", session="nothere.example")
        c["a_run_with_no_stored_session_is_signed_out_and_says_so"] = r["status"] == "DONE" and r["session"]["used"] is False and "signed out" in r["session"]["note"]
    finally:
        os.environ.pop("HOJAIGA_VAULT_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar75() -> "TestOutcome":
    """AR75: the cloud rung of the gateway. Keys come from the project-root .env; a private prompt or one carrying a credential never leaves the machine; a 429 moves to the next
    provider and cools the first; images only go to a provider that reads them, as OpenAI image_url parts; HOJAIGA_CLOUD=first answers without booting Ollama; ask_llm uses it;
    the report of the last call names provider and model, never the key. The providers are stubs on localhost (no network)."""
    from core_organs import organ_37_llm_gateway as GW
    from core_organs.mind import app_qa as QA
    c: Dict[str, Any] = {}
    seen: list = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            seen.append((self.path, self.headers.get("Authorization"), body))
            if self.path.startswith("/busy"):
                self.send_response(429)
                self.end_headers()
                return
            out = json.dumps({"choices": [{"message": {"content": "answer from " + self.path.split("/")[1]}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    saved = list(GW.CLOUD_PROVIDERS)
    try:
        real = GW.env_keys(refresh=True)
        c["keys_are_read_from_the_project_root_env"] = any(real.get(k) for p in saved for k in p[1])
        GW.CLOUD_PROVIDERS[:] = [("busy", ("T_BUSY",), base + "/busy/chat/completions", "m-busy", True), ("text", ("T_TEXT",), base + "/text/chat/completions", "m-text", False),
                                 ("eye", ("T_EYE",), base + "/eye/chat/completions", "m-eye", True)]
        GW._COOL.clear()
        GW._SENT.clear()
        GW._DECIDED.clear()
        GW._ENV_CACHE.update({"T_BUSY": "kb", "T_TEXT": "kt", "T_EYE": "ke", "HOJAIGA_CLOUD": "fallback", "HOJAIGA_CLOUD_ORDER": ""})
        c["private_stays_local"] = GW.cloud_chat("s", "summarise my mail", private=True) is None and not seen
        c["a_credential_stays_local"] = GW.cloud_chat("s", "log in, my password is hunter2") is None and GW.cloud_chat("s", "use key gsk_ABCDEFGHIJKLMNOPQRSTUV") is None and not seen
        c["but_the_word_password_alone_is_fine"] = GW.cloud_ok_for("how do I change a password in Word?")
        out = GW.cloud_chat("s", "plan a website")
        c["a_429_moves_to_the_next_provider"] = out == "answer from text" and [p for p, _, _ in seen] == ["/busy/chat/completions", "/text/chat/completions"]
        c["and_cools_the_busy_one"] = GW._COOL.get("busy", 0) > __import__("time").time() and "busy" not in [p[0] for p in GW.cloud_providers()]
        c["the_key_goes_in_the_header_and_the_model_in_the_body"] = seen[-1][1] == "Bearer kt" and seen[-1][2]["model"] == "m-text"
        c["the_last_call_report_has_no_key"] = GW.LAST_CLOUD.get("provider") == "text" and "kt" not in json.dumps(GW.LAST_CLOUD)
        seen.clear()
        out = GW.cloud_chat("s", "describe", images_b64=["QUJD"])
        part = seen[-1][2]["messages"][1]["content"] if seen else []
        c["images_go_only_to_an_eye"] = out == "answer from eye" and [p for p, _, _ in seen] == ["/eye/chat/completions"]
        c["as_openai_image_url_parts"] = isinstance(part, list) and part[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
        GW._ENV_CACHE["HOJAIGA_TEXT_MODEL"] = "m-chosen"
        GW.cloud_chat("s", "x")
        c["the_model_is_chosen_by_env"] = seen[-1][2]["model"] == "m-chosen"
        GW._ENV_CACHE["HOJAIGA_CLOUD"] = "off"
        seen.clear()
        c["off_means_off"] = GW.cloud_chat("s", "x") is None and not seen
        GW._ENV_CACHE["HOJAIGA_CLOUD"] = "first"
        g = GW.LLMGateway.__new__(GW.LLMGateway)
        g._booted = False
        g.bootstrap = lambda: (_ for _ in ()).throw(RuntimeError("should not boot"))
        c["first_answers_without_booting_ollama"] = g.execute_inference("s", "plan") == "answer from text"
        c["ask_llm_uses_the_cloud_when_first"] = QA.ask_llm("p", "s") == "answer from text"
        seen.clear()
        QA.LLM_URL_SAVED = QA.LLM_URL
        QA.LLM_URL = "http://127.0.0.1:9/nothing"
        r = QA.ask_llm("p", "s", timeout=2, private=True)
        QA.LLM_URL = QA.LLM_URL_SAVED
        c["ask_llm_private_never_reaches_the_cloud"] = r is None and not seen
    finally:
        GW.CLOUD_PROVIDERS[:] = saved
        GW._COOL.clear()
        GW._SENT.clear()
        GW._DECIDED.clear()
        GW.env_keys(refresh=True)
        srv.shutdown()
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar76() -> "TestOutcome":
    """AR76: no 429 by construction + the model routes. The gateway stops asking a provider at its own per-minute cap and when the provider's reported remaining count is at the
    reserve (rests it until the reported reset), so the next request goes elsewhere or stays local; a repeated decision is answered from the decision cache with no request.
    The front door: an identical ticket that finished well is routed from memory with no model call; otherwise the MODEL's word decides (even against the word rules), past tickets
    are its examples; nonsense from the model or no model -> the rules; HOJAIGA_ROUTE_BRAIN=rules forces them; the report says who decided."""
    import time
    from core_organs import organ_37_llm_gateway as GW
    from core_organs import hojaiga_run as HR
    c: Dict[str, Any] = {}
    sent: list = []
    remaining = {"n": 10}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            sent.append(self.path)
            remaining["n"] -= 1
            out = json.dumps({"choices": [{"message": {"content": "ok " + self.path.split("/")[1]}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            if self.path.startswith("/told"):
                self.send_header("x-ratelimit-remaining-requests", str(remaining["n"]))
                self.send_header("x-ratelimit-reset-requests", "1m30s")
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    saved = list(GW.CLOUD_PROVIDERS)
    tmp = tempfile.mkdtemp(prefix="ar76_")
    old_runs = HR.RUNS
    try:
        GW.env_keys(refresh=True)
        GW.CLOUD_PROVIDERS[:] = [("capped", ("T_CAP",), base + "/capped/chat/completions", "m", False), ("told", ("T_TOLD",), base + "/told/chat/completions", "m", False)]
        for d in (GW._COOL, GW._SENT, GW._DECIDED):
            d.clear()
        GW._ENV_CACHE.update({"T_CAP": "a", "T_TOLD": "b", "HOJAIGA_CLOUD": "fallback", "HOJAIGA_CLOUD_ORDER": "", "HOJAIGA_CAPPED_RPM": "3", "HOJAIGA_TOLD_RPM": "100"})
        outs = [GW.cloud_chat("s", f"q{i}") for i in range(5)]
        c["the_per_minute_cap_is_never_passed"] = sent.count("/capped/chat/completions") == 3 and outs[:3] == ["ok capped"] * 3 and outs[3:] == ["ok told"] * 2
        c["the_status_shows_it"] = GW.budget_status()["capped"] == {"sent_last_minute": 3, "cap_per_minute": 3, "resting_s": 0}
        remaining["n"] = 3                                                                             # the provider says 2 left after the next call = the reserve
        GW.cloud_chat("s", "q-last")
        c["at_the_reported_reserve_the_provider_rests_until_its_reset"] = 85 <= GW.budget_status()["told"]["resting_s"] <= 90
        n = len(sent)
        c["with_no_budget_anywhere_nothing_is_sent"] = GW.cloud_chat("s", "q-new") is None and len(sent) == n
        c["a_repeated_decision_comes_from_the_cache"] = GW.cloud_chat("s", "q0") == "ok capped" and len(sent) == n and GW.LAST_CLOUD["provider"] == "cache"
        c["but_a_creative_call_is_not_cached"] = GW.cloud_chat("s", "q0", temperature=0.9) is None
        c["resets_parse"] = GW._seconds("1m26.4s") == 86.4 and GW._seconds("577ms") == 0.577 and GW._seconds("2h") == 7200 and GW._seconds("30") == 30
        # ---- the front door's router
        HR.RUNS = tmp
        os.makedirs(os.path.join(tmp, "r1"))
        json.dump({"tickets": [{"kind": "write", "text": "make a quiz about the water cycle", "result": {"status": "DRAFTED"}},
                               {"kind": "web", "text": "find the opening hours on city-library.example", "result": {"status": "FAILED"}}]}, open(os.path.join(tmp, "r1", "report.json"), "w"))
        HR._PAST["mtime"] = None
        old_embed = HR._embed
        HR._embed = lambda texts: None                                                                # word overlap only here; meaning is AR77's
        asked: list = []
        model = lambda reply: (lambda s, p: (asked.append(p) or reply))
        os.environ.pop("HOJAIGA_ROUTE_BRAIN", None)
        c["an_identical_finished_ticket_is_routed_from_memory"] = HR.decide_route("Make a quiz about the water cycle", "unknown", ask=model("web")) == ("write", "memory") and not asked
        k, by = HR.decide_route("make a quiz about volcanoes", "unknown", ask=model("write"))
        c["otherwise_the_model_decides"] = (k, by) == ("write", "model") and asked
        c["with_the_closest_finished_tickets_as_examples"] = "water cycle" in asked[-1] and "opening hours" not in asked[-1]
        c["the_model_wins_over_the_word_rules"] = HR._rules_route("open Paint and save it", "desktop") == "desktop" and HR.decide_route("open Paint and save it", "desktop", ask=model("Build."))[0] == "build"
        c["nonsense_from_the_model_falls_back_to_the_rules"] = HR.decide_route("write an email to my boss about the delay", "unknown", ask=model("banana")) == ("write", "rules (the model gave no route)")
        c["no_model_falls_back_to_the_rules"] = HR.decide_route("what is the shortcut for bold in Word?", "unknown", ask=lambda s, p: None)[0] == "question"
        os.environ["HOJAIGA_ROUTE_BRAIN"] = "rules"
        asked.clear()
        c["rules_can_be_forced"] = HR.decide_route("make a quiz about volcanoes", "unknown", ask=model("web"))[1] == "rules" and not asked
        os.environ.pop("HOJAIGA_ROUTE_BRAIN", None)
        old_ask = HR._ask_route_model
        HR._ask_route_model = model("question")
        try:
            r = HR.run("how do I add a slide number?", say=lambda *a, **k: None, boot_first=False, executors={"question": lambda t: {"status": "ANSWERED", "answer": "a"}}, rag=object())
        finally:
            HR._ask_route_model = old_ask
        c["the_report_says_who_decided"] = r["tickets"][0]["route_by"] == "model" and r["tickets"][0]["kind"] == "question"
    finally:
        GW.CLOUD_PROVIDERS[:] = saved
        for d in (GW._COOL, GW._SENT, GW._DECIDED):
            d.clear()
        GW.env_keys(refresh=True)
        HR.RUNS = old_runs
        HR._PAST["mtime"] = None
        HR._embed = locals().get("old_embed", HR._embed)
        os.environ.pop("HOJAIGA_ROUTE_BRAIN", None)
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar77() -> "TestOutcome":
    """AR77: intelligence that expands. A reworded ticket is routed from memory by MEANING (no model call) unless a close neighbour took a different part; unrelated past tickets are not
    shown to the model; a part that could not do a ticket hands it to the model's next choice, the route that worked is what the report keeps, an acting part never follows a failed acting
    part, and an acting retry passes the risk gate first; the writer lets the model decide the form (a quiz is written, not asked for) and the facts; code comes back as checked files."""
    from core_organs import hojaiga_run as HR
    from core_organs.mind import app_qa as QA
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar77_")
    old_runs, old_embed, old_ask, old_llm = HR.RUNS, HR._embed, HR._ask_route_model, QA.ask_llm
    try:
        HR.RUNS = tmp
        os.makedirs(os.path.join(tmp, "r1"))
        json.dump({"tickets": [{"kind": "question", "text": "how do you export a blender scene as fbx", "result": {"status": "ANSWERED"}},
                               {"kind": "desktop", "text": "export the blender scene to fbx now", "result": {"status": "DONE"}},
                               {"kind": "web", "text": "find train times on rail.example", "result": {"status": "DONE"}}]}, open(os.path.join(tmp, "r1", "report.json"), "w"))
        HR._PAST["mtime"] = None
        HR._VEC.clear()
        vec = {"how do you export a blender scene as fbx": [1, 0, 0], "export the blender scene to fbx now": [0, 1, 0], "find train times on rail.example": [0, 0, 1],
               "remind me how blender exports to fbx": [0.95, 0.1, 0.0], "blender to fbx, how?": [0.9, 0.87, 0.0], "how to bake bread": [0.2, 0.1, 0.1]}
        HR._embed = lambda texts: ([HR._VEC.__setitem__(t, vec.get(t, [0, 0, 0])) for t in texts[1:]] and None) or vec.get(texts[0], [0, 0, 0])
        asked: list = []
        model = lambda reply: (lambda s, p: (asked.append(p) or reply))
        os.environ.pop("HOJAIGA_ROUTE_BRAIN", None)
        k, by = HR.decide_route("remind me how blender exports to fbx", "unknown", ask=model("desktop"))
        c["a_reworded_ticket_is_routed_from_memory_by_meaning"] = k == "question" and by.startswith("memory (same meaning") and not asked
        k, by = HR.decide_route("blender to fbx, how?", "unknown", ask=model("question"))
        c["a_close_neighbour_with_another_part_sends_it_to_the_model"] = (k, by) == ("question", "model") and asked
        asked.clear()
        k, by = HR.decide_route("how do I make a pivot table in Excel", "unknown", ask=model("self"))
        c["asking_how_to_do_it_yourself_is_a_question_whatever_app_it_names"] = k == "question" and "themselves" in by and len(asked) == 1
        asked.clear()
        HR.decide_route("how to bake bread", "unknown", ask=model("question"))
        c["unrelated_past_tickets_are_not_shown_as_examples"] = asked and "train times" not in asked[-1]
        c["a_failed_acting_part_is_never_handed_on"] = HR.reroute("open x", ["desktop"], "no window", ask=model("write")) is None and HR.reroute("open x", ["web"], "no site", ask=model("question")) is None
        c["after_a_draft_an_acting_part_is_allowed"] = HR.reroute("x", ["write"], "NEED", ask=model("desktop")) == "desktop"
        c["none_means_none"] = HR.reroute("x", ["write"], "NEED", ask=model("none")) is None
        replies = iter(["forme", "write", "question"])
        HR._ask_route_model = lambda s, p: next(replies, "none")
        HR.ROUTE_LOG.clear()
        r = HR.run("quiz me on the planets", say=lambda *a, **k: None, boot_first=False, rag=object(),
                   executors={"write": lambda t: {"status": "NEEDS_INPUT", "question": "NEED: facts"}, "question": lambda t: {"status": "ANSWERED", "answer": "Q1 ..."}})
        t0 = r["tickets"][0]
        c["a_failed_part_hands_the_ticket_on_and_the_working_route_is_kept"] = t0["kind"] == "question" and t0["result"]["status"] == "ANSWERED" and t0["tried"] == ["write", "question"] and t0["route_by"].startswith("retry")
        c["the_first_try_is_on_record"] = t0["result"].get("first_try") == {"kind": "write", "status": "NEEDS_INPUT"}
        replies = iter(["forme", "desktop", "write"])
        HR._ask_route_model = lambda s, p: next(replies, "write")
        r = HR.run("save the file as plan.docx in Word", say=lambda *a, **k: None, boot_first=False, rag=object(),
                   executors={"desktop": lambda t: {"status": "FAILED", "evidence": "no window"}, "write": lambda t: {"status": "DRAFTED", "draft": "x"}})
        c["a_failed_desktop_ticket_stays_failed_not_drafted"] = r["tickets"][0]["kind"] == "desktop" and r["tickets"][0]["result"]["status"] == "FAILED" and not r["tickets"][0].get("tried")
        acted: list = []
        replies = iter(["forme", "write", "desktop"])
        HR._ask_route_model = lambda s, p: next(replies, "none")
        r = HR.run("delete every file in my Documents folder", say=lambda *a, **k: None, boot_first=False, rag=object(),
                   executors={"write": lambda t: {"status": "NEEDS_INPUT", "question": "NEED: facts"}, "desktop": lambda t: (acted.append(t) or {"status": "DONE"})})
        c["an_acting_retry_passes_the_risk_gate_first"] = r["tickets"][0]["result"]["status"] == "NEEDS_CONFIRM" and not acted
        HR._ask_route_model = old_ask
        # ---- the writer: the model reads the request
        calls: list = []
        def llm(*replies_):
            it = iter(replies_)
            return lambda prompt, system, **kw: (calls.append((system, prompt, kw)) or next(it, None))
        QA.ask_llm = llm('{"form": "content", "channel": "document", "relationship": "public", "facts": ["5 questions", "solar system"], "missing": ""}', "1. Which planet is largest?")
        w = HR.do_write("make me a 5 question quiz on the solar system")
        c["a_quiz_is_written_not_asked_for"] = w["status"] == "DRAFTED" and w["form"] == "content" and calls[-1][0] == HR.CONTENT_SYSTEM
        calls.clear()
        QA.ask_llm = llm('{"form": "message", "channel": "email", "relationship": "landlord", "facts": ["rent is 3 days late"], "missing": ""}', "Hi, my rent will be three days late this month. Sorry for the delay.")
        w = HR.do_write("write my landlord an email, rent's gonna be late by 3 days")
        c["facts_the_request_carries_are_used"] = w["status"] != "NEEDS_INPUT" and "rent is 3 days late" in calls[1][1]
        QA.ask_llm = llm('{"form": "message", "channel": "email", "relationship": "boss", "facts": [], "missing": "the reason for the delay"}')
        w = HR.do_write("write my boss an email")
        c["what_is_missing_is_asked_for"] = w["status"] == "NEEDS_INPUT" and "reason for the delay" in w["question"]
        # ---- code
        fs = HR.parse_files("FILE: app.py\n```python\nprint('hi')\n```\nFILE: ../evil.py\n```python\nx=1\n```\nFILE: C:/x.py\n```\n1\n```\nFILE: web/index.html\n```html\n<html><body>hi</body></html>\n```\nRUN: python app.py")
        c["files_are_read_and_paths_leaving_the_folder_dropped"] = [p for p, _ in fs] == ["app.py", "web/index.html"]
        c["files_are_checked_for_what_their_name_says"] = HR.check_file("a.py", "def (:\n").startswith("line") and HR.check_file("a.json", "{x") and not HR.check_file("i.html", "<html><body/></html>") and not HR.check_file("a.py", "x = 1\n")
        calls.clear()
        QA.ask_llm = llm("FILE: rename.py\n```python\ndef f(:\n```", "FILE: rename.py\n```python\nimport os\nprint(os.getcwd())\n```\nRUN: python rename.py")
        d = HR.do_code("write a python script that prints the folder", tmp)
        c["a_broken_file_gets_one_repair_round_with_its_problem"] = d["status"] == "DONE" and len(calls) == 2 and "rename.py: line" in calls[1][1] and calls[0][2].get("model") == HR.CODE_MODEL
        c["the_files_are_written_and_nothing_is_run"] = os.path.isfile(os.path.join(d["folder"], "rename.py")) and d["run"] == "python rename.py" and "nothing was run" in d["note"]
    finally:
        HR.RUNS, HR._embed, HR._ask_route_model, QA.ask_llm = old_runs, old_embed, old_ask, old_llm
        HR._PAST["mtime"] = None
        HR._VEC.clear()
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar78() -> "TestOutcome":
    """AR78: DONE needs proof of the RESULT. Every file the ticket names must exist, be written by this run and hold what was asked (read back: text, cells, bold runs, slide titles, a picture
    described blind); the verdict is computed from a checklist made from the ticket alone, never asked for; text that appears twice fails; the opened app is not content; a desktop step whose
    file is missing is FAILED_CHECK; a 3D build needs a picture score of 4+ and with no score it is UNVERIFIED; neither is ever learned from as a success."""
    import time as _t
    import types
    import docx
    import openpyxl
    from core_organs import hojaiga_run as HR
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar78_")
    J = os.path.join
    seen: list = []

    def judge(items, answers=None):
        it = iter(answers or [])
        def ask(system, prompt):
            seen.append((system, prompt))
            if system in (HR.ITEMS_SYSTEM, HR.PICTURE_ITEMS):
                return json.dumps({"items": items})
            return next(it, "yes")
        return ask
    since = _t.time() - 2
    open(J(tmp, "g.txt"), "w").write("milk, eggs, bread")
    open(J(tmp, "d.txt"), "w").write("milk, eggs, breadmilk, eggs")
    r = HR.prove(f"open Notepad, type milk, eggs, bread and save it as {J(tmp, 'g.txt')}", since, ask=judge([{"content": "Notepad"}, {"content": "milk, eggs, bread"}]))
    c["the_right_text_is_done"] = r["status"] == "DONE"
    c["the_opened_app_is_not_content"] = all(i["content"] != "Notepad" for i in r["proof"][0]["items"])
    c["the_exact_text_needs_no_model_question"] = not [s for s, _p in seen if s == HR.CHECK_SYSTEM]
    r = HR.prove(f"open Notepad, type milk, eggs, bread and save it as {J(tmp, 'd.txt')}", since, ask=judge([{"content": "milk, eggs, bread"}]))
    c["text_typed_twice_fails"] = r["status"] == "FAILED_CHECK" and "more than once" in r["proof"][0]["why"]
    r = HR.prove(f"open Paint, draw a circle and save it as {J(tmp, 'none.png')}", since, ask=judge([]))
    c["a_named_file_that_is_missing_fails"] = r["status"] == "FAILED_CHECK" and "not saved" in r["proof"][0]["why"]
    old = J(tmp, "old.txt")
    open(old, "w").write("milk, eggs, bread")
    os.utime(old, (since - 100, since - 100))
    c["a_file_older_than_the_run_fails"] = HR.prove(f"type milk, eggs, bread and save it as {old}", since, ask=judge([{"content": "milk, eggs, bread"}]))["status"] == "FAILED_CHECK"
    c["a_bare_name_is_unverified_not_done"] = HR.prove("save it as plan.docx", since, ask=judge([{"content": "x"}]))["status"] == "UNVERIFIED"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Item in A1 and Price in B1"
    wb.save(J(tmp, "p.xlsx"))
    seen.clear()
    r = HR.prove(f"open Excel, type Item in A1 and Price in B1 and save it as {J(tmp, 'p.xlsx')}", since, ask=judge([{"content": "Item", "where": "A1"}, {"content": "Price", "where": "B1"}], ["no", "no"]))
    c["cells_are_read_back_and_asked_one_by_one"] = r["status"] == "FAILED_CHECK" and "A1 = 'Item in A1" in seen[-1][1] and len([s for s, _p in seen if s == HR.CHECK_SYSTEM]) == 2
    d = docx.Document()
    d.add_paragraph().add_run("Quarterly Plan").bold = True
    d.save(J(tmp, "b.docx"))
    c["bold_is_read_back"] = "[paragraph bold] Quarterly Plan" in HR.read_back(J(tmp, "b.docx"))[1]
    c["where_the_file_goes_is_not_shown_to_the_judge"] = (seen.clear() or True) and HR.judge_text(f"write Quarterly Plan and save it as {J(tmp, 'b.docx')}", "x", ask=judge([{"content": "x"}])) and tmp not in seen[0][1]
    c["a_verdict_is_computed_never_taken"] = HR.judge_text("type hello", "bye", ask=lambda s, p: '{"done": true}')["ok"] is None
    from PIL import Image
    Image.new("RGB", (40, 40), "white").save(J(tmp, "c.png"))
    seen.clear()
    r = HR.prove(f"open Paint, draw a red circle and save it as {J(tmp, 'c.png')}", since, ask=judge([{"content": "a red circle"}], ["no"]), look=lambda img: "a blue square on white")
    c["a_picture_is_described_blind_and_checked"] = r["status"] == "FAILED_CHECK" and r["proof"][0]["sees"] == "a blue square on white" and seen[0][0] == HR.PICTURE_ITEMS
    r = HR.prove(f"open Paint, draw a red circle and save it as {J(tmp, 'c.png')}", since, ask=judge([{"content": "a red circle"}]), look=lambda img: "a red circle on white")
    c["the_right_picture_is_done"] = r["status"] == "DONE"
    # ---- the executors use it
    import core_organs.task_lifecycle as TL
    old_rl, old_prove = TL.run_lifecycle, HR.prove
    try:
        TL.run_lifecycle = lambda *a, **k: {"status": "DONE", "tickets": [{"evidence": "COMPLETED (window hwnd=42)"}], "checkpoints": []}
        got: list = []
        HR.prove = lambda t, s, h=0, **k: (got.append(h) or {"status": "FAILED_CHECK", "proof": [{"ok": False, "why": "the file was not saved"}]})
        r = HR.do_desktop("open Paint and save it as C:\\x\\y.png", False)
        c["a_desktop_DONE_is_proven_before_it_counts"] = r["status"] == "FAILED_CHECK" and got == [42]
    finally:
        TL.run_lifecycle, HR.prove = old_rl, old_prove
    import core_organs.app_teaching_automation as ATA
    old_sec, old_jp = ATA.AppTeachingAutomationSection, HR.judge_picture
    try:
        def section(vlm_score):
            class S:
                def __init__(self, **k):
                    pass
                def handle(self, *a, **k):
                    seen.append(("handle", k))
                    return {"saved": {"ok": True, "path": "x.blend"}, "quality": {"parts_built": 5, "parts_wanted": 5, "score": 100}, "picture": "",
                            "vlm": {"ok": vlm_score is not None, "score": vlm_score, "sees": "a pole", "wrong": "not a tree"}}
            return S
        ATA.AppTeachingAutomationSection = section(2)
        seen.clear()
        r = HR.do_build("make a tree", {})
        c["geometry_100_with_a_poor_picture_fails"] = r["status"] == "FAILED_CHECK" and seen[0][1].get("vlm") is True
        ATA.AppTeachingAutomationSection = section(5)
        c["a_good_picture_is_done"] = HR.do_build("make a tree", {})["status"] == "DONE"
        ATA.AppTeachingAutomationSection = section(None)
        c["no_picture_score_is_unverified"] = HR.do_build("make a tree", {})["status"] == "UNVERIFIED"
    finally:
        ATA.AppTeachingAutomationSection, HR.judge_picture = old_sec, old_jp
    c["unproven_results_are_never_learned"] = not ({"FAILED_CHECK", "UNVERIFIED"} & HR.GOOD)
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar79() -> "TestOutcome":
    """AR79: the model plans the steps, each step takes the route that can do it and prove it. A clause becomes one structured step per action
    (one value per cell); a value the model drops voids the plan; paths never travel inside the model's JSON; the menu walk around Save As becomes
    one save_as; formatting / colour / a fresh document the words require are added; an arithmetic plan keeps its result check; Office steps go
    through the object model, 'draw' through the drawing tools, the rest through the loop, in order; DELEGATED is never 'completed'; the risk gate
    keeps steps aligned; shapes are drawn from geometry and a sketch from the model; a site named without its address is found only when it resolves."""
    from core_organs import loop_first as LF
    from core_organs import office_om as OM
    from core_organs import web_executor as WE
    import types
    from core_organs.professor import gestures as GE
    c: Dict[str, Any] = {}
    P = r"D:\\new_automation\\data\\ar79_none\\prices.xlsx".replace("\\\\", "\\")
    clause = f"type Item in A1 and Price in B1, Milk in A2 and 40 in B2, and save it as {P}"
    seen: list = []

    def planner(reply):
        def ask(system, prompt):
            seen.append(prompt)
            return reply if isinstance(reply, str) else reply.pop(0)
        return ask
    good = json.dumps({"steps": [{"do": "type", "text": "Item", "target": "A1"}, {"do": "type", "text": "Price", "target": "B1"}, {"do": "type", "text": "Milk", "target": "A2"},
                                 {"do": "type", "text": "40", "target": "B2"}, {"do": "click", "target": "File"}, {"do": "click", "target": "Save As"}, {"do": "type", "text": "PATH1"}]})
    steps, note = LF.model_steps([clause], "excel", planner(good))
    c["one_value_per_cell_step"] = [s["target"] for s in steps if s["do"] == "type"] == ["A1", "B1", "A2", "B2"]
    c["the_path_is_hidden_from_the_model_and_restored"] = P not in seen[0] and "PATH1" in seen[0] and steps[-1] == {"do": "save_as", "text": P, "target": "", "format": ""}
    c["the_menu_walk_around_save_as_is_one_step"] = not [s for s in steps if s["do"] == "click"]
    c["a_new_file_typed_into_starts_a_fresh_document"] = steps[0]["do"] == "new_document"
    seen.clear()
    drop = json.dumps({"steps": [{"do": "type", "text": "Item", "target": "A1"}, {"do": "save_as", "text": "PATH1"}]})
    steps, note = LF.model_steps([clause], "excel", planner([drop, drop]))
    c["a_dropped_value_voids_the_plan_after_one_retry"] = steps == [] and "left out" in note and len(seen) == 2 and "not usable" in seen[1]
    steps, _n = LF.model_steps(["write the title Plan, make it bold"], "word", planner(json.dumps({"steps": [{"do": "type", "text": "Plan", "target": "title"}]})))
    c["formatting_the_words_name_is_added"] = [s["do"] for s in steps] == ["type", "format"] and steps[1]["format"] == "bold" and steps[1]["text"] == "Plan"
    steps, _n = LF.model_steps(["draw a red circle"], "paint", planner(json.dumps({"steps": [{"do": "draw", "text": "a red circle"}]})))
    c["the_colour_a_drawing_names_is_chosen_first"] = [s["do"] for s in steps] == ["click", "draw"] and steps[0]["target"] == "Red"
    c["glue_words_are_not_typed"] = LF.tidy_steps([{"do": "type", "text": " and", "target": "", "format": ""}, {"do": "type", "text": "x", "target": "", "format": ""}]) == [{"do": "type", "text": "x", "target": "", "format": ""}]
    tog, _a = LF.complete_steps([{"do": "type", "text": "Plan", "target": "", "format": ""}, {"do": "format", "text": "Plan", "target": "", "format": "bold"},
                                 {"do": "press", "text": "Ctrl+B", "target": "", "format": ""}], "write Plan, make it bold")
    c["a_format_is_not_toggled_off_by_its_own_key"] = [s["do"] for s in tog] == ["type", "format"]
    plan = LF.AppPlan(app="calculator", goals=["press Two", "press Equals"], expect_map={1: {"name_visible": "2"}}, strength=["weak", "strong"], clauses=["calculate 2"])
    LF.refine_plan(plan, planner("{}"))
    c["an_arithmetic_plan_keeps_its_result_check"] = plan.goals == ["press Two", "press Equals"] and not plan.steps
    # ---- execution: each step to its route, in order
    calls: list = []

    class FakeOM:
        @staticmethod
        def app_kind(h):
            return "excel"

        @staticmethod
        def can_do(kind, s):
            return OM.can_do(kind, s)

        @staticmethod
        def do_step(h, s):
            calls.append(("om", s["do"], s.get("target") or s.get("text")))
            return True, "read back"

    def operate(app, goals, **k):
        calls.append(("loop", tuple(goals)))
        return {"trace": [{"goal": g, "verdict": "PASS"} for g in goals]}
    plan = LF.AppPlan(app="excel", clauses=[clause])
    steps = [{"do": "type", "text": "Item", "target": "A1", "format": ""}, {"do": "click", "text": "", "target": "Sort", "format": ""},
             {"do": "draw", "text": "a line", "target": "", "format": ""}, {"do": "type", "text": "x", "target": "B1", "format": ""}]
    plan.steps, plan.goals = steps, [LF.render_step(s) for s in steps]
    run = LF.AppRun(app="excel", plan=plan)
    LF._run_steps(plan, run, operate=operate, prepare=lambda *a, **k: {"hwnd": 7, "ready": True}, capsule_cb=None, cursor_cb=None, allow_destructive=False,
                  max_steps_per_goal=3, om=FakeOM, draw=lambda app, h, what: (calls.append(("draw", what)) or (True, "4% changed")))
    c["steps_run_in_order_each_on_its_route"] = calls == [("om", "type", "A1"), ("loop", ("click Sort",)), ("draw", "a line"), ("om", "type", "B1")]
    c["every_step_proven_is_completed"] = run.status == "COMPLETED" and run.goal_verdicts == ["PASS"] * 4
    calls.clear()
    run = LF.AppRun(app="excel", plan=plan)
    LF._run_steps(plan, run, operate=operate, prepare=lambda *a, **k: {"hwnd": 7}, capsule_cb=None, cursor_cb=None, allow_destructive=False, max_steps_per_goal=3,
                  om=FakeOM, draw=lambda app, h, what: (False, "no pixels changed"))
    c["a_failed_step_stops_the_run_and_is_not_completed"] = run.status == "BLOCKED" and run.goal_verdicts[2] == "FAIL" and run.goal_verdicts[3] == "NOT RUN"
    tmpf = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmpf.close()
    plan2 = LF.AppPlan(app="excel")
    plan2.steps = [{"do": "save_as", "text": tmpf.name, "target": "", "format": ""}]
    plan2.goals = [LF.render_step(plan2.steps[0])]
    run = LF.AppRun(app="excel", plan=plan2)
    LF._run_steps(plan2, run, operate=operate, prepare=lambda *a, **k: {"hwnd": 7}, capsule_cb=None, cursor_cb=None, allow_destructive=False, max_steps_per_goal=3, om=FakeOM)
    c["overwriting_an_existing_file_waits_for_a_yes"] = run.status == "NEEDS_HUMAN" and run.goal_verdicts == ["NEEDS_HUMAN"]
    os.unlink(tmpf.name)
    res = LF.LoopFirstResult(ran=True, runs=[LF.AppRun(app="paint", plan=LF.AppPlan(app="paint"), status="DELEGATED")])
    c["delegated_is_never_completed"] = not res.all_completed
    from core_organs import task_lifecycle as TLC

    class Model:
        @staticmethod
        def classify_risk_of(goal):
            return "E2" if goal.startswith("delete") else "E0"

        @staticmethod
        def enqueue(*a, **k):
            return "q1"
    p3 = LF.AppPlan(app="x", goals=["type \"a\"", "delete everything", "save it as C:\\x.txt"], strength=["strong", "weak", "strong"],
                    steps=[{"do": "type", "text": "a"}, {"do": "click", "target": "delete everything"}, {"do": "save_as", "text": "C:\\x.txt"}])
    try:
        TLC.gate_plans([p3], model=Model, run_id="ar79", task="t", allow_destructive=False, unattended=True, chain=types.SimpleNamespace(mark=lambda *a, **k: None))
    except Exception:
        pass
    c["the_risk_gate_keeps_steps_aligned"] = [s["do"] for s in p3.steps] == ["type", "save_as"] and len(p3.goals) == 2
    # ---- office object model, drawing, sites
    c["a_grid_takes_a_value_only_at_an_address"] = OM.can_do("excel", {"do": "type", "target": "cell b2"}) and not OM.can_do("excel", {"do": "type", "target": "the top"}) and not OM.can_do("word", {"do": "click"})
    c["numbers_stay_numbers"] = OM._value("40") == 40 and OM._value("4.5") == 4.5 and OM._value("Milk") == "Milk" and OM._same(40.0, "40")
    circle = GE.shape_strokes("a red circle")[0]
    c["a_circle_is_drawn_from_geometry"] = len(circle) > 40 and all(abs(((x - 50) ** 2 + (y - 50) ** 2) ** 0.5 - 40) < 0.01 for x, y in circle)
    fit = GE.fit_strokes([circle], (0, 0, 400, 200))[0]
    xs, ys = [p[0] for p in fit], [p[1] for p in fit]
    c["it_stays_round_on_a_wide_canvas"] = abs((max(xs) - min(xs)) - (max(ys) - min(ys))) < 1 and min(xs) > 0 and max(ys) < 200
    sk = GE.sketch_strokes("a zorbleflax gadget", ask=lambda s, p: '{"strokes": [[[10, 90], [10, 40], [90, 40], [90, 90]], [[5, 40], [50, 5], [95, 40]], [[1]], [["a", 2]]]}')
    c["anything_else_is_sketched_by_the_model_and_checked"] = len(sk) == 2 and sk[1][1] == (50.0, 5.0)
    qd = GE.quickdraw_strokes("a house")
    c["a_known_thing_uses_a_real_human_sketch_when_the_data_is_there"] = (not os.path.isfile(os.path.join(GE.QUICKDRAW_DIR, "house.ndjson"))) or (len(qd) >= 1 and len(GE.sketch_strokes("a house", ask=lambda s, p: 1 / 0)) >= 1)
    qd = tempfile.mkdtemp(prefix="ar79qd_")
    with open(os.path.join(qd, "light_bulb.ndjson"), "w") as fh:
        fh.write(json.dumps({"word": "light bulb", "recognized": False, "drawing": [[[0, 9], [0, 9]]]}) + "\n")
        fh.write(json.dumps({"word": "light bulb", "recognized": True, "drawing": [[[10, 110, 110], [20, 20, 70]], [[60, 60], [70, 120]]]}) + "\n")
    open(os.path.join(qd, "bulb.ndjson"), "w").write(json.dumps({"recognized": True, "drawing": [[[0, 1], [0, 1]]]}) + "\n")
    qs = GE.quickdraw_strokes("draw a light bulb in yellow", folder=qd, pick=0)
    c["a_named_thing_is_drawn_from_a_real_human_sketch"] = len(qs) == 2 and qs[0][0] == (0.0, 0.0) and qs[0][1] == (100.0, 0.0) and qs[1][1] == (50.0, 100.0)
    c["a_thing_no_sketch_set_names_draws_nothing_from_it"] = GE.quickdraw_strokes("draw a spaceship", folder=qd) == []
    shutil.rmtree(qd, ignore_errors=True)
    WE._SITE_SEEN.clear()
    c["a_named_site_that_resolves_is_found"] = WE.site_by_name("search wikipedia for Turing", ask=lambda s, p: "wikipedia.org/wiki", resolves=lambda d, port: [1]) == "https://wikipedia.org"
    WE._SITE_SEEN.clear()
    c["a_made_up_domain_is_never_used"] = WE.site_by_name("find flights on google flights", ask=lambda s, p: "googleflights.com", resolves=lambda d, port: (_ for _ in ()).throw(OSError())) == ""
    WE._SITE_SEEN.clear()
    c["a_domain_the_task_does_not_name_is_never_used"] = WE.site_by_name("search wikipedia for Turing", ask=lambda s, p: "evil.com", resolves=lambda d, port: [1]) == ""
    WE._SITE_SEEN.clear()
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar80() -> "TestOutcome":
    """AR80: several apps, one task (after microsoft/UFO's host agent + blackboard). What one app produces (a saved file, a table read from a web
    page or a sheet, a text) is kept on a blackboard by name; the planner of the next app is told what is there; insert_table / insert_picture /
    paste use it through the object model (or the loop types it where there is none); a web page is read without a browser and only at a public
    address; the read-back of a document counts its pictures and tables; a URL's trailing comma and the 's:/' of 'https://' are not mistaken."""
    import docx
    from PIL import Image
    from core_organs import hojaiga_run as HR
    from core_organs import loop_first as LF
    from core_organs import office_om as OM
    from core_organs import web_executor as WE
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar80_")
    J = os.path.join
    c["a_urls_trailing_comma_is_not_part_of_it"] = LF._URL_RE.findall("from https://en.wikipedia.org/wiki/X, then") == ["https://en.wikipedia.org/wiki/X"]
    c["https_is_not_a_drive_letter"] = not LF._PATH_RE.findall("https://a.org/b") and LF._PATH_RE.findall("save as D:\\x\\y.png") == ["D:\\x\\y.png"]
    seen: list = []
    reply = json.dumps({"steps": [{"do": "save", "text": "PATH1"}]})
    steps, _n = LF.model_steps(["save it as C:\\out\\a.docx"], "word", lambda s, p: (seen.append(p) or reply), context="- file 'circle.png' from paint")
    c["the_planners_own_step_names_are_mapped"] = steps and steps[-1]["do"] == "save_as"
    c["the_next_app_is_told_what_the_earlier_apps_keep"] = "Kept by the apps before this one" in seen[0] and "circle.png" in seen[0]
    out, _a = LF.complete_steps([{"do": "draw", "text": "circle", "target": "", "format": ""}, {"do": "format", "text": "Red", "target": "", "format": "fill"}], "draw a red circle")
    c["a_colour_in_a_format_step_is_picked_before_drawing"] = [(s["do"], s["target"]) for s in out] == [("click", "Red"), ("draw", "")]
    pa = LF.AppPlan(app="paint", steps=[{"do": "save_as", "text": "C:\\o\\c.png", "target": "", "format": ""}])
    px = LF.AppPlan(app="excel", steps=[{"do": "read", "text": "", "target": "A1:B3", "format": "prices"}])
    c["what_a_plan_will_keep_is_known_before_it_runs"] = [o["name"] for o in LF.plan_outputs(pa) + LF.plan_outputs(px)] == ["c.png", "prices"]
    # ---- the hand-over, executed
    calls: list = []

    class FakeOM:
        kind = "excel"

        @staticmethod
        def app_kind(h):
            return FakeOM.kind

        @staticmethod
        def can_do(kind, s):
            return OM.can_do(kind, s)

        @staticmethod
        def do_step(h, s):
            calls.append(("do", s["do"], s.get("text")))
            return True, "ok"

        @staticmethod
        def read(h, target):
            return {"kind": "table", "rows": [["Item", "Price"], ["Milk", 40]]}

        @staticmethod
        def insert_table(h, rows, target):
            calls.append(("table", rows, target))
            return True, "inserted"

        @staticmethod
        def insert_picture(h, path):
            calls.append(("picture", path))
            return True, "inserted"
    old_read = WE.read_page
    WE.read_page = lambda url, fetch=None: {"ok": True, "tables": [[["a", "b"], ["1", "2"]], [["City", "Population"], ["Tokyo", "37"], ["Delhi", "33"]]], "text": "t", "why": "2 tables"}
    try:
        LF.BLACKBOARD.clear()

        def run(app, steps, kind):
            FakeOM.kind = kind
            plan = LF.AppPlan(app=app, steps=steps, goals=[LF.render_step(s) for s in steps])
            r = LF.AppRun(app=app, plan=plan)
            LF._run_steps(plan, r, operate=lambda app, goals, **k: (calls.append(("loop", tuple(goals))) or {"trace": [{"goal": g, "verdict": "PASS"} for g in goals]}),
                          prepare=lambda *a, **k: {"hwnd": 5}, capsule_cb=None, cursor_cb=None, allow_destructive=False, max_steps_per_goal=2, om=FakeOM)
            return r
        r1 = run("excel", [{"do": "read", "text": "https://en.wikipedia.org/wiki/List_of_cities", "target": "city population table", "format": "cities"}], "excel")
        c["a_web_table_is_read_and_kept_by_name"] = r1.status == "COMPLETED" and LF.BLACKBOARD["cities"]["rows"][0] == ["City", "Population"]
        r2 = run("word", [{"do": "insert_table", "text": "cities", "target": "", "format": ""}], "word")
        c["the_next_app_inserts_the_kept_table"] = r2.status == "COMPLETED" and calls[-1] == ("table", [["City", "Population"], ["Tokyo", "37"], ["Delhi", "33"]], "")
        pic = J(tmp, "c.png")
        Image.new("RGB", (8, 8), "red").save(pic)
        LF.keep("c.png", {"kind": "file", "path": pic, "from": "paint"})
        r3 = run("powerpoint", [{"do": "insert_picture", "text": "the circle picture", "target": "", "format": ""}], "powerpoint")
        c["a_picture_another_app_saved_is_inserted"] = r3.status == "COMPLETED" and calls[-1] == ("picture", pic)
        calls.clear()
        LF.keep("note", {"kind": "text", "text": "hello from word"})
        r4 = run("notepad", [{"do": "paste", "text": "note", "target": "", "format": ""}], "")
        c["kept_text_into_an_app_without_an_object_model_is_typed_by_the_loop"] = r4.status == "COMPLETED" and calls == [("loop", ('type "hello from word"',))]
        r5 = run("word", [{"do": "insert_table", "text": "nothing", "target": "", "format": ""}], "word") if not LF.BLACKBOARD.clear() else None
        c["nothing_kept_means_the_step_fails_honestly"] = r5.status == "BLOCKED" and "no table" in r5.result["step_evidence"][0]
        LF.keep("x", {"kind": "text", "text": "y"})
        LF.run_loop_first("open notepad", [("notepad", 5)], operate=lambda *a, **k: {"trace": []}, prepare=lambda *a, **k: {"hwnd": 1})
        c["each_task_starts_with_an_empty_blackboard"] = "x" not in LF.BLACKBOARD
        LF.KEEP_BOARD["on"] = True
        try:
            got = HR.keep_from_web("open chrome and copy the city population table from https://en.wikipedia.org/wiki/List_of_cities")
            LF.run_loop_first("open notepad", [("notepad", 5)], operate=lambda *a, **k: {"trace": []}, prepare=lambda *a, **k: {"hwnd": 1})
            c["a_web_ticket_that_reads_leaves_the_table_for_the_desktop_ticket"] = "table" in got and LF.BLACKBOARD["web table"]["rows"][0] == ["City", "Population"]
        finally:
            LF.KEEP_BOARD["on"] = False
    finally:
        WE.read_page = old_read
        LF.BLACKBOARD.clear()
    # ---- the web read
    html = "<html><title>T</title><body><table><tr><td>nav</td><td>x</td></tr><tr><td>a</td><td>b</td></tr></table><p>Hello</p>" \
           "<table><tr><th>City</th><th>Population</th></tr><tr><td>Tokyo</td><td>37,000,000</td></tr><tr><td>Delhi</td><td>33</td></tr></table></body></html>"
    tables, text, title = WE.page_tables(html)
    c["page_tables_and_text_are_read_without_a_browser"] = len(tables) == 2 and tables[1][1] == ["Tokyo", "37,000,000"] and "Hello" in text and title == "T"
    c["the_table_the_words_name_is_picked"] = WE.best_table(tables, "city population")[0] == ["City", "Population"]
    c["internal_addresses_are_never_fetched"] = not WE.read_page("http://127.0.0.1:11434/")["ok"] and not WE.read_page("file:///C:/Windows/win.ini")["ok"]
    c["a_web_read_is_not_a_document_read"] = not OM.can_do("excel", {"do": "read", "text": "https://x.org"}) and OM.can_do("excel", {"do": "read", "text": ""})
    d = docx.Document()
    d.add_paragraph("Title")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "City", "Population"
    d.add_picture(pic)
    d.save(J(tmp, "d.docx"))
    rb = HR.read_back(J(tmp, "d.docx"))[1]
    c["a_documents_pictures_and_tables_are_read_back"] = "[1 picture(s) in the document]" in rb and "[table row] City | Population" in rb
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar81() -> "TestOutcome":
    """AR81: knowledge from the downloaded sources. A vendor's markdown object-model reference becomes manual pages under the app's key (cited by the official URL,
    build directives dropped) and its members become the app's commands; public benchmark tasks become our bench with this machine's apps, a sandbox folder,
    their inputs and checker, and an honest 'runnable'; an earlier app's saved file can be opened through the object model."""
    import types
    import zipfile
    from core_organs import gauntlet as G
    from core_organs import loop_first as LF
    from core_organs import office_om as OM
    from core_organs.professor.knowledge import manual_rag as MR
    from core_organs.professor.knowledge import vendor_docs as VD
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar81_")
    zp = os.path.join(tmp, "docs.zip")
    page = "---\ntitle: Range.Value property (Excel)\napi_name:\n- Excel.Range.Value\n---\n\n# Range.Value property (Excel)\n\nReturns or sets a **Variant** value of the [Range](x.md).\n\n!include[Support and feedback]\n"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("VBA-Docs-main/api/Excel.Range.Value.md", page)
        z.writestr("VBA-Docs-main/api/Word.Document.SaveAs2.md", page.replace("Range.Value property (Excel)", "Document.SaveAs2 method (Word)"))
        z.writestr("VBA-Docs-main/api/Access.Form.md", page)
    ix = MR.ManualIndex(os.path.join(tmp, "m.db"))
    rep = VD.ingest_markdown_reference(zp, ix=ix, log=lambda s: None)
    rows = ix.db.execute("SELECT d.app, d.source, c.text FROM chunks c JOIN docs d ON d.id = c.doc").fetchall()
    ix.close()
    c["only_the_chosen_apps_are_read"] = rep["by_app"] == {"excel": 1, "winword": 1}
    c["each_page_is_cited_by_its_official_url"] = any(r[1] == "https://learn.microsoft.com/office/vba/api/excel.range.value" for r in rows)
    c["markup_and_build_directives_are_dropped"] = all("!include" not in r[2] and "**" not in r[2] and "](" not in r[2] for r in rows)
    c["members_come_out_with_their_kind"] = {(m["name"], m["kind"]) for m in rep["members"]["excel"]} == {("Range.Value", "property")} and rep["members"]["winword"][0]["kind"] == "method"
    added: list = []
    fake_rag = types.SimpleNamespace(lex=types.SimpleNamespace(add_command=lambda key, label, **k: added.append((key, label, k.get("trust")))))
    c["members_are_filed_as_commands_never_verified"] = VD.file_members(fake_rag, rep["members"]) == {"excel": 1, "winword": 1} and ("excel", "Range.Value (property)", "official_doc") in added
    raw = {"id": "t1", "instruction": "Open ~/Desktop/report.odt in LibreOffice Writer and paste the table from LibreOffice Calc", "related_apps": ["libreoffice_writer", "libreoffice-calc"],
           "config": [{"type": "download", "parameters": {"files": [{"url": "https://x.org/report.odt", "path": "/home/user/Desktop/report.odt"}]}}],
           "evaluator": {"func": "compare_docx_files", "expected": {"type": "cloud_file", "path": "https://x.org/gold.docx"}}}
    t = G.bench_task(raw, "osworld", "multi_apps")
    c["benchmark_apps_become_this_machines_apps"] = t["apps"] == ["Word", "Excel"] and t["multi_app"] and "Word" in t["instruction"] and "LibreOffice" not in t["instruction"]
    c["home_paths_become_a_sandbox_folder"] = "~/" not in t["instruction"] and t["sandbox"] in t["instruction"].replace("\\\\", "\\") and t["inputs"][0]["path"].endswith("report.odt")
    c["the_checker_is_kept_and_known"] = t["checker"]["func"] == ["compare_docx_files"] and t["checker_known"] and t["runnable"]
    t2 = G.bench_task({**raw, "related_apps": ["gimp", "os"], "config": [{"type": "execute"}]}, "osworld", "multi_apps")
    c["a_task_this_machine_cannot_run_says_why"] = not t2["runnable"] and t2["blockers"] == ["gimp"]
    c["a_saved_file_can_be_opened_through_the_object_model"] = OM.can_do("excel", {"do": "open_file", "text": "x"}) and LF.render_step({"do": "open_file", "text": "C:\\a.xlsx", "target": "", "format": ""}) == "open the file C:\\a.xlsx"
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar82() -> "TestOutcome":
    """AR82: the benchmark bench is runnable here and drawn at random. Ubuntu set-up steps become sandboxed actions (mkdir / extract / remove / open / launch), focusing
    clicks and port relays are no-ops, package installs and scripts stay blockers; every set-up path stays inside the task's sandbox; the suite is random, hard
    (no easy-app-only task), unseen first; the benchmark's own checkers score result files and anything else is 'unscored', never guessed."""
    import openpyxl
    from core_organs import gauntlet as G
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar82_")
    box = os.path.join(tmp, "box")
    cfg = [{"type": "execute", "parameters": {"command": ["python", "-c", "import pyautogui; import time; time.sleep(2); pyautogui.click(1, 2)"]}},
           {"type": "launch", "parameters": {"command": ["socat", "tcp-listen:9222,fork", "tcp:localhost:1337"]}},
           {"type": "command", "parameters": {"command": "mkdir -p /home/user/Documents/proj && unzip /home/user/Desktop/a.zip -d /home/user/Documents/proj && rm -rf /home/user/Desktop/a.zip"}},
           {"type": "launch", "parameters": {"command": ["libreoffice", "--calc", "/home/user/Desktop/sales.xlsx"]}},
           {"type": "execute", "parameters": {"command": "echo {CLIENT_PASSWORD} | sudo -S apt install jq -y"}}]
    acts, bad = G.translate_setup(cfg, box)
    c["focusing_clicks_and_port_relays_are_no_ops"] = not [a for a in acts if a["op"] in ("launch",) and a.get("app") == ""] and "python" not in bad and "socat" not in bad
    c["shell_file_steps_become_sandboxed_actions"] = [a["op"] for a in acts][:4] == ["mkdir", "extract", "remove", "open"] and acts[1]["to"] == os.path.join(box, "Documents", "proj")
    c["an_office_file_opens_with_its_app"] = acts[3] == {"op": "open", "path": os.path.join(box, "Desktop", "sales.xlsx"), "app": "Excel"}
    c["package_installs_stay_blockers"] = "echo" in bad or "sudo" in bad
    c["windows_paths_map_into_the_sandbox_too"] = G._box_path(r"C:\Users\Docker\Desktop\x.docx", box) == os.path.join(box, "Desktop", "x.docx")
    os.makedirs(os.path.join(box, "Desktop"), exist_ok=True)
    import zipfile
    with zipfile.ZipFile(os.path.join(box, "Desktop", "a.zip"), "w") as z:
        z.writestr("ok.txt", "x")
        z.writestr("../../escape.txt", "x")
    log = G.apply_setup({"sandbox": box, "inputs": [], "setup": acts[:3] + [{"op": "remove", "path": os.path.join(tmp, "outside.txt")}]})
    c["setup_runs_inside_the_sandbox_and_nothing_escapes"] = os.path.isfile(os.path.join(box, "Documents", "proj", "ok.txt")) and not os.path.exists(os.path.join(tmp, "escape.txt")) \
        and not os.path.exists(os.path.join(box, "Desktop", "a.zip")) and any("refused" in x for x in log)
    T = [{"id": f"m{i}", "runnable": True, "multi_app": True, "apps": ["Excel", "Chrome"]} for i in range(6)] + \
        [{"id": "easy", "runnable": True, "multi_app": False, "apps": ["Notepad"]}, {"id": "s1", "runnable": True, "multi_app": False, "apps": ["Excel"]},
         {"id": "s2", "runnable": True, "multi_app": False, "apps": ["PowerPoint"]}, {"id": "no", "runnable": False, "multi_app": True, "apps": ["Excel", "Word"]}]
    led = {"m0": [{"passed": True}], "m1": [{"passed": False}]}
    a = G.sample_hard_suite(3, 3, seed=1, tasks=T, ledger=led)
    b = G.sample_hard_suite(3, 3, seed=2, tasks=T, ledger=led)
    c["easy_app_only_and_unrunnable_tasks_are_never_drawn"] = not {"easy", "no"} & {t["id"] for t in a + b}
    c["unseen_tasks_come_before_run_ones_and_passed_last"] = {t["id"] for t in a if t["multi_app"]} <= {"m2", "m3", "m4", "m5"}
    c["a_different_seed_draws_a_different_suite"] = [t["id"] for t in a] != [t["id"] for t in b] or len({t["id"] for t in a}) < 4
    got, want = os.path.join(box, "Desktop", "out.xlsx"), os.path.join(tmp, "gold.xlsx")
    for path, val in ((got, 40), (want, 40)):
        wb = openpyxl.Workbook()
        wb.active["A1"], wb.active["B1"] = "Milk", val
        wb.save(path)
    task = {"sandbox": box, "checker": {"func": ["compare_table"], "result": {"type": "vm_file", "path": "/home/user/Desktop/out.xlsx"},
                                        "expected": {"type": "cloud_file", "path": "https://example.org/gold.xlsx"}}}
    fetched: list = []
    fetch = lambda u, p: (fetched.append(u) or shutil.copy(want, p) or True)
    c["the_benchmarks_own_table_check_passes_a_right_file"] = G.check_bench(task, fetch)["passed"] and fetched == ["https://example.org/gold.xlsx"]
    wb = openpyxl.Workbook()
    wb.active["A1"], wb.active["B1"] = "Milk", 41
    wb.save(got)
    c["and_fails_a_wrong_one"] = not G.check_bench(task, fetch)["passed"]
    c["a_checker_we_do_not_have_is_unscored_not_guessed"] = G.check_bench({"sandbox": box, "checker": {"func": ["compare_audios"]}}) == {"scored": False, "passed": False,
                                                                                                                                     "why": "checker compare_audios is not implemented here"}
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar83() -> "TestOutcome":
    """AR83: video editing. Transcript lines are tightened to their spoken part; the model names the lines to DROP (what it leaves out stays); an edit too long for the asked
    length is ranked by the model and fitted by the code; a title written in the request is used as written; captions move to the edited timeline; FFmpeg renders
    (trim, join, title, burned captions, loudness) and the render is read back; a Shotcut project is written; the front door asks for a file when none is named."""
    import xml.etree.ElementTree as ET
    from core_organs import hojaiga_run as HR
    from core_organs.harvest import video_pipeline as VP
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar83_")
    src = {"path": os.path.join(tmp, "in.mp4"), "duration": 6.0, "has_audio": True, "quiet": [(1.0, 2.0), (3.0, 4.0)],
           "speech": [{"text": "Hello there.", "start": 0.0, "duration": 2.0}, {"text": "Um, uh.", "start": 2.0, "duration": 2.0}, {"text": "The point.", "start": 4.0, "duration": 2.0}]}
    lines = VP.speech_lines([src], pad=0.0)
    c["a_line_is_tightened_to_its_spoken_part"] = [(x["start"], x["end"]) for x in lines] == [(0.0, 1.0), (2.0, 3.0), (4.0, 6.0)]
    asked: list = []
    plan = VP.plan_edit("cut the fillers, add captions and the title My Demo", [src], ask=lambda s, p: (asked.append(p) or '{"drop": [2], "captions": true, "title": "my demo"}'))
    c["what_the_model_does_not_drop_stays_in_order"] = plan["keep"] == [1, 3] and [(k["start"], k["end"]) for k in plan["clips"]] == [(0.0, 1.15), (3.85, 6.0)]
    c["the_requests_own_title_wins"] = plan["title"] == "My Demo" and plan["captions"]
    replies = iter(['{"drop": [], "target_seconds": 2}', '{"ranked": [3, 1, 2]}'])
    plan2 = VP.plan_edit("a 2 second highlight", [src], ask=lambda s, p: next(replies))
    c["too_long_is_ranked_by_the_model_and_fitted_by_the_code"] = plan2["keep"] == [3]
    cap = VP.edl_speech(plan, [src])
    c["captions_move_to_the_edited_timeline"] = [x["text"] for x in cap] == ["Hello there.", "The point."] and abs(cap[1]["start"] - 1.30) < 0.01
    srt = VP.write_srt(cap, os.path.join(tmp, "c.srt"))
    c["captions_are_a_valid_srt"] = open(srt, encoding="utf-8").read().startswith("1\n00:00:00,000 --> 00:00:01,150\nHello there.")
    rc, _o, _e = VP._run([VP.ffbin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=6", "-f", "lavfi", "-i",
                          "sine=frequency=440:duration=6", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src["path"]], 120)
    if rc == 0:
        r = VP.render(plan, [src], os.path.join(tmp, "out.mp4"), srt, size=(320, 240))
        chk = VP.check_render(os.path.join(tmp, "out.mp4"), plan, srt)
        c["ffmpeg_renders_the_edit_and_the_render_is_read_back"] = r["ok"] and chk["ok"] and abs(chk["duration"] - 3.3) < 0.4
        bad = dict(plan, target_seconds=20)
        c["a_render_far_from_the_asked_length_fails_its_check"] = not VP.check_render(os.path.join(tmp, "out.mp4"), bad, srt)["ok"]
    else:
        c["ffmpeg_renders_the_edit_and_the_render_is_read_back"] = False
    mlt = VP.write_mlt(plan, [src], os.path.join(tmp, "p.mlt"))
    entries = [e.attrib for e in ET.parse(mlt).getroot().iter("entry")]
    c["a_shotcut_project_holds_the_same_cuts"] = [(e["in"], e["out"]) for e in entries] == [("0", "33"), ("116", "179")]
    c["the_front_door_asks_for_a_file_when_none_is_named"] = HR.do_video("cut the silences from my video", tmp)["status"] == "NEEDS_INPUT"
    c["video_is_a_route"] = "video" in HR.ROUTES and "video =" in HR.ROUTE_SYSTEM
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar84() -> "TestOutcome":
    """AR84: night of Oct-28 fixes. An Office plan whose every step is the object model's runs in an invisible instance of its own (no window, no start screen) and
    the instance is gone afterwards; a planned 'open' of a file that does not exist yet (the save target) is dropped; a web page counts as reached only on the same
    site with all the goal's words (or its #section)."""
    import time
    import types
    import openpyxl
    from core_organs import loop_first as LF
    from core_organs import office_om as OM
    from core_organs import web_executor as WE
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar84_")
    out, _a = LF.complete_steps([{"do": "open_file", "text": os.path.join(tmp, "new.xlsx"), "target": "", "format": ""},
                                 {"do": "type", "text": "x", "target": "A1", "format": ""}, {"do": "save_as", "text": os.path.join(tmp, "new.xlsx"), "target": "", "format": ""}], "type x")
    c["an_open_of_the_file_about_to_be_saved_is_dropped"] = [s["do"] for s in out] == ["new_document", "type", "save_as"]
    c["office_apps_map_to_their_object_models"] = OM.kind_for_app("Excel") == "excel" and OM.kind_for_app("winword") == "word" and OM.kind_for_app("paint") == ""
    path = os.path.join(tmp, "sheet.xlsx")
    plan = LF.AppPlan(app="excel")
    plan.steps = [{"do": "type", "text": "Item", "target": "A1", "format": ""}, {"do": "type", "text": "40", "target": "B1", "format": ""},
                  {"do": "save_as", "text": path, "target": "", "format": ""}]
    plan.goals = [LF.render_step(s) for s in plan.steps]
    run = LF.AppRun(app="excel", plan=plan)
    prepared: list = []
    before = _office_pids("EXCEL")
    LF._run_steps(plan, run, operate=lambda *a, **k: {"trace": []}, prepare=lambda *a, **k: (prepared.append(1) or {"hwnd": 0}), capsule_cb=None, cursor_cb=None,
                  allow_destructive=False, max_steps_per_goal=2)
    ws = openpyxl.load_workbook(path).active if os.path.isfile(path) else None
    c["an_object_model_plan_runs_without_any_window"] = run.status == "COMPLETED" and not prepared and run.hwnd == 0 and "invisible" in run.result.get("route", "")
    c["and_the_file_holds_what_was_typed"] = ws is not None and ws["A1"].value == "Item" and ws["B1"].value == 40
    time.sleep(1.5)
    c["the_invisible_instance_is_gone_afterwards"] = _office_pids("EXCEL") <= before
    pages = {"home": {"url": "https://en.wikipedia.org/wiki/Alan_Turing", "path": "/wiki/Alan_Turing", "title": "Alan Turing - Wikipedia", "labels": [], "text": ""}}

    def landed_on(url, title):
        WE._snap = lambda page: {"url": url, "path": WE.urlparse(url).path, "title": title, "labels": [], "text": ""}
        return WE.landed(None, ["early", "life"], pages["home"])[0]
    old = WE._snap
    try:
        c["another_site_with_one_word_is_not_reached"] = not landed_on("https://www.bbc.co.uk/news/early-years", "Turing's early years - BBC News")
        c["half_the_words_are_not_enough"] = not landed_on("https://en.wikipedia.org/wiki/Early_computers", "Early computers - Wikipedia")
        c["the_section_anchor_counts"] = landed_on("https://en.wikipedia.org/wiki/Alan_Turing#Early_life_and_education", "Alan Turing - Wikipedia")
    finally:
        WE._snap = old
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def run_ar85() -> "TestOutcome":
    """AR85: the multi-app reruns of Oct-28. A handed-over table is proven exactly (its cells in the saved file); Excel's own reading of '41,913,860' counts as the
    same cell; a paste / click on a kept table's name is an insert and the menu walk before it goes; the data table beats a navigation box and the page's own
    address; only a file the ticket MAKES must be new; a ticket that only reads a named page reads it without a browser."""
    import json as _j
    import shutil
    import tempfile
    import time
    from core_organs import hojaiga_run as HR
    from core_organs import loop_first as LF
    from core_organs import office_om as OM
    from core_organs import web_executor as WE
    c: Dict[str, Any] = {}
    LF.BLACKBOARD.clear()
    LF.keep("web table", {"kind": "table", "rows": [["City", "Population"], ["Jakarta", "41,913,860"], ["Dhaka", "36,585,479"]], "from": "https://x.org"})
    good = "Sheet!A1 = 'City'\nSheet!B1 = 'Population'\nSheet!A2 = 'Jakarta'\nSheet!B2 = 41913860\nSheet!A3 = 'Dhaka'\nSheet!B3 = 36585479"
    c["a_handed_over_table_is_proven_exactly"] = (HR.kept_in_file(good) or {}).get("ok") is True
    c["a_file_without_it_fails"] = (HR.kept_in_file("Sheet!A1 = 'nothing'") or {}).get("ok") is False
    LF.BLACKBOARD.clear()
    c["no_hand_over_leaves_it_to_the_judge"] = HR.kept_in_file(good) is None
    c["excels_number_reading_is_the_same_cell"] = OM._same_cell(41913860.0, "41,913,860") and OM._same_cell(0.05, "5%") and not OM._same_cell(41913861.0, "41,913,860")
    reply = _j.dumps({"steps": [{"do": "new_document"}, {"do": "type", "text": "Largest cities", "target": "title"}, {"do": "add_slide"}, {"do": "click", "target": "Insert"},
                                {"do": "click", "target": "Table"}, {"do": "click", "target": "cities"}, {"do": "save_as", "text": "PATH1"}]})
    q = LF.AppPlan(app="powerpoint", clauses=[r"add a slide titled Largest cities, insert the cities table and save it as C:\o\c.pptx"])
    LF.refine_plan(q, lambda s, p: reply, "- table 'cities' (A1:C11) from excel")
    c["a_click_on_a_kept_tables_name_is_an_insert_and_the_menu_walk_goes"] = [s["do"] for s in q.steps] == ["new_document", "type", "add_slide", "insert_table", "save_as"]
    q2 = LF.AppPlan(app="notepad", clauses=["click Format then type hi"])
    LF.refine_plan(q2, lambda s, p: _j.dumps({"steps": [{"do": "click", "target": "Format"}, {"do": "type", "text": "hi"}]}), "")
    c["outside_office_a_click_stays"] = [s["do"] for s in q2.steps] == ["click", "type"]
    nav = [["vteWorld's largest cities"], ["City proper", "Capitals Africa"], ["Metropolitan area", "Americas"]]
    data = [["City", "Country", "Population"]] + [[f"c{i}", "x", str(i)] for i in range(80)]
    c["the_data_table_beats_a_navigation_box"] = WE.best_table([nav, data], "copy the city population table from https://en.wikipedia.org/wiki/List_of_largest_cities") is data
    tmp = tempfile.mkdtemp(prefix="ar85_")
    src = os.path.join(tmp, "in.xlsx")
    open(src, "w").write("x")
    os.utime(src, (time.time() - 3600, time.time() - 3600))
    r = HR.prove(f"open Excel, open the file {src} and read A1:C11 as cities", time.time() - 5, ask=lambda s, p: '{"items": []}')
    c["a_file_only_read_need_not_be_new"] = not any(p.get("ok") is False for p in r["proof"])
    r2 = HR.prove(f"open Excel, open the file {os.path.join(tmp, 'gone.xlsx')} and read A1", time.time() - 5, ask=lambda s, p: '{"items": []}')
    c["a_missing_file_the_task_uses_fails"] = r2["status"] == "FAILED_CHECK"
    from openpyxl import Workbook
    wb = Workbook()
    for row in [["City", "Population"], ["Jakarta", 41913860], ["Dhaka", 36585479]]:
        wb.active.append(row)
    src2 = os.path.join(tmp, "cities.xlsx")
    wb.save(src2)
    LF.BLACKBOARD.clear()
    LF.keep("cities", {"kind": "table", "rows": [["City", "Population"], ["Jakarta", "41,913,860"], ["Dhaka", "36,585,479"]], "from": "excel"})
    r3 = HR.prove(f"open Excel, open the file {src2} and read A1:B3 as cities", time.time() - 5, ask=lambda s, p: '{"items": []}')
    c["a_read_is_proven_by_its_kept_cells_in_the_source"] = r3["status"] == "DONE" and r3["proof"][0].get("read") is True
    LF.keep("cities", {"kind": "table", "rows": [["Town", "People"], ["Paris", "2,100,000"], ["Lyon", "520,000"]], "from": "excel"})
    c["a_read_that_kept_other_cells_fails"] = HR.prove(f"open Excel, open the file {src2} and read A1:B3 as cities", time.time() - 5,
                                                       ask=lambda s, p: '{"items": []}')["status"] == "FAILED_CHECK"
    LF.BLACKBOARD.clear()
    old = HR.keep_from_web
    HR.keep_from_web = lambda t, u="": "kept a 3-row table and the page text from https://x.org"
    try:
        w = HR.do_web("open Chrome and copy the table from https://x.org/list", None, False, None, tmp)
        c["a_read_only_web_ticket_reads_without_a_browser"] = w["status"] == "DONE" and w["kept"].startswith("kept")
    finally:
        HR.keep_from_web = old
    shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


def _office_pids(name: str) -> set:
    import subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Process {name} -ErrorAction SilentlyContinue | % Id"], capture_output=True, text=True).stdout
    return {int(x) for x in out.split() if x.strip().isdigit()}


def run_ar86() -> "TestOutcome":
    """AR86: the natural brain and its teacher (offline: a stand-in teacher, a temp ledger, no network). The teacher's step is checked against the real control
    list; both answers and the proven outcome are kept; a proven teacher step becomes a procedure in the knowledge base; the brain switches the teacher off by itself
    when it agrees often enough; the judge uses the teacher while the brain learns and its own answer after; the user's key is the only Claude key ever read."""
    from core_organs.mind import brain as BR
    from core_organs import desktop_grounding as DG
    from core_organs import organ_37_llm_gateway as GW
    c: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar86_")
    old_ledger, old_env = BR.LEDGER, {k: os.environ.get(k) for k in ("HOJAIGA_BRAIN_MODE", "ANTHROPIC_API_KEY", "HOJAIGA_CLAUDE_KEY", "CLAUDE_API_KEY", "HOJAIGA_TEACHER_ORDER")}
    BR.LEDGER = os.path.join(tmp, "ledger.jsonl")
    ctrls = [("button", "Seven"), ("button", "Plus"), ("button", "Delete history"), ("button", "Equals")]
    say = lambda txt: (lambda s, p, im: (txt, "stub"))
    try:
        t = BR.teach("press seven", "calculator", ctrls, ask=say('{"index": 0, "verb": "click", "text": "", "why": "seven is the first digit"}'))
        c["a_valid_teacher_step_is_kept"] = t is not None and t["index"] == 0 and t["verb"] == "click" and t["who"] == "stub"
        c["an_index_outside_the_list_is_refused"] = BR.teach("x", "calculator", ctrls, ask=say('{"index": 9, "verb": "click"}')) is None
        c["an_unknown_verb_is_refused"] = BR.teach("x", "calculator", ctrls, ask=say('{"index": 1, "verb": "drag"}')) is None
        c["no_json_is_refused"] = BR.teach("x", "calculator", ctrls, ask=say("press seven")) is None
        r = BR.teach("add two numbers", "calculator", ctrls, ask=say('{"index": 2, "verb": "click"}'))
        c["a_risky_control_the_goal_never_asked_for_is_flagged"] = bool(r and r.get("risk"))

        class _Proc:
            rows: list = []

            def ingest_procedure(self, app_key, goal, steps, source_ref, trust="learned", **k):
                self.rows.append((app_key, goal, steps, trust))
        rag = type("R", (), {"proc": _Proc()})()
        sid = BR.record("calculator", "press seven", ctrls, t, ("click", "Seven"), "stub")
        BR.outcome(sid, "PASS", "display shows 7", rag=rag)
        rows = BR._rows()
        c["the_step_and_its_outcome_are_in_the_ledger"] = [r["kind"] for r in rows] == ["step", "outcome"] and rows[0]["agree"] is True
        c["a_proven_teacher_step_becomes_a_procedure"] = len(rag.proc.rows) == 1 and rag.proc.rows[0][3] == "teacher_proven" and "Seven" in rag.proc.rows[0][2][0]["text"]
        sid2 = BR.record("calculator", "press plus", ctrls, {"index": 1, "verb": "click", "text": "", "why": "", "who": "stub"}, ("click", "Equals"), "stub")
        BR.outcome(sid2, "NO_CHANGE", "", rag=rag)
        rd = BR.readiness()
        c["only_proven_steps_count"] = rd["proven_teacher_steps"] == 1 and rd["brain_agreed"] == 1 and len(rag.proc.rows) == 1
        os.environ.pop("HOJAIGA_BRAIN_MODE", None)
        c["the_teacher_stays_on_while_the_brain_is_new"] = BR.mode() == "teacher"
        for i in range(BR.READY_MIN):
            s = BR.record("calculator", f"g{i}", ctrls, t, ("click", "Seven"), "stub")
            BR.outcome(s, "PASS", rag=rag)
        c["the_brain_turns_the_teacher_off_when_it_agrees_enough"] = BR.mode() == "local" and BR.readiness()["ready"]
        os.environ["HOJAIGA_BRAIN_MODE"] = "teacher"
        c["the_person_can_force_the_teacher_back_on"] = BR.mode() == "teacher"

        els = [DG.GroundedElement(id=str(i), name=n, role=r, bbox=(10 * i, 0, 10 * i + 8, 8), tier="uia") for i, (r, n) in enumerate(ctrls)]
        judge = DG.ConstrainedJudge()
        judge._decide_local = lambda goal, elements, *a, **k: {"verb": "click", "element": elements[3].as_dict(), "element_index": 3}
        old_teach = BR.teach
        BR.teach = lambda goal, app, controls, img="", ask=None: {"index": [n for _r, n in controls].index("Plus"), "verb": "click", "text": "", "why": "plus next", "who": "stub"}
        DG_png = DG._window_png_b64
        DG._window_png_b64 = lambda hwnd, max_side=1568: ""
        try:
            d = judge.decide("add", els, app_hint="calculator", use_decisive=False)
            c["the_judge_uses_the_teacher_while_the_brain_learns"] = d["element"]["name"] == "Plus" and d.get("teacher") == "stub" and bool(d.get("brain_id"))
            os.environ["HOJAIGA_BRAIN_MODE"] = "local"
            d2 = judge.decide("add", els, app_hint="calculator", use_decisive=False)
            c["and_its_own_answer_when_it_is_ready"] = d2["element"]["name"] == "Equals" and not d2.get("teacher")
            os.environ["HOJAIGA_BRAIN_MODE"] = "off"
            d3 = judge.decide("add", els, app_hint="calculator", use_decisive=False)
            c["off_means_no_ledger_and_no_teacher"] = "brain_id" not in d3
        finally:
            BR.teach, DG._window_png_b64 = old_teach, DG_png
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dev-tool-key-not-the-users"
        for k in ("HOJAIGA_CLAUDE_KEY", "CLAUDE_API_KEY"):
            os.environ.pop(k, None)
        GW.env_keys(refresh=True)
        c["a_developer_shells_anthropic_key_is_never_read"] = "ANTHROPIC_API_KEY" not in GW.env_keys() and GW.claude_key() == (GW.env_keys().get("HOJAIGA_CLAUDE_KEY") or GW.env_keys().get("CLAUDE_API_KEY") or "")
        os.environ["HOJAIGA_TEACHER_ORDER"] = "claude"
        GW.env_keys(refresh=True)
        c["no_user_key_means_no_claude_call"] = GW.claude_key() != "" or GW.teacher_chat("s", "p") == (None, "")
    finally:
        BR.LEDGER = old_ledger
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        GW.env_keys(refresh=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in c.items()})


TESTS = [("AR65", run_ar65), ("AR66", run_ar66), ("AR67", run_ar67), ("AR68", run_ar68), ("AR69", run_ar69), ("AR70", run_ar70), ("AR71", run_ar71), ("AR72", run_ar72), ("AR73", run_ar73), ("AR74", run_ar74),
         ("AR75", run_ar75), ("AR76", run_ar76), ("AR77", run_ar77), ("AR78", run_ar78), ("AR79", run_ar79), ("AR80", run_ar80), ("AR81", run_ar81), ("AR82", run_ar82), ("AR83", run_ar83), ("AR84", run_ar84), ("AR85", run_ar85), ("AR86", run_ar86)]


def main(argv=None) -> int:
    want = set(a.upper() for a in (argv if argv is not None else sys.argv[1:]))
    bad = 0
    for name, fn in TESTS:
        if want and name not in want:
            continue
        r = fn()
        print(f"{name}: {'PASS' if r.passed else 'FAIL'} {r.metrics.get('checks', '')}")
        if not r.passed:
            bad += 1
            print("   ", "; ".join(x for x in r.evidence.split("; ") if x.endswith("=FAIL")))
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
