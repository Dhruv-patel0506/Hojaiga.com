"""
HOJAIGA SPRINT: Main Entry Point
One command to look at any Windows app, learn what it can do, and save it.

    python hojaiga_sprint_main.py --scan Notepad
    python hojaiga_sprint_main.py --scan Calculator 20 --shortcuts
    python hojaiga_sprint_main.py --scan Notepad 40 --text-tab   # prove typing on a scratch tab
    python hojaiga_sprint_main.py --query Notepad save
    python hojaiga_sprint_main.py --apps
    python hojaiga_sprint_main.py --list
"""

import asyncio
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import uiautomation as auto

from hojaiga_sprint_perception import HOJAIGAPerception, find_window, list_windows
from hojaiga_sprint_prober import HOJAIGAProber
from hojaiga_sprint_knowledge import HOJAIGAKnowledge, HOJAIGAQuery

auto.SetGlobalSearchTimeout(2)


def repo_root():
    """Walk up from this file until we find the repo root, so paths do not depend on cwd.
    .git wins: 'All codes' has its own data/ dir but is not the repo root."""
    for marker in (".git", "data"):
        node = HERE
        for _ in range(6):
            if os.path.isdir(os.path.join(node, marker)):
                return node
            parent = os.path.dirname(node)
            if parent == node:
                break
            node = parent
    return os.path.dirname(HERE)


KNOWLEDGE_DIR = os.path.join(repo_root(), "data", "knowledge_bases")


def slug(app_name):
    return re.sub(r"[^a-z0-9]+", "_", app_name.lower()).strip("_").replace("_exe", "") or "app"


def knowledge_path(app_name):
    return os.path.join(KNOWLEDGE_DIR, f"{slug(app_name)}_knowledge.json")


def wait_for_window(name, timeout=12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        window = find_window(name)
        if window is not None:
            return window
        time.sleep(0.4)
    return None


def launch_app(name):
    """Start an app by human name. Packaged/UWP apps (Calculator, Notepad on Win11)
    are not on PATH, so resolve them through the Start menu using the repo's own
    resolver, then fall back to the shell."""
    import subprocess
    target = None
    try:
        sys.path.insert(0, os.path.dirname(HERE))  # the 'All codes' package root
        from core_organs import universal_scan as us
        resolved = us.resolve_app(name)
        if resolved:
            target = resolved[1]
    except Exception:
        pass
    if target and "!" in target:  # AUMID: Microsoft.WindowsCalculator_...!App
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"])
            return True
        except Exception:
            return False
    if target:  # a real path or .exe from the Start menu
        try:
            subprocess.Popen([target])
            return True
        except OSError:
            pass
    try:
        os.startfile(name)
        return True
    except OSError:
        try:
            subprocess.Popen([name])
            return True
        except OSError:
            return False


async def scan_app_complete(app_name, time_budget=20, launch=True, keep_open=True,
                            enable_ocr=False, probe_shortcuts=False, allow_destructive=False,
                            max_elements=60, out_path=None, scratch_text=False):
    print(f"\n{'=' * 70}")
    print(f"HOJAIGA SPRINT: learning {app_name}")
    print(f"{'=' * 70}\n")

    we_launched = False
    window = find_window(app_name)
    if window is None and launch:
        print(f"[1] Not on screen - starting {app_name} ...")
        if launch_app(app_name):
            we_launched = True
            window = wait_for_window(app_name)
    if window is None:
        print("[1] x Could not find an open window for that app.")
        print("    Open it yourself, or pass the exact title. --apps lists what is visible.")
        return None

    hwnd = window.NativeWindowHandle
    import ctypes
    if ctypes.windll.user32.IsIconic(hwnd):
        # A minimised window has no pixels to look at; restore before perceiving.
        window.Restore()
        time.sleep(0.6)
        print("[1] (was minimised - restored)")
    print(f"[1] + Window: {window.Name!r} (hwnd={hwnd}, class={window.ClassName})")

    print(f"\n[2] Scanning app structure ...")
    perception = HOJAIGAPerception(enable_ocr=enable_ocr)
    data = perception.scan_app_fast(window, 5)
    actionable = [e for e in data["uia_elements"] if e["action"] and not e["offscreen"]]
    print(f"    + {len(data['uia_elements'])} UIA elements, {len(actionable)} actionable, "
          f"{len(data['ocr_results'])} OCR regions in {data['scan_time']:.2f}s")

    print(f"\n[3] Discovering interactions (budget {time_budget}s) ...")
    prober = HOJAIGAProber(allow_destructive=allow_destructive)
    probes = await prober.probe_app(window, data, app_name, budget_seconds=time_budget,
                                   probe_shortcuts=probe_shortcuts, max_elements=max_elements,
                                   scratch_text=scratch_text)
    print(f"    + {probes['total_discovered']} verified interactions in {probes['time_taken']:.1f}s")

    print(f"\n[4] Building knowledge base ...")
    knowledge = HOJAIGAKnowledge(app_name)
    knowledge.properties["scan_time"] = data["scan_time"]
    knowledge.properties["probe_time"] = probes["time_taken"]
    knowledge.properties["hwnd_title"] = window.Name
    knowledge.properties["window_class"] = window.ClassName
    knowledge.properties["process_id"] = window.ProcessId
    knowledge.add_elements(data["uia_elements"])
    for interaction in probes["interactions"]:
        knowledge.add_interaction(interaction)

    filepath = out_path or knowledge_path(app_name)
    knowledge.save_json(filepath)
    print(f"[5] + Saved: {filepath}")

    print(f"[6] Query demo:")
    query = HOJAIGAQuery(knowledge)
    for verb in ("save", "create", "open", "find", "text", "settings"):
        print(f"    can {verb:<9} {query.can_do(verb)}")

    query.print_report()

    if we_launched and not keep_open:
        try:
            import ctypes
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            print(f"[7] Closed the window we started.\n")
        except Exception:
            pass
    elif we_launched:
        print(f"[7] Left {app_name} open (launched by this scan).")

    return knowledge


async def query_app_knowledge(app_name, question):
    filepath = knowledge_path(app_name)
    if not os.path.exists(filepath):
        print(f"x No knowledge base at {filepath}")
        print("  Scan it first: python hojaiga_sprint_main.py --scan " + app_name)
        return

    print(f"\n[QUERY] {app_name}: {question}")
    knowledge = HOJAIGAKnowledge.load_json(filepath)
    query = HOJAIGAQuery(knowledge)
    can = query.can_do(question)
    print(f"Answer: {can}")
    if can:
        for i, inter in enumerate(query.how_to_do(question)[:8]):
            if inter.method == "read-menu" and ":" in inter.label:
                menu, _, item = inter.label.partition(":")
                step = f"open the {menu} menu, then choose {item}"
            elif inter.source == "keyboard":
                step = f"press {inter.label.split()[0]}"
            elif inter.effect_type == "accepts_text_input":
                step = "click the text area and type"
            elif inter.label:
                # a named control: tell the human which button, not which pixel
                step = f"{inter.method or 'click'} {inter.label!r} at ({inter.x}, {inter.y})"
            else:
                step = f"{inter.method or 'click'} at ({inter.x}, {inter.y})"
            print(f"  {i + 1}. {step}   [{inter.effect_type}]")
    else:
        verbs = [c.verb for c in knowledge.capabilities()]
        print(f"  Learned verbs for this app: {', '.join(verbs[:20]) or '(none)'}")
    print()


def show_apps():
    print(f"\n{'WINDOW TITLE':<52}{'PROCESS':<26}SIZE")
    print("-" * 92)
    for w in list_windows():
        if not (w["title"] or w["process"]):
            continue
        print(f"{w['title'][:50]:<52}{w['process'][:24]:<26}{w['rect'][2]}x{w['rect'][3]}")
    print()


def show_library():
    if not os.path.isdir(KNOWLEDGE_DIR):
        print(f"No knowledge base yet ({KNOWLEDGE_DIR})")
        return
    print(f"\nKnowledge library: {KNOWLEDGE_DIR}")
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(KNOWLEDGE_DIR, name)
        try:
            kb = HOJAIGAKnowledge.load_json(path)
            verbs = [c.verb for c in kb.capabilities()]
            print(f"  * {kb.app_name:<24} {len(kb.interactions):>4} interactions, "
                  f"{len(kb.elements):>5} elements, verbs: {', '.join(verbs[:8])}")
        except Exception as exc:
            print(f"  ! {name} unreadable ({type(exc).__name__})")
    print()


USAGE = __doc__


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return

    flags = {a for a in argv if a.startswith("--") and a != "--scan"}

    def value_after(flag, default):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv) and not argv[idx + 1].startswith("--"):
                return argv[idx + 1]
        return default

    if "--apps" in flags:
        show_apps()
        return
    if "--list" in flags:
        show_library()
        return

    if "--scan" in argv:
        idx = argv.index("--scan")
        if idx + 1 >= len(argv):
            print("Usage: python hojaiga_sprint_main.py --scan <app title> [budget seconds]")
            return
        app_name = argv[idx + 1]
        budget = 20
        for token in argv[idx + 2:]:
            if token.isdigit():
                budget = int(token)
        asyncio.run(scan_app_complete(
            app_name,
            time_budget=budget,
            launch="--no-launch" not in flags,
            keep_open="--keep-open" in flags or "--no-launch" in flags,
            enable_ocr="--ocr" in flags,
            probe_shortcuts="--shortcuts" in flags,
            allow_destructive="--dangerous" in flags,
            max_elements=int(value_after("--max-elements", 60)),
            out_path=value_after("--out", None),
            scratch_text="--text-tab" in flags,
        ))
        return

    if "--query" in argv:
        idx = argv.index("--query")
        if idx + 2 >= len(argv):
            print("Usage: python hojaiga_sprint_main.py --query <app> <question>")
            return
        asyncio.run(query_app_knowledge(argv[idx + 1], " ".join(argv[idx + 2:])))
        return

    print(f"Unknown command: {argv[0]}")
    print(USAGE)


if __name__ == "__main__":
    main()
