"""
Verification suite for blueprint v2 (run: python -m pytest tests -v).

1. Feeding text, structured workflow JSON, an unseen UI image (run 1 not recognized, run 2
   recognized from memory), a video array and a multimodal stream through
   DynamicHubDatasetStreamer works end to end — including the real `datasets` code path.
2. Contrastive writing edits are learned from fed <draft, polished> records; nothing is
   pre-loaded and the source holds no static word lists or replacement dictionaries.
3. run_overnight_consolidation updates model weights and consolidates Orthogonal-LoRA.
4. HojaigaUniversalRenderer writes a valid 2D/3D/Hologram HTML file.
"""
import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.config import BrainSystemConfig, LLMConfig  # noqa: E402
from brain.curiosity_and_langchain import HojaigaExecutiveBrain  # noqa: E402
from brain.dataset_hub_loader import DynamicHubDatasetStreamer  # noqa: E402
from brain.tokenizer_and_llm import HAS_TORCH  # noqa: E402
from brain.universal_renderer import HojaigaUniversalRenderer  # noqa: E402
from brain_cli import run_overnight_consolidation  # noqa: E402


def make_brain(ws: Path) -> HojaigaExecutiveBrain:
    return HojaigaExecutiveBrain(BrainSystemConfig(workspace_dir=ws, llm=LLMConfig.from_variant("tiny_5m"),
                                                   teacher_provider="none"))


def ui_screenshot(variant: int = 0) -> np.ndarray:
    """An app window nobody has shown the brain before (variant changes the layout)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (800, 500), (250, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 800, 44], fill=(20 + variant * 90, 30, 60))
    for i in range(6):
        d.rectangle([20, 70 + i * 60, 180 - variant * 40, 110 + i * 60], fill=(70, 120, 220))
    d.rectangle([220, 70, 760, 120], outline=(10, 10, 10), width=3)
    for i in range(5):
        d.rectangle([220, 150 + i * 50, 700 - variant * 200, 180 + i * 50], fill=(190, 190, 200))
    d.ellipse([680, 420, 760, 480], fill=(20, 170, 90))
    return np.array(img)


def video_clip(frames: int = 12) -> np.ndarray:
    clip = np.full((frames, 120, 160, 3), 15, dtype=np.uint8)
    for t in range(frames):
        clip[t, 50:70, 5 + t * 12: 25 + t * 12] = (255, 210, 0)
    return clip


# ─────────────────────────────────────────────────────────────── 1. every modality end to end
def test_text_workflow_ui_video_end_to_end(tmp_path):
    ws = tmp_path / "ws"
    brain = make_brain(ws)

    text = ("Photovoltaic panels convert sunlight into direct current electricity.\n\n"
            "An inverter converts direct current into alternating current for household appliances.")
    r_text = brain.feed_dataset(text, hint="solar_notes")
    assert r_text["modality"] == "text" and r_text["episodes_added"] == 2

    workflow = {"process": "Customer order fulfilment",
                "steps": ["receive order", "check stock", "pick items", "pack parcel", "ship parcel"]}
    r_wf = brain.feed_dataset(workflow, hint="warehouse")
    assert r_wf["modality"] == "workflow"
    edges = {(s, o) for s, rels in brain.l2.concept_triples.items() for _, o, _ in rels}
    assert ("pick items", "pack parcel") in edges, "workflow transitions were not extracted"

    first = brain.feed_dataset(ui_screenshot(), hint="unseen_app")
    assert first["recognized_from_memory"] is False and first["interfaces_learned"] == 1
    assert first["epistemic_surprise"] > 0.5
    later = make_brain(ws).feed_dataset(ui_screenshot(), hint="unseen_app")      # a new process / run
    assert later["recognized_from_memory"] is True and later["interfaces_learned"] == 0
    assert later["interface_id"] == first["interface_id"] and later["epistemic_surprise"] < 0.1

    r_vid = brain.feed_dataset(video_clip(), hint="screen_recording")
    assert r_vid["modality"] == "video" and r_vid["episodes_added"] == 1 and r_vid["mean_motion"] > 0

    ans = make_brain(ws).run_cognitive_cycle("What does an inverter convert direct current into?")
    assert "alternating current" in ans["answer"]
    assert "inverter" in ans["answer"].lower()


class _Pil:
    @staticmethod
    def img(color):
        from PIL import Image
        return Image.new("RGB", (64, 48), color)


def multimodal_rows():
    long_passage = ("Mitochondria are organelles that release energy from glucose through cellular respiration. "
                    "They have an inner membrane folded into cristae, which increases the surface area for the "
                    "enzymes of the electron transport chain. Cells that need a lot of energy, such as muscle "
                    "cells, contain many mitochondria.")
    return [
        {"image": _Pil.img((200, 30, 30)), "instruction": "Click the red record button", "bbox": [4, 4, 60, 44]},
        {"messages": [{"role": "user", "content": "What is the capital of Kenya?"},
                      {"role": "assistant", "content": "Nairobi is the capital of Kenya."}]},
        {"question": "Which river flows through Cairo?",
         "context": [{"title": "Cairo", "text": "The Nile flows through Cairo, the capital of Egypt."},
                     {"title": "Paris", "text": "The Seine flows through Paris."}]},
        {"id": 7, "url": "https://example.org/bio", "text": long_passage, "score": np.float32(0.93)},
        {"draft": "In today's fast-paced world, it is important to note that teamwork matters a lot.",
         "polished": "Teamwork matters a lot."},
        {"clip": video_clip(8), "label": "loading spinner animation"},
    ]


def test_multimodal_stream_through_hub_streamer(tmp_path):
    brain = make_brain(tmp_path / "ws")
    stats = DynamicHubDatasetStreamer(brain).ingest_iterable_stream(iter(multimodal_rows()), "fake_hub", max_samples=50)
    assert stats["rows_streamed"] == 6
    assert stats["visual_episodes"] == 1 and stats["video_episodes"] == 1
    assert stats["text_or_workflow_episodes"] >= 4
    assert stats["emergent_domains_discovered"]
    assert brain.l6.learned_span_edits, "draft/polished row taught no edits"
    # long passages are stored as readable prose, not one escaped JSON blob
    prose = [ep for ep in brain.l2.episodes.values() if "cristae" in ep.content]
    assert prose and all(not ep.content.lstrip().startswith("{") for ep in prose)
    fresh = make_brain(tmp_path / "ws")          # everything was persisted once, at the end of the batch
    assert "Nairobi" in fresh.run_cognitive_cycle("What is the capital of Kenya?")["answer"]
    assert "Nile" in fresh.run_cognitive_cycle("Which river flows through Cairo?")["answer"]


def test_import_from_huggingface_code_path(tmp_path, monkeypatch):
    """The real `datasets` IterableDataset (with an Image feature) through import_from_huggingface.
    Only the network download is replaced: the Hub is unreachable from the test sandbox."""
    datasets = pytest.importorskip("datasets")
    rows = [{"image": _Pil.img((30, 30 + i * 40, 200)), "instruction": f"Open settings panel number {i}"}
            for i in range(5)]
    feats = datasets.Features({"image": datasets.Image(), "instruction": datasets.Value("string")})
    ids = datasets.IterableDataset.from_generator(lambda: iter(rows), features=feats)
    seen = {}

    def fake_load_dataset(repo_id, name=None, split="train", streaming=True):
        seen.update(repo_id=repo_id, name=name, split=split, streaming=streaming)
        return ids
    monkeypatch.setattr(datasets, "load_dataset", fake_load_dataset)
    brain = make_brain(tmp_path / "ws")
    stats = DynamicHubDatasetStreamer(brain).import_from_huggingface("Voxel51/WaveUI-25k", max_samples=4)
    assert seen == {"repo_id": "Voxel51/WaveUI-25k", "name": None, "split": "train", "streaming": True}
    assert stats["source"] == "hf://Voxel51/WaveUI-25k" and stats["rows_streamed"] == 4
    assert stats["visual_episodes"] == 4 and stats["text_or_workflow_episodes"] == 4


# ─────────────────────────────────────────────────────────────── 2. learned writing edits
def test_writing_edits_are_learned_from_fed_pairs(tmp_path):
    brain = make_brain(tmp_path / "ws")
    assert brain.l6.learned_span_edits == {}, "edits must not be pre-loaded"
    pairs = tmp_path / "edits.jsonl"
    pairs.write_text("\n".join(json.dumps(r) for r in [
        {"draft": "We will leverage our synergies to move the needle on revenue this quarter.",
         "polished": "We will work together to grow revenue this quarter."},
        {"draft": "Please kindly revert back to me at your earliest convenience regarding the invoice.",
         "polished": "Please reply to me soon regarding the invoice."},
    ]), encoding="utf-8")
    brain.feed_dataset(pairs)
    learned = brain.l6.learned_span_edits
    assert any("leverage" in k for k in learned) and any("revert back" in k for k in learned), learned
    polished, trace = make_brain(tmp_path / "ws").l6.polish_writing_dynamically(
        "Could you kindly revert back to me at your earliest convenience about the leverage our synergies plan?")
    assert "revert back" not in polished and "reply" in polished and trace


def test_source_has_no_static_word_lists_or_replacement_dicts():
    """Zero-hardcoding check over every brain module: no literal list/set/tuple of ≥10 words and
    no literal dict of ≥6 word→word replacements."""
    offenders = []
    for py in sorted((ROOT / "brain").glob("*.py")):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
                words = [e for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                         and re.fullmatch(r"[A-Za-z][A-Za-z' -]*", e.value)]
                if len(words) >= 10:
                    offenders.append(f"{py.name}:{node.lineno} list of {len(words)} words")
            if isinstance(node, ast.Dict):
                pairs = [1 for k, v in zip(node.keys, node.values)
                         if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                         and isinstance(k.value, str) and isinstance(v.value, str)]
                if len(pairs) >= 6:
                    offenders.append(f"{py.name}:{node.lineno} dict of {len(pairs)} string replacements")
    assert not offenders, offenders


# ─────────────────────────────────────────────────────────────── 3. overnight consolidation
def test_overnight_updates_weights_and_consolidates_olora(tmp_path):
    brain = make_brain(tmp_path / "ws")
    brain.feed_dataset("Rivers carry water to the sea. Rain refills rivers in spring.\n\n"
                       "Deltas form where rivers slow down and drop sediment near the coast.", hint="rivers")
    if HAS_TORCH:
        import torch
        from brain.tokenizer_and_llm import OrthogonalLoRALinear
        lora = [m for m in brain.llm.modules() if isinstance(m, OrthogonalLoRALinear)]
        assert lora
        before_base = [m.base.weight.detach().clone() for m in lora]
        before_ffn = brain.llm.layers[0].ffn.w1.weight.detach().clone()
        assert all(float(m.consolidated_subspace.abs().sum()) == 0.0 for m in lora)
    else:
        before_value = brain.llm.value_w.copy()
        before_lora_b = brain.llm.lora_B.copy()

    stats = run_overnight_consolidation(brain, epochs=2)
    assert stats["trained_samples"] > 0 and stats["final_loss"] > 0
    ck = brain.cfg.workspace_dir / "checkpoints"
    if HAS_TORCH:
        assert not torch.equal(before_ffn, brain.llm.layers[0].ffn.w1.weight)          # weights trained
        assert any(not torch.equal(b, m.base.weight) for b, m in zip(before_base, lora))  # adapters merged
        assert all(float(m.lora_B.abs().sum()) == 0.0 for m in lora)                     # adapters reset
        assert all(float(m.consolidated_subspace.abs().sum()) > 0.0 for m in lora)       # subspace protected
        assert (ck / "hojaiga_tiny_5m.pt").exists()
    else:
        assert not np.array_equal(before_value, brain.llm.value_w)
        assert not np.array_equal(before_lora_b, brain.llm.lora_B)
        assert (ck / "hojaiga_tiny_5m_numpy.npz").exists()
    assert make_brain(tmp_path / "ws").llm_trained


# ─────────────────────────────────────────────────────────────── 4. renderer
class _Html(HTMLParser):
    VOID = {"meta", "br", "img", "input", "link", "hr"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad, self.tags = [], [], set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.bad.append(tag)


@pytest.mark.parametrize("payload", [
    "Sunlight -> photovoltaic panel -> inverter -> home appliances",
    {"process": "order fulfilment", "steps": ["receive", "pick", "pack", "ship"]},
    "IMAGE",
    "VIDEO",
])
def test_renderer_writes_valid_2d_3d_hologram_html(tmp_path, payload):
    if payload == "IMAGE":
        payload = ui_screenshot()
    elif payload == "VIDEO":
        payload = video_clip()
    out = HojaigaUniversalRenderer().render_to_html(payload, tmp_path / "view.html")
    doc = out.read_text(encoding="utf-8")
    p = _Html()
    p.feed(doc)
    assert doc.startswith("<!DOCTYPE html>") and not p.bad and not p.stack
    assert {"canvas", "script", "button"} <= p.tags
    for mode in ("'2d'", "'3d'", "'hologram'"):
        assert f"setMode({mode})" in doc
    scene = json.loads(re.search(r"const scene = (\{.*?\});\n", doc, re.S).group(1))
    assert len(scene["nodes"]) >= 2 and 0 < scene["entropy_energy"] <= 1
