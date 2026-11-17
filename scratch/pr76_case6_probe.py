"""Replicate PR76 case 6 exactly: an app that ignores posted and whose shim is recorded unavailable. Print what the ladder and note actually are."""
import json, os, tempfile
from types import SimpleNamespace as NS
import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import pointer as PT, config as CFG

old = CFG.DATA_DIR
CFG.DATA_DIR = tempfile.mkdtemp()
try:
    PT.save_trait("n6", "posted", "ignored")
    PT.save_trait("n6", "shim", "unavailable")
    print("raw file:", json.load(open(os.path.join(CFG.DATA_DIR, "app_traits.json"))))
    print("loaded  :", PT.load_traits("n6"))
    sc = PT.s_click(10, 10)
    v6 = PT.VirtualPointer(0, "n6", NS(allowed=True, owned=True, why_not=lambda: ""), allow_touch=False)
    v6.allowed = lambda: (True, "")
    print("session traits:", v6.traits)
    print("order:", v6.order(sc))
    print("pid:", v6.pid)
    r6 = v6.perform(sc, "click", verify=lambda: True)
    print("ok:", r6.ok, "| tried:", r6.tried)
    print("note:", r6.note)
    print("why_no_route:", v6.why_no_route(sc))
finally:
    CFG.DATA_DIR = old
