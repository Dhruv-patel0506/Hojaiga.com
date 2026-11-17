# HOJAIGA Deep App Knowledge Specification

**Status:** living design doc · **Empirical basis:** OBS Studio 32.2.2 perception spike, 2026-10-07 (`_e2e_tmp/omni_uia_spike.py`, `evidence_spike_report.json`, `evidence_spike_omni.png`)
**North star:** the system gains *professional* knowledge of how an app operates — not by counting buttons, but by **measuring what each control does** — and can state, with evidence, how any app works even better than a human who "has used it before."

---

## LAW 0 — Universal & app-agnostic (the "holographic plate")

The scanner is a plate: **put any window on it and it fully scans and reports, with zero knowledge of which app it is.** No named-button targeting anywhere in the discovery path.

- **Discovery is by pattern, not by name.** A control is a target iff it exposes an actionable UIA pattern (`Invoke/Toggle/ExpandCollapse/SelectionItem/RangeValue/Scroll/Value-set`) — never because its label matches a word list.
- **Learn by effect, click everything.** Every actionable control is probed within budget; the *observed* state delta (new window, control-set change, value change, region delta) is what classifies it. The system keeps a work-list of un-probed affordances until `exhausted`.
- **Recursion is generic.** Any newly-revealed surface (menu, dialog, master/detail pane, wizard page) is treated as a sub-window and re-scanned by the same rule — no app-specific "the '+' opens a dialog" logic.
- **Universal revert = open-then-cancel.** We learn a dialog by opening it and cancelling, never by committing. Safety comes from *not pressing the final action*, so no per-app deny-list is required.
- **Name heuristics & oracles are OPTIONAL priors only** — they may *order* probes under budget pressure or *cross-check* coverage where an app exposes one; they must never gate what is discovered, and the core must never reference a specific app by name.

---

## 0. Axiom — knowledge is measured causality, never assertion

A capability is only committed when it is a verified state delta:

```
Capability = { Trigger_Control, Pre_State_Hash, Action_Pattern,
               Post_State_Hash, Observable_Delta, Risk_Class, Evidence }
```

- No `Evidence` (before/after snapshot + delta + timestamp) → the row is `unverified` and the brain **may not** claim it.
- This is the anti-"vibes" rule. It is the whole point of the system.

---

## 1. Perception tier hierarchy (measured, not assumed)

The spike on OBS main window (1802×986) produced these real numbers:

| Tier | Tool | Result on OBS | Cost | Role |
|---|---|---|---|---|
| **Tier 0 — Spine** | Windows **UIA** (`uiautomation`) | **53 actionable** controls (of 136 nodes) in **0.19 s** | ~0 VRAM | **Primary** for actuation, naming, verification. Deterministic addresses + patterns. |
| **Tier 1 — Candidate filler** | **OmniParser** (YOLO icon det + Florence-2 caption) | 85 icon boxes in **1.86 s**; 32 "UIA-blind" (see §1.3) | YOLO ~0.6 GB VRAM / RSS→1.2 GB; **Florence 39.9 s**, VRAM→4.1 GB, RSS→1.4 GB | **Secondary**: surface controls UIA under-exposes (sliders/meters/icon-only). Hypotheses only. |
| **Tier 2 — Semantic check** | **Qwen3-VL-8B** (local :8081) | — | shares the 6 GB card | **Gated to verification checkpoints only**, never the raw poll loop. |

### 1.1 The rule the pixels forced
> **UIA where it exists. OmniParser where UIA has no element. Self-consistency (`exhausted`) to prove coverage — an oracle only sharpens it when the app happens to expose one.**

- If a control has a UIA address → actuate via its **COM pattern** (`Invoke/ExpandCollapse/Toggle/SelectionItem/RangeValue/Scroll`). Never a pixel click.
- **What counts as a target is decided by pattern presence, never by the control's name** (Law 0).
- OmniParser results are **candidates to verify by effect**, never trusted for names/labels.

### 1.2 Why OmniParser is NOT the actuation authority (measured)
Of OmniParser's 32 "UIA-blind" boxes on OBS:
- ~a dozen were **real** but only because they are `Slider`/`Button` controls (Audio-Mixer faders, mute/headphone icons) that a naive 4-pattern filter under-counts → Omni's genuine value-add.
- ~a dozen+ were **false positives**: CPU/FPS/time stats text, the Sources empty-state "?" placeholder art, window edge/scrollbar, black-preview "Empty screen".
- Florence-2 labels were **unreliable**: `"M0,0L0,5 4.5,5z"`, `"Have and Share"`, `"12, October, 2014"`, `"Measuring"`.
→ Making a VLM parser the naming/actuation authority re-imports the hallucination failure this system exists to remove.

### 1.3 Measurement caveats to fix in the real prober
- "UIA-blind" must be computed against **all** UIA-addressed nodes (136), not just the actionable subset (53) — otherwise sliders/meters are mislabelled as gaps.
- Gate every Omni candidate by `conf >= 0.30` (most OBS noise was `< 0.20`) and drop boxes overlapping the preview canvas / stats strip / window chrome.
- OCR was intentionally excluded from the spike (first-run model download). Re-enable via bundled PaddleOCR (installed) for offline text grounding.

### 1.4 Measured contrast → the tier is CHOSEN PER APP, not fixed (Blender spike, 2026-10-08)
The same read-only plate run on two apps inverted the roles:

| | OBS (Qt) | Blender 5.2 (OpenGL / `GHOST_WindowClass`) |
|---|---|---|
| UIA actionable / nodes | 53 / 136 | **4 / 6** |
| OmniParser credible boxes (conf≥0.30) | ~12 (mostly noise) | **156** |
| Effective primary | UIA | **Vision (UIA is blind)** |

Blender draws its whole UI on a GL canvas → the accessibility tree is empty. A fixed "UIA-primary" design fails catastrophically here. **Correct universal rule:** *measure the tree, then adapt* —
- If UIA exposes a rich actionable set relative to the visible UI → UIA is the spine, vision fills icon-only gaps.
- If UIA is thin (few actionable vs the rendered UI) → **vision (OmniParser) becomes the primary discovery source** for that app; actuation for those regions falls back to `PostMessage` at the detected centroid (Law 0's generic revert still applies).
- The decision is made from **observed tree density vs. screenshot content**, never from an app name (Law 0).

---

## 2. Deep Dialog Protocol (Master/Detail & Wizards) — generic, effect-triggered

*This is not a special case for OBS's "+". It runs automatically whenever ANY actionable control's probe produces a new window — the same code path for every app.*

1. **Trigger:** a probe on any pattern-exposing control produced a new top-level window (classified by the *observed* effect, not by the control's name).
2. **Await** the new window handle (event-driven, not `sleep`).
3. **Register** the left pane (`List`/`Tree`/`Table`). Enumerate **every** item.
4. **Exhaustive sweep:** for each left item → `SelectionItem.Select()` → hash the right pane (`control_set_hash` + cheap `cv2.absdiff` on the pane bbox) → store `{item_name: right_pane_schema_json}`.
5. **Wizard follower:** if an enabled `Next|Continue|>|Finish` exists → record page schema, advance (**depth ≤ 4**).
6. **Restoration:** invoke `Cancel`/`Escape`/`WM_CLOSE`; **assert the main-window state hash returned to baseline**. If it did not → mark probe `unsafe-revert-failed`, halt that branch.
7. **Never commit.** A dialog is learned by opening + cancelling, never by OK.

---

## 3. Effect-differential settle loop (replace fixed sleeps)

- **Reject continuous SSIM** (CPU-heavy, chokes during UI animation).
- Settle = `UIA control-set hash` **OR** `cv2.absdiff` pixel-delta over the affected bbox, with a short idle floor (~80 ms stable). Reuse `organ_63`'s existing control-set hashing.
- A probe "did something" iff: new window handle, control-set hash change, value/focus change, or region delta > threshold. Otherwise `no_effect` — recorded honestly.

---

## 4. Completeness proof (primary) + optional oracles (secondary)

**Primary, app-agnostic proof = `exhausted=True`:** a second recursive pass over the same window discovers **0 new actionable edges** (nothing left un-probed). This works on *any* app with no external knowledge and is the guarantee we rely on.

**Optional cross-check — only when an app happens to expose a machine-readable command registry:** `Discovered_Actions / Oracle_Manifest_Actions`. This is a *pluggable oracle adapter* behind a generic interface; **the core scanner never references a specific app by name** and runs identically with no oracle present.

| App (example) | Optional oracle | Note |
|---|---|---|
| OBS Studio | `obs-websocket` input/scene list | adapter only; not required |
| Word / Office | `win32com` `CommandBars` / Fluent UIA names | labels only, never actuation |
| LibreOffice / Blender / GIMP / VS Code | `.uno:*` / `bpy` / PDB / `contributes.commands` | adapter only |
| **Any app with no oracle** | **none** | `exhausted` self-consistency still proves coverage |

Where an oracle exists it sharpens the coverage number the user cannot otherwise obtain; where none exists, `exhausted` is the honest, universal proof.

---

## 5. Enumeration completeness (R2) — nothing stays hidden

After the passive tree, enumerate **every** named+enabled control exposing any actionable pattern, including:
- every **ribbon group** (ribbons are containers, not leaves), every **More ▾ / gallery / collapse-arrow**,
- **dock/panel headers** and footer/tray buttons,
- **list items** (via `SelectionItem`),
- **right-click context menus** (`ExpandCollapse`/`MenuExpand` → read → collapse).
Emit a **coverage manifest** (`{menus, menu_items, toolbar_buttons, panel_actions, sliders, dialogs_discovered, ...}`) + `exhausted` re-check.

---

## 6. Actuation integrity (product laws — non-negotiable)

- **No physical cursor.** UIA COM patterns first; OmniParser-only regions fall back to `win32gui.PostMessage(hwnd, WM_LBUTTONDOWN/UP, …)` at the bbox centroid (still headless).
- **Restore state** after every probe; verify baseline hash.
- **Safety is generic, not name-based.** The universal revert is *open-then-cancel*: we learn a control by observing what it opens and then cancelling/closing, **never by pressing the final commit**. Risk is judged by **observed reversibility** (did it open a cancellable surface? is the effect undone by Cancel/Escape/WM_CLOSE?), not by a word list. An action whose effect is neither cancellable nor undoable is *catalogued as existing* (via recursion into where it is reachable) but not committed.
- **Word lists (e.g. "Record/Stream/Delete") are only a soft prior** to order probes under budget pressure — they never decide what is safe to click, and the core does not depend on them.
- **Sandbox targets:** blank scratch doc / OBS test profile — learn "Start Recording" exists without starting one.

---

## 7. Per-host / per-version identity + portability

- Key = `(app_family, exe_path + PE version-hash, UIA structure signature, host_id)`. Reuse only on full match; new host/build/structure-drift → re-scan.
- **Portable capability IDs** decouple logical actions from physical control IDs → cross-version Word maps by name/resource/effect with per-version overrides; a new build is a *diff*, not a rebuild.

---

## 8. Knowledge schema (queryable "what leads to what")

`organ_48` behavior model + `organ_50` layout extend to:
- `bm_dialogs`: `left_items_json`, `pages_json`, `per_item_schema_json`.
- `bm_commands` / `bm_transitions`: `effect_class` (`opens-dialog | master-detail | wizard | inline-mutate | toggle-pane | opens-surface | destructive | none`), `reversibility`, `idempotent`, `risk`, `evidence_ref`, `confidence`.
- Capability graph (networkx-style edges) + semantic index (`sqlite-vec`/`chromadb`) for "find the control that mutes audio."

---

## 9. Runtime copilot loop (the OBS streamer case) — **deferred milestone**

Event-driven watcher (focus lost / scene mis-set / user command) → resolve to a graph path → execute headlessly → verify by outcome. **Separate from scanning/understanding** (R1–R8); do not block the knowledge core on it.

---

## 10. Acceptance tests (measurable, on-screen)

1. **Perception spike (DONE, baseline recorded):** UIA 53 actionable/0.19 s; Omni 85 boxes/1.86 s; true UIA gaps = sliders/meters, gated by conf≥0.30.
2. **Deep dialog:** on OBS, open Sources "+", sweep every add-type + right pane, cancel all, `exhausted=True`, baseline restored.
3. **Coverage vs oracle:** OBS grounded ≥ (oracle commands discovered / total) reported as a %; Word likewise via CommandBars.
4. **Exhausted re-run:** 2nd pass = 0 new actionable edges.
5. **End-to-end by artifact:** Word → a real `.docx` re-opened and asserted to contain requested headings/page-numbers/bibliography. OBS → actual scene/audio state reflects the command. **Judged by outcome, not by log.**
6. **`--live-visual`:** passive always-on-top overlay ring on the probed control + `evidence/<app>/NNN_step.png` + `trace.jsonl`, so the human can watch every action.

---

## 11. Environment gotchas discovered (so we don't re-learn them)

- **OBS launch:** must start with `cwd = D:\obs-studio\bin\64bit` **and** `--multi`, else it aborts with `Failed to find locale/en-US.ini` (it resolves `./data/...` from the working directory). Leftover `obs64.exe` parent/child pairs from force-kills also block startup — kill `/T` and confirm count 0 first.
- **6 GB VRAM budget:** Qwen3-VL-8B is resident on the GPU. YOLO fits (~0.6 GB). Florence-2 works but is slow (40 s) and adds VRAM pressure → **YOLO-only for candidate generation; Florence off the hot loop.**
- **Florence-2** loads its processor from HF `microsoft/Florence-2-base` (cached offline here); custom-code load can fail offline → degrade to YOLO-only and report it.
- **OCR:** use bundled **PaddleOCR** (installed) to avoid EasyOCR first-run downloads.

---

## 12. Decision log (what we deliberately did NOT adopt)

- **UI-TARS / UI-TARS-desktop** — rejected as *executor*: its NutJS/coordinate clicking moves the **physical cursor**, violating §6. (Planning schema may be studied.)
- **Windows Agent Arena** — rejected as a *runtime*: Azure-provisioned (cloud/cost), a benchmark not a scanner. For sandboxing (§6) we build a **local** throwaway-profile snapshot instead.
- **OS-Copilot / APEX** — clone to **read** its Actor/Critic→procedural-memory schema (informs §8), but keep our own `organ_48` store; do not run its framework.
- **OmniParser** — **adopted** (already local) as Tier-1 candidate filler, per §1.1.

---

## 13. Build order

1. Custom **prober** (§2,§3) on top of existing `organ_63` — the novel part; no repo provides it.
2. **Oracles** (§4): `pip install obs-websocket-py`; `win32com` (installed). Coverage % + `exhausted`.
3. **OmniParser Tier-1** wired as candidate-filler with conf/overlap gates (§1.3).
4. **Schema** upgrade (§8) + per-host identity (§7).
5. **`--live-visual`** harness (§10.6) — then re-run OBS + Word with the human watching.
6. **Copilot loop** (§9) — last.
