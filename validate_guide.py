"""
validate_guide -- check a procedural guide against brain/guide.schema.json + confirm it
conforms to the contract the guided executor consumes. Uses jsonschema if present, else a
manual structural check (so it runs anywhere). Prints conformance + a per-step summary.
"""
import json
import sys
from pathlib import Path

SCHEMA = json.loads(Path("brain/guide.schema.json").read_text(encoding="utf-8"))


def manual_validate(guide):
    errs = []
    for k in SCHEMA.get("required", []):
        if k not in guide:
            errs.append(f"missing top-level '{k}'")
    if not isinstance(guide.get("steps"), list) or not guide.get("steps"):
        errs.append("'steps' must be a non-empty array")
    ACTIONS = {"click", "fill", "select", "toggle", "keypress", "wait"}
    PROPS = {"text", "count", "visible", "attr:class", "attr:data-status", "value", "dom-diff"}
    for i, s in enumerate(guide.get("steps", [])):
        for req in ("id", "intent", "action", "target", "verify"):
            if req not in s:
                errs.append(f"step {i}: missing '{req}'")
        if s.get("action") not in ACTIONS:
            errs.append(f"step {i}: bad action '{s.get('action')}'")
        v = s.get("verify", {})
        if v.get("prop") not in PROPS:
            errs.append(f"step {i}: bad verify.prop '{v.get('prop')}'")
        if "expected" not in v:
            errs.append(f"step {i}: verify missing 'expected'")
    return errs


def main(path):
    guide = json.loads(Path(path).read_text(encoding="utf-8"))
    errs = []
    try:
        import jsonschema
        jsonschema.validate(guide, SCHEMA)
        method = "jsonschema"
    except ImportError:
        errs = manual_validate(guide)
        method = "manual"
    except Exception as e:
        errs = [str(e)]
        method = "jsonschema"
    print(f"[validate] {path}  ({method} check)")
    print(f"[validate] app={guide.get('app')}  tier={guide.get('tier')}  steps={len(guide.get('steps', []))}  source={guide.get('source', {}).get('kind')}")
    if errs:
        print("[validate] SCHEMA ERRORS:")
        for e in errs:
            print("   -", e)
    else:
        print("[validate] CONFORMS to guide.schema.json + executor contract (action/target/verify per step).")
        for s in guide["steps"]:
            print(f"   {s['id']:>2}. [{s.get('tut_time','')}] {s['action']:<6} {s['target']:<22} -> verify {s['verify']['prop']}~'{s['verify']['expected']}'")
    return not errs


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "brain/trello_guide.json")
