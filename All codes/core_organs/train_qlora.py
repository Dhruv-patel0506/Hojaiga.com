"""
train_qlora -- Checkpoint 4: QLoRA fine-tuning of a Qwen3-VL model on the grounded Set-of-Marks pairs that harvest.video_explain produces.

    python -m core_organs.train_qlora preflight [--model M] [--seq N] [--rank R] [--backend unsloth|hf]   will it fit THIS GPU? (numbers, not hope)
    python -m core_organs.train_qlora prepare   [--jsonl P] [--all-pairs]                                  validate pairs, split train/eval BY VIDEO, write the run's train.jsonl / eval.jsonl
    python -m core_organs.train_qlora train     [--model M] [--steps N] [--min-examples K] [--force]       preflight -> prepare -> train -> adapter + run_summary.json
    python -m core_organs.train_qlora export    [--run DIR]                                                 print / run the merge -> GGUF -> llama-server steps (needs LLAMA_CPP_DIR)

WHAT IS VERIFIED vs NOT (2026-10-17): the VRAM model, dataset validation/splitting, label masking, LoRA targeting and a CPU training loop are tested on a TINY RANDOM Qwen3-VL built from config
(si_tests_train.py). Training a REAL model has not been run: no trainable weights are on disk (only inference GGUFs), Unsloth is not installed, and Qwen3-VL-8B does not fit this GPU (see preflight).

Backends: 'unsloth' when importable (lower VRAM: fused kernels, chunked cross-entropy, offloaded checkpoints), otherwise 'hf' (transformers + peft + bitsandbytes, all installed). Same data, same config.
The brief's settings are the defaults: 4-bit, r=16 / alpha=16, batch 1 x accumulation 8, paged_adamw_8bit, gradient checkpointing, max_seq_length 2048 (see preflight for what a 6 GB card allows).
"""
from __future__ import annotations

import argparse
import json
import re
import math
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

GIB = 2 ** 30


# ---- what a model costs ------------------------------------------------------------------------------------------------------------------------------
@dataclass
class ModelSpec:
    name: str
    hidden: int
    layers: int
    ffn: int
    heads: int
    kv_heads: int
    head_dim: int
    vocab: int
    tied: bool                      # lm_head shares the embedding matrix
    vision_params: float            # parameters of the vision tower (kept in 16-bit under QLoRA)
    source: str                     # where these numbers come from

    @property
    def layer_params(self) -> float:
        attn = self.hidden * self.heads * self.head_dim + 2 * self.hidden * self.kv_heads * self.head_dim + self.heads * self.head_dim * self.hidden
        return self.layers * (attn + 3 * self.hidden * self.ffn)

    @property
    def embed_params(self) -> float:
        return self.vocab * self.hidden * (1 if self.tied else 2)

    @property
    def total_params(self) -> float:
        return self.layer_params + self.embed_params + self.vision_params


MODEL_SPECS: Dict[str, ModelSpec] = {
    # MEASURED: read from the header of D:/new_automation/models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf (block_count 36, embedding_length 4096, feed_forward_length 12288, head_count 32/8, vocab 151936)
    "8b": ModelSpec("Qwen3-VL-8B-Instruct", 4096, 36, 12288, 32, 8, 128, 151936, False, 0.45e9, "measured from the local GGUF header; vision tower size estimated"),
    # NOT measured locally (no weights on disk): the published model configs, to be re-checked the moment a config.json is downloaded
    "4b": ModelSpec("Qwen3-VL-4B-Instruct", 2560, 36, 9728, 32, 8, 128, 151936, True, 0.40e9, "published config, unverified locally"),
    "2b": ModelSpec("Qwen3-VL-2B-Instruct", 2048, 28, 6144, 16, 8, 128, 151936, True, 0.40e9, "MEASURED: matches the downloaded config.json (28 layers, hidden 2048, ffn 6144, 16/8 heads, vocab 151936, tied embeddings); vision tower size estimated"),
}
HF_NAMES = {"8b": "Qwen/Qwen3-VL-8B-Instruct", "4b": "Qwen/Qwen3-VL-4B-Instruct", "2b": "Qwen/Qwen3-VL-2B-Instruct"}
UNSLOTH_NAMES = {"8b": "unsloth/Qwen3-VL-8B-Instruct-unsloth-bnb-4bit", "4b": "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "2b": "unsloth/Qwen3-VL-2B-Instruct-unsloth-bnb-4bit"}


def spec_for(model: str) -> ModelSpec:
    low = model.lower()
    for k in ("8b", "4b", "2b"):
        if k in low:
            return MODEL_SPECS[k]
    raise ValueError(f"no size spec for {model!r}: pass a name containing 8b / 4b / 2b, or add a ModelSpec")


@dataclass
class TrainConfig:
    model: str = "unsloth/Qwen3-VL-8B-Instruct"            # the brief's choice; preflight refuses it on a 6 GB card unless --force
    backend: str = "auto"                                  # auto | unsloth | hf
    max_seq_length: int = 2048
    lora_r: int = 16
    lora_alpha: int = 16
    lora_dropout: float = 0.0
    finetune_vision: bool = False                          # vision-tower LoRA costs memory; the SoM task is mostly language-side grounding. Flip on only with headroom.
    per_device_batch: int = 1
    grad_accum: int = 8
    lr: float = 2e-4
    warmup_steps: int = 10
    max_steps: int = 300
    optim: str = "paged_adamw_8bit"
    max_pixels: int = 448 * 448                            # images are resized to at most this many pixels (-> about max_pixels/1024 visual tokens at 32 px per token)
    seed: int = 3407
    grounded_only: bool = True
    require_ui_gate: bool = True                           # pairs whose frames were not verified as a software UI (meta.ui_frames) are rejected
    eval_frac: float = 0.1
    min_examples: int = 200
    quantize_embeddings: bool = False
    slice_logits: bool = True                              # plain-transformers path: compute logits/loss only over the answer positions (the prompt is masked anyway)
    answer_tokens: int = 160                               # upper bound on the assistant's answer length (the JSON action list)
    out_dir: str = ""
    name: str = ""


@dataclass
class Estimate:
    parts: Dict[str, float]
    total_gib: float
    free_gib: float
    total_gpu_gib: float
    fits: bool
    margin_gib: float
    seq_used: int
    notes: List[str] = field(default_factory=list)


STRIP_PIXELS = int(os.environ.get("HOJAIGA_STRIP_PIXELS", "0"))          # 0 = strips use the same cap as the main picture (the adapters trained so far); set 65536 (512*128) for the next training pass: a zoomed toolbar strip is wide and thin: it is capped at this many pixels (about 64 visual tokens) so a row with several strips fits the 2048-token / 4.5 GB budget


def image_tokens_for(width: int, height: int, max_pixels: int, px_per_token: int = 32) -> int:
    """Visual tokens for an image after it is shrunk to <= max_pixels (aspect kept, sides rounded to the 32-px token grid). Qwen3-VL: 16-px patches merged 2x2 = one token per 32x32 pixels."""
    scale = min(1.0, math.sqrt(max_pixels / max(1, width * height)))
    w = max(px_per_token, round(width * scale / px_per_token) * px_per_token)
    h = max(px_per_token, round(height * scale / px_per_token) * px_per_token)
    return (w // px_per_token) * (h // px_per_token)


def estimate_vram(cfg: TrainConfig, spec: Optional[ModelSpec] = None, backend: str = "hf", free_gib: float = 0.0, total_gib: float = 0.0, seq: Optional[int] = None) -> Estimate:
    """Peak VRAM of QLoRA training, by component. An ESTIMATE (the components are exact arithmetic on the architecture; activations are modelled), meant to say 'impossible' or 'tight' reliably."""
    spec = spec or spec_for(cfg.model)
    seq = seq or cfg.max_seq_length
    r = cfg.lora_r
    h, hd = spec.hidden, spec.head_dim
    per_layer_lora = r * ((h + spec.heads * hd) + 2 * (h + spec.kv_heads * hd) + (spec.heads * hd + h) + 2 * (h + spec.ffn) + (spec.ffn + h))
    lora_params = per_layer_lora * spec.layers
    parts = {
        "transformer_layers_nf4": spec.layer_params * 0.53 / GIB,                                    # 4 bits + double-quant constants
        "embeddings_and_head": spec.embed_params * (0.53 if cfg.quantize_embeddings else 2.0) / GIB,    # kept in bf16 unless quantised
        "vision_tower_bf16": spec.vision_params * 2.0 / GIB,
        "lora_weights_grads_optimizer": lora_params * (4 + 4 + 2) / GIB,                              # fp32 adapter + fp32 grad + 8-bit Adam states
        # gradient checkpointing keeps one hidden state per layer, plus the working set of the layer being recomputed
        "activations": (seq * h * 2 * spec.layers + seq * (4 * h + 2 * spec.ffn) * 2 * 3) * cfg.per_device_batch / GIB,
        # logits: the full sequence x vocab. Unsloth computes the loss in chunks; plain transformers materialises bf16 logits + an fp32 upcast + the gradient
        "logits_and_loss": (seq if (backend != "unsloth" and not cfg.slice_logits) else (cfg.answer_tokens + 1 if backend != "unsloth" else seq)) * spec.vocab
        * (2.0 if backend == "unsloth" else 10.0) * cfg.per_device_batch / GIB,
        "cuda_context_and_fragmentation": 0.55,
    }
    total = sum(parts.values())
    notes = []
    if cfg.finetune_vision:
        parts["vision_lora"] = 0.05
        total += 0.05
    avail = free_gib * 0.92
    return Estimate({k: round(v, 3) for k, v in parts.items()}, round(total, 2), round(free_gib, 2), round(total_gib, 2), bool(free_gib) and total <= avail, round(avail - total, 2) if free_gib else 0.0, seq, notes)


def gpu_memory_gib() -> Tuple[float, float, str]:
    """(free, total, name) in GiB. torch.cuda.mem_get_info first: it is what an allocation will actually see (on Windows, nvidia-smi does not count the display's reservation and reports ~1 GiB
    more free than a training run can use). nvidia-smi as the fallback; (0, 0, '') when there is no usable GPU."""
    # in a CHILD process: initialising CUDA in the caller would leave a CUDA context in it, and on this stack (torch 2.7.1+cu118, transformers 5.19) a CPU Trainer run in a process that has
    # initialised CUDA segfaults (measured). A preflight must never change the caller's process.
    try:
        code = "import torch,json; f,t=torch.cuda.mem_get_info(); print(json.dumps([f/2**30, t/2**30, torch.cuda.get_device_name(0)]))"
        r = subprocess.run([sys.executable, "-I", "-W", "ignore", "-c", code], capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and r.stdout.strip():
            f, t, n = json.loads(r.stdout.strip().splitlines()[-1])
            return float(f), float(t), str(n)
    except Exception:
        pass
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        name, total, used = [x.strip() for x in out.split(",")]
        return (float(total) - float(used)) / 1024, float(total) / 1024, name
    except Exception:
        pass
    return 0.0, 0.0, ""


def preflight(cfg: TrainConfig, free_gib: Optional[float] = None, total_gib: Optional[float] = None, backend: str = "") -> Dict[str, Any]:
    """The verdict for cfg on this GPU, with every component, the alternatives that would fit, and what to change."""
    if free_gib is None:
        free_gib, tot, gpu = gpu_memory_gib()
        total_gib = tot
    else:
        gpu = "(given)"
        total_gib = total_gib or free_gib
    backend = backend or resolve_backend(cfg)
    spec = spec_for(cfg.model)
    est = estimate_vram(cfg, spec, backend, free_gib, total_gib)
    alts = []
    for key in ("8b", "4b", "2b"):
        for seq in (cfg.max_seq_length, 1536, 1024):
            c = TrainConfig(**{**asdict(cfg), "model": HF_NAMES[key], "max_seq_length": seq})
            e = estimate_vram(c, MODEL_SPECS[key], backend, free_gib, total_gib)
            if e.fits:
                alts.append({"model": HF_NAMES[key], "max_seq_length": seq, "estimated_gib": e.total_gib, "margin_gib": e.margin_gib, "spec_source": MODEL_SPECS[key].source})
                break
    advice = []
    if not free_gib:
        advice.append("no usable GPU found (nvidia-smi and torch.cuda both failed)")
    elif not est.fits:
        biggest = max(est.parts, key=lambda k: est.parts[k])
        advice.append(f"{spec.name} needs ~{est.total_gib} GiB; {est.free_gib} GiB is free ({round(est.total_gib - est.free_gib * 0.92, 2)} GiB short). Largest part: {biggest} = {est.parts[biggest]} GiB.")
        if alts:
            advice.append("what fits: " + "; ".join(f"{a['model']} @ seq {a['max_seq_length']} (~{a['estimated_gib']} GiB)" for a in alts))
        else:
            advice.append("nothing in the table fits this GPU; free VRAM (close other GPU programs) or train elsewhere")
        if backend != "unsloth":
            advice.append("Unsloth's chunked loss would remove most of the logits term (not installed here: `pip install unsloth` would repoint torch/transformers; ask before doing it)")
    return {"ok": bool(est.fits), "gpu": gpu, "free_gib": round(free_gib, 2), "total_gib": round(total_gib or 0, 2), "backend": backend, "model": cfg.model, "spec": asdict(spec),
            "params_b": round(spec.total_params / 1e9, 2), "estimate": asdict(est), "alternatives": alts, "advice": advice}


def resolve_backend(cfg: TrainConfig) -> str:
    if cfg.backend in ("unsloth", "hf"):
        return cfg.backend
    try:
        import importlib.util
        return "unsloth" if importlib.util.find_spec("unsloth") else "hf"
    except Exception:
        return "hf"


# ---- the data ------------------------------------------------------------------------------------------------------------------------------------------
def default_root() -> str:
    from core_organs.harvest.paths import harvest_dir
    return harvest_dir()[0]


def load_pairs(jsonl: str, grounded_only: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    rows, stats = [], {"read": 0, "bad_json": 0, "ungrounded_dropped": 0}
    if not os.path.isfile(jsonl):
        return rows, stats
    for line in open(jsonl, encoding="utf-8"):
        if not line.strip():
            continue
        stats["read"] += 1
        try:
            r = json.loads(line)
        except Exception:
            stats["bad_json"] += 1
            continue
        if grounded_only and not r.get("meta", {}).get("grounded"):
            stats["ungrounded_dropped"] += 1
            continue
        rows.append(r)
    return rows, stats


ACTION_JOBS = ("ground", "decide")                                       # jobs whose answer is ONE on-screen action from a numbered element list
ACTIONS = ("click", "hotkey", "type", "confirm", "replan", "ask", "done")
JSON_JOBS = {"plan": "steps", "judge": "items", "draw": "strokes", "point": "point", "route": "parts", "video": ""}   # answers that must be one JSON object (key it must hold)


def validate_job_pair(rec: Dict[str, Any], root: str) -> List[str]:
    """Checks for the jobs that are NOT one on-screen action (spec section 2: see, plan, judge, teach, video, draw, point, route, general): each keeps its OWN answer
    format. Oct-29: wrapping every answer as 'type it into element #1' so the action validator passed taught a model to answer everything as an action."""
    probs = []
    msgs = rec.get("messages") or []
    if [m.get("role") for m in msgs] != ["system", "user", "assistant"]:
        return ["roles must be system, user, assistant"]
    job = (rec.get("meta") or {}).get("job", "")
    if not (rec.get("meta") or {}).get("verified_by"):
        probs.append("no meta.verified_by: a label with no proof is not trained on")
    for c in msgs[1].get("content") or []:
        if c.get("type") == "image":
            p = c.get("image", "")
            if not os.path.isfile(p if os.path.isabs(p) else os.path.join(root, p)):
                probs.append(f"image missing: {p}")
    ans = "".join(c.get("text", "") for c in msgs[2].get("content") or [] if c.get("type") == "text").strip()
    if not ans:
        return probs + ["empty answer"]
    if job in JSON_JOBS:
        try:
            d = json.loads(ans)
            if not isinstance(d, dict) or (JSON_JOBS[job] and JSON_JOBS[job] not in d):
                probs.append(f"a {job} answer must be one JSON object holding '{JSON_JOBS[job]}'")
        except ValueError as exc:
            probs.append(f"a {job} answer is not JSON ({exc})")
    if job == "teach":
        n_ev = len(re.findall(r"^\[(\d{1,2})\]", "".join(c.get("text", "") for c in msgs[1].get("content") or [] if c.get("type") == "text"), re.M))
        cites = [int(x) for x in re.findall(r"\[(\d{1,2})\]", ans)]
        if not ans.upper().startswith("NOT IN EVIDENCE") and (not cites or any(x < 1 or x > n_ev for x in cites)):
            probs.append("a teach answer must cite evidence that exists, or say NOT IN EVIDENCE")
    return probs


def validate_pair(rec: Dict[str, Any], root: str, require_ui: bool = True) -> List[str]:
    """Problems that would make a pair useless or harmful for training ([] = fine). A pair whose meta.job is not an action job is checked by its own job's rules."""
    job = (rec.get("meta") or {}).get("job", "")
    if job and job not in ACTION_JOBS:
        return validate_job_pair(rec, root)
    probs = []
    if require_ui and rec.get("meta", {}).get("ui_frames") is not True:
        probs.append("frames not verified as a software UI (a talking head labelled 'click profile' teaches the model to click faces)")
    msgs = rec.get("messages") or []
    if [m.get("role") for m in msgs] != ["system", "user", "assistant"]:
        return ["roles must be system, user, assistant"]
    user, asst = msgs[1].get("content") or [], msgs[2].get("content") or []
    imgs = [c for c in user if c.get("type") == "image"]
    v2 = rec.get("meta", {}).get("prompt_version") == 2                     # prompt format v2: the full picture first, then up to four zoomed strip crops
    if job == "decide" and not imgs:
        pass                                                                # a decision can be made from the element list alone (the web-explore rows)
    elif (not v2 and len(imgs) != 1) or (v2 and not 1 <= len(imgs) <= 5):
        probs.append("exactly one image expected" if not v2 else None)
    else:
        for im in imgs:
            p = im.get("image", "")
            full = p if os.path.isabs(p) else os.path.join(root, p)
            if not os.path.isfile(full):
                probs.append(f"image missing: {p}")
    if not any(c.get("type") == "text" and "Elements:" in c.get("text", "") for c in user):
        probs.append("no numbered element list in the prompt")
    try:
        acts = json.loads(asst[0]["text"])
        if not isinstance(acts, list) or not acts:
            raise ValueError("empty")
        a = acts[0]
        if a.get("action") not in (ACTIONS if job == "decide" else ("click", "hotkey", "drag", "type")):
            probs.append(f"unknown action {a.get('action')!r}")
        if a.get("action") == "click" and a.get("target_id") is None:
            probs.append("click without a target_id")
        ids = {int(x) for c in user if c.get("type") == "text" for x in re.findall(r"^#(\d+)\b", c.get("text", ""), re.M)}
        if a.get("target_id") is not None and ids and int(a["target_id"]) not in ids:
            probs.append(f"target_id {a['target_id']} is not in the element list")
        if a.get("action") == "hotkey" and not a.get("hotkey"):
            probs.append("hotkey without keys")
    except Exception as exc:
        probs.append(f"assistant answer is not a JSON action list ({exc})")
    return probs


def _group_of(p: Dict[str, Any]) -> str:
    """What must not straddle the split. A video's frames are near-duplicates of each other (group = the video). A locally recorded pair has ONE 'video' per app, so that would put a whole app on one side:
    there the unit is the CONTROL (app + its UIA name): the eval set is then controls the model never saw a label for, on layouts it has seen."""
    m = p.get("meta", {})
    if m.get("source") == "local_uia":
        return f"{m.get('app_key', '')}::{m.get('uia_name', '')}"
    return m.get("video_id", "").split("@")[0]


def split_by_video(pairs: Sequence[Dict[str, Any]], eval_frac: float, seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Train/eval split by GROUP (see _group_of): a random pair-level split would leak the answer into the eval set. Whole groups are moved to eval until it holds ~eval_frac of the pairs."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in pairs:
        groups.setdefault(_group_of(p), []).append(p)
    keys = sorted(groups)
    if len(keys) < 2:
        return list(pairs), []
    rnd = random.Random(seed)
    rnd.shuffle(keys)
    want = int(round(len(pairs) * eval_frac))
    eval_k, n = set(), 0
    for k in keys:
        if n >= want or len(eval_k) >= len(keys) - 1:
            break
        eval_k.add(k)
        n += len(groups[k])
    if not eval_k:
        eval_k.add(keys[0])
    tr = [p for p in pairs if _group_of(p) not in eval_k]
    ev = [p for p in pairs if _group_of(p) in eval_k]
    return tr, ev


def estimate_pair_tokens(rec: Dict[str, Any], root: str, max_pixels: int) -> int:
    from PIL import Image
    user = rec["messages"][1]["content"]
    n_img, seen = 0, 0
    for c in user:                                                          # every picture counts (prompt format v2 adds the zoomed strip crops, which have their own smaller cap)
        if c.get("type") == "image":
            img = c["image"]
            w, h = Image.open(img if os.path.isabs(img) else os.path.join(root, img)).size
            n_img += image_tokens_for(w, h, max_pixels if (seen == 0 or not STRIP_PIXELS) else STRIP_PIXELS)
            seen += 1
    text = "".join(c.get("text", "") for m in rec["messages"] for c in m["content"] if c.get("type") == "text")
    return n_img + int(len(text) / 3.2) + 40


def prepare(cfg: TrainConfig, jsonl: str = "", root: str = "", out_dir: str = "") -> Dict[str, Any]:
    root = root or default_root()
    jsonl = jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    out_dir = out_dir or cfg.out_dir or os.path.join(root, "training", "runs", cfg.name or time.strftime("run_%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    rows, st = load_pairs(jsonl, cfg.grounded_only)
    good, rejected, too_long = [], [], 0
    for r in rows:
        p = validate_pair(r, root, cfg.require_ui_gate)
        if p:
            rejected.append({"pair_id": r.get("meta", {}).get("pair_id"), "problems": p})
            continue
        try:
            if estimate_pair_tokens(r, root, cfg.max_pixels) > cfg.max_seq_length:
                too_long += 1
                continue
        except Exception as exc:
            rejected.append({"pair_id": r.get("meta", {}).get("pair_id"), "problems": [f"unreadable image: {exc}"]})
            continue
        good.append(r)
    tr, ev = split_by_video(good, cfg.eval_frac, cfg.seed)
    for name, part in (("train", tr), ("eval", ev)):
        with open(os.path.join(out_dir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"jsonl": jsonl, "root": root, "out_dir": out_dir, **st, "valid": len(good), "rejected": rejected[:50], "n_rejected": len(rejected), "too_long": too_long, "train": len(tr), "eval": len(ev),
               "videos": len({p.get("meta", {}).get("video_id", "").split("@")[0] for p in good}), "actions": _count(good)}
    json.dump(summary, open(os.path.join(out_dir, "data_summary.json"), "w"), indent=2)
    return summary


def _count(pairs: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in pairs:
        try:
            a = json.loads(p["messages"][2]["content"][0]["text"])[0]["action"]
            out[a] = out.get(a, 0) + 1
        except Exception:
            pass
    return out


# ---- tokenised batches ---------------------------------------------------------------------------------------------------------------------------------
def shrink(img, max_pixels: int):
    w, h = img.size
    if w * h <= max_pixels:
        return img
    s = math.sqrt(max_pixels / (w * h))
    return img.resize((max(32, int(w * s)), max(32, int(h * s))))


def mask_prompt_labels(input_ids: List[int], prompt_len: int, ignore: int = -100) -> List[int]:
    """Loss only on the assistant's answer: everything the model is GIVEN (system, elements, image, goal) is masked."""
    return [ignore] * min(prompt_len, len(input_ids)) + list(input_ids[prompt_len:])


class VLMCollator:
    """Turns a validated pair into model inputs with prompt-masked labels. `processor` is a transformers AutoProcessor (or any object with apply_chat_template)."""

    def __init__(self, processor, root: str, max_pixels: int, max_len: int, pad_id: int = 0):
        self.p, self.root, self.max_pixels, self.max_len, self.pad_id = processor, root, max_pixels, max_len, pad_id

    def _messages(self, rec: Dict[str, Any]):
        from PIL import Image
        msgs = []
        for m in rec["messages"]:
            content = []
            seen = 0
            for c in m["content"]:
                if c["type"] == "image":
                    path = c["image"] if os.path.isabs(c["image"]) else os.path.join(self.root, c["image"])
                    content.append({"type": "image", "image": shrink(Image.open(path).convert("RGB"), self.max_pixels if (seen == 0 or not STRIP_PIXELS) else STRIP_PIXELS)})
                    seen += 1
                else:
                    content.append({"type": "text", "text": c["text"]})
            msgs.append({"role": m["role"], "content": content})
        return msgs

    def encode(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        msgs = self._messages(rec)
        full = self.p.apply_chat_template(msgs, tokenize=True, add_generation_prompt=False, return_dict=True, return_tensors="pt")
        prompt = self.p.apply_chat_template(msgs[:-1], tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        ids = full["input_ids"][0].tolist()
        n_prompt = prompt["input_ids"].shape[1]
        if len(ids) > self.max_len:
            raise ValueError(f"example is {len(ids)} tokens, over max_seq_length {self.max_len}")
        out = dict(full)
        out["labels"] = __import__("torch").tensor([mask_prompt_labels(ids, n_prompt)])
        return out

    def __call__(self, batch: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        import torch
        enc = [self.encode(r) for r in batch]
        if len(enc) == 1:
            return enc[0]
        width = max(e["input_ids"].shape[1] for e in enc)
        out: Dict[str, Any] = {}
        for k in enc[0]:
            vals = [e[k] for e in enc]
            if torch.is_tensor(vals[0]) and vals[0].dim() == 2 and vals[0].shape[1] == enc[0]["input_ids"].shape[1] and k not in ("pixel_values", "image_grid_thw"):
                pad = {"input_ids": self.pad_id, "labels": -100}.get(k, 0)                      # per-token tensors (input_ids, attention_mask, labels, mm_token_type_ids, ...)
                out[k] = torch.cat([torch.nn.functional.pad(v, (0, width - v.shape[1]), value=pad) for v in vals], 0)
            else:
                out[k] = torch.cat(vals, 0)                                                      # per-image tensors (pixel_values, image_grid_thw)
        return out


# ---- LoRA ----------------------------------------------------------------------------------------------------------------------------------------------
LANG_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def lora_target_regex(finetune_vision: bool) -> str:
    """Module-name regex for peft. Language-model projections always; the vision tower's attn.qkv / attn.proj / mlp.linear_fc* only with finetune_vision. Never the embeddings or lm_head."""
    lang = r".*language_model.*\.(?:" + "|".join(LANG_TARGETS) + r")"
    if not finetune_vision:
        return lang
    return r"(?:" + lang + r"|.*visual\.blocks\.\d+\.(?:attn\.qkv|attn\.proj|mlp\.linear_fc1|mlp\.linear_fc2))"


def make_lora_config(cfg: TrainConfig):
    from peft import LoraConfig
    return LoraConfig(r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, bias="none", target_modules=lora_target_regex(cfg.finetune_vision), task_type="CAUSAL_LM")


def training_arguments(cfg: TrainConfig, out_dir: str, optim: Optional[str] = None, **extra):
    from transformers import TrainingArguments
    import torch
    bf16 = bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported())
    kw = dict(output_dir=out_dir, per_device_train_batch_size=cfg.per_device_batch, gradient_accumulation_steps=cfg.grad_accum, learning_rate=cfg.lr, warmup_steps=cfg.warmup_steps,
              max_steps=cfg.max_steps, optim=optim or cfg.optim, logging_steps=5, save_strategy="steps", save_steps=25, save_total_limit=2, report_to="none", remove_unused_columns=False,
              gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False}, bf16=bf16, fp16=not bf16 and torch.cuda.is_available(), seed=cfg.seed, dataloader_num_workers=0)
    kw.update(extra)
    return TrainingArguments(**kw)


def build_model_hf(cfg: TrainConfig, model_id: str):
    import torch
    from peft import get_peft_model
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
    bf16 = torch.cuda.is_bf16_supported()
    skip = ["visual", "lm_head"] if not cfg.finetune_vision else ["lm_head"]
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16, llm_int8_skip_modules=skip)
    model = Qwen3VLForConditionalGeneration.from_pretrained(model_id, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16 if bf16 else torch.float16)
    # NOT peft.prepare_model_for_kbit_training: it upcasts every non-quantised parameter to fp32, which would double the embeddings/head (~2.5 GB for 8B)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, make_lora_config(cfg))
    proc = AutoProcessor.from_pretrained(model_id)
    return model, proc


def build_model_unsloth(cfg: TrainConfig, model_id: str):
    from unsloth import FastVisionModel
    model, tok = FastVisionModel.from_pretrained(model_id, load_in_4bit=True, use_gradient_checkpointing="unsloth")
    model = FastVisionModel.get_peft_model(model, finetune_vision_layers=cfg.finetune_vision, finetune_language_layers=True, finetune_attention_modules=True, finetune_mlp_modules=True,
                                           r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, bias="none", random_state=cfg.seed)
    return model, tok


def sliced_loss(model, inputs: Dict[str, Any]):
    """Cross-entropy over the ANSWER positions only. The prompt (system, element list, image, goal) is masked from the loss, yet a normal forward still builds seq x vocab logits for it; here the
    model returns logits for just the last K positions (logits_to_keep=K, K covering the first unmasked label), and the shifted loss is computed on those. Mathematically the same loss."""
    import torch
    labels = inputs.pop("labels")
    L = labels.shape[1]
    first = int((labels != -100).any(0).nonzero()[0])                       # first position that carries a label (the answer is a suffix)
    K = L - first + 1
    out = model(**inputs, logits_to_keep=K)
    logits = out.logits[:, :-1].float()                                     # positions L-K .. L-2 predict labels L-K+1 .. L-1
    tgt = labels[:, L - K + 1:]
    loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), tgt.reshape(-1), ignore_index=-100)
    return loss, out


def make_trainer_class():
    from transformers import Trainer

    class SlicedLossTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            loss, out = sliced_loss(model, dict(inputs))
            return (loss, out) if return_outputs else loss
    return SlicedLossTrainer


class ListDataset:
    def __init__(self, rows):
        self.rows = list(rows)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def memory_callback(every: int = 10):
    """Every `every` steps: gc.collect() + torch.cuda.empty_cache(). MEASURED: without it the step time on the 6 GB WDDM card crept from 27 s to 68 s as the allocator fragmented and spilled into shared memory."""
    from transformers import TrainerCallback

    class _Mem(TrainerCallback):
        def on_step_end(self, args, state, control, **kw):
            if state.global_step % every == 0:
                import gc
                import torch
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
    return _Mem()


def latest_checkpoint(out_dir: str, max_steps: int) -> str:
    """The newest checkpoint-N of this run that belongs to the same plan (its trainer_state has the same max_steps) and still has its optimizer, else ''."""
    best, path = -1, ""
    for d in os.listdir(out_dir) if os.path.isdir(out_dir) else []:
        m = re.match(r"checkpoint-(\d+)$", d)
        p = os.path.join(out_dir, d)
        if not m or not os.path.isfile(os.path.join(p, "optimizer.pt")):
            continue
        try:
            st = json.load(open(os.path.join(p, "trainer_state.json"), encoding="utf-8"))
        except Exception:
            continue
        if int(st.get("max_steps") or 0) == int(max_steps) and int(m.group(1)) > best:
            best, path = int(m.group(1)), p
    return path


def run_training(model, collate_fn, train_rows: Sequence[Dict[str, Any]], cfg: TrainConfig, out_dir: str, optim: Optional[str] = None, eval_rows: Sequence[Dict[str, Any]] = (), **args_extra) -> Dict[str, Any]:
    """The training loop (transformers.Trainer): the same code path the real model uses, so it can be exercised on a tiny model."""
    from transformers import Trainer
    args = training_arguments(cfg, out_dir, optim, **args_extra)
    trainer = (make_trainer_class() if cfg.slice_logits else Trainer)(model=model, args=args, train_dataset=ListDataset(train_rows), eval_dataset=ListDataset(eval_rows) if eval_rows else None, data_collator=collate_fn)
    trainer.add_callback(memory_callback(10))
    t0 = time.time()
    resume = latest_checkpoint(out_dir, cfg.max_steps) if os.environ.get("HOJAIGA_TRAIN_RESUME", "1") != "0" else ""
    res = trainer.train(resume_from_checkpoint=resume or None)                                        # an interrupted run continues (round 3 stopped at 200/700 with its optimizer saved)
    model.save_pretrained(os.path.join(out_dir, "adapter"))
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    return {"train_seconds": round(time.time() - t0, 1), "steps": trainer.state.global_step, "first_loss": losses[0] if losses else None, "last_loss": losses[-1] if losses else None,
            "adapter": os.path.join(out_dir, "adapter")}


def train(cfg: TrainConfig, force: bool = False, jsonl: str = "", root: str = "", presplit_dir: str = "") -> Dict[str, Any]:
    """`presplit_dir`: a directory that already holds train.jsonl / eval.jsonl (a split made by the caller, e.g. whole apps held out); it is used as it is instead of the automatic split."""
    root = root or default_root()
    backend = resolve_backend(cfg)
    pf = preflight(cfg, backend=backend)
    out: Dict[str, Any] = {"preflight": pf}
    if not pf["ok"] and not force:
        out["status"] = "refused: does not fit this GPU (see preflight.advice; --force to try anyway)"
        return out
    if presplit_dir:
        n_tr = sum(1 for _ in open(os.path.join(presplit_dir, "train.jsonl"), encoding="utf-8"))
        n_ev = sum(1 for _ in open(os.path.join(presplit_dir, "eval.jsonl"), encoding="utf-8"))
        data = {"out_dir": presplit_dir, "train": n_tr, "eval": n_ev, "presplit": True}
    else:
        data = prepare(cfg, jsonl, root)
    out["data"] = {k: v for k, v in data.items() if k not in ("rejected",)}
    if data["train"] < cfg.min_examples:
        out["status"] = (f"refused: {data['train']} training examples (< --min-examples {cfg.min_examples}). A LoRA trained on this few pairs memorises them and learns nothing general; "
                         "harvest and extract far more pairs first (the brief targets 10-25k)")
        return out
    run_dir = data["out_dir"]
    model_id = UNSLOTH_NAMES[next(k for k in MODEL_SPECS if k in cfg.model.lower())] if backend == "unsloth" and "/" not in cfg.model.replace("unsloth/", "") else cfg.model
    model, proc = (build_model_unsloth if backend == "unsloth" else build_model_hf)(cfg, model_id)
    tok = getattr(proc, "tokenizer", proc)
    collate = VLMCollator(proc, root, cfg.max_pixels, cfg.max_seq_length, pad_id=getattr(tok, "pad_token_id", 0) or 0)
    rows = [json.loads(l) for l in open(os.path.join(run_dir, "train.jsonl"), encoding="utf-8")]
    ev = [json.loads(l) for l in open(os.path.join(run_dir, "eval.jsonl"), encoding="utf-8")]
    if presplit_dir:                                                # a presplit set is checked too (Oct-29: 544k presplit rows went in unchecked, most of them template copies)
        bad: Dict[str, int] = {}
        def _ok(r: Dict[str, Any]) -> bool:
            p = validate_pair(r, root, cfg.require_ui_gate and (r.get("meta") or {}).get("job", "") in ("", "ground"))
            for x in p[:1]:
                bad[x.split(":")[0][:60]] = bad.get(x.split(":")[0][:60], 0) + 1
            return not p
        rows, ev = [r for r in rows if _ok(r)], [r for r in ev if _ok(r)]
        out["rejected_by_check"] = bad
        print(f"[train] presplit check: {len(rows)} train / {len(ev)} eval pass; rejected: {bad}", flush=True)
    kept, dropped = [], 0
    for r in rows:                                                  # the estimate under-counts some multi-image rows (measured: 2087 and 2472 tokens against 2048): the real tokenizer decides
        try:
            collate.encode(r)
            kept.append(r)
        except ValueError:
            dropped += 1
    rows = kept
    out["dropped_over_length"] = dropped
    print(f"[train] {len(rows)} rows kept, {dropped} dropped for length", flush=True)
    out["train"] = run_training(model, collate, rows, cfg, run_dir, eval_rows=ev)
    json.dump({**out, "config": asdict(cfg)}, open(os.path.join(run_dir, "run_summary.json"), "w"), indent=2, default=str)
    out["status"] = "trained"
    return out


# ---- evaluation ------------------------------------------------------------------------------------------------------------------------------------
def parse_action_detail(text: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Return ``(first_action, strict_json)`` for a model reply.

    The recovery path deliberately accepts a response cut off in the free-text
    ``verify_expectation`` after all action fields have arrived. That is useful
    for a guarded executor, but must not be reported as valid JSON during model
    evaluation.  ``strict_json`` therefore records a successfully decoded JSON
    action list, independently of whether an action can be recovered.
    """
    raw = text or ""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", raw):
        try:
            arr, _ = decoder.raw_decode(raw[match.start():])
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            return arr[0], True
    kind = re.search(r'"action"\s*:\s*"(click|hotkey|type)"', text or "")
    if not kind:
        return None, False
    out: Dict[str, Any] = {"step": 1, "action": kind.group(1), "target_id": None, "hotkey": None, "text": None}
    tid = re.search(r'"target_id"\s*:\s*(\d+)', text)
    if tid:
        out["target_id"] = int(tid.group(1))
    for k in ("hotkey", "text"):
        mm = re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if mm:
            out[k] = mm.group(1)
    if out["action"] == "click" and out["target_id"] is None:
        return None, False
    return out, False


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Compatibility wrapper for callers that only need a recoverable action."""
    return parse_action_detail(text)[0]


def _norm_keys(k: Any) -> str:
    return re.sub(r"\s+", "", str(k or "")).lower()


def score_action(pred: Optional[Dict[str, Any]], gold: Dict[str, Any]) -> Dict[str, bool]:
    """valid JSON / right kind of action / the whole action right (click: same target_id; hotkey: same keys; type: same text). verify_expectation is free text and not scored."""
    if pred is None:
        return {"valid": False, "action": False, "exact": False}
    same_kind = pred.get("action") == gold.get("action")
    exact = same_kind and (pred.get("target_id") == gold.get("target_id") if gold.get("action") == "click"
                           else _norm_keys(pred.get("hotkey")) == _norm_keys(gold.get("hotkey")) if gold.get("action") == "hotkey"
                           else str(pred.get("text") or "").strip() == str(gold.get("text") or "").strip())
    return {"valid": True, "action": bool(same_kind), "exact": bool(exact)}


def summarize_scores(rows: Sequence[Dict[str, bool]]) -> Dict[str, Any]:
    n = max(len(rows), 1)
    # Old callers only supply ``valid``; use it as a compatibility fallback.
    # Evaluations add strict_json, so their published valid_json metric is
    # genuinely syntactic JSON validity rather than regex recovery rate.
    return {"n": len(rows), "valid_json": round(sum(r.get("strict_json", r["valid"]) for r in rows) / n, 3),
            "recoverable_action": round(sum(r["valid"] for r in rows) / n, 3),
            "action_kind": round(sum(r["action"] for r in rows) / n, 3), "exact": round(sum(r["exact"] for r in rows) / n, 3)}


def balanced_eval_slice(rows: Sequence[Dict[str, Any]], max_examples: int = 0, seed: int = 3407) -> List[Dict[str, Any]]:
    """A deterministic, app-and-action-balanced evaluation slice.

    Evaluating every held-out visual interaction can be slow on a laptop GPU.
    A prefix is a misleading shortcut because harvest order clusters near-
    duplicate frames from the same app.  This round-robins stable
    ``app_key/action`` groups so a bounded smoke evaluation measures a broad
    cross-section.  ``max_examples=0`` always means the complete held-out set.
    """
    if max_examples <= 0 or max_examples >= len(rows):
        return list(rows)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        meta = row.get("meta", {})
        try:
            action = json.loads(row["messages"][2]["content"][0]["text"])[0].get("action", "unknown")
        except Exception:
            action = "unknown"
        key = f"{meta.get('app_key', 'unknown')}::{action}"
        groups.setdefault(key, []).append(row)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    positions = {key: 0 for key in keys}
    out: List[Dict[str, Any]] = []
    while len(out) < max_examples:
        added = False
        for key in keys:
            i = positions[key]
            if i >= len(groups[key]):
                continue
            out.append(groups[key][i])
            positions[key] = i + 1
            added = True
            if len(out) >= max_examples:
                break
        if not added:
            break
    return out


def evaluate_run(run_dir: str, model_id: str, cfg: Optional[TrainConfig] = None, root: str = "", max_new_tokens: int = 160, eval_file: str = "eval.jsonl", adapter_dir: str = "", with_base: bool = True,
                 report_name: str = "eval_report.json", max_examples: int = 0, eval_seed: int = 3407) -> Dict[str, Any]:
    """Held-out pairs (run_dir/eval.jsonl): the BASE model (same 4-bit load) and base + the trained adapter, greedy decoding, scored with score_action. The honest question: did the adapter learn
    anything the base model did not already do? (Held-out = controls the adapter never saw a label for, on layouts it has seen.)"""
    import torch
    from peft import PeftModel
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
    cfg = cfg or TrainConfig(model=model_id)
    root = root or default_root()
    all_rows = [json.loads(l) for l in open(os.path.join(run_dir, eval_file), encoding="utf-8")]
    rows = balanced_eval_slice(all_rows, max_examples=max_examples, seed=eval_seed)
    bf16 = torch.cuda.is_bf16_supported()
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16, llm_int8_skip_modules=["visual", "lm_head"])
    model = Qwen3VLForConditionalGeneration.from_pretrained(model_id, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16 if bf16 else torch.float16)
    proc = AutoProcessor.from_pretrained(model_id)
    col = VLMCollator(proc, root, cfg.max_pixels, cfg.max_seq_length)

    def run(m, tag: str) -> Dict[str, Any]:
        m.eval()
        scores, samples = [], []
        for r in rows:
            gold = json.loads(r["messages"][2]["content"][0]["text"])[0]
            msgs = col._messages(r)[:-1]
            enc = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
            enc = {k: (v.to(m.device) if hasattr(v, "to") else v) for k, v in enc.items()}
            with torch.no_grad():
                out = m.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
            text = proc.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0]
            pred, strict_json = parse_action_detail(text)
            sc = score_action(pred, gold)
            sc["strict_json"] = strict_json
            scores.append(sc)
            samples.append({"goal": [c.get("text", "") for c in r["messages"][1]["content"] if c.get("type") == "text"][-1].split("Goal: ")[-1][:70], "gold": {k: gold.get(k) for k in ("action", "target_id", "hotkey", "text")}, "reply": text[:200], **sc})
        return {"scores": summarize_scores(scores), "samples": samples, "tag": tag}
    res: Dict[str, Any] = {"selection": {"available": len(all_rows), "selected": len(rows), "max_examples": max_examples, "seed": eval_seed,
                                           "strategy": "full held-out set" if len(rows) == len(all_rows) else "deterministic round-robin by app_key/action"}}
    if with_base:
        res["base"] = run(model, "base")
    adapter = adapter_dir or os.path.join(run_dir, "adapter")
    if os.path.isdir(adapter):
        tuned = PeftModel.from_pretrained(model, adapter)
        res["adapter"] = run(tuned, "adapter")
    json.dump(res, open(os.path.join(run_dir, report_name), "w"), indent=2, default=str)
    return res


# ---- export ----------------------------------------------------------------------------------------------------------------------------------------------
def export_plan(run_dir: str, base_model: str, llama_cpp_dir: str = "") -> Dict[str, Any]:
    """merge -> GGUF -> mmproj -> quantise -> the llama-server line this project already uses. Each step is a command; prerequisites are checked, nothing is guessed.
    (Ollama cannot load a custom vision GGUF + projector from a Modelfile for this architecture reliably; llama-server, which start_hojaiga.bat already uses, can.)"""
    llama = llama_cpp_dir or os.environ.get("LLAMA_CPP_DIR", "")
    conv = os.path.join(llama, "convert_hf_to_gguf.py") if llama else ""
    missing = []
    if not llama or not os.path.isfile(conv):
        missing.append("LLAMA_CPP_DIR (a llama.cpp checkout containing convert_hf_to_gguf.py)")
    if not os.path.isdir(os.path.join(run_dir, "adapter")):
        missing.append(f"a trained adapter at {os.path.join(run_dir, 'adapter')}")
    if shutil.which("llama-quantize") is None:
        missing.append("llama-quantize on PATH")
    merged = os.path.join(run_dir, "merged_bf16")
    name = os.path.basename(run_dir.rstrip("/\\"))
    steps = [
        {"step": "merge", "what": f"load {base_model} in bf16 on the CPU (needs ~{round(spec_for(base_model).total_params * 2 / GIB)} GiB RAM, ~{round(spec_for(base_model).total_params * 2 / GIB)} GiB disk), merge the adapter, save", "out": merged},
        {"step": "convert", "cmd": f'python "{conv}" "{merged}" --outfile "{run_dir}/{name}-f16.gguf" --outtype f16'},
        {"step": "mmproj", "cmd": f'python "{conv}" "{merged}" --mmproj --outfile "{run_dir}/mmproj-{name}-f16.gguf" --outtype f16'},
        {"step": "quantize", "cmd": f'llama-quantize "{run_dir}/{name}-f16.gguf" "{run_dir}/{name}-Q4_K_M.gguf" Q4_K_M'},
        {"step": "serve", "cmd": f'llama-server --model "{run_dir}/{name}-Q4_K_M.gguf" --mmproj "{run_dir}/mmproj-{name}-f16.gguf"   (same flags as scratch/_start_vision_8b.bat)'},
    ]
    return {"ready": not missing, "missing": missing, "steps": steps}


def merge_adapter(base_model: str, adapter_dir: str, out_dir: str) -> str:
    import torch
    from peft import PeftModel
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    base = Qwen3VLForConditionalGeneration.from_pretrained(base_model, dtype=torch.bfloat16, device_map={"": "cpu"})
    merged = PeftModel.from_pretrained(base, adapter_dir).merge_and_unload()
    merged.save_pretrained(out_dir)
    AutoProcessor.from_pretrained(base_model).save_pretrained(out_dir)
    return out_dir


# ---- CLI -----------------------------------------------------------------------------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core_organs.train_qlora")
    ap.add_argument("cmd", choices=["preflight", "prepare", "train", "evaluate", "export"])
    ap.add_argument("--model", default=TrainConfig.model)
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=0, help="LoRA alpha (0 = the rank)")
    ap.add_argument("--max-pixels", type=int, default=0, help="largest image size in pixels (0 = 448x448); screens need about 1024x768 to keep their text readable")
    ap.add_argument("--lr", type=float, default=0.0)
    ap.add_argument("--warmup", type=int, default=0)
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--jsonl", default="")
    ap.add_argument("--run", default="")
    ap.add_argument("--all-pairs", action="store_true", help="include ungrounded pairs (not recommended)")
    ap.add_argument("--allow-unchecked-frames", action="store_true", help="include pairs whose frames were not verified as a software UI (not recommended)")
    ap.add_argument("--min-examples", type=int, default=200)
    ap.add_argument("--vision", action="store_true", help="also LoRA the vision tower")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--presplit", default="", help="a directory holding train.jsonl + eval.jsonl made by the caller (whole apps held out)")
    ap.add_argument("--eval-file", default="eval.jsonl")
    ap.add_argument("--adapter", default="", help="evaluate this adapter directory instead of <run>/adapter")
    ap.add_argument("--no-base", action="store_true")
    ap.add_argument("--report", default="eval_report.json")
    ap.add_argument("--max-examples", type=int, default=0, help="evaluate this many app/action-balanced held-out examples; 0 means all")
    ap.add_argument("--eval-seed", type=int, default=3407, help="deterministic seed for a bounded evaluation slice")
    ap.add_argument("--max-new-tokens", type=int, default=160, help="greedy decoding cap per held-out example")
    a = ap.parse_args(argv)
    cfg = TrainConfig(model=a.model, backend=a.backend, max_seq_length=a.seq, lora_r=a.rank, lora_alpha=a.alpha or a.rank, max_steps=a.steps, grounded_only=not a.all_pairs, require_ui_gate=not a.allow_unchecked_frames, min_examples=a.min_examples, finetune_vision=a.vision)
    cfg.max_pixels = a.max_pixels or cfg.max_pixels
    cfg.lr = a.lr or cfg.lr
    cfg.warmup_steps = a.warmup or cfg.warmup_steps
    if a.cmd == "preflight":
        out = preflight(cfg)
    elif a.cmd == "prepare":
        out = prepare(cfg, a.jsonl)
    elif a.cmd == "train":
        out = train(cfg, a.force, a.jsonl, presplit_dir=a.presplit)
    elif a.cmd == "evaluate":
        res = evaluate_run(a.run, cfg.model, cfg, eval_file=a.eval_file, adapter_dir=a.adapter, with_base=not a.no_base, report_name=a.report,
                           max_examples=a.max_examples, eval_seed=a.eval_seed, max_new_tokens=a.max_new_tokens)
        out = {"selection": res["selection"], **{k: v["scores"] for k, v in res.items() if isinstance(v, dict) and "scores" in v}}
    else:
        out = export_plan(a.run or os.path.join(default_root(), "training", "runs"), a.model)
    print(json.dumps(out, indent=2, default=str))
    return 0 if (out.get("ok", True) is not False and not str(out.get("status", "")).startswith("refused")) else 2


if __name__ == "__main__":
    sys.exit(main())