# Hojaiga Teaching Acceptance Test

This test checks the complete teaching path in one lesson: startup, Void activation, structured explanation, visual diagramming, narration, Q&A, quiz, report output, and free navigation.

## Start exactly this test

Close any previous Hojaiga Teaching Void terminal first. Then run this command in PowerShell:

```powershell
python "D:\new_automation\All codes\ai_teaching_assistant_v8_master_engine_universal_hojaiga_holographic.py" --7b --voice --listen --task "Teach the graph of e^(-x). Define the function, identify the y-intercept and horizontal asymptote, draw labelled coordinate axes and the exponential-decay curve, explain how the graph is constructed step by step, ask for questions, then give one quiz question."
```

Expected start behaviour:

- The Hojaiga avatar begins at a left or right screen edge.
- The initial task opens the Void automatically.
- Voice narration begins after the model response; this is local turn-based inference and will take time on a 6 GB GPU.

## Verify during the lesson

| Check | Expected result |
|---|---|
| Board content | The task is written and explained in distinct steps, not generic filler. |
| Visual output | Labelled x/y axes, `y = e^(-x)`, the point `(0, 1)`, and a decreasing curve approaching `y = 0`. |
| No false graph | A text-only answer is a failure for this prompt. |
| Pointer | Laser dot moves without a `TUTOR (x, y)` label. |
| Void surface | Transparent dark dotted background; desktop is still faintly visible. |
| Navigation | Left-drag pans. Plain wheel moves up/down. Ctrl + wheel zooms around the cursor. Text and drawing scale together. |
| Ribbon | Bottom ribbon stays screen-fixed. Use Focus, Pen, Shade, previous/next, Hide, and Min. |
| Avatar | Minimize through `Min` or `M`; avatar returns to an edge and the lesson remains active. Click avatar to restore Void. |

## When Hojaiga asks for Q&A

Type exactly:

```text
no questions
```

## When Hojaiga asks the quiz

Type exactly:

```text
The graph passes through (0, 1), decreases as x increases, and approaches y = 0 without crossing it.
```

## Report test

After quiz feedback, type:

```text
report
```

Expected terminal output includes a path under:

```text
D:\new_automation\hojaiga_reports\
```

The Markdown report must contain lesson stages, board text, reasoning, diagram descriptions, quiz information, spatial navigation notes, and manual annotation bounds if any were drawn.

## Fast regression commands

Run these after closing Hojaiga:

```powershell
python -m py_compile "D:\new_automation\All codes\ai_teaching_assistant_v8_master_engine_universal_hojaiga_holographic.py"
Get-ChildItem "D:\new_automation\hojaiga_reports" -Filter *.md | Sort-Object LastWriteTime -Descending | Select-Object -First 3 FullName, LastWriteTime, Length
```

## Pass criteria

The test passes only if the graph is visibly drawn, navigation works without crashing, the Q&A/quiz progress normally, and a report is written. Capture a screenshot and terminal output if any one of these fails.