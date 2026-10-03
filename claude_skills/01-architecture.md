# Skill 01 — Architecture Map (Organs)

Everything lives under `All codes/core_organs/`. Organs are numbered modules wired
together by the CrewAI engine. Import path is `core_organs.organ_NN_...`.

## The organs you must know

| Organ | File | Responsibility |
|---|---|---|
| **01** | `organ_01_crewai_engine.py` | The brain/orchestrator. Builds agents, wires tools, routes tasks. Hosts `operate_desktop_tool`, `type_text_tool`, `launch_app_tool`. ~5400 lines. |
| **03** | `organ_03_*` | Memory (working store, TTL, session rooms, snapshots). |
| **04** | `organ_04_*` | Knowledge base — ingests distilled **recipes** (procedural how-to), natural search. |
| **19** | web/CDP scanner | Chrome DevTools Protocol accessibility scan on `:9222`; emits same element contract as desktop tiers. |
| **24** | `organ_24_dap.py` | DAP = Desktop Action/element Profile store. Batch element profiles (1.5 ms/element cached round-trip). |
| **29** | `organ_29_popup_handler.py` | Popup defense (see skill 04). `DesktopInteractionManager`. |
| **30** | `organ_30_app_scanner.py` | Deep app scanner — walks UIA/Win32/OCR, learns element trees, in-window roadblock mitigation. |
| **31** | `organ_31_visual_perception.py` | Screen OCR via pytesseract + ImageGrab (full-screen text). |
| **36** | compiler | Task text → ordered step JSON (deterministic; LLM never plans here). |
| **40** | `organ_40_app_launcher.py` | Dynamic app resolution + **direct** launch (`resolve_and_launch`). Picker-free Chrome. |
| **41** | continuous scanner | Change detection cycles on a running app. |
| **44** | `organ_44_enhanced_scanner.py` | Playwright / FlaUI / **OmniParserScanner** (vision tier) / DOM graph parsers. |
| **47** | `organ_47_app_intelligence.py` | **Pro app knowledge**: learned > catalog > archetype > distilled trust order; confidence climb/erode. |
| — | `database_manager.py` | SQLite SSMS store: `check_popup_history`, `log_new_pathway`, `generate_layout_hash`, cookie vault. |
| — | `desktop_grounding.py` | The closed autonomy loop + perception ladder + verifier (see skill 03). |
| — | `visual_cursor.py` | Multi-agent overlay cursor engine (see skill 05). |
| — | `cns_bridge.py` | IPC (named pipes/localhost) between AppAgent (detector) and HostAgent (organ_29 resolver). |

## The element contract (the glue)
Every perception source (UIA, Win32, OCR, vision, web/CDP) produces ONE flat list shape:
```
{id, name, role, bbox(x,y,x,y), provider_tier, confidence}
```
The actor and judge never know or care whether an element came from a COM tree walk or a
neural net. **When you add a new perception source, it MUST emit this shape** so organ_01
holds one mental model for Chrome and Blender alike.

## Layering (top → bottom)
```
User task text
  → organ_36 compile (steps JSON)          [deterministic]
  → organ_01 route + agent tools           [operate_desktop_tool is the high-level one]
  → desktop_grounding loop                 [perceive→decide→act→verify→recover→checkpoint→learn]
      ├─ perceive: ground() ladder         [UIA→Win32→OCR→vision]
      ├─ decide:   organ_47 knowledge + Gatekeeper LLM judge
      ├─ act:      Invoke→PostMessage→SendInput
      ├─ verify:   DesktopVerifier snapshot diff → PASS/NO_CHANGE/WRONG_STATE
      ├─ recover:  organ_29 popup / retry ladder / HITL
      └─ learn:    distill_recipe → organ_04 + DB pathway
```

## Key rule about the brain
The **only** place an LLM decides is the judge step (≤8 candidate elements → one id+verb,
model switchable via `HOJAIGA_JUDGE_MODEL`). Planning (organ_36), perception, action and
verification are all deterministic code. Keep it that way — do not move planning into the LLM.
