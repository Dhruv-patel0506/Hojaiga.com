# ============================================================================
# RE-EXPORT SHIM — DO NOT EDIT LOGIC HERE.
# ----------------------------------------------------------------------------
# The canonical implementation lives in:
#     core_organs.organ_29_popup_handler
# This top-level copy exists only so that legacy `import organ_29_popup_handler`
# paths keep working. It mirrors the canonical module's full namespace so the
# two can never drift apart. ALL edits must be made in the canonical module.
# ============================================================================
import sys

import core_organs.organ_29_popup_handler as _canonical

# Mirror every public name (classes, functions, module globals) from the
# canonical module into this module's namespace.
for _name, _value in vars(_canonical).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

del sys, _canonical, _name, _value
