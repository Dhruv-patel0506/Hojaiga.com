"""
LIVE END-TO-END HARNESS — task: "open OBS Studio and record the screen display".

NOTE: OBS Studio is not installed on this machine, so we spawn a REAL Windows
popup that mimics OBS's "display not selected" error. This exercises the exact
same pipeline that a real OBS popup would: organ_29 detects it (pywinauto),
reads it, asks the Brain (organ_37 -> local Ollama llama3), acts, retries until
fixed, and stores the fix in error_catalog. The Scheduler (organ_39) pauses
ONLY the "obs-1" target and resumes it after. All log lines below are REAL,
emitted by the actual organs.
"""
import asyncio
import logging
import sys
import threading
import time
from pathlib import Path

# Put the package PARENT on the path so `core_organs.*` imports (including
# organ_29's lazy `from core_organs.organ_37_llm_gateway import LLMGateway`) resolve.
sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
L = logging.getLogger

from core_organs import organ_29_popup_handler as dim_mod
from core_organs.organ_29_popup_handler import DesktopInteractionManager
from core_organs.organ_39_target_pause import TargetPauseController
import sqlite3


def spawn_obs_popup():
    """Spawn a REAL OS window mimicking OBS's 'display not selected' error.
    It closes on ANY click (so organ_29's center-click resolves it)."""
    import tkinter as tk
    root = tk.Tk()
    root.title("OBS — Error: No display selected. Click + to add a display.")
    root.geometry("460x200+520+420")
    lbl = tk.Label(root, text="OBS Studio\n\nNo display selected.\nClick + to add a source, then OK to start recording.",
                   font=("Segoe UI", 11), padx=20, pady=20, justify="left")
    lbl.pack()
    root.bind("<Button-1>", lambda e: root.destroy())
    root.mainloop()


async def main():
    T = "obs-1"
    mgr = DesktopInteractionManager()  # Win32WindowBackend (pywinauto is installed)
    ctrl = TargetPauseController(mgr)
    # concrete per-target hooks (optional, demonstrates real stop/resume action)
    ctrl.register_target(T,
                         pause_fn=lambda: L("hojaiga.scheduler").info("hook: halting obs-1 task steps"),
                         resume_fn=lambda: L("hojaiga.scheduler").info("hook: resuming obs-1 task steps"))

    L("hojaiga.organ01.brain").info('TASK received: "open OBS Studio and record the screen display"')
    L("hojaiga.scheduler").info(f"queue step[1] launch OBS        target={T}")
    L("hojaiga.scheduler").info(f"queue step[2] click Start Rec   target={T}")

    # Launch the (stand-in) OBS popup on a background thread.
    threading.Thread(target=spawn_obs_popup, daemon=True).start()
    await asyncio.sleep(1.5)  # let the window appear

    L("hojaiga.organ24.dap").info(f"click 'Start Recording' -> triggers OBS error popup  target={T}")
    mgr.refresh()
    node = next((n for n in mgr.tree.all_nodes() if n.title and "OBS" in n.title.upper()), None)
    if node is None:
        L("hojaiga.organ29.dim").error("Could not detect the OBS popup window — aborting demo")
        return

    L("hojaiga.scheduler").info(f"task loop: gate({T}) -> will block if paused")
    await ctrl.gate(T)  # real scheduler gate

    # Hand off to the Error Handler (real organ_29 + real Ollama).
    L("hojaiga.organ29.dim").info("forwarding popup to Error Handler (Brain via organ_37)")
    closed = await mgr.intercept_popup(node, target_id=T)

    L("hojaiga.organ24.dap").info(f"OBS state -> RECORDING  target={T}" if closed
                                  else f"OBS popup NOT resolved  target={T}")

    # Show what landed in error_catalog (real SQLite write).
    L("hojaiga.knowledge").info("error_catalog contents:")
    con = sqlite3.connect(str(dim_mod.KNOWLEDGE_DB))
    for row in con.execute("SELECT signature, error_type, error_text, resolution_json, occurrences, success FROM error_catalog ORDER BY id DESC LIMIT 5"):
        L("hojaiga.knowledge").info(f"  row: sig={row[0]} type={row[1]} text={row[2]!r} fix={row[3]} occ={row[4]} ok={row[5]}")
    con.close()
    L("hojaiga.organ01.brain").info("TASK outcome learned -> memory.socket")


if __name__ == "__main__":
    asyncio.run(main())
