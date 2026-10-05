---
name: hojaiga-skill-set-index
description: Index of the Hojaiga Claude skill set - the 14 fragmented skill files, what each covers, and the recommended load order starting from the 8 laws in CLAUDE.md.
---

# Hojaiga Automation — Claude Skill Set (Index)

> Drop this folder into your context (or reference it from CLAUDE.md). Each file is a
> self-contained skill; load the ones relevant to the task. All rules are REAL rules
> learned from live debugging of this codebase — not theory.

## Parts

| File | Skill | Load when… |
|---|---|---|
| `00-master-rules.md` | Non-negotiable project laws (free/local/no-API, honesty, dynamic) | Always — every task |
| `01-architecture.md` | Organ system map: what lives where, how data flows | Touching any `core_organs/` module |
| `02-environment.md` | Exact venv, PYTHONPATH, PowerShell command patterns | Running/installing anything |
| `03-autonomy-loop.md` | Perception ladder, verify-don't-trust, checkpoints, readiness | Working on desktop_grounding / operate tool |
| `04-popup-defense.md` | organ_29 tiered popup pipeline + Tier-2.5 lexical intent | Any popup/modal work |
| `05-virtual-cursor-hud.md` | Multi-agent overlay cursor engine + status capsule | visual_cursor / HUD work |
| `06-dependency-policy.md` | Free-only dependency law, version pins, local models | Installing/upgrading any library |
| `07-testing.md` | System intelligence suite, honest evidence format | Adding/running tests, reporting results |
| `08-safety-hitl.md` | Destructive-action guardrails, human-in-the-loop law | Anything that clicks/types/confirms |
| `09-pitfalls.md` | Catalogue of every bug class we've actually hit | Before fixing anything UI/vision related |
| `10-performance.md` | Latency budgets, caching rules, CPU-vision discipline | Any perf work or slow-test triage |

## One-paragraph project summary

Hojaiga is a **fully local, zero-paid-API desktop/web automation agent** built from
"organs" (`All codes/core_organs/organ_NN_*.py`). Its core loop perceives any app through
a cost-ordered ladder (UIA → Win32 → OCR → OmniParser vision), decides via a **locally
running LLM** (Gatekeeper on port 11435), acts through the cheapest effective input path
(Invoke → PostMessage → SendInput), and **verifies every action with before/after
snapshots** — an action is never believed, only verified. Knowledge of apps is learned at
runtime (organ_47 pro-knowledge + organ_04 recipes), never hardcoded per app. Unknown or
dangerous situations escalate to the human instead of guessing.
