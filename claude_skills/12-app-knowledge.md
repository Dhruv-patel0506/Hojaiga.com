---
name: hojaiga-app-knowledge
description: Procedural app knowledge system in organ_47_app_intelligence.py - trust order learned over catalog over archetype over distilled, confidence climb and erosion mechanics, and the direct-control gate reserved for verified shortcuts.
---

# Skill 12 — Pro App Knowledge (`organ_47_app_intelligence.py`)

Scanning finds **where** the button is. organ_47 decides **what a pro would do**. This is
the answer to "knowledge, not just scanning": the bot should operate any app like someone
who has used it for years, and that knowledge is *learned at runtime*, never hardcoded
per app (skill 00 L3).

## The trust order (highest → lowest)
```
learned  >  catalog  >  archetype  >  distilled/LLM-briefing
```
- **learned** — a shortcut/path this system personally *verified* on this machine. Only
  these can take **direct control** (execute without the LLM). Muscle memory.
- **catalog** — curated generic affordances (e.g. "most editors: Ctrl+S = save").
- **archetype** — app-class defaults (e.g. "IDE-like app → File menu → Export").
- **distilled / LLM-briefing** — a one-off guess from the Gatekeeper.

**The law (skill 08 A3):** an *unverified* archetype/guess can NEVER take direct control —
it only **ranks hints for the judge.** Direct execution is reserved for verified/learned
records. This is what makes unattended runs safe from random destructive clicks.

## Confidence dynamics (measured in test W8)
- Start ~0.85. On each **verified** success, climb toward the cap **0.97**.
- On **failure**, erode **−0.25** (e.g. 0.85 → 0.60). Below threshold it stops being a
  direct-control candidate and reverts to hint-only until re-verified.
- A confident learned shortcut (confidence ≥ `PRO_SHORTCUT_CONF = 0.70`, and verified) is
  executed directly, skipping the LLM entirely → fast.

## How knowledge is created
1. The autonomy loop (skill 03) completes a goal and **distills a recipe** (organ_04) from
   ≥2 verified PASS steps. That recipe becomes a future `learned` record.
2. organ_47 consults learned/catalog/archetype before the judge is asked, so the 5th run of
   "export a mesh in Blender" is near-instant: the compiler is handed a verified prior
   ("File→Export→glTF, picker node #f03 role=menuitem") instead of re-perceiving.

## Integration points
- `desktop_grounding.DesktopAutonomyLoop` attaches organ_47 in its constructor; if the organ
  is unavailable the loop still runs on pure perception (graceful).
- The judge receives organ_47's ranked candidates (≤8) + the live element list; it picks one
  id+verb. organ_47 never clicks — it advises; verification decides.

## Rules for extending it
1. Add knowledge as **data** (learned records, generic archetypes), never as
   `if app == "X": do Y` branches.
2. Anything not backed by a verified outcome is hint-only. Guard the direct-control gate.
3. New app-classes get an *archetype* (generic affordances), not a per-app script.
4. Prove learning works with a W8-style test: temp DB, archetype route, guess-never-learned,
   verified-shortcut-trusted, climb-to-cap, failure-erodes.

## Direct control needs TWO verified successes (backlog 6.4, 2026-10-05)
`steps.hits` counts EVERY recorded outcome (a FAIL bumps it too) and a first PASS starts at confidence 0.85, so a single lucky
trace used to cross `PRO_SHORTCUT_CONF` and take direct control (a weak "the UI changed" PASS on Ctrl+N once poisoned a step).
Now `steps.successes` counts verified PASSes only (a failure takes one away) and `_consult_intel` hands a learned shortcut to
direct control only at `successes >= HOJAIGA_DIRECT_MIN_SUCCESSES` (default 2). Same rule in `knowledge_bridge.direct_ok`.
Tests: KB1 (single pass stays a hint, second pass allows it, failure revokes, old databases migrate to one verification).

## Where scan knowledge enters the loop
organ_47 is the loop's own step memory. Everything a scan or an exploration learns (menu IDs, accelerators, dialog schemas, how
the app takes input) lives in organ_48 + `knowledge_store` and reaches the loop through `knowledge_bridge` (hint / direct route /
declared-accelerator attempt / precondition + mode repair / transition recording). See `16-app-mastery.md`.
`classify_archetype` asks the EVIDENCE profile first (`static_knowledge.infer_profile`) and name tokens only for an unknown app.
