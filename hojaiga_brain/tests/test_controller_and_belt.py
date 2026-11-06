"""
Conveyor belt, brain-inside-the-brain and the always-on controller (python -m pytest tests -v).
"""
import csv
import json
import random
import sys
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.config import BrainSystemConfig, LLMConfig  # noqa: E402
from brain.controller import NaturalIntelligenceController  # noqa: E402
from brain.conveyor import belt as belt_mod  # noqa: E402
from brain.conveyor.belt import ConveyorBelt, classify_text  # noqa: E402
from brain.curiosity_and_langchain import HojaigaExecutiveBrain  # noqa: E402
from brain.inner_brain import DualBrain  # noqa: E402


def make_brain(ws: Path) -> HojaigaExecutiveBrain:
    return HojaigaExecutiveBrain(BrainSystemConfig(workspace_dir=ws, llm=LLMConfig.from_variant("tiny_5m"),
                                                   teacher_provider="none"))


def make_dataset(root: Path) -> Path:
    """Support tickets (3 real categories + a random 'priority' column), a duplicate, a leaked key,
    policy documents, two folders of images and a short clip."""
    from PIL import Image, ImageDraw
    rnd = random.Random(4)
    root.mkdir(parents=True, exist_ok=True)
    subj = {"billing": (["I was charged twice for", "My invoice shows the wrong amount for", "Please refund",
                         "The credit card charge for", "Why did the price change for"],
                        ["my annual subscription", "last month's plan", "the premium upgrade", "the family bundle"]),
            "technical": (["The app crashes when I open", "I get error 500 when loading", "Login fails on",
                           "The page freezes after updating", "Sync stopped working for"],
                          ["the dashboard", "the mobile app", "the settings page", "the desktop client"]),
            "shipping": (["My parcel has not arrived for", "The tracking number does not work for",
                          "Delivery was late for", "The courier lost", "Can I change the address for"],
                         ["order 7710", "my package", "the replacement item", "the gift box"])}
    rows = []
    for cat, (a, b) in subj.items():
        for _ in range(20):
            rows.append({"ticket_id": f"T{len(rows) + 1000}", "message": f"{rnd.choice(a)} {rnd.choice(b)}. "
                         f"{rnd.choice(['Please help.', 'This is urgent.', 'Thanks in advance.', 'What next?'])}",
                         "category": cat, "priority": rnd.choice(["low", "high", "medium"])})
    rows.append(dict(rows[0]))
    rows.append({"ticket_id": "T9999", "message": "My key sk_live_9fQ2x7LmP4vR8tZ1kW3n stopped working after the upgrade",
                 "category": "technical", "priority": "high"})
    with (root / "tickets.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (root / "policies.md").write_text(
        "# Refunds\n\nCustomers can request a refund within 30 days of purchase. Refunds are returned to the "
        "original payment method within five business days.\n\n# Shipping\n\nStandard delivery takes three to "
        "five business days. Express delivery arrives the next business day when ordered before 2 pm.\n",
        encoding="utf-8")
    for shape in ("circle", "square"):
        (root / "images" / shape).mkdir(parents=True, exist_ok=True)
        for i in range(10):
            im = Image.new("RGB", (96, 96), tuple(rnd.randint(200, 255) for _ in range(3)))
            o = rnd.randint(8, 20)
            draw = ImageDraw.Draw(im)
            (draw.ellipse if shape == "circle" else draw.rectangle)([o, o, 96 - o, 96 - o],
                                                                    fill=tuple(rnd.randint(0, 150) for _ in range(3)))
            im.save(root / "images" / shape / f"{shape}_{i}.png")
    frames = []
    for t in range(8):
        im = Image.new("RGB", (80, 60), (20, 20, 30))
        ImageDraw.Draw(im).ellipse([5 + t * 8, 20, 20 + t * 8, 35], fill=(250, 200, 0))
        frames.append(im)
    frames[0].save(root / "clip.gif", save_all=True, append_images=frames[1:], duration=100)
    return root


@pytest.fixture(scope="module")
def belt_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("belt")
    data = make_dataset(tmp / "data")
    brain = make_brain(tmp / "ws")
    return brain, ConveyorBelt(brain).run([str(data)]), tmp


# ─────────────────────────────────────────────────────────────── conveyor belt
def test_belt_runs_every_station(belt_run):
    _, rep, _ = belt_run
    assert not rep.get("errors"), rep.get("errors")
    for station in ("ingest", "clean", "vectorize", "classical_ml", "deep_learning", "algorithms", "llm_vlm", "rag"):
        assert station in rep and station in rep["seconds"], station
    assert rep["orchestrator"] == ("langgraph" if belt_mod.HAS_LANGGRAPH else "built-in")
    assert Path(rep["report_file"]).exists()


def test_cleaning_removes_duplicates_and_secrets(belt_run):
    brain, rep, _ = belt_run
    assert rep["clean"]["dropped"].get("near_duplicate", 0) >= 1
    assert rep["clean"]["redacted_items"] == 1
    assert not any("sk_live_9fQ2x7LmP4vR8tZ1kW3n" in ep.content for ep in brain.l2.episodes.values())


def test_classical_ml_finds_the_real_label_and_classifies(belt_run):
    _, rep, _ = belt_run
    tc = rep["classical_ml"]["text_classification"]
    assert tc["label_field"] == "category", tc["label_candidates"]        # not the random 'priority' column
    assert tc["naive_bayes"]["accuracy"] >= 0.9 and tc["logistic_regression"]["accuracy"] >= 0.9
    assert rep["classical_ml"]["topics"]["k"] >= 2
    assert rep["classical_ml"]["image_classification"]["logistic_regression"]["accuracy"] >= 0.85


def test_deep_learning_station(belt_run):
    _, rep, _ = belt_run
    dl = rep["deep_learning"]
    assert dl["mlp_text"]["accuracy"] >= 0.8
    assert dl["mlp_image"]["accuracy"] >= 0.75
    if dl["engine"] == "pytorch":
        assert dl["transformer_text"]["accuracy"] >= 0.6 and dl["transformer_text"]["params"] > 0


def test_algorithms_llm_vlm_and_rag_stations(belt_run):
    brain, rep, tmp = belt_run
    alg = rep["algorithms"]
    assert alg["nodes"] > 10 and alg["communities"] >= 1
    assert all(c[0] not in ("the", "please", "for") for c in alg["top_concepts"][:5]), alg["top_concepts"]
    assert rep["llm_vlm"]["tokenizer_new_merges"] > 0 and rep["llm_vlm"]["vlm_interfaces"].get("videos") == 1
    assert rep["rag"]["recall_at_3"] >= 0.8
    pred = classify_text(brain.cfg.workspace_dir, "the courier never delivered my parcel")
    assert pred["label"] == "shipping"
    assert "three to five business days" in brain.run_cognitive_cycle("How long does standard delivery take?")["answer"]


# ─────────────────────────────────────────────────────────────── brain inside the brain
def test_inner_brain_takes_over_and_learns_corrections(tmp_path):
    brain = make_brain(tmp_path / "ws")
    brain.feed_dataset("Standard delivery takes three to five business days.\n\n"
                       "Refunds are returned to the original payment method within five business days.")
    dual = DualBrain(brain)
    q = "How long does standard delivery take?"
    first = dual.ask(q)
    assert first["answered_by"] == "main_brain" and first["distilled_into_inner"] == "new"
    second = dual.ask(q)
    assert second["answered_by"] == "inner_brain" and "three to five" in second["answer"]
    assert second["self_reliance"] == 0.5
    dual.feedback(q, good=False, correction="Standard delivery takes two to four business days since May.")
    third = dual.ask(q)
    assert third["answered_by"] == "inner_brain" and "two to four" in third["answer"]
    # persisted: a new process keeps the inner memory
    assert DualBrain(make_brain(tmp_path / "ws")).inner.recall(q)["answer"].startswith("Standard delivery takes two")


def test_inner_llm_distillation(tmp_path):
    brain = make_brain(tmp_path / "ws")
    dual = DualBrain(brain)
    dual.inner.learn("What is the capital of Kenya?", "Nairobi is the capital of Kenya.")
    rep = dual.inner.distill_llm(brain.tokenizer, epochs=1)
    assert rep["trained_pairs"] == 1 and rep["final_loss"] > 0


# ─────────────────────────────────────────────────────────────── controller
def test_router_uses_descriptions_then_learns(tmp_path):
    ctrl = NaturalIntelligenceController(make_brain(tmp_path / "ws"))
    calls = []
    ctrl.register_skill("send_invoice", "send email invoice billing payment to a customer",
                        lambda p: calls.append(p["text"]) or {"sent": True}, requires_approval=True)
    ctrl.register_skill("restart_server", "restart reboot server machine service host",
                        lambda p: {"restarted": True})
    assert ctrl.route("please reboot the web server")["skill"] == "restart_server"
    assert ctrl.route("email the invoice to the customer")["skill"] == "send_invoice"
    # a phrasing the descriptions don't cover: a person corrects the routing once
    phrase = "bounce prod-7 again"
    ctrl.correct_routing(phrase, "restart_server")
    assert ctrl.route(phrase)["skill"] == "restart_server"
    # risky skill waits for a human
    r = ctrl.handle({"text": "email the invoice to the customer"})
    assert r["status"] == "awaiting_approval" and not calls
    done = ctrl.approve(r["id"])
    assert done["status"] == "done" and calls
    events = [json.loads(line)["event"] for line in ctrl.audit_path.read_text().splitlines()]
    assert "awaiting_approval" in events and "approved" in events and "done" in events


def test_controller_scans_screens_and_renders(tmp_path):
    from PIL import Image, ImageDraw
    ctrl = NaturalIntelligenceController(make_brain(tmp_path / "ws"))
    img = Image.new("RGB", (400, 300), (245, 245, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 400, 30], fill=(30, 40, 90))
    for i in range(4):
        d.rectangle([20, 50 + i * 50, 140, 80 + i * 50], fill=(70, 120, 220))
    img.save(tmp_path / "app.png")
    scan = ctrl.handle({"text": "look at this screenshot of the app interface", "image": str(tmp_path / "app.png")})
    assert scan["skill"] == "scan_screen" and scan["result"]["discovered_regions_count"] >= 2
    rendered = ctrl.handle({"text": "render a 3d hologram view", "content": "order -> pick -> pack -> ship",
                            "out": str(tmp_path / "v.html")})
    assert rendered["skill"] == "render" and Path(rendered["result"]["html"]).exists()


def test_always_on_service_http_and_inbox(tmp_path):
    ws = tmp_path / "ws"
    ctrl = NaturalIntelligenceController(make_brain(ws))
    server, stop = ctrl.serve(port=0, poll_s=3600, consolidate_every_s=0, block=False)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    try:
        # drop a dataset into the inbox; one tick of the background loop learns it
        (ctrl.inbox / "policies").mkdir()
        (ctrl.inbox / "policies" / "p.md").write_text(
            "Express delivery arrives the next business day when ordered before 2 pm.", encoding="utf-8")
        tick = ctrl.tick(consolidate_every_s=0)
        assert tick["learned"] == ["policies"] and not any(ctrl.inbox.iterdir())
        a1 = post("/ask", {"question": "When does express delivery arrive?"})
        assert a1["status"] == "done" and "next business day" in a1["result"]["answer"]
        a2 = post("/ask", {"question": "When does express delivery arrive?"})
        assert a2["result"]["answered_by"] == "inner_brain"
        fb = post("/feedback", {"question": "When does express delivery arrive?", "good": True})
        assert fb["recorded"]
        with urllib.request.urlopen(base + "/status", timeout=30) as r:
            st = json.loads(r.read())
        assert st["self_reliance"] == 0.5 and "answer" in st["skills"] and st["inner_memory"] == 1
    finally:
        server.shutdown()
        stop.set()


def test_consolidation_trains_inner_and_main(tmp_path):
    ctrl = NaturalIntelligenceController(make_brain(tmp_path / "ws"))
    ctrl.brain.feed_dataset("Rivers carry water to the sea.\n\nDeltas form where rivers drop sediment near the coast.")
    ctrl.dual.ask("Where do deltas form?")
    rep = ctrl.handle({"skill": "consolidate", "text": "sleep and improve", "epochs": 1})
    assert rep["status"] == "done", rep
    assert rep["result"]["main_llm"]["trained_samples"] > 0 and rep["result"]["inner_llm"]["trained_pairs"] >= 1
    assert make_brain(tmp_path / "ws").llm_trained
