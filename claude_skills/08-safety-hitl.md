# Skill 08 — Safety & Human-in-the-Loop (HITL) Law

Autonomy without guardrails is a liability. These rules make the bot trustworthy enough to
run unattended. They are absolute.

## A1 — Never auto-accept these categories
| Category | Examples | Required behaviour |
|---|---|---|
| **Elevation / credentials** | UAC "wants to make changes", password/PIN prompts, Windows Security | `need_human` — fire **zero** keystrokes/clicks, escalate |
| **Destructive commit** | "Save changes?", "Are you sure", "Permanently delete", "Format", "Overwrite" | `need_human` — never confirm on the user's behalf |
| **Payment / legal consent** | purchase confirm, ToS binding, "Buy", subscription | `need_human` |

Rationale: escape/dismiss may "work" mechanically, but silently cancelling or confirming a
consequential dialog is worse than stopping and asking. organ_29 Tier 2.5 enforces this.

## A2 — The 3-strike judge rule
If the LLM judge returns an invalid or rejected choice **3 times in a row**, do NOT attempt
a 4th. Flip the capsule to `input_needed` ("Agent needs your input"), freeze state, write a
checkpoint. This converts unbounded LLM flailing (observed live) into a bounded, recoverable
stop. A human answers once, the recipe is learned, the class of failure never recurs.

## A3 — Direct control requires verification
- A **learned** shortcut with confidence ≥ 0.97 (e.g. Ctrl+S once verified) may execute directly.
- An **unverified** archetype/guess/LLM suggestion may ONLY rank hints for the judge —
  never act. This is the trust order in organ_47: learned > catalog > archetype > distilled.
- Confidence climbs 0.85 → 0.97 on verified success; erodes −0.25 on failure.

## A4 — Destructive verbs need a pre-snapshot
Before any verb in the destructive set (delete, overwrite, send, format, empty):
require a file/state snapshot of affected paths, else HITL. Audit log already exists — write to it.
`operate_desktop_tool(..., allow_destructive=False)` is the default; only flip it when the
task explicitly authorises it.

## A5 — Verification is the safety net
No action is believed until a before/after snapshot diff proves the outcome (skill 03).
WRONG_STATE (unexpected dialog/menu/tab) → run popup mitigation → re-ground → replan, never
blindly continue. This is what stops a misclick from cascading.

## A6 — Prefer input paths that don't fight the user
Order: `UIA Invoke() → PostMessage(WM_LBUTTON) → SendInput`. Invoke/PostMessage work in the
background and under a pointer clip and don't steal focus; SendInput (real cursor) is last
resort. Never `SetForegroundWindow`-hijack the user's active app gratuitously.

## A7 — The capsule is the contract with the human
Whatever the bot is doing, the floating capsule must reflect `working` / `input_needed` /
`done` with a short plain-language text. If the bot blocks, the human must see WHY and what
input is needed. An unattended run that silently dies is a failure even if no crash occurred.

## A8 — Offline & local = privacy-preserving
Never send screen contents, element trees, credentials, or task text to any remote host.
All reasoning is local (`127.0.0.1`). Session cookies stay in the local vault (organ DB).
This is both a cost rule (skill 06) and a safety rule.
