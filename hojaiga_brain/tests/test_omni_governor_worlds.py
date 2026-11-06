"""
Multimodal network from zero, audio, the AI-model governor, parallel worlds and the belt's
model zoo + charts (python -m pytest tests -v).
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.config import BrainSystemConfig, LLMConfig  # noqa: E402
from brain.controller import NaturalIntelligenceController  # noqa: E402
from brain.curiosity_and_langchain import HojaigaExecutiveBrain  # noqa: E402
from brain.governor import ModelGovernor  # noqa: E402
from brain.omni.audio import load_audio, log_mel, mfcc_features, write_wav  # noqa: E402
from brain.parallel_worlds import ParallelWorlds, World  # noqa: E402
from brain.tokenizer_and_llm import HAS_TORCH  # noqa: E402


def make_brain(ws: Path) -> HojaigaExecutiveBrain:
    return HojaigaExecutiveBrain(BrainSystemConfig(workspace_dir=ws, llm=LLMConfig.from_variant("tiny_5m"),
                                                   teacher_provider="none"))


def tone(freq: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(16000 * seconds)) / 16000
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# ─────────────────────────────────────────────────────────────── audio
def test_audio_pipeline(tmp_path):
    write_wav(str(tmp_path / "a.wav"), tone(440))
    x = load_audio(str(tmp_path / "a.wav"))
    assert x is not None and abs(len(x) - 16000) < 10 and abs(float(np.abs(x).max()) - 0.4) < 0.01
    lm = log_mel(x)
    assert lm.shape[0] == 64 and lm.shape[1] > 90
    peak_hz = np.argmax(np.abs(np.fft.rfft(x))) * 16000 / len(x)
    assert abs(peak_hz - 440) < 2
    assert not np.allclose(mfcc_features(x), mfcc_features(tone(2000)))


# ─────────────────────────────────────────────────────────────── multimodal network from zero
def omni_dataset(root: Path) -> Path:
    from PIL import Image, ImageDraw
    rnd = random.Random(1)
    root.mkdir(parents=True)
    cols = {"red": (220, 40, 40), "blue": (40, 70, 220), "green": (40, 170, 70)}
    for i in range(30):
        cn, sh = rnd.choice(list(cols)), rnd.choice(["circle", "square"])
        im = Image.new("RGB", (96, 96), "white")
        o = rnd.randint(10, 22)
        d = ImageDraw.Draw(im)
        (d.ellipse if sh == "circle" else d.rectangle)([o, o, 96 - o, 96 - o], fill=cols[cn])
        im.save(root / f"img_{i}.png")
        (root / f"img_{i}.txt").write_text(f"a {cn} {sh} on a white background")
    (root / "sounds").mkdir()
    for i in range(12):
        f = [220, 880][i % 2]
        write_wav(str(root / "sounds" / f"t{i}.wav"), tone(f * (1 + 0.02 * rnd.random()), 2.0))
        (root / "sounds" / f"t{i}.txt").write_text(f"a {'low' if f == 220 else 'high'} pitched tone")
    (root / "notes.md").write_text("An inverter converts direct current into alternating current.\n")
    return root


@pytest.mark.skipif(not HAS_TORCH, reason="the multimodal network needs PyTorch")
def test_omni_trains_from_zero_and_understands_unseen_media(tmp_path):
    from PIL import Image, ImageDraw
    from brain.omni.trainer import OmniTrainer
    data = omni_dataset(tmp_path / "data")
    brain = make_brain(tmp_path / "ws")
    assert not (tmp_path / "ws" / "omni" / "omni.pt").exists()            # starts empty
    tr = OmniTrainer(brain, size="tiny")
    rep = tr.train([str(data)], epochs=60, batch=8, lr=1e-3, max_minutes=4)
    assert rep["data"]["by_kind"]["image+text"] == 30 and rep["data"]["by_kind"]["audio+text"] == 12
    assert {"caption", "contrastive", "jepa"} <= set(rep["val_loss"]) and Path(rep["chart"]).exists()

    im = Image.new("RGB", (96, 96), "white")
    ImageDraw.Draw(im).ellipse([15, 15, 81, 81], fill=(40, 70, 220))
    im.save(tmp_path / "unseen.png")
    write_wav(str(tmp_path / "unseen_high.wav"), tone(870, 2.0))
    write_wav(str(tmp_path / "unseen_low.wav"), tone(225, 2.0))
    again = OmniTrainer(brain)                                           # reload from checkpoint
    assert again.step == tr.step
    assert again.describe(str(tmp_path / "unseen.png")) == "a blue circle on a white background"
    assert again.describe(str(tmp_path / "unseen_high.wav")) == "a high pitched tone"
    ranked = again.search("a low pitched tone", [str(tmp_path / "unseen_high.wav"), str(tmp_path / "unseen_low.wav")])
    assert ranked[0][0].endswith("unseen_low.wav")
    more = again.train([str(data)], epochs=1, batch=8)                   # resume continues the step count
    assert more["total_steps"] > tr.step


# ─────────────────────────────────────────────────────────────── AI model governor
def test_governor_learns_explores_and_retires(tmp_path):
    db = tmp_path / "sw.sqlite"
    gov = ModelGovernor(db, retire_after=10, retire_below=0.3, seed=0)
    for name, cost in (("strong", 0.0), ("weak", 0.0), ("pricey", 1.0)):
        gov.register(name, ["answer"], lambda q, n=name: n, cost=cost)
    for _ in range(12):
        gov.record("answer:billing", "strong", 1.0)
        gov.record("answer:billing", "weak", 0.0)
        gov.record("answer:billing", "pricey", 1.0)
    ranked = gov.rank("answer", "answer:billing", explore=False, include_retired=True)
    assert ranked[0]["model"] == "strong"                       # same success as 'pricey' but free
    assert gov.belief("answer:billing", "weak")["retired"]      # clearly bad → retired
    assert "weak" not in [r["model"] for r in gov.rank("answer", "answer:billing")]
    gov.register("newcomer", ["answer"], lambda q: "new")       # unseen model: Thompson sampling explores it
    picks = {gov.choose("answer", "answer:billing", explore=True).name for _ in range(60)}
    assert "newcomer" in picks
    gov.revive("answer:billing", "weak")
    assert not gov.belief("answer:billing", "weak")["retired"]
    assert ModelGovernor(db).belief("answer:billing", "strong")["uses"] == 12   # the switchboard persists


# ─────────────────────────────────────────────────────────────── parallel worlds
def test_parallel_worlds_choose_best_and_learn_from_all(tmp_path):
    gov = ModelGovernor(tmp_path / "sw.sqlite")
    worlds = [World("careful", lambda: "Paris is the capital of France.", lambda o: 0.9),
              World("sloppy", lambda: "Lyon is the capital of France.", lambda o: 0.3),
              World("broken", lambda: 1 / 0, lambda o: 1.0)]
    emb = make_brain(tmp_path / "ws").l2.compute_embedding
    res = ParallelWorlds(gov, embed=emb).explore("answer:geo", worlds)
    assert res["chosen"] == "careful" and res["outcome"].startswith("Paris")
    by = {w["world"]: w for w in res["worlds"]}
    assert by["broken"]["error"].startswith("ZeroDivisionError") and by["broken"]["eu"] == -1.0
    assert 0 < by["careful"]["agreement"] <= 1
    assert gov.belief("answer:geo", "careful")["alpha"] == 1.9          # chosen: full weight (1 + 0.9)
    assert gov.belief("answer:geo", "sloppy")["alpha"] == pytest.approx(1.15)   # imagined: half weight


def test_inner_brain_controller_opens_worlds_and_governs_models(tmp_path):
    ctrl = NaturalIntelligenceController(make_brain(tmp_path / "ws"))
    ctrl.brain.feed_dataset("Refunds are returned to the original payment method within five business days.")
    ctrl.register_model("oracle", ["answer"], lambda q: "Refunds are returned to the original payment method "
                                                         "within five business days.", kind="external")
    ctrl.register_model("liar", ["answer"], lambda q: "Bananas grow on the moon during winter.", kind="external")
    out = ctrl.handle({"skill": "answer", "text": "How are refunds returned?"})["result"]
    names = {w["world"] for w in out["worlds"]}
    assert "hojaiga-main-brain" in names and len(names) == 3
    assert "five business days" in out["answer"] and out["answered_by"] != "liar"
    worlds = {w["world"]: w for w in out["worlds"]}
    if "liar" in worlds:
        assert worlds["liar"]["evidence"] < worlds["hojaiga-main-brain"]["evidence"]
    # the same question again: the inner brain answers alone (fast path, no worlds)
    again = ctrl.handle({"skill": "answer", "text": "How are refunds returned?"})["result"]
    assert again["answered_by"] == "inner_brain" and "worlds" not in again
    report = ctrl.handle({"skill": "models", "text": "report"})["result"]
    assert {"hojaiga-main-brain", "oracle", "liar"} <= set(report["models"]) and report["switchboard"]


# ─────────────────────────────────────────────────────────────── belt: audio, model zoo, charts
def test_belt_audio_model_zoo_and_charts(tmp_path):
    from brain.conveyor import ml_stations as ml
    from brain.conveyor.belt import ConveyorBelt
    rng = np.random.default_rng(0)
    for kind in ("hum", "beep", "noise"):
        d = tmp_path / "data" / "audio" / kind
        d.mkdir(parents=True)
        for i in range(8):
            t = np.arange(16000) / 16000
            x = {"hum": 0.3 * np.sin(2 * np.pi * (100 + rng.integers(0, 30)) * t),
                 "beep": 0.3 * np.sin(2 * np.pi * (1500 + rng.integers(0, 300)) * t) * (t % 0.2 < 0.1),
                 "noise": 0.2 * rng.standard_normal(len(t))}[kind]
            write_wav(str(d / f"{kind}_{i}.wav"), x)
    (tmp_path / "data" / "tickets.jsonl").write_text("\n".join(json.dumps(
        {"message": f"{['refund my payment', 'app crashes on start', 'parcel is late'][i % 3]} case {i}",
         "team": ["billing", "tech", "shipping"][i % 3]}) for i in range(30)))
    rep = ConveyorBelt(make_brain(tmp_path / "ws")).run([str(tmp_path / "data")])
    assert not rep.get("errors"), rep.get("errors")
    ac = rep["classical_ml"]["audio_classification"]
    assert ac["best_model"] and ac[ac["best_model"]]["accuracy"] >= 0.9
    tc = rep["classical_ml"]["text_classification"]
    assert tc["label_field"] == "team" and tc[tc["best_model"]]["accuracy"] >= 0.9
    if ml.HAS_SKLEARN:
        assert {"random_forest", "linear_svm"} <= set(tc)
    assert rep["deep_learning"]["mlp_audio"]["accuracy"] >= 0.8
    charts = rep["charts"]
    assert any(c.endswith("_models.png") for c in charts) and all(Path(c).exists() for c in charts)


def test_cli_init_creates_an_empty_brain(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "brain_cli.py"), "--workspace", str(tmp_path / "ws"),
                          "--variant", "tiny_5m", "init"], capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert out.returncode == 0, out.stderr[-1500:]
    info = json.loads(out.stdout)
    assert info["episodes"] == 0 and info["vocab"] == 264
    assert all((tmp_path / "ws" / d.rstrip("/")).is_dir() for d in info["layout"])
