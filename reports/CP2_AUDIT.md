# Checkpoint 2 audit (2026-10-25) - Qwen3-VL-2B base vs SFT adapters vs RAG pipeline

All numbers below come from `model.generate()` on the RTX 3050 in this run (`audit/cp2_eval.py`).
Raw per-sample data: `reports/cp2_head_to_head*.json`. Gatekeeper: `reports/cp2_gatekeeper_v2.json`.

## Suites
- **heldout**: 25 per kind (click/drag/hotkey/type) from `qwen_10k_test_ready.jsonl`, no exact-prompt overlap with train. Same synthetic template family as training.
- **dynamic**: 24 generated prompts, 3-4 elements, shuffled ids, distractors, natural goal wording. Gold fixed by construction.
- **popup**: 20 trap dialogs from 12 families, safe control and trap at shuffled ids (random-guess floor = 33%).

## Results (kind = action kind correct, exact = kind + target_id/hotkey correct)
| Config | heldout kind/exact | dynamic kind/exact | popup safe-pick |
|---|---|---|---|
| base Qwen3-VL-2B | 16% / 14% | 54% / 42% (valid JSON 71%) | 0% (valid JSON 70%) |
| broad adapter (3000 steps) | 75% / 75% | 58% / 38% | 35% |
| balanced adapter (400 steps) | 74% / 74% | 75% / 46% | 35% |
| pipeline v1 (hint + regen) | 99% / 99% | 25% / 21% | 95% |
| pipeline final (no hint, no regen) | 100% / 100% | 58% / 38% | 95% (19/20) |

Pipeline = broad adapter + gatekeeper v2 (drag routed to Tier-2 canvas drag) + popup resolver.

## What the numbers mean
- Gap A: gatekeeper `drag` 0% -> 97.8%, balanced 74.7% -> 99.4%. The adapters still cannot emit `drag` (zero drag rows in their training, schema is click|hotkey|type); the +25 points on heldout is the drag route.
- Gap B: 35% -> 95%, all from the popup resolver (label semantics). Single miss: "Export Settings" ties the safe "Go Back".
- Heldout 100% is template recognition: training rows are synthetic, one element at `#1`, modality encoded in the element label ("Primary Input Box", "Ctrl+Shift+P", "Canvas Safe Box").
- On naturally worded multi-element prompts the pipeline equals the broad adapter (58% / 38%): click 100%, hotkey kind 100% but key wrong, type 33%, drag 0%. This is the real dynamicity gap.
- The gatekeeper says "click" with ~100% confidence on natural type/hotkey/drag goals. Letting it hint or force Qwen (v1) cut dynamic kind to 25%. Used only for the drag route in the final config.

## Not done / not verified
- Checkpoints 1, 3, 4 (live app scans) not run: need the user's go (`HOJAIGA_ALLOW_LIVE`).
- Qwen VLM visual-dot (SoM) config not evaluated: the "50k" dot dataset has 500 rows and no adapter was trained on it.
- popup_resolver and gatekeeper v2 are not wired into the production executor/dispatcher yet.
- n is small (100 / 24 / 20); single run, greedy decoding.
- Old scorecards (`evaluate_full_rag_and_qwen.py`, `fix_all_groups_rag_and_eval.py`) print hardcoded base/adapter columns and a hardcoded 100% valid-JSON for the "pipeline"; do not cite them.
