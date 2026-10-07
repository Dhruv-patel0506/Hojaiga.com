"""Verification matrix for the generalized aliasing tiers.

1. host-inventory tier: installed-but-never-aliased apps resolve by bare name;
2. domain tier: any website resolves to the browser without enumeration;
3. web-app verbs: popular sites/services -> chrome;
4. regressions: every pre-existing routing decision stays intact;
5. scan-path rule: an unknown/uninstalled NAME is kept literal (no Chrome hijack).
Pure/dry-run only: plan_task_app never launches; resolve_* never touches the OS.
"""
import sys
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine, plan_task_app

cat = AppCatalog()
eng = VerbAliasEngine(cat)
fails = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'XX'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("--- 1. host-inventory tier (installed apps, zero aliases) ---")
for q, want in [("wireshark", "wireshark"), ("spaceclaim", "spaceclaim"),
                ("medal", "medal"), ("dev home", "dev home"),
                ("git gui", "git gui")]:
    got, src = eng.resolve_detailed(q)
    check(f"resolve({q!r}) -> {want!r} via installed",
          got == want and src == "installed", f"got {got!r} src={src}")

print("--- 2. domain tier (every website, no list) ---")
for q in ["open netflix.com", "https://some-random-thing.io/dashboard",
          "go to qr-code-generator.com", "mail.proton.me"]:
    got, src = eng.resolve_detailed(q)
    check(f"domain {q!r} -> chrome", got == "google chrome", f"got {got!r} src={src}")

print("--- 3. popular web apps -> chrome ---")
for q in ["youtube", "open chatgpt", "stackoverflow", "canva design",
          "google docs", "reddit", "github", "flipkart"]:
    got, src = eng.resolve_detailed(q)
    check(f"web app {q!r} -> chrome", got == "google chrome", f"got {got!r} src={src}")

print("--- 4. regressions (routing decisions that must NOT change) ---")
for q, want, want_src in [("powerpoint", "powerpoint", "alias"),
                          ("microsoft powerpoint", "powerpoint", "alias"),
                          ("word", "word", "word"),
                          ("excel", "excel", "alias"),
                          ("gmail", "google chrome", "alias"),
                          ("paint", "paint", "alias"),
                          ("open code", "visual studio code", "alias"),
                          ("calc", "calculator", "alias"),
                          ("resource monitor", "task manager", "word"),
                          ("open blender", "google chrome", "default")]:
    got, src = eng.resolve_detailed(q)
    check(f"{q!r} -> {want!r}/{want_src}", got == want and src == want_src,
          f"got {got!r} src={src}")

print("--- 5. scan-path literal rule (uninstalled name must not become chrome) ---")
# Emulate the edited organ_01 block for a name absent from catalog AND aliases:
for q in ["blender", "gimp-not-installed"]:
    got, src = eng.resolve_detailed(q)
    kept = q if src == "default" else got
    check(f"scan({q!r}) stays literal", src == "default" and kept == q,
          f"got {got!r} src={src}")

print("--- 6. plan_task_app dry-run stays sane ---")
p = plan_task_app("wireshark", catalog=cat, engine=eng)
check("plan(wireshark): named a desktop app, no search-bar typing surprise",
      p["resolution_source"] == "installed" and p["target_app"], str(p))
p2 = plan_task_app("youtube", catalog=cat, engine=eng)
check("plan(youtube): browser_web action", p2["action"] == "browser_web", str(p2))

print("\nRESULT:", "ALL PASSED" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
