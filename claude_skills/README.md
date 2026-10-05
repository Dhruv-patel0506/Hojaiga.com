---
name: hojaiga-skill-set-index
description: Index of the Hojaiga Claude skill set - the 17 skill files, what each covers, and the recommended load order starting from the 8 laws in CLAUDE.md.
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
| `11-web-automation.md` | Web / CDP automation, session cookies, URL guards | Browser or web-app tasks |
| `12-app-knowledge.md` | organ_47 pro knowledge: trust order, confidence climb/erode, the direct-control gate | Touching learned shortcuts / hints |
| `13-scenario-playbook.md` | Situation -> execution path map | Planning how a task should run |
| `14-lifecycle-checkpoints.md` | A-H lifecycle checkpoint chain, risk gate, template-first | Task intake / lifecycle work |
| `15-knowledge-accuracy.md` | MEASURED accuracy + timings of first-contact knowledge, tasks, vision | Quoting or improving any number |
| `16-app-mastery.md` | The app-knowledge engine: static harvest, frontier exploration, conventions, unified registry, knowledge bridge | Any "how does this app work" question / `organ_63`, `static_knowledge`, `command_registry` |

## One-paragraph project summary

Hojaiga is a **fully local, zero-paid-API desktop/web automation agent** built from
"organs" (`All codes/core_organs/organ_NN_*.py`). Its core loop perceives any app through
a cost-ordered ladder (UIA → Win32 → OCR → OmniParser vision), decides via a **locally
running LLM** (Gatekeeper on port 11435), acts through the cheapest effective input path
(Invoke → PostMessage → SendInput), and **verifies every action with before/after
snapshots** — an action is never believed, only verified. Knowledge of apps is learned at
runtime (organ_47 pro-knowledge + organ_04 recipes), never hardcoded per app. Unknown or
dangerous situations escalate to the human instead of guessing.
