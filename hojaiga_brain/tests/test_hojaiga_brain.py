"""
Automated verification of the Hojaiga Brain (run: python -m pytest tests -v).

1. All 8 cortical layers run end-to-end and answer >84% of symbolic/RAG questions correctly
   before any neural training.
2. The 5-tier value critic (WORST/BAD/GOOD/BETTER/BEST), the FailureMemory pain registry
   (blocks known bad trajectories) and the 3-step span editor.
3. The VLM encodes 2D images / UI screenshots (encode_image + deep_scan_ui_screen) and 3D video
   clips (encode_video) through the same network, and recognizes an interface across runs.
4. Teacher-to-student graduation: external Claude calls stop once local verification passes the
   0.85 competency threshold for that domain.
5. The Universal Renderer emits valid 2D/3D/Hologram HTML from JSON, text, image and video input.
"""
import json
import re
import subprocess
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.config import BrainSystemConfig, LLMConfig, VLMConfig  # noqa: E402
from brain.curiosity_and_langchain import HojaigaExecutiveBrain  # noqa: E402
from brain.layers_l1_to_l8 import FailureMemory, Layer5DefaultModeThink, Layer6BrocaAnswer  # noqa: E402
from brain.rag_hippocampus import HippocampusRAGEngine  # noqa: E402
from brain.tokenizer_and_llm import HAS_TORCH  # noqa: E402
from brain.universal_renderer import HojaigaUniversalRenderer  # noqa: E402
from brain.vlm_encoder import HojaigaVLMEncoder  # noqa: E402

TEXTBOOK = """Human reproduction

The male reproductive system produces sperm. The testes produce sperm and the hormone testosterone. Sperm moves from the testes to the epididymis. The epididymis stores sperm while it matures. Sperm travels through the vas deferens to the urethra. Seminal vesicles and the prostate gland add fluid that nourishes sperm.

The female reproductive system produces eggs and supports a developing baby. The ovaries produce eggs and the hormones estrogen and progesterone. During ovulation an egg moves from the ovary into the fallopian tube. The fallopian tube connects to the uterus. The uterus is a muscular organ where a fertilized egg develops.

Fertilization happens when a sperm cell joins an egg cell in the fallopian tube. The fertilized egg is called a zygote. The zygote divides and moves to the uterus. The zygote implants in the lining of the uterus. If no fertilization happens, the uterus lining is shed during menstruation.

Gravity and orbits

Gravity is a force that pulls masses toward each other. Escape velocity is the minimum speed needed to leave a planet without further propulsion. The escape velocity of Earth is about 11.2 kilometres per second. Orbital speed depends on the mass of the planet and the radius of the orbit. A satellite in low Earth orbit travels at about 7.8 kilometres per second.

Mira and the fox

Mira lived in a small village beside a dark forest. Every night she watched the stars from her window. One stormy night a tiny glowing fox appeared at her door, shivering in the rain. Mira wrapped the fox in a warm blanket.

Solar power

Photovoltaic panels convert sunlight into direct current electricity. An inverter converts direct current into alternating current for the home. A charge controller protects the battery from overcharging.
"""

# (question, words that must all appear in a correct answer)
QA = [
    ("What do the testes produce?", ["sperm", "testosterone"]),
    ("Where does sperm mature?", ["epididymis"]),
    ("Which tube carries sperm to the urethra?", ["vas deferens"]),
    ("What do seminal vesicles and the prostate gland add?", ["fluid"]),
    ("What do the ovaries produce?", ["eggs", "estrogen"]),
    ("Where does an egg move during ovulation?", ["fallopian tube"]),
    ("What is the uterus?", ["muscular organ"]),
    ("Where does fertilization happen?", ["fallopian tube"]),
    ("What is a fertilized egg called?", ["zygote"]),
    ("Where does the zygote implant?", ["lining"]),
    ("What happens to the uterus lining if no fertilization happens?", ["menstruation"]),
    ("What is gravity?", ["force", "masses"]),
    ("What is escape velocity?", ["minimum speed"]),
    ("What is the escape velocity of Earth?", ["11.2"]),
    ("How fast does a satellite in low Earth orbit travel?", ["7.8"]),
    ("What does orbital speed depend on?", ["mass", "radius"]),
    ("Where did Mira live?", ["village"]),
    ("What appeared at Mira's door?", ["fox"]),
    ("What did Mira wrap the fox in?", ["blanket"]),
    ("What do photovoltaic panels convert sunlight into?", ["direct current"]),
    ("What does an inverter do?", ["alternating current"]),
    ("What protects the battery from overcharging?", ["charge controller"]),
    ("What is 12 * 12?", ["144"]),
    ("Calculate 2 ^ 10", ["1024"]),
    ("What is (45 + 15) / 4?", ["15"]),
]


def make_brain(tmp_path: Path, **overrides) -> HojaigaExecutiveBrain:
    cfg = BrainSystemConfig(workspace_dir=tmp_path / "ws", llm=LLMConfig.from_variant("tiny_5m"),
                            teacher_provider=overrides.pop("teacher_provider", "none"), **overrides)
    return HojaigaExecutiveBrain(cfg)


@pytest.fixture()
def fed_brain(tmp_path):
    book = tmp_path / "textbook.md"
    book.write_text(TEXTBOOK, encoding="utf-8")
    brain = make_brain(tmp_path)
    brain.feed_dataset(book)
    return brain


def is_correct(answer: str, must) -> bool:
    a = answer.lower()
    return all(m.lower() in a for m in must)


# ─────────────────────────────────────────────────────────────── 1. eight layers + accuracy
def test_all_eight_layers_run_and_accuracy_above_84_percent(fed_brain):
    assert not fed_brain.llm_trained, "accuracy must be measured before any neural training"
    correct, wrong = 0, []
    for q, must in QA:
        r = fed_brain.run_cognitive_cycle(q)
        prov = r["provenance"]
        for layer in ("L1:Filter", "L2:Know", "L3:Understand", "L4:Reason", "L5:Think", "L7:Verify", "L6:Answer"):
            assert layer in prov, f"{layer} missing from provenance {prov}"
        assert "domain_competence" in r["autonomy_status"]          # L8 ran and recorded the outcome
        assert r["value_tier"] in ("WORST", "BAD", "GOOD", "BETTER", "BEST")
        assert r["segregated_steps"] and r["verification"]
        if is_correct(r["answer"], must):
            correct += 1
        else:
            wrong.append((q, r["answer"][:120]))
    acc = correct / len(QA)
    print(f"\naccuracy {correct}/{len(QA)} = {acc:.2%}; wrong: {wrong}")
    assert acc > 0.84, f"accuracy {acc:.2%} <= 84%: {wrong}"


def test_answers_are_precise_not_pasted_memories(fed_brain):
    r = fed_brain.run_cognitive_cycle("What is a fertilized egg called?")
    body = r["answer"].split(" [Sources:")[0]
    assert "zygote" in body and len(body.split()) <= 40
    assert "What is a fertilized egg called" not in body        # the question is not echoed back


# ─────────────────────────────────────────────────────────────── 2. critic, pain, span editor
def test_five_tier_value_critic_produces_every_tier():
    l5 = Layer5DefaultModeThink()
    l5.observe_reference_writing("Short line. Then a much longer sentence that wanders through several ideas "
                                 "before it ends. Another short one. Variety keeps prose alive and readable.")
    rng = np.random.default_rng(0)
    tiers = set()
    texts = ["word word word word word word", "The sun heats the land and the sea at different rates.",
             "Clouds form as moist air rises, cools and condenses into droplets around dust.",
             "ok", "Rain falls. Rivers swell quickly after storms, then slowly drain back into lakes."]
    for i in range(200):
        g, c = float(rng.uniform(0, 1)), float(rng.uniform(0, 1))
        pain = 0.9 if i % 37 == 0 else float(rng.uniform(0, 0.3))
        _, tier, feats = l5.score_and_classify_tier(texts[i % len(texts)], g, c, pain)
        tiers.add(tier)
        assert feats.shape == (5,)
    assert tiers == {"WORST", "BAD", "GOOD", "BETTER", "BEST"}, tiers


def test_failure_memory_blocks_known_bad_trajectory(tmp_path):
    rag = HippocampusRAGEngine(tmp_path / "rag")
    fm = FailureMemory(rag)
    bad = "The heart is located in the left foot and pumps air."
    assert fm.pain_overlap(bad) == 0.0
    fm.register("domain_1", "Where is the heart?", bad, value_score=0.1)
    assert fm.blocks(bad)                                         # identical trajectory: blocked
    assert fm.pain_overlap("The heart is located in the chest.") < fm.pain_overlap(bad)
    assert not fm.blocks("Photosynthesis turns light into chemical energy in leaves.")


def test_brain_never_repeats_a_corrected_answer(fed_brain):
    q = "What colour was the fox's fur?"            # the book never says: the first answer is wrong
    first = fed_brain.run_cognitive_cycle(q)["answer"].split(" [Sources:")[0]
    assert "orange" not in first.lower()
    fixed = "The fox's fur was bright orange with a white tip on its tail."
    fed_brain.run_cognitive_cycle(q, user_correction=fixed)
    assert len(fed_brain.l8.failure_memory) >= 1
    assert fed_brain.l8.failure_memory.blocks(first + " [Sources: x]") or \
        fed_brain.l8.compute_pain_overlap(first) > 0.5
    second = fed_brain.run_cognitive_cycle(q)["answer"].split(" [Sources:")[0]
    assert second != first, "the refuted answer was repeated"
    assert "orange" in second.lower(), second


def test_three_step_span_editor_polishes_robotic_writing():
    l6 = Layer6BrocaAnswer()
    learned = l6.learn_from_edit_pair(
        "We leverage cutting-edge synergies to deliver value to customers.",
        "We work together to deliver value to customers.")
    assert learned, "no span edit learned from the draft/polished pair"
    draft = "We leverage cutting-edge synergies to deliver value   to deliver value to customers."
    polished, trace = l6.polish_writing_dynamically(draft)
    assert "leverage" not in polished.lower() and "work together" in polished      # step 1: learned span edit
    assert "to deliver value to deliver value" not in polished                    # step 2: duplicate n-gram
    assert "  " not in polished                                                    # step 3: whitespace
    assert trace


# ─────────────────────────────────────────────────────────────── 3. vision: 2D, UI, 3D video
def synthetic_ui(seed: int = 0) -> np.ndarray:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 400), (245, 246, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 640, 40], fill=(40, 60, 120))                       # title bar
    d.rectangle([0, 40, 140, 400], fill=(225, 228, 236))                   # sidebar
    for i in range(5):
        d.rectangle([12, 60 + i * 48, 128, 92 + i * 48], fill=(90, 110, 200))   # sidebar buttons
    d.rectangle([170, 70, 610, 110], outline=(30, 30, 30), width=2)        # search box
    d.rectangle([500, 330, 610, 370], fill=(30, 160, 90))                  # primary button
    for i in range(4):
        d.rectangle([170, 140 + i * 40, 470, 160 + i * 40], fill=(180, 180, 190))   # list rows
    return np.array(img)


def test_vlm_encodes_images_and_scans_ui(tmp_path):
    vlm = HojaigaVLMEncoder(VLMConfig(), memory_dir=tmp_path / "ui")
    ui = synthetic_ui()
    tokens = vlm.encode_image(ui)
    if HAS_TORCH:
        assert tuple(tokens.shape) == (1, (224 // 16) ** 2 + 1, VLMConfig().proj_dim)
    else:
        assert tokens.shape == (VLMConfig().proj_dim,)
    scan = vlm.deep_scan_ui_screen(ui, context_hint="settings_app")
    assert scan["discovered_regions_count"] >= 3
    assert all(0 <= r["bbox"][0] < r["bbox"][2] <= 640 and 0 <= r["bbox"][1] < r["bbox"][3] <= 400
               for r in scan["layout"])
    assert scan["recognized_from_memory"] is False and scan["epistemic_surprise"] > 0.5


def test_vlm_recognizes_same_interface_in_a_later_run(tmp_path):
    ui = synthetic_ui()
    first = HojaigaVLMEncoder(VLMConfig(), memory_dir=tmp_path / "ui").deep_scan_ui_screen(ui, "mail_app")
    later = HojaigaVLMEncoder(VLMConfig(), memory_dir=tmp_path / "ui").deep_scan_ui_screen(ui, "mail_app")
    assert first["recognized_from_memory"] is False
    assert later["recognized_from_memory"] is True, "interface memory did not survive a restart"
    assert later["interface_id"] == first["interface_id"] and later["epistemic_surprise"] < 0.1


def test_vlm_encodes_video_in_the_same_network(tmp_path):
    vlm = HojaigaVLMEncoder(VLMConfig(), memory_dir=tmp_path / "ui")
    frames = np.zeros((10, 120, 160, 3), dtype=np.uint8)
    for t in range(10):
        frames[t, 50:70, 10 + t * 12: 30 + t * 12] = (255, 200, 0)            # a ball moving right
    calls = []
    if HAS_TORCH:
        hook = vlm.llm_projector.register_forward_hook(lambda *a: calls.append(1))
    vid_tokens = vlm.encode_video(frames)
    img_tokens = vlm.encode_image(frames[0])
    if HAS_TORCH:
        hook.remove()
        cfg = VLMConfig()
        n_spatial = (cfg.image_size // cfg.patch_size) ** 2
        assert tuple(vid_tokens.shape) == (1, 1 + (cfg.temporal_frames // cfg.temporal_tubelet) * n_spatial,
                                           cfg.proj_dim)
        assert len(calls) == 2, "image and video must pass through the same projector"
        v, i = vid_tokens.mean(1)[0].numpy(), img_tokens.mean(1)[0].numpy()
    else:
        v, i = vid_tokens, img_tokens
    assert v.shape == i.shape and not np.allclose(v, i)


# ─────────────────────────────────────────────────────────────── 4. teacher → student graduation
class FakeAnthropic(types.ModuleType):
    def __init__(self):
        super().__init__("anthropic")
        self.calls = 0
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls += 1
                block = types.SimpleNamespace(type="text", text="The fertilized egg is called a zygote.")
                return types.SimpleNamespace(content=[block], stop_reason="end_turn")

        class Anthropic:
            def __init__(self, api_key=None):
                self.messages = _Messages()

        self.Anthropic = Anthropic


def test_teacher_api_is_disabled_after_graduation(tmp_path, monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    book = tmp_path / "book.md"
    book.write_text(TEXTBOOK, encoding="utf-8")
    brain = make_brain(tmp_path, teacher_provider="anthropic", min_runs_before_graduation=5)
    assert brain.cfg.graduation_competence_threshold == 0.85
    brain.feed_dataset(book)

    # direct gate: an ungraduated domain consults the teacher
    assert brain._consult_teacher_if_needed("domain_probe", "What is a zygote?") is not None
    assert fake.calls == 1

    q = "What is a fertilized egg called?"
    status = None
    for _ in range(12):
        status = brain.run_cognitive_cycle(q)["autonomy_status"]
        if status["domain_graduated_off_api"]:
            break
    assert status["domain_graduated_off_api"], status
    assert status["domain_competence"] >= 0.85
    calls_at_graduation = fake.calls

    # force local verification to fail: while graduated, the API must NOT be called
    orig = brain.l7.verify
    monkeypatch.setattr(brain.l7, "verify", lambda *a, **k: {**orig(*a, **k), "passes_verification": False})
    brain.run_cognitive_cycle(q)
    assert fake.calls == calls_at_graduation, "teacher was called after the domain graduated"
    # that failure drops recent competence to 4/5 = 0.8 < 0.85: the domain loses graduation and the
    # teacher is consulted again (graduation is earned continuously, not granted forever)
    assert not brain.l8.is_domain_graduated(status["domain_id"])
    brain.run_cognitive_cycle(q)
    assert fake.calls == calls_at_graduation + 1
    monkeypatch.setattr(brain.l7, "verify", orig)

    # competence is re-earned with verified local answers, and graduation survives a restart
    for _ in range(6):
        status = brain.run_cognitive_cycle(q)["autonomy_status"]
    assert status["domain_graduated_off_api"]
    again = make_brain(tmp_path, teacher_provider="anthropic", min_runs_before_graduation=5)
    assert again.l8.is_domain_graduated(status["domain_id"])


# ─────────────────────────────────────────────────────────────── 5. universal renderer
class _Checker(HTMLParser):
    VOID = {"meta", "br", "img", "input", "link", "hr"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.tags = [], [], set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced </{tag}>")
        else:
            self.stack.pop()


def check_render(path: Path) -> dict:
    doc = path.read_text(encoding="utf-8")
    assert doc.startswith("<!DOCTYPE html>")
    chk = _Checker()
    chk.feed(doc)
    assert not chk.errors and not chk.stack, (chk.errors, chk.stack)
    assert {"canvas", "script", "title"} <= chk.tags
    for mode in ("setMode('2d')", "setMode('3d')", "setMode('hologram')"):
        assert mode in doc
    scene = json.loads(re.search(r"const scene = (\{.*?\});\n", doc, re.S).group(1))
    assert scene["nodes"] and "entropy_energy" in scene
    return scene


def test_renderer_outputs_valid_html_for_every_input_type(tmp_path):
    r = HojaigaUniversalRenderer()
    workflow = {"name": "Order fulfilment", "steps": ["receive order", "pick items", "pack", "ship"],
                "owner": "warehouse"}
    s_json = check_render(r.render_to_html(workflow, tmp_path / "json.html"))
    assert len(s_json["nodes"]) == 3
    s_text = check_render(r.render_to_html("Sperm moves from the testes -> epididymis -> vas deferens -> urethra.",
                                           tmp_path / "text.html",
                                           triples=[("testes", "to", "epididymis"), ("epididymis", "to", "vas deferens")]))
    assert {n["label"] for n in s_text["nodes"]} >= {"testes", "epididymis", "vas deferens"}
    s_img = check_render(r.render_to_html(synthetic_ui(), tmp_path / "image.html"))
    assert len(s_img["nodes"]) == 8 and all("x_norm" in n for n in s_img["nodes"])
    frames = np.stack([synthetic_ui()] * 4)
    check_render(r.render_to_html(frames, tmp_path / "video.html"))
    meta = {"clip": "screen_recording.mp4", "frames": 240, "fps": 30, "motion": 0.034}
    check_render(r.render_to_html(meta, tmp_path / "video_meta.html"))
    check_render(r.render_to_html('{"a": "b", "c": "d"}', tmp_path / "json_string.html"))
    assert "<script>alert(1)</script>" not in (r.render_to_html(
        {"title": "<script>alert(1)</script>"}, tmp_path / "xss.html")).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────── persistence, training, CLI
def test_learning_survives_restart(fed_brain):
    fed_brain.run_cognitive_cycle("What appeared at Mira's door?", user_correction="A glowing fox appeared.")
    n_fail, n_tokens = len(fed_brain.l8.failure_memory), len(fed_brain.tokenizer.token_to_id)
    again = HojaigaExecutiveBrain(fed_brain.cfg)
    assert len(again.l8.failure_memory) == n_fail and n_fail > 0
    assert len(again.tokenizer.token_to_id) == n_tokens > 264
    assert again.l1.total_docs == fed_brain.l1.total_docs
    assert again.l6.learned_span_edits == fed_brain.l6.learned_span_edits


def test_overnight_training_creates_a_checkpoint_the_brain_loads(tmp_path):
    """PyTorch engine → .pt checkpoint; zero-dependency NumPy engine → .npz + continuations."""
    book = tmp_path / "book.md"
    book.write_text(TEXTBOOK, encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    from brain_cli import run_overnight_consolidation
    brain = make_brain(tmp_path)
    brain.feed_dataset(book)
    stats = run_overnight_consolidation(brain, epochs=1)
    assert stats["trained_samples"] > 0 and stats["final_loss"] > 0
    ck = brain.cfg.workspace_dir / "checkpoints"
    assert (ck / ("hojaiga_tiny_5m.pt" if HAS_TORCH else "hojaiga_tiny_5m_numpy.npz")).exists()
    reloaded = make_brain(tmp_path)
    assert reloaded.llm_trained
    r = reloaded.run_cognitive_cycle("What is a fertilized egg called?")
    assert "zygote" in r["answer"]                 # symbolic layers still guard the answer


def test_cli_ingest_ask_render(tmp_path):
    book = tmp_path / "book.md"
    book.write_text(TEXTBOOK, encoding="utf-8")
    ws = tmp_path / "cli_ws"
    base = [sys.executable, str(ROOT / "brain_cli.py"), "--workspace", str(ws), "--variant", "tiny_5m"]
    import os
    env = {"PYTHONPATH": os.pathsep.join(filter(None, [os.environ.get("PYTHONPATH", ""), str(ROOT)])),
           "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)}
    out = subprocess.run(base + ["ingest", str(book)], capture_output=True, text=True, env=env, cwd=ROOT, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    out = subprocess.run(base + ["ask", "What is a fertilized egg called?"], capture_output=True, text=True,
                         env=env, cwd=ROOT, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "zygote" in json.loads(out.stdout)["answer"]
    html_out = tmp_path / "r.html"
    out = subprocess.run(base + ["render", str(book), "--out", str(html_out)], capture_output=True, text=True,
                         env=env, cwd=ROOT, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    check_render(html_out)
