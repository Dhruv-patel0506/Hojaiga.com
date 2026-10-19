"""
Professor -- Hojaiga's vision-first teaching layer for ANY application.  (Clicky-inspired, local, no API keys.)

    You hold a key and ask. The Professor LOOKS at your screen like a person, finds every control, knows what the controls do,
    SPEAKS the answer and POINTS at the buttons with a pointer that flies over your windows -- then waits for you to do it and checks what happened.

Pipeline (each stage is a module; every stage reports honestly what it skipped):

    capture      screen / window pixels, DPI, change detection                      capture.py
    see          every control: accessibility tree + shapes + OCR + remembered icons uia_source.py  candidates.py  icon_memory.py
    name         vision model names icons from numbered contact sheets               labeler.py  vlm.py  grounding.py  vision_server.py
    structure    menu bar / ribbon / ribbon GROUPS / panels / canvas                 regions.py
    fuse+prove   one list, provenance, pixel-level coverage audit                    fusion.py  coverage.py  sweeper.py
    know         measured UI knowledge + source-code graph in the 7 Hojaiga divisions knowledge/
    teach        grounded lesson planning (element ids, never invented coordinates)  teacher.py  brain.py  pointing.py
    show         click-through overlay: pointer, outline, bubble                     overlay.py  overlay_render.py
    speak/hear   local TTS and push-to-talk STT                                      voice_out.py  voice_in.py
    run          the interactive lesson and the whole session                        lesson_runner.py  session.py

Entry point: core_organs/hojaiga_professor.py       Skill file: claude_skills/18-professor.md
"""

__all__ = ["config", "schema", "capture", "vlm", "sweeper", "teacher", "session"]
