# Perception Flow Atlas

How the desktop automation should work physically: see, decide, act, verify, heal, learn. Matches `desktop_grounding.py` as it exists today.

**Core rule:** no action is ever believed. Every action is followed by a measurement of the screen, and only the measurement decides success. Every perception tier returns the same element shape: `id, name, role, bbox, provider_tier, confidence`.

## 1. Master loop for one goal

The full path from task text to a verified result, including every stop and recovery.

```mermaid
flowchart TD
  A["Task text"] --> B["Compiler organ_36 + VerbAlias organ_40 - deterministic goal list"]
  B --> C{"step kind"}
  C -->|web| W["organ_19 CDP :9222 - same element shape"]
  C -->|desktop| T["triage popups first"]
  T --> G["GROUND - perception ladder"]
  G --> H{"app hung or crashed?"}
  H -->|yes| R["organ_40 relaunch, wait for ready, re-ground"]
  R --> G
  H -->|no| E{"any elements?"}
  E -->|no| WS["WRONG_STATE - nothing grounded"]
  E -->|yes| S1["PRE-SNAPSHOT - structure hash plus pixel hash"]
  S1 --> F{"path in goal and file dialog open?"}
  F -->|yes| FD["Native file dialog rung - set path, confirm"]
  F -->|no| K{"learned shortcut or recipe?"}
  K -->|yes| SC["send shortcut - verified like any action"]
  K -->|no| J["CONSTRAINED JUDGE - pick 1 of max 8 ids plus a legal verb"]
  J -->|invalid x3| HITL["HITL - Agent needs your input - freeze and checkpoint"]
  J -->|destructive cue| HITL
  J -->|done| OK
  J -->|choice| A1["ACT - UIA Invoke, PostMessage, SendInput"]
  A1 --> SET["settle - wait until element tree stops changing"]
  SET --> V["POST-SNAPSHOT and verdict vs expectation"]
  FD --> V
  SC --> V
  V --> D{"verdict"}
  D -->|PASS| OK["checkpoint and capsule: verified fact"]
  D -->|NO_CHANGE| RL["recovery ladder"]
  RL --> V
  D -->|WRONG_STATE| PW["popup triage, re-verify, else re-ground and replan"]
  PW --> G
  OK --> N{"last goal?"}
  N -->|no| T
  N -->|yes| L["distill recipe into knowledge store"]
```

## 2. Perception: what physically happens

Cheapest real signal first. Pixels are only touched when a specific text target is missing from the structural tiers.

```mermaid
flowchart TD
  S["find_window by process and title"] --> U["TIER 1 UIA walk - COM accessibility tree, depth 12, 900 nodes, plus menus and flyouts as extra windows"]
  U -->|elements| M
  U -->|none| W32["TIER 2 Win32 walk - EnumChildWindows, GetWindowRect, GetWindowText"]
  W32 --> M["merge and dedupe by id"]
  M --> Q{"looking for target text and no structural match?"}
  Q -->|no| OUT["sorted element list - confident first, top to bottom"]
  Q -->|window minimized| SKIP["pixel tiers impossible - reported as skipped"]
  Q -->|yes| O["TIER 3 OCR - PrintWindow to PNG to tesseract words and boxes"]
  O --> VIS["TIER 4 Vision - PrintWindow to OmniParser detect and caption, budgeted per run"]
  VIS --> OUT
  SKIP --> OUT
```

| Tier | Mechanism | Pixels | Use for |
| --- | --- | --- | --- |
| 1 UIA | COM accessibility tree | no | Office, Explorer, Settings, browser chrome |
| 2 Win32 | child window enumeration | no | legacy and owner-drawn controls |
| 3 OCR | PrintWindow then tesseract | yes | custom-drawn text, sparse UIA |
| 4 Vision | PrintWindow then OmniParser | yes | canvases: Blender, games, GL |

Every call returns `tiers_ran`, `tiers_skipped` and `tier_ms`. A tier that did not run is reported as skipped, never assumed.

## 3. Verification: the trust core

```mermaid
sequenceDiagram
  participant L as Loop
  participant V as Verifier
  participant A as Target app
  L->>V: snapshot BEFORE - title, hash of sorted ids, 64x64 pixel hash
  L->>A: act - Invoke, PostMessage or SendInput
  L->>L: settle - re-walk until the tree is stable
  L->>V: snapshot AFTER
  V->>V: check title, element appeared or gone, file exists, region changed
  V-->>L: PASS, NO_CHANGE or WRONG_STATE plus evidence
```

Two signatures matter: the UIA tree does not change when you extrude a face in Blender, only pixels do. Structure catches dialogs and menus. The pixel hash catches canvases.

| Verdict | Meaning | Reaction |
| --- | --- | --- |
| PASS | after-state matches the postcondition | checkpoint, reinforce knowledge, next goal |
| NO_CHANGE | the app never reacted | climb the recovery ladder one rung |
| WRONG_STATE | UI changed into something unexpected | popup triage, re-ground, replan |

## 4. Self-healing

Recovery ladder for NO_CHANGE, in the order the code runs it. Each rung is re-verified.

```mermaid
flowchart LR
  A["act"] -->|NO_CHANGE| B["wait 0.3s and re-invoke"] -->|NO_CHANGE| C["PostMessage to control"] -->|NO_CHANGE| D["headless post_click at element center"] -->|NO_CHANGE| E["goal fail count up"]
  E -->|4 or more fails and learned key route| F["try shortcut once"]
  E -->|judge invalid x3| H["HITL"]
  F -->|still failing| H
```

Failure classes and what heals each:

```mermaid
flowchart TD
  X["Something went wrong"] --> C1{"what"}
  C1 -->|popup or installer| P1["popup triage - auto-dismiss known-safe Next, OK, Allow"]
  C1 -->|UAC, payment, delete| P2["never auto-accepted"]
  C1 -->|not responding| P3["kill, relaunch via organ_40, wait for ready, resume from checkpoint"]
  C1 -->|splash or loading| P4["wait until window exists and element list is stable"]
  C1 -->|judge garbage| P5["re-ask once, 3 strikes then HITL"]
  C1 -->|open or save dialog| P6["set path in Edit control, confirm, handle overwrite prompt"]
  C1 -->|menu not populated| P7["settle before verifying"]
  C1 -->|web login wall| P8["HITL, cookie extract, seed"]
  P1 --> back["re-ground and continue"]
  P3 --> back
  P4 --> back
  P5 --> back
  P6 --> back
  P7 --> back
  P2 --> stop["freeze, checkpoint, capsule: Agent needs your input"]
  P8 --> stop
```

The 3-strike rule turns unbounded LLM flailing into a bounded, resumable stop. A human answers once and the answer is learned.

## 5. n8n-style operator view

The same loop drawn as workflow nodes.

```mermaid
flowchart TD
  WH(["Webhook: task text"]) --> CMP["Function: compile - organ_36 + organ_40 aliases to steps JSON"]
  CMP --> SPLIT[["Split In Batches: one step at a time"]]
  SPLIT --> IFK{"IF kind"}
  IFK -->|web| CDP["HTTP / CDP :9222 - organ_19"]
  IFK -->|desktop| POP["Function: popup triage"]
  POP --> GND["Function: ground"]
  GND --> SW{"Switch: tier"}
  SW -->|1| T1["UIA query"]
  SW -->|2| T2["Win32 walk"]
  SW -->|3| T3["OCR PrintWindow"]
  SW -->|4| T4["OmniParser"]
  T1 --> MRG["Merge: element list"]
  T2 --> MRG
  T3 --> MRG
  T4 --> MRG
  MRG --> PRO{"IF learned recipe or shortcut?"}
  PRO -->|yes| SCUT["Execute: shortcut"]
  PRO -->|no| JDG["Function: judge - max 8 candidates to id plus verb"]
  JDG -->|invalid x3| HI["Wait: human input"]
  JDG --> SB["Function: snapshot BEFORE"]
  SB --> ACT["Execute: invoke, postmessage, sendinput"]
  SCUT --> SA
  ACT --> SA["Function: settle, snapshot AFTER, diff"]
  SA --> VD{"Switch: verdict"}
  VD -->|PASS| CK["Write File: checkpoint.json"]
  VD -->|NO_CHANGE| RT{"IF retries left?"}
  RT -->|yes| ACT
  RT -->|no| HI
  VD -->|WRONG_STATE| PD{"IF popup?"}
  PD -->|yes| DIS["Execute: dismiss"] --> GND
  PD -->|no| JDG
  CK --> LAST{"IF last step"}
  LAST -->|no| SPLIT
  LAST -->|yes| DST["Function: distill recipe"]
  DST --> DB[("DB upsert: knowledge store")]
  DB --> DONE(["capsule: done and digest"])
  DB -.next run.-> CMP
  HI --> RES(["resume from checkpoint after answer"]) --> GND
```

## 6. Learning loop

```mermaid
flowchart LR
  R1["Run 1: ladder, judge, maybe vision"] --> V1["verified PASS trace"]
  V1 --> D1["distill: app and goal key, element fingerprints, shortcut"]
  D1 --> K[("knowledge store")]
  K --> R2["Run 2 and later: recipe offered as hint or learned shortcut"]
  R2 --> V2{"verified?"}
  V2 -->|PASS| UP["confidence climbs"]
  V2 -->|fail| DOWN["confidence erodes, back to ladder"]
  UP --> K
  DOWN --> K
```

Learned knowledge only nudges the judge or sends a shortcut that is still verified. A stale recipe fails verification and the ladder takes over, so it cannot cause a silent wrong action.

## 7. Scenario matrix

| # | Scenario | Detected by | Path | Fallback |
| --- | --- | --- | --- | --- |
| 1 | Standard UI (Settings, Office, Explorer) | tier 1 finds target | UIA Invoke | tier 2 rect click |
| 2 | Canvas or GL app (Blender, games) | few UIA nodes, target missing | tier 3 then 4; pixel-hash verify | HITL |
| 3 | UIA-sparse custom-drawn app | structural miss on target text | OCR pseudo-elements | tier 4 |
| 4 | Popup or installer wizard | popup triage, WRONG_STATE | auto-dismiss safe buttons | HITL |
| 5 | UAC or permission shield | elevation cue | never auto-accepted | HITL and checkpoint |
| 6 | Native Open/Save dialog | dialog title and path in goal | set path in Edit, confirm | click by label |
| 7 | Crash or Not Responding | hung check | relaunch, wait ready, re-ground | HITL |
| 8 | Splash or slow load | element list unstable | settle and backoff | HITL |
| 9 | Foreign cursor clip | SendInput ineffective | Invoke or PostMessage first | vision-click (not built) |
| 10 | Several windows of one app | multiple matches | process and title; popups grounded as extra windows | explicit hwnd |
| 11 | Destructive element | destructive cue in name | needs allow_destructive | HITL, audit log |
| 12 | Hours-long run | checkpoint per step | resume session, relaunch, re-ground | ladder |
| 13 | Web login wall | login detector | HITL, cookie seed | isolated profile |
| 14 | Web plus desktop task | mixed step graph | browser reused on 9222 | direct launch |
| 15 | Judge returns garbage | id outside candidates | re-ask, 3-strike HITL | stronger judge model |
| 16 | Window minimized | window state | pixel tiers skipped and reported | restore window |
| 17 | Menu not yet populated | tree still changing | settle before verify | retry |
| 18 | Overwrite confirm | overwrite title check | handled in file-dialog rung | HITL if destructive |

## 8. Status, read from the code

in code UIA and Win32 tiers, popup-window grounding, OCR and vision gating with honest skip reporting, structural and pixel verifier, constrained judge with 3-strike HITL, destructive guard, native file dialog rung, shortcut path, NO_CHANGE ladder, popup triage, crash relaunch, settle, checkpoint and resume, recipe distill and recall.

unmeasured pytesseract, torch, easyocr and uiautomation are installed, so tiers 3 and 4 can run, but no latency or accuracy has been measured. Treat millisecond figures as expectations until read from real `tier_ms` reports.

not yet vision-click as a final recovery rung; an unattended end-to-end run of a long task such as the Blender chair; recipe retrieval quality on multi-step traces.

**Next step:** run `ground()` on five real apps (Settings, Notepad, Chrome, Blender, an Electron app), save each ladder report, and replace the expectations with measured numbers.

## 9. Measured results (benchmark, 2026-10-04)

From `benchmarks/grounding_reports/*.json`, CPU only. Forced escalation used a target text that cannot exist.

| App | UIA ms | UIA elems | OCR ms | OCR words | Vision s | Vision boxes |
| --- | --- | --- | --- | --- | --- | --- |
| Notepad | 188 | 29 | 505 | 11 | 62.0 | 30 |
| Settings | 1618 | 47 | 1897 | 123 | 105.1 | 69 |
| Chrome | 1297 | 142 | 1691 | 181 | 213.7 | 126 |
| Paint (canvas stand-in) | 568 | 127 | 739 | 16 | 278.4 | 101 |
| Claude desktop (Electron) | 312 | 9 | 3669 | 390 | 409.7 | 161 |
| VS Code | not groundable: title filter excludes "visual studio" (scenario 19) |  |  |  |  |  |

**Corrections to the earlier estimates:** UIA takes 0.2 to 1.6 s, not milliseconds. Vision takes 62 to 410 s per pass on CPU, not 1.5 to 4 s, so it is a learning-time cost, not a per-step tier. No PrintWindow black frames appeared on any app.

**Canvas hash:** in a controlled Tk window a canvas-only change moved the pixel hash while the structure signature stayed the same. The Paint test was inconclusive because posted clicks never drew. Blender is not installed, so the Blender pre-test is still open.