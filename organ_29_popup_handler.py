"""
Shim redirecting root organ_29_popup_handler to All codes/core_organs/organ_29_popup_handler.py
"""
import os
import sys

CORE_PATH = os.path.join(os.path.dirname(__file__), "All codes", "core_organs")
if CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

from organ_29_popup_handler import *

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    manager = DesktopInteractionManager()
    manager._running = True
    try:
        asyncio.run(manager.run_listener_loop())
    except KeyboardInterrupt:
        logger.info("[HOST AGENT] Defensive shield deactivated safely.")
