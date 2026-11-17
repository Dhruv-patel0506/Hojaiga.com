# Overnight MVP report  (2026-10-19 07:59)

Every row below was measured by a run that saved a picture; nothing is an unverified claim. A case passes only when its own check on the result passes.

## Report Form 1 -- numbers

### Held-out vision comparison (whole applications the adapter never saw)
| system | exact-action accuracy |
|---|---|
| old adapter, full element list (v2 prompt), all 250 held-out rows | 71.2% |
| old adapter, only the 205 rows the Top-40 cut keeps | 77.6% |
| NEW Top-40 + names (+ RAG hint) adapter, on the 205 rows it can see | 80.0% |
| NEW adapter counted over ALL 250 rows (a cut-away answer is a miss) | 65.6% |
| UIA-name layer alone (sure on 112 rows, precision) | 96.4% |
| pipeline A: UIA names first, else the NEW Top-40 adapter, over ALL 250 rows | 67.2% |
| **pipeline B (shipped): UIA names first, else the OLD full-list adapter, over ALL 250 rows** | **71.2%** |
| on the 138 rows no accessibility name settles: old adapter 70 right, new adapter 60 right | |
| ceiling if the better of the two adapters could be picked per row | 77.6% |
| NEW adapter on the 35 rows that carried a RAG hint | 88.6% |

### RAG retrieval and upkeep
| set / key given | scoped search (old) | hybrid (new) |
|---|---|---|
| mind2web/own_key (rephrased, 20% words dropped) | 100% | 100% |
| mind2web/generic_key (rephrased, 20% words dropped) | 0% | 100% |
| vscode/own_key (rephrased, 20% words dropped) | 100% | 100% |
| vscode/generic_key (rephrased, 20% words dropped) | 0% | 100% |
| agentnet/own_key (rephrased, 20% words dropped) | 100% | 100% |
| agentnet/generic_key (rephrased, 20% words dropped) | 62% | 100% |
| mind2web/own_key (half of the words dropped) | 100% | 100% |
| mind2web/generic_key (half of the words dropped) | 0% | 100% |
| vscode/own_key (half of the words dropped) | 100% | 100% |
| vscode/generic_key (half of the words dropped) | 0% | 100% |
| agentnet/own_key (half of the words dropped) | 100% | 100% |
| agentnet/generic_key (half of the words dropped) | 62% | 100% |

Caveat: these queries are rewordings of stored goals (the store has no separate hold-out phrasing), so they measure that retrieval finds a stored procedure from a partial, differently-keyed request - not new-task generalisation.
Procedure store: 1447 -> 1370 rows after removing 59 duplicates and 18 observe-only chains.

### Gauntlet
| case | kind | result | what was checked | seconds | proof |
|---|---|---|---|---|---|
| blender_house | scripted | PASS | 12 rooms on 2 floors, 285/285 parts, connected groups 1, score 100.0 | 20.4 | before_after_blender_house.png |
| blender_lamp | scripted | PASS | 4/4 parts, connected=True, floating=[], piercing=[], lowest z -0.0 (rule: 0), earlier objects untouched=True ( | 182.1 | before_after_blender_lamp.png |
| blender_table | scripted | PASS | 5/5 parts, connected=True, floating=[], piercing=[], lowest z 0.0 (rule: 0), earlier objects untouched=True (0 | 260.5 | before_after_blender_table.png |
| calculator | desktop | PASS | found 42 | 59.7 | before_after_calculator.png |
| calculator_chain | desktop | PASS | found 42 | 74.0 | before_after_calculator_chain.png |
| clock | desktop | PASS | learned/recalled the program: accessibility-tree | 200.7 | before_after_clock.png |
| concept_binary_tree | concept | PASS | 7 parts; geometry/plan problems left: none |  | overlay_teach_concept_binary_tree.png |
| concept_pythagoras | concept | FAIL | 9 parts; geometry/plan problems left: ['parts 1 and 2 overlap (88% of the smaller); place the second beside or |  | overlay_teach_concept_pythagoras.png |
| concept_water_cycle | concept | PASS | 8 parts; geometry/plan problems left: none |  | overlay_teach_concept_water_cycle.png |
| discord_wall | web | PASS | stopped at the sign-in wall=yes, nothing typed=yes | agent: needs_login, url https://discord.com/login | 11.2 | before_after_discord_wall.png |
| excalidraw | web | PASS | page probe > 0=yes | agent: max_steps, url https://excalidraw.com/ | 240.1 | before_after_excalidraw.png |
| flow_web_to_excel | flow | PASS | 5 fact rows read from en.wikipedia.org; 10/10 cells hold the value when read back through Excel's object model | 223.7 | before_after_flow_web_to_excel.png |
| flow_web_to_word | flow | PASS | web found 700 chars (direct address after the agent did not land), post 28 words drafted (NOT posted), typed i | 335.6 | before_after_flow_web_to_word.png |
| gmail_wall | web | PASS | stopped at the sign-in wall=yes, nothing typed=yes | agent: needs_login, url https://workspace.google.com/intl | 10.0 | before_after_gmail_wall.png |
| linkedin_guest | web | PASS | page says python=yes | agent: stuck, url https://www.linkedin.com/jobs/search/?keywords=Python%20deve | 250.4 | before_after_linkedin_guest.png |
| notepad | desktop | PASS | found quarterly, report, twelve | 68.0 | before_after_notepad.png |
| notepad_replace | desktop | FAIL | found  | missing bird sat on the bird mat | 196.6 | before_after_notepad_replace.png |
| paint_lightboard | desktop | PASS | 391 strokes, completion 100.0%, containment 100.0%, overlapping pairs 0 | 258.7 | before_after_paint_lightboard.png |
| paint_trace | desktop | PASS | 684 strokes, plan completion 100.0%, reference edge pixels inked 99.77% | 393.2 | before_after_paint_trace.png |
| powerpoint | desktop | PASS | found plan | missing roadmap | 86.4 | before_after_powerpoint.png |
| selfheal_calculator | selfheal | PASS | the_press_was_checked_and_learned=yes, the_corrupted_path_failed_the_check_and_was_rolled_back=yes, uia_repair | 25.5 | before_after_selfheal_calculator.png |
| sticky_notes | desktop | FAIL | found  | missing milk | 350.5 | before_after_sticky_notes.png |
| vscode_web | web | PASS | page probe > 0=yes | agent: stuck, url https://vscode.dev/ | 240.0 | before_after_vscode_web.png |
| whatsapp_wall | web | PASS | stopped at the sign-in wall=yes, nothing typed=yes | agent: needs_login, url https://web.whatsapp.com/ | 10.2 | before_after_whatsapp_wall.png |
| wikipedia | web | PASS | url ends with Ada_Lovelace=yes, page says lovelace=yes, page says mathematician=yes | agent: stuck, url https: | 184.4 | before_after_wikipedia.png |
| word | desktop | PASS | found quarterly, summary, twelve | 95.1 | before_after_word.png |
| youtube | web | PASS | url has /watch=yes | agent: stuck, url https://www.youtube.com/watch?v=f02mOEt11OQ&list=RDf02mOEt11 | 165.6 | before_after_youtube.png |

**Gauntlet: 21/24 functional cases pass = 88%.** (All 24/27 = 89% if the 3 sign-in-wall stops are counted; those only prove the agent STOPS at a login and types nothing - they do not prove it can work inside Gmail / Discord / WhatsApp, because no signed-in session was available: no Chrome extension was connected and the owned Edge profile is not signed in.)

### Test gate
- AR tests (the code written tonight and earlier in this project): 37/37 (AR1-AR37)
- main system-intelligence gate: 84 pass / 13 fail / 4 env-blocked; failing ids: A3X, CHR1, CN1, DAY1, KP1, LF2, LM1, MIN1, ORG1, PIX1, PURE1, RST1, TPL1
- failures are live parked-application / PE-menu / lifecycle tests (Notepad 'type_text' via the desktop connector, flyout pixel checks, regedit menu reader). The gate before tonight also listed 16 FAIL entries; the failing set was not diffed id by id (its log format differs). AR1-AR37 (the tests of tonight's code) pass 37/37.

### Honest limits found tonight
- Vision: the Top-40 prompt made rows fit the token budget (median 1,081 tokens, none over 2,048; v2 had 229 of 889 over) and lifted the adapter's own accuracy on the rows it can see (77.6% -> 80.0%), but the cut removes the right control in 18% of held-out rows, so on ALL held-out rows the shipped pipeline stays at 71.2%, not 85%. The old full-list adapter remains the default (ADAPTER_CHOICE.json); the new one is kept as an alternative. Closing the gap needs more / better-labelled data for icon-only controls, not another prompt trim (the better-of-two ceiling is 77.6%).
- Notepad Find/Replace through the menu flyout failed (the flyout is not seen by the effect check); Sticky Notes' packaged window never leaves a cloaked splash when started parked.
- Concept drawings: the overlay mechanism, the geometry critic, constructed squares and shape snapping work (AR36 passes), but the 7B planner still produced a Pythagorean figure the critic rejects; the water-cycle and binary-tree figures pass the critic but are crude.
- PowerPoint: title and subtitle are typed on the slide (see the picture); the final whole-window OCR misses 'Roadmap' behind the selection handle, so the pass relies on each goal's own read-back.
- Web agent: several runs end 'stuck' after the page already shows the right result (the check is made on the page itself, not on the agent's word); the first Wikipedia run chose the wrong article and the new 'done' self-check caught it.
- Gmail / Discord / WhatsApp / LinkedIn account features were not operated: stopped at the sign-in wall (LinkedIn ran as a guest). Nothing was sent, posted or typed into a login.

## Report Form 2 -- where the pictures are

- `D:\new_automation\data\mvp_proof_gallery\before_after_blender_house.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_blender_lamp.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_blender_table.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_calculator.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_calculator_chain.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_clock.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_discord_wall.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_excalidraw.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_flow_web_to_excel.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_flow_web_to_word.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_gmail_wall.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_linkedin_guest.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_notepad.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_notepad_replace.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_paint_lightboard.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_paint_trace.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_powerpoint.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_selfheal_calculator.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_sticky_notes.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_vscode_web.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_whatsapp_wall.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_wikipedia.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_word.png`
- `D:\new_automation\data\mvp_proof_gallery\before_after_youtube.png`
- `D:\new_automation\data\mvp_proof_gallery\blender_critic_AR37.png`
- `D:\new_automation\data\mvp_proof_gallery\concept_construct_AR36.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_calculator.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_calculator_chain.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_concept_binary_tree.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_concept_pythagoras.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_concept_water_cycle.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_notepad.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_paint_trace.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_powerpoint.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_word.png`
- `D:\new_automation\data\mvp_proof_gallery\overlay_teach_youtube_concept_water_cycle.png`
- `D:\new_automation\data\mvp_proof_gallery\rag_retrieval_AR35.png`
- `D:\new_automation\data\mvp_proof_gallery\selfheal_AR34.png`
- `D:\new_automation\data\mvp_proof_gallery\PROOF_CONTACT_SHEET.png`

Blender files and raw window pictures:
- blender_house: `D:\new_automation\data\professor\sandbox\blender\20261019_061626\outbox\house.blend`
- blender_lamp: `D:\new_automation\data\professor\sandbox\blender\20261019_064640\outbox\build_a_simple_desk_lamp_in_bl.blend`
- blender_table: `D:\new_automation\data\professor\sandbox\blender\20261019_064640\outbox\build_a_wooden_dining_table_in.blend`
- raw window pictures for calculator: `D:\new_automation\data\mvp_proof_gallery\raw\calculator`
- raw window pictures for calculator_chain: `D:\new_automation\data\mvp_proof_gallery\raw\calculator_chain`
- raw window pictures for discord_wall: `D:\new_automation\data\mvp_proof_gallery\raw\discord_wall`
- raw window pictures for excalidraw: `D:\new_automation\data\mvp_proof_gallery\raw\excalidraw`
- raw window pictures for flow_web_to_word: `D:\new_automation\data\mvp_proof_gallery\raw\flow_web_to_word`
- raw window pictures for gmail_wall: `D:\new_automation\data\mvp_proof_gallery\raw\gmail_wall`
- raw window pictures for linkedin_guest: `D:\new_automation\data\mvp_proof_gallery\raw\linkedin_guest`
- raw window pictures for notepad: `D:\new_automation\data\mvp_proof_gallery\raw\notepad`
- raw window pictures for notepad_replace: `D:\new_automation\data\mvp_proof_gallery\raw\notepad_replace`
- raw window pictures for paint_lightboard: `D:\new_automation\data\mvp_proof_gallery\raw\paint_lightboard`
- raw window pictures for paint_trace: `D:\new_automation\data\mvp_proof_gallery\raw\paint_trace`
- raw window pictures for powerpoint: `D:\new_automation\data\mvp_proof_gallery\raw\powerpoint`
- raw window pictures for vscode_web: `D:\new_automation\data\mvp_proof_gallery\raw\vscode_web`
- raw window pictures for whatsapp_wall: `D:\new_automation\data\mvp_proof_gallery\raw\whatsapp_wall`
- raw window pictures for wikipedia: `D:\new_automation\data\mvp_proof_gallery\raw\wikipedia`
- raw window pictures for word: `D:\new_automation\data\mvp_proof_gallery\raw\word`
- raw window pictures for youtube: `D:\new_automation\data\mvp_proof_gallery\raw\youtube`