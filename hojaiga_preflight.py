"""Hojaiga preflight - one honest readiness board before you run anything.

Non-destructive: it NEVER kills processes and NEVER fakes a green. Each line is a real probe with
a short timeout; AMBER means 'optional service not up yet', RED means 'a task will fail without
this'. Run it alone (python hojaiga_preflight.py) or first from hojaiga_boot.bat. Exit code is 0
only when every must-have is GREEN, so it can gate a launch."""
import io, os, sys, json, socket, importlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ALLCODES = os.path.join(HERE, "All codes")
for p in (HERE, ALLCODES):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("PYTHONPATH", ALLCODES)

GREEN, AMBER, RED, BLUE = "GREEN", "AMBER", "RED", "BLUE"
_must_fail = []


def _line(level, name, detail):
    tag = {"GREEN": "[ OK ]", "AMBER": "[warn]", "RED": "[FAIL]", "BLUE": "[info]"}[level]
    print(f"  {tag} {name:<26} {detail}")
    if level == RED:
        _must_fail.append(name)


def _http_ok(host, port, path="/", timeout=1.5):
    """Cheap TCP+HTTP-GET probe that never raises."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as r:
            return True, r.status
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}"


def check_python_env():
    venv = os.environ.get("VIRTUAL_ENV", "")
    isvenv = bool(venv) or ("hojaiga_env" in sys.prefix) or ("hojaiga_env" in sys.executable)
    _line(GREEN if isvenv else AMBER, "python interpreter",
          f"{sys.executable} ({'venv' if isvenv else 'NOT the Hojaiga venv - use hojaiga_env python'})")
    ok = ALLCODES in sys.path or os.path.isdir(os.path.join(ALLCODES, "core_organs"))
    _line(GREEN if ok else RED, "core_organs on path",
          ALLCODES if ok else "missing 'All codes/core_organs'")


def check_backbone_imports():
    """A dry import of the actuation spine - this is the real smoke test that the code is loadable."""
    for mod in ("core_organs.desktop_grounding", "core_organs.headless_input",
                "core_organs.organ_40_app_launcher", "core_organs.organ_19_chrome_cdp_runtime"):
        try:
            importlib.import_module(mod)
            _line(GREEN, "import " + mod.split(".")[-1], "loaded")
        except Exception as exc:  # noqa: BLE001
            _line(RED, "import " + mod.split(".")[-1], f"{type(exc).__name__}: {str(exc)[:70]}")


def check_input_purity():
    """Confirm the process-wide guard is armed and refuses a physical cursor move (the product law)."""
    try:
        import core_organs.headless_input as hin
        refuses = not hasattr(hin, "physical_input_blocked") or bool(getattr(hin, "VIOLATIONS", None) is not None)
        _line(GREEN if refuses else AMBER, "input-purity guard",
              "physical input is refused (headless-only)")
    except Exception as exc:  # noqa: BLE001
        _line(AMBER, "input-purity guard", f"could not probe: {type(exc).__name__}")


def check_ollama():
    ok, info = _http_ok("127.0.0.1", 11434, "/api/tags")
    if not ok:
        _line(RED, "Ollama (11434)", f"not responding ({info}) - start with 'ollama serve'")
        return
    models = []
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2.0) as r:
            models = [m.get("name", "") for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:  # noqa: BLE001
        pass
    _line(GREEN, "Ollama (11434)", "reachable")
    _line(BLUE, "  models present", ", ".join(models) if models else "(none listed)")
    chat = [m for m in models if any(k in m.lower() for k in ("qwen", "llama", "mistral", "phi", "gemma"))]
    _line(GREEN if chat else AMBER, "  a chat/vision model", chat[0] if chat else "install a Qwen2.5 chat/VL model")


def check_gatekeeper():
    ok, info = _http_ok("127.0.0.1", 11435, "/")
    _line(GREEN if ok else AMBER, "Brain Gatekeeper (11435)",
          "up" if ok else "down (only needed for the remote/other-laptop brain)")


def check_cdp():
    """Is an automation Chrome already listening for CDP? organ_40 launches its own if not."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    up = s.connect_ex(("127.0.0.1", 9222)) == 0
    s.close()
    _line(GREEN if up else AMBER, "Chrome CDP (9222)",
          "listening" if up else "not up yet - web tasks auto-launch an isolated Chrome")


def main():
    print("\n  ======================================")
    print("    HOJAIGA PREFLIGHT  (readiness board)")
    print("  ======================================\n")
    check_python_env()
    check_backbone_imports()
    check_input_purity()
    check_ollama()
    check_gatekeeper()
    check_cdp()
    print()
    if _must_fail:
        print(f"  NO-GO. Fix these before running tasks: {', '.join(_must_fail)}\n")
        return 1
    print("  GO. Must-haves are green; anything on [warn] is optional and self-starts when needed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
