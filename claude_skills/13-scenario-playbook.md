---
name: hojaiga-scenario-playbook
description: Scenario playbook - every plausible desktop/web automation situation mapped to its physical execution path through the organ system, with fallbacks when a tier cannot run.
---

# Skill 13 — Scenario Playbook (every plausible situation & its physical path)

When a task looks unusual, find the row. The design intent: **fully robust and autonomous**
means every scenario has a named detection, a primary path, and a bounded fallback.

| # | Scenario | Detected by | Path | Fallback |
|---|---|---|---|---|
| 1 | Standard desktop UI (Settings, Office, Explorer) | tier 1 returns ≥1 named target | UIA Invoke | tier 2 rect + click |
| 2 | Canvas / GL app (Blender, games) | tier 1 returns <5 nodes | tier 4 OmniParser on PrintWindow | region-delta verification only |
| 3 | Custom-drawn / UIA-sparse app | structural miss on target_text | tier 3 OCR pseudo-elements | tier 4 |
| 4 | Modal popup / installer wizard | WRONG_STATE + PopupSubsystem pattern | auto-dismiss known-safe (Next/OK/Allow) | HITL |
| 5 | UAC / permission shield | class `#32770` + secure desktop | **never auto-accepted** — capsule "needs your input" | hard stop, checkpoint |
| 6 | Native Open/Save dialog | title regex + Edit + toolbar | NativeFilePicker (set path into the edit, not synthetic keys) | tier 4 click on button label |
| 7 | App crash / "Not Responding" | hung flag / IsWindowVisible | kill → relaunch via organ_40 → resume from checkpoint | HITL with checkpoint path |
| 8 | Splash / loading screen | window exists ∧ element list stable across 2 samples | exponential backoff 0.5→1→2→4→8 s, cap 60 s | HITL |
| 9 | Pointer clip (foreign SetCursorPos fails) | probe set+get delta before acting | prefer PostMessage/Invoke; overlay cursor still glides, never blocks | vision-click |
| 10 | Multiple windows/tabs for one app | window enumeration returns >1 match | one DAPSession per app + smooth switching; capsule names active app | explicit window id in contract |
| 11 | Destructive verb (Delete/overwrite/send) | verb ∈ destructive set | require file snapshot of affected paths first | else HITL (audit log) |
| 12 | Long run, hours (3D-chair case) | checkpoint after every PASS | resume = relaunch → replay learned recipe → re-ground (fingerprints re-validate bboxes) | recipe invalid ⇒ fall back to ladder |
| 13 | Login wall (web) | `_detect_login_page` | HITL 120 s → cookie extract → seed | per-agent isolated profile |
| 14 | Web + desktop mixed task | compiler emits mixed step graph | handoff per step; browser reused on 9222, never relaunched | organ_40 direct launch (picker-free) |
| 15 | LLM judge returns garbage | id not in the ≤8 candidates | re-ask once, then 3-strike HITL flip | stronger judge via `HOJAIGA_JUDGE_MODEL` |

## How to use this table
- **New failure mode** → add a row here first (detection + path + bounded fallback), THEN code it.
- Every row must end in either a verified PASS or a **bounded** stop (HITL + checkpoint). A row
  that can loop forever is a bug by definition (skill 00 L6).
- The self-correction meta-loop (3-strike judge rule) is what makes this *autonomous*, not just
  retrying: it converts unbounded LLM flailing into a bounded, recoverable stop that a human
  answers once and the system learns from.
