"""
hojaiga_tutor -- launch the live tutor: the real program on screen, red teaching marks over it, a voice, and you.

    python hojaiga_tutor.py Notepad                              # then talk or type: "how do I find a word?", "next", "do it for me", "stop"
    python hojaiga_tutor.py Notepad "how do I find a word?"      # starts teaching that straight away
    python hojaiga_tutor.py Paint --mic                          # the microphone is on from the start (local speech recognition)

    --no-voice   silent (the words are on screen anyway)      --no-bar   no text box      --auto   a scripted 'next' after every beat (a demonstration that needs no hands)

In the project environment:  D:\\new_automation\\hojaiga_env\\Scripts\\python.exe -X utf8 "D:\\new_automation\\All codes\\hojaiga_tutor.py" Notepad
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class AutoWatcher:
    """A watcher that presses 'next' for you after a short pause - for demonstrations and checks."""

    def __init__(self, pause: float = 2.0) -> None:
        self.pause, self._speaking = pause, (lambda: False)
        self.voice_in = False

    def wait(self, box=None, keys=(), timeout: float = 0.0):
        time.sleep(self.pause)
        return {"kind": "line", "text": "next", "command": "next"}

    def push(self, text: str) -> None:
        pass

    def toggle_voice(self) -> bool:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app")
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--mic", action="store_true")
    ap.add_argument("--no-bar", action="store_true")
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args(argv)
    from core_organs import app_teaching_automation as _ATA  # noqa: F401  (sets the environment-check relaxation before anything imports the vision stack)
    from core_organs import micro_tutor as MT, tutor_voice as TV
    import uiautomation as auto
    tutor = MT.MicroTutor(voice=TV.Voice(enabled=not a.no_voice), watcher=AutoWatcher() if a.auto else None, bar=not a.no_bar and not a.auto, mic=a.mic)
    with auto.UIAutomationInitializerInThread():
        tutor.open(a.app)
        try:
            if a.question:
                tutor.teach(a.question)
            if not a.auto:
                tutor.session()
        finally:
            tutor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
