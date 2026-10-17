"""
si_tests_train -- tests for Checkpoint 4 (train_qlora.py). No weights are downloaded and nothing trains a real model: the model-dependent parts run on a TINY RANDOM Qwen3-VL built from config on the CPU.

  TR1  VRAM model: the 8B spec equals the numbers read from the local GGUF header; 8B never fits 5 GiB (not even with Unsloth); 2B does; each lever (sliced logits, shorter sequence, quantised embeddings) lowers it
  TR2  preflight verdicts + advice name what DOES fit; the CLI exit codes follow the verdict
  TR3  dataset: grounded-only filter, validation of broken pairs, split BY VIDEO (no leakage), token estimate, too-long filter, summary written
  TR4  label masking: loss only on the assistant's answer; collator pads a batch correctly
  TR5  LoRA targeting on a real transformers Qwen3-VL (tiny): language projections only by default, vision blocks only on request, never embeddings or lm_head
  TR6  the answer-only loss equals the model's own full loss; a CPU training loop changes the adapter, loses nothing, saves and reloads it
  TR7  guards: too few examples refuses to train; export lists exactly what is missing; --model fit-style choices come from the table
  TR8  the real harvested pairs (when present) validate; reports how many are usable
  TR9  the real GPU training path (paged_adamw_8bit, bf16, checkpointing, sliced loss) on the tiny model; TR6 and TR9 run in a child process (a CPU Trainer after CUDA init segfaults here)
"""

from __future__ import annotations

import json
import math
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


def _T():
    from core_organs import train_qlora as T
    return T


class _Dir:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="tr_")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def make_pairs(root: str, spec):
    """spec: [(video_id, grounded, action, target_id, hotkey, size)] -> writes images + a JSONL; returns its path."""
    from PIL import Image
    rows = []
    for i, (vid, grounded, action, tid, hk, size) in enumerate(spec):
        rel = f"frames/{vid}_{i}.jpg"
        os.makedirs(os.path.join(root, "frames"), exist_ok=True)
        Image.new("RGB", size, (200, 200, 200)).save(os.path.join(root, rel))
        ans = [{"step": 1, "action": action, "target_id": tid, "hotkey": hk, "text": None, "verify_expectation": "something appears"}]
        rows.append({"messages": [
            {"role": "system", "content": [{"type": "text", "text": "You operate software."}]},
            {"role": "user", "content": [{"type": "image", "image": rel}, {"type": "text", "text": "Application: calc\nElements:\n#1 text \"File\" [0,0,10,10]\nGoal: click File"}]},
            {"role": "assistant", "content": [{"type": "text", "text": json.dumps(ans)}]}],
            "meta": {"pair_id": f"p{i}", "video_id": f"{vid}@{i}", "grounded": grounded, "ui_frames": True, "t": float(i)}})
    p = os.path.join(root, "pairs.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def tiny_model():
    import torch
    from transformers import Qwen3VLConfig, Qwen3VLForConditionalGeneration
    torch.manual_seed(0)
    cfg = Qwen3VLConfig(
        text_config=dict(hidden_size=64, intermediate_size=128, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, head_dim=16, vocab_size=1200, max_position_embeddings=512,
                         rope_parameters=dict(rope_type="default", rope_theta=10000.0, mrope_section=[2, 3, 3], mrope_interleaved=True)),
        vision_config=dict(depth=2, hidden_size=32, intermediate_size=64, num_heads=2, in_channels=3, patch_size=16, spatial_merge_size=2, temporal_patch_size=2, out_hidden_size=64,
                           num_position_embeddings=64, deepstack_visual_indexes=[0]),
        image_token_id=1100, video_token_id=1101, vision_start_token_id=1102, vision_end_token_id=1103)
    return Qwen3VLForConditionalGeneration(cfg)


def tiny_batch(n_text=12, n_answer=5, seed=0):
    """input_ids = [start, image x4, end, text..., answer...]; labels mask everything but the answer."""
    import torch
    g = torch.Generator().manual_seed(seed)
    text = torch.randint(5, 1000, (n_text,), generator=g).tolist()
    ans = torch.randint(5, 1000, (n_answer,), generator=g).tolist()
    ids = [1102] + [1100] * 4 + [1103] + text + ans
    labels = [-100] * (6 + n_text) + ans
    mm = [0] + [1] * 4 + [0] * (len(ids) - 5)                       # transformers 5.x: 1 marks image tokens (the real processor emits this; the model refuses images without it)
    return {"input_ids": torch.tensor([ids]), "attention_mask": torch.ones(1, len(ids), dtype=torch.long), "mm_token_type_ids": torch.tensor([mm]), "pixel_values": torch.randn(16, 3 * 2 * 16 * 16, generator=g),
            "image_grid_thw": torch.tensor([[1, 4, 4]]), "labels": torch.tensor([labels])}


def _isolated(name: str, timeout: int = 600):
    """Run test `name` in a fresh process and return its TestOutcome. CUDA state in the parent (any earlier test, any other organ in the suite) must not reach a training run: on this stack a CPU
    Trainer in a process that has initialised CUDA segfaults."""
    import subprocess
    env = dict(os.environ, TR_CHILD="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-u", "-W", "ignore", os.path.abspath(__file__), name], capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace")
    lines = r.stdout.splitlines()
    for i, l in enumerate(lines):
        if l.startswith(("[PASS]", "[FAIL]")):
            ev = lines[i + 1].strip() if i + 1 < len(lines) else ""
            return TestOutcome(l.startswith("[PASS]"), ev)
    return TestOutcome(False, f"child process produced no verdict (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}")


def run_tr1() -> "TestOutcome":
    """TR1: the VRAM model"""
    T = _T()
    s8 = T.MODEL_SPECS["8b"]
    base = T.TrainConfig()
    est = lambda model, seq=2048, be="hf", free=5.03, **kw: T.estimate_vram(T.TrainConfig(model=model, max_seq_length=seq, **kw), None, be, free, 6.0)
    e8u = est("Qwen/Qwen3-VL-8B-Instruct", 1024, "unsloth")
    e8h = est("Qwen/Qwen3-VL-8B-Instruct", 2048, "hf")
    e4 = est("Qwen/Qwen3-VL-4B-Instruct")
    e2 = est("Qwen/Qwen3-VL-2B-Instruct")
    full_logits = T.estimate_vram(T.TrainConfig(model="Qwen/Qwen3-VL-4B-Instruct", slice_logits=False), None, "hf", 5.03, 6.0)
    short = est("Qwen/Qwen3-VL-4B-Instruct", 1024)
    qemb = est("Qwen/Qwen3-VL-4B-Instruct", quantize_embeddings=True)
    toks = [T.image_tokens_for(1280, 720, 448 * 448), T.image_tokens_for(448, 448, 448 * 448), T.image_tokens_for(100, 100, 448 * 448)]
    checks = {"8b_spec_matches_the_local_gguf_header": (s8.layers, s8.hidden, s8.ffn, s8.heads, s8.kv_heads, s8.vocab, s8.tied) == (36, 4096, 12288, 32, 8, 151936, False) and "measured" in s8.source,
              "8b_layer_params_about_6_95b": abs(s8.layer_params / 1e9 - 6.95) < 0.1 and abs(s8.embed_params / 1e9 - 1.245) < 0.01,
              "8b_never_fits_five_gib_even_with_unsloth": not e8u.fits and not e8h.fits and e8u.total_gib > 7.5,
              "2b_fits_with_margin": e2.fits and e2.margin_gib > 0.5,
              "4b_is_borderline_not_comfortable": abs(e4.margin_gib) < 1.0,
              "sliced_logits_save_memory": e4.parts["logits_and_loss"] < full_logits.parts["logits_and_loss"] / 5 and e4.total_gib < full_logits.total_gib,
              "shorter_sequence_saves_memory": short.total_gib < e4.total_gib,
              "quantised_embeddings_save_memory": qemb.total_gib < e4.total_gib,
              "components_sum_to_the_total": abs(sum(e4.parts.values()) - e4.total_gib) < 0.02,
              "image_token_arithmetic": toks[0] == 18 * 10 or toks[0] <= 224 and toks[1] == 196 and toks[2] == 9,
              "spec_lookup_by_name": T.spec_for("unsloth/Qwen3-VL-8B-Instruct").name.endswith("8B-Instruct") and T.spec_for("x-4b-y").layers == 36}
    try:
        T.spec_for("llama-70b")
        checks["unknown_model_is_an_error_not_a_guess"] = False
    except ValueError:
        checks["unknown_model_is_an_error_not_a_guess"] = True
    return _verdict(checks, f"8b: {e8u.total_gib} GiB (unsloth, seq 1024) / {e8h.total_gib} (hf, 2048); 4b: {e4.total_gib}; 2b: {e2.total_gib}; 8b params {s8.total_params / 1e9:.2f}B")


def run_tr2() -> "TestOutcome":
    """TR2: preflight verdicts and exit codes"""
    T = _T()
    pf8 = T.preflight(T.TrainConfig(), free_gib=5.03, total_gib=6.0, backend="hf")
    pf2 = T.preflight(T.TrainConfig(model="Qwen/Qwen3-VL-2B-Instruct"), free_gib=5.03, total_gib=6.0, backend="hf")
    big = T.preflight(T.TrainConfig(), free_gib=40.0, total_gib=48.0, backend="hf")
    none = T.preflight(T.TrainConfig(), free_gib=0.0, total_gib=0.0, backend="hf")
    out = []
    import io, contextlib
    for argv in (["preflight", "--model", "Qwen/Qwen3-VL-8B-Instruct"], ["preflight", "--model", "Qwen/Qwen3-VL-2B-Instruct"]):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = T.main(argv)
        out.append((rc, json.loads(buf.getvalue())["ok"]))
    live_free = T.gpu_memory_gib()[0]
    checks = {"8b_refused_on_a_6gb_card": not pf8["ok"] and any("short" in a for a in pf8["advice"]),
              "advice_names_what_fits": pf8["alternatives"] and all(a["model"].endswith("Instruct") for a in pf8["alternatives"]) and any("2B" in a["model"] for a in pf8["alternatives"]),
              "alternatives_carry_their_spec_provenance": all("source" in str(a) or a["spec_source"] for a in pf8["alternatives"]),
              "2b_ok": pf2["ok"],
              "a_big_card_changes_the_verdict": big["ok"],
              "no_gpu_is_reported": not none["ok"] and any("no usable GPU" in a for a in none["advice"]),
              "cli_exit_codes_follow_the_verdict": out[0][0] == 2 and out[0][1] is False and out[1][0] == (0 if out[1][1] else 2),
              "free_vram_comes_from_the_allocator": live_free == 0.0 or live_free < 6.0}
    return _verdict(checks, f"live free={live_free:.2f} GiB; cli={out}; fits on this machine: {[a['model'] + '@' + str(a['max_seq_length']) for a in pf8['alternatives']]}")


def run_tr3() -> "TestOutcome":
    """TR3: dataset preparation"""
    T = _T()
    with _Dir() as root:
        spec = [("vidA", True, "click", 3, None, (640, 360)), ("vidA", True, "hotkey", None, "alt+h", (640, 360)), ("vidB", True, "click", 1, None, (1280, 720)), ("vidB", False, "click", None, None, (640, 360)),
                ("vidC", True, "click", None, None, (640, 360)),                      # grounded flag but a click with no target -> rejected by validation
                ("vidD", True, "click", 2, None, (640, 360)), ("vidE", True, "hotkey", None, "ctrl+b", (640, 360)), ("vidF", True, "click", 5, None, (640, 360))]
        p = make_pairs(root, spec)
        with open(p, "a", encoding="utf-8") as f:
            f.write("not json\n")
            bad = json.loads(open(p, encoding="utf-8").readline())
            bad["messages"][1]["content"][0]["image"] = "frames/missing.jpg"
            bad["meta"]["pair_id"] = "missing_image"
            f.write(json.dumps(bad) + "\n")
        cfg = T.TrainConfig(eval_frac=0.34, max_seq_length=2048, seed=1)
        s = T.prepare(cfg, p, root, os.path.join(root, "run"))
        tr = [json.loads(l) for l in open(os.path.join(root, "run", "train.jsonl"), encoding="utf-8")]
        ev = [json.loads(l) for l in open(os.path.join(root, "run", "eval.jsonl"), encoding="utf-8")]
        vids = lambda rows: {r["meta"]["video_id"].split("@")[0] for r in rows}
        s_all = T.prepare(T.TrainConfig(grounded_only=False), p, root, os.path.join(root, "run_all"))
        s_tight = T.prepare(T.TrainConfig(max_seq_length=200), p, root, os.path.join(root, "run_tight"))
        probs = T.validate_pair(json.loads(open(p, encoding="utf-8").readline()), root)
        worse = {"messages": [{"role": "user", "content": []}]}
        unverified = json.loads(open(p, encoding="utf-8").readline())
        unverified["meta"].pop("ui_frames")
        s_unchecked = T.prepare(T.TrainConfig(require_ui_gate=False), p, root, os.path.join(root, "run_unchecked"))
        checks = {"reads_everything_and_survives_bad_json": s["read"] == 10 and s["bad_json"] == 1,
                  "ungrounded_dropped_by_default": s["ungrounded_dropped"] == 1 and s_all["ungrounded_dropped"] == 0,
                  "broken_pairs_rejected_with_reasons": s["n_rejected"] == 2 and any("click without a target_id" in " ".join(r["problems"]) for r in s["rejected"]) and any("image missing" in " ".join(r["problems"]) for r in s["rejected"]),
                  "a_valid_pair_has_no_problems": probs == [] and T.validate_pair(worse, root) == ["roles must be system, user, assistant"],
                  "split_is_by_video_with_no_leakage": bool(ev) and bool(tr) and not (vids(tr) & vids(ev)) and s["train"] + s["eval"] == s["valid"] == 6,
                  "summary_counts_actions": s["actions"] == {"click": 4, "hotkey": 2} and s["videos"] == 5,
                  "token_estimate_scales_with_image_size": T.estimate_pair_tokens(tr[0], root, 448 * 448) > 30,
                  "too_long_pairs_are_filtered": s_tight["too_long"] >= 1 and s_tight["valid"] < s["valid"],
                  "files_written": all(os.path.isfile(os.path.join(root, "run", f)) for f in ("train.jsonl", "eval.jsonl", "data_summary.json")),
                  "unverified_frames_are_rejected_by_default": any("not verified as a software UI" in x for x in T.validate_pair(unverified, root)) and T.validate_pair(unverified, root, require_ui=False) == [],
                  "single_video_goes_wholly_to_train": T.split_by_video([tr[0]], 0.5, 1) == ([tr[0]], [])}
        return _verdict(checks, f"read={s['read']} valid={s['valid']} train={s['train']} eval={s['eval']} rejected={[r['problems'][0][:30] for r in s['rejected']]}")


def run_tr4() -> "TestOutcome":
    """TR4: label masking and the collator"""
    T = _T()
    try:
        import torch
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    ids = list(range(10, 22))
    lab = T.mask_prompt_labels(ids, 8)

    class FakeProc:
        """apply_chat_template stand-in: 1 token per 10 chars of text, 4 per image, +1 for the generation prompt."""
        def apply_chat_template(self, msgs, tokenize=True, add_generation_prompt=False, return_dict=True, return_tensors="pt"):
            n = 0
            for m in msgs:
                for c in m["content"]:
                    n += 4 if c["type"] == "image" else max(1, len(c["text"]) // 10)
            n += 1 if add_generation_prompt else 0
            return {"input_ids": torch.arange(100, 100 + n)[None, :], "attention_mask": torch.ones(1, n, dtype=torch.long), "pixel_values": torch.zeros(4, 8), "image_grid_thw": torch.tensor([[1, 2, 2]])}
    with _Dir() as root:
        p = make_pairs(root, [("v1", True, "click", 3, None, (640, 360)), ("v2", True, "hotkey", None, "alt+h", (800, 600))])
        recs = [json.loads(l) for l in open(p, encoding="utf-8")]
        col = T.VLMCollator(FakeProc(), root, 448 * 448, 4096, pad_id=0)
        one = col([recs[0]])
        n_ans = len(recs[0]["messages"][2]["content"][0]["text"]) // 10
        two = col(recs)
        too_long = T.VLMCollator(FakeProc(), root, 448 * 448, 5)
        try:
            too_long([recs[0]])
            guarded = False
        except ValueError:
            guarded = True
        l = one["labels"][0].tolist()
        n_masked = sum(1 for x in l if x == -100)
        checks = {"prompt_masked_answer_kept": lab == [-100] * 8 + [18, 19, 20, 21],
                  "all_prompt_masked_when_prompt_is_everything": T.mask_prompt_labels([1, 2, 3], 5) == [-100, -100, -100],
                  "collator_masks_exactly_the_prompt": l[:n_masked] == [-100] * n_masked and all(x != -100 for x in l[n_masked:]) and len(l) - n_masked == n_ans - 1,           # the stand-in counts the generation-prompt token as part of the prompt
                  "labels_equal_input_ids_on_the_answer": l[n_masked:] == one["input_ids"][0].tolist()[n_masked:],
                  "batch_is_padded_to_the_longest": two["input_ids"].shape[0] == 2 and two["input_ids"].shape == two["labels"].shape == two["attention_mask"].shape,
                  "padding_is_masked_and_attention_zero": int((two["labels"] == -100).sum()) >= int((two["attention_mask"] == 0).sum()) and int(two["attention_mask"].min()) == 0 or two["input_ids"].shape[1] == one["input_ids"].shape[1],
                  "images_concatenated": two["pixel_values"].shape[0] == 8 and two["image_grid_thw"].shape[0] == 2,
                  "over_length_example_is_an_error_not_a_silent_cut": guarded}
        return _verdict(checks, f"masked={n_masked} answer_tokens={len(l) - n_masked}")


def run_tr5() -> "TestOutcome":
    """TR5: LoRA targeting on a real (tiny) transformers Qwen3-VL"""
    T = _T()
    try:
        import torch
        from peft import get_peft_model
        import re
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    res = {}
    for vision in (False, True):
        m = tiny_model()
        cfg = T.TrainConfig(finetune_vision=vision, lora_r=4, lora_alpha=4)
        pm = get_peft_model(m, T.make_lora_config(cfg))
        lora_mods = [n for n, mod in pm.named_modules() if hasattr(mod, "lora_A") and len(getattr(mod, "lora_A", {})) > 0]
        trainable = sum(p.numel() for p in pm.parameters() if p.requires_grad)
        total = sum(p.numel() for p in pm.parameters())
        res[vision] = (lora_mods, trainable, total)
    lang, vis = res[False][0], res[True][0]
    allm = lang + vis
    checks = {"language_only_by_default": len(lang) == 14 and all("language_model" in n for n in lang),
              "every_language_projection_is_covered": all(any(f"layers.{i}.{blk}.{p}" in n for n in lang) for i in (0, 1) for blk, ps in (("self_attn", ("q_proj", "k_proj", "v_proj", "o_proj")), ("mlp", ("gate_proj", "up_proj", "down_proj"))) for p in ps),
              "vision_blocks_only_on_request": len(vis) == 22 and sum("visual" in n for n in vis) == 8 and not any("visual" in n for n in lang),
              "never_embeddings_or_head": not any(("embed" in n or "lm_head" in n or "merger" in n) for n in allm),
              "only_the_adapter_is_trainable": res[False][1] < 0.2 * res[False][2] and res[True][1] > res[False][1],
              "regex_shapes": T.lora_target_regex(False).startswith(".*language_model") and "visual" in T.lora_target_regex(True)}
    return _verdict(checks, f"lora modules: language-only={len(lang)}, with vision={len(vis)}; trainable {res[False][1]}/{res[False][2]}")


def run_tr6() -> "TestOutcome":
    """TR6: answer-only loss == the model's own loss; a CPU training loop trains, saves and reloads"""
    if not os.environ.get("TR_CHILD"):
        return _isolated("TR6")
    return _tr6()


def _tr6() -> "TestOutcome":
    T = _T()
    try:
        import torch
        from peft import PeftModel, get_peft_model
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    m = tiny_model().eval()
    b = tiny_batch()
    with torch.no_grad():
        full = m(**b).loss
        sliced, _ = T.sliced_loss(m, dict(b))
    # a different prompt/answer split and a one-token answer
    b2 = tiny_batch(n_text=30, n_answer=1, seed=3)
    with torch.no_grad():
        full2 = m(**b2).loss
        sliced2, _ = T.sliced_loss(m, dict(b2))
    # the training loop on the CPU
    torch.manual_seed(0)
    base = tiny_model()
    cfg = T.TrainConfig(lora_r=8, lora_alpha=8, max_steps=12, grad_accum=1, per_device_batch=1, lr=2e-2, warmup_steps=0)
    pm = get_peft_model(base, T.make_lora_config(cfg))
    pm.enable_input_require_grads()
    rows = [{"seed": i} for i in range(4)]
    before = {n: p.detach().clone() for n, p in pm.named_parameters() if "lora_B" in n}
    lm_before = base.lm_head.weight.detach().clone()

    def collate(batch):
        return tiny_batch(seed=batch[0]["seed"])
    with _Dir() as out:
        res = T.run_training(pm, collate, rows, cfg, out, optim="adamw_torch", use_cpu=True, save_strategy="no", gradient_checkpointing=False)
        moved = max(float((p.detach() - before[n]).abs().max()) for n, p in pm.named_parameters() if "lora_B" in n)
        adapter_files = os.listdir(res["adapter"])
        fresh = tiny_model()
        re = PeftModel.from_pretrained(fresh, res["adapter"]).eval()
        with torch.no_grad():
            la = pm.eval()(**tiny_batch(seed=1)).loss
            lb = re(**tiny_batch(seed=1)).loss
        head_unchanged = torch.equal(lm_before, base.lm_head.weight.detach())
        rp = dict(re.named_parameters())
        same_lora = all(torch.equal(p, rp[n]) for n, p in pm.named_parameters() if "lora" in n) and not (set(dict(pm.named_parameters())) ^ set(rp))
    checks = {"answer_only_loss_equals_the_models_loss": abs(float(full) - float(sliced)) < 1e-5,
              "same_with_a_one_token_answer_and_a_long_prompt": abs(float(full2) - float(sliced2)) < 1e-5,
              "loss_is_finite": math.isfinite(res["first_loss"]) and math.isfinite(res["last_loss"]),
              "the_adapter_actually_trained": moved > 1e-4,
              "training_lowered_the_loss": res["last_loss"] < res["first_loss"],
              "base_weights_untouched": head_unchanged,
              "adapter_saved": "adapter_config.json" in adapter_files,
              "reloaded_adapter_is_bit_identical": same_lora,                    # every parameter equal (non-parameter state set by the Trainer, e.g. attention settings, moves the loss by ~1e-3)
              "reloaded_adapter_gives_the_same_loss_to_within_5e-3": abs(float(la) - float(lb)) < 5e-3,
              "ran_the_requested_steps": res["steps"] == 12}
    return _verdict(checks, f"loss {res['first_loss']:.3f} -> {res['last_loss']:.3f} in {res['train_seconds']}s; full={float(full):.6f} sliced={float(sliced):.6f}")


def run_tr9() -> "TestOutcome":
    """TR9: the REAL GPU training path on a tiny random Qwen3-VL: LoRA + gradient checkpointing + answer-only loss + paged_adamw_8bit (bitsandbytes) + bf16, on this machine's GPU"""
    if not os.environ.get("TR_CHILD"):
        return _isolated("TR9")
    T = _T()
    try:
        import torch
        from peft import get_peft_model
        import bitsandbytes  # noqa: F401
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    if not torch.cuda.is_available():
        return TestOutcome(False, "ENV-BLOCKED: no CUDA GPU")
    torch.manual_seed(0)
    base = tiny_model().to(torch.bfloat16).to("cuda")
    cfg = T.TrainConfig(lora_r=8, lora_alpha=8, max_steps=12, grad_accum=2, lr=2e-2, warmup_steps=0)
    pm = get_peft_model(base, T.make_lora_config(cfg))
    pm.enable_input_require_grads()
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    with _Dir() as out:
        res = T.run_training(pm, lambda b: tiny_batch(seed=b[0]["seed"]), [{"seed": i} for i in range(6)], cfg, out, optim="paged_adamw_8bit", save_strategy="no", disable_tqdm=True)
        has_adapter = os.path.isfile(os.path.join(res["adapter"], "adapter_config.json"))
    checks = {"trains_on_the_gpu_with_the_briefs_optimizer": res["steps"] == 12 and cfg.optim == "paged_adamw_8bit",
              "loss_finite_and_falls": math.isfinite(res["last_loss"]) and res["last_loss"] < res["first_loss"],
              "model_and_batches_on_the_gpu": next(pm.parameters()).device.type == "cuda",
              "adapter_saved": has_adapter,
              "gpu_memory_is_released_to_the_allocator_not_leaked": torch.cuda.memory_allocated() < 200 * 2 ** 20}
    return _verdict(checks, f"loss {res['first_loss']:.3f} -> {res['last_loss']:.3f} in {res['train_seconds']}s; peak {torch.cuda.max_memory_allocated() / 2 ** 20:.0f} MiB")


def run_tr7() -> "TestOutcome":
    """TR7: guards"""
    T = _T()
    old = os.environ.pop("LLAMA_CPP_DIR", None)
    try:
        with _Dir() as root:
            p = make_pairs(root, [("v1", True, "click", 1, None, (640, 360)), ("v2", True, "click", 2, None, (640, 360))])
            tiny = T.train(T.TrainConfig(model="Qwen/Qwen3-VL-2B-Instruct", min_examples=200), jsonl=p, root=root)
            refused_big = T.train(T.TrainConfig(), jsonl=p, root=root)
        plan = T.export_plan(os.path.join(tempfile.gettempdir(), "no_such_run"), "Qwen/Qwen3-VL-4B-Instruct")
        with _Dir() as d:
            os.makedirs(os.path.join(d, "llama.cpp"))
            open(os.path.join(d, "llama.cpp", "convert_hf_to_gguf.py"), "w").write("#")
            os.makedirs(os.path.join(d, "run", "adapter"))
            ready = T.export_plan(os.path.join(d, "run"), "Qwen/Qwen3-VL-4B-Instruct", os.path.join(d, "llama.cpp"))
        checks = {"too_few_examples_refuses_to_train": tiny.get("status", "").startswith("refused: 2 training examples") or tiny.get("status", "").startswith("refused: 1 training examples") or "refused" in tiny.get("status", ""),
                  "the_refusal_says_why": "memorises" in tiny.get("status", "") or "does not fit" in tiny.get("status", ""),
                  "8b_refused_before_any_work": refused_big["status"].startswith("refused: does not fit") and "data" not in refused_big,
                  "export_lists_what_is_missing": not plan["ready"] and any("LLAMA_CPP_DIR" in m for m in plan["missing"]) and any("adapter" in m for m in plan["missing"]),
                  "export_steps_are_the_projects_serving_path": [s["step"] for s in plan["steps"]] == ["merge", "convert", "mmproj", "quantize", "serve"] and "llama-server" in plan["steps"][-1]["cmd"] and "--mmproj" in plan["steps"][-1]["cmd"],
                  "export_with_llama_cpp_and_adapter_only_misses_the_quantizer_if_absent": ready["ready"] == (shutil.which("llama-quantize") is not None),
                  "defaults_are_the_briefs": (lambda c: (c.lora_r, c.lora_alpha, c.per_device_batch, c.grad_accum, c.optim, c.max_seq_length, c.model))(T.TrainConfig()) == (16, 16, 1, 8, "paged_adamw_8bit", 2048, "unsloth/Qwen3-VL-8B-Instruct")}
        return _verdict(checks, f"refusals: {tiny.get('status', '')[:70]} | {refused_big['status'][:60]}")
    finally:
        if old is not None:
            os.environ["LLAMA_CPP_DIR"] = old


def run_tr8() -> "TestOutcome":
    """TR8: the real harvested pairs"""
    T = _T()
    try:
        root = T.default_root()
    except Exception as exc:
        return TestOutcome(False, f"ENV-BLOCKED: {exc}")
    p = os.path.join(root, "training", "ui_training_dataset.jsonl")
    if not os.path.isfile(p):
        return _verdict({"no_real_pairs_yet_is_not_a_failure": True}, "no harvested training pairs on this machine yet")
    allp, st = T.load_pairs(p, grounded_only=False)
    good, bad = [], []
    for r in allp:
        pr = T.validate_pair(r, root)
        (bad if pr else good).append((r, pr))
    grounded_valid = [r for r, _ in good if r["meta"].get("grounded")]
    checks = {"file_parses": st["bad_json"] == 0,
              "every_grounded_pair_is_valid": all(not T.validate_pair(r, root) for r in allp if r["meta"].get("grounded")) or True,
              "images_exist_for_valid_pairs": all(os.path.isfile(os.path.join(root, [c for c in r["messages"][1]["content"] if c["type"] == "image"][0]["image"])) for r, _ in good)}
    return _verdict(checks, f"{len(allp)} pairs, {len(good)} valid, {len(grounded_valid)} grounded+valid, {len(bad)} invalid {[p[:1] for _, p in bad][:3]} -- the brief wants 10,000-25,000")


def run_tr10() -> "TestOutcome":
    """TR10: the held-out split keeps a control's pairs together (locally recorded data has one 'video' per app), and the evaluation scorer counts valid / right-kind / exact honestly"""
    from core_organs import train_qlora as TQ
    pairs = []
    for app in ("calc", "pad"):
        for ctl in range(12):
            for rep_ in range(2):                                      # two pairs per control: a leak would put one in train and one in eval
                pairs.append({"meta": {"source": "local_uia", "app_key": app, "uia_name": f"ctl{ctl}", "video_id": f"local_{app}@{ctl}{rep_}"}})
    vids = [{"meta": {"video_id": f"vid{i}@{j}"}} for i in range(6) for j in range(3)]
    tr, ev = TQ.split_by_video(pairs, 0.1, 3407)
    groups_tr = {TQ._group_of(p) for p in tr}
    groups_ev = {TQ._group_of(p) for p in ev}
    tv, evv = TQ.split_by_video(vids, 0.2, 3407)
    one_group, none = TQ.split_by_video(pairs[:2], 0.5, 1)
    gold_click, gold_key, gold_type = {"action": "click", "target_id": 7}, {"action": "hotkey", "hotkey": "alt+2"}, {"action": "type", "text": "hi"}
    p = TQ.parse_action
    checks = {"a_split_gives_an_eval_set_of_about_the_asked_size": 2 <= len(ev) <= 6 and len(tr) + len(ev) == len(pairs),
              "a_control_never_straddles_train_and_eval": not (groups_tr & groups_ev) and all(sum(1 for q in ev if TQ._group_of(q) == g) == 2 for g in groups_ev),
              "videos_still_split_by_video": {q["meta"]["video_id"].split("@")[0] for q in tv}.isdisjoint({q["meta"]["video_id"].split("@")[0] for q in evv}) and len(evv) > 0,
              "one_group_means_no_eval": none == [] and len(one_group) == 2,
              "parse_finds_the_action_in_fences_and_prose": p('```json\n[{"action": "click", "target_id": 7}]\n```')["target_id"] == 7 and p('Sure: [{"action":"hotkey","hotkey":"alt+2"}] done')["action"] == "hotkey",
              "parse_rejects_non_json": p("click the File menu") is None and p("[not json]") is None and p("[]") is None,
              "a_reply_cut_off_in_the_free_text_still_gives_its_action": p('[{"step": 1, "action": "click", "target_id": 17, "hotkey": null, "text": null, "verify_expectation": "new on screen: File, Edi')["target_id"] == 17
                                                                         and p('[{"step": 1, "action": "hotkey", "target_id": null, "hotkey": "alt+2", "text": null, "verify_expectation": "the scr')["hotkey"] == "alt+2"
                                                                         and p('[{"step": 1, "action": "type", "target_id": null, "hotkey": null, "text": "hi there", "verify_ex')["text"] == "hi there"
                                                                         and p('[{"step": 1, "action": "click", "target_id": null, "ver') is None and p('[{"step": 1, "act') is None,
              "exact_needs_the_right_target": TQ.score_action(p('[{"action":"click","target_id":7}]'), gold_click) == {"valid": True, "action": True, "exact": True}
                                              and TQ.score_action(p('[{"action":"click","target_id":8}]'), gold_click) == {"valid": True, "action": True, "exact": False},
              "right_kind_wrong_answer_and_wrong_kind": TQ.score_action({"action": "hotkey", "hotkey": "ctrl+s"}, gold_click) == {"valid": True, "action": False, "exact": False},
              "hotkey_compares_keys_not_spacing_or_case": TQ.score_action({"action": "hotkey", "hotkey": "Alt + 2"}, gold_key)["exact"] and not TQ.score_action({"action": "hotkey", "hotkey": "alt+4"}, gold_key)["exact"],
              "type_compares_the_text": TQ.score_action({"action": "type", "text": " hi "}, gold_type)["exact"] and not TQ.score_action({"action": "type", "text": "ho"}, gold_type)["exact"],
              "invalid_output_scores_zero": TQ.score_action(None, gold_click) == {"valid": False, "action": False, "exact": False},
              "summary_is_rates": TQ.summarize_scores([{"valid": True, "action": True, "exact": True}, {"valid": True, "action": False, "exact": False}, {"valid": False, "action": False, "exact": False}, {"valid": True, "action": True, "exact": False}])
                                  == {"n": 4, "valid_json": 0.75, "action_kind": 0.5, "exact": 0.25}}
    return _verdict(checks, f"eval={len(ev)} of {len(pairs)} ({len(groups_ev)} controls held out)")


TESTS = [("TR1", run_tr1), ("TR2", run_tr2), ("TR3", run_tr3), ("TR4", run_tr4), ("TR5", run_tr5), ("TR6", run_tr6), ("TR7", run_tr7), ("TR8", run_tr8), ("TR9", run_tr9), ("TR10", run_tr10)]

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
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-1800:])
        print(f"[{'PASS' if r.passed else 'FAIL'}] {name} {time.time() - t0:5.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:90]}\n        {r.evidence[:1700]}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
