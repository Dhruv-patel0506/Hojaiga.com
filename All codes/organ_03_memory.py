# ============================================================================
# RE-EXPORT SHIM -- DO NOT EDIT LOGIC HERE.
# ----------------------------------------------------------------------------
# The canonical implementation lives in:
#     core_organs.organ_03_memory
# This top-level copy exists only so that legacy `import organ_03_memory`
# paths keep working. It mirrors the canonical module's full namespace so the
# two can never drift apart. ALL edits must be made in the canonical module.
# ============================================================================
import logging
import os
import sys

import core_organs.organ_03_memory as _canonical

logger = logging.getLogger("organ_03_memory")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
if os.environ.get("HOJAIGA_QUIET_LOGS", "1") == "1":
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.INFO)

# Mirror every public name (classes, functions, module globals) from the
# canonical module into this module's namespace.
for _name, _value in vars(_canonical).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

del sys, _canonical, _name, _value