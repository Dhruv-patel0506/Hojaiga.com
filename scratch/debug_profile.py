import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["chrome"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    ad = run.adapter
    print("targets before:", [(t["type"], t["url"], t["title"]) for t in ad.b._http_targets()] if hasattr(ad.b, "_http_targets") else ad.b.targets())
    ok, how = ad.b.new_tab("chrome://profile-picker/")
    print("open picker:", ok, how); time.sleep(2.0)
    import json, urllib.request
    allt = json.loads(urllib.request.urlopen(ad.b.base + "/json/list").read())
    print("all targets:", [(t["type"], t["url"][:50], t["title"][:30]) for t in allt])
    print("windows:", [(w, hin._class_name(w), hin.safe_window_text(w, 100)) for w in hin.process_windows(run.hwnd, include_hidden=True)][:8])
finally:
    run.finish()
