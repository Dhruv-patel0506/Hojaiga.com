"""
zero_shot_web -- prove the architecture reasons through UNSEEN interfaces with NO guides.
For each webapp: Stage-1 dynamic Xerox scan (live DOM/aria controls) -> ZERO-SHOT LLM goal
decomposition (Ollama qwen2.5:7b, format=json, given ONLY the goal + the scanned control list,
no guide text) -> Playwright execution -> strict DOM oracle. Records task success, failure
mode, and the model's reasoning (the emitted plan). This isolates the core engine from any
memorised trajectory. Honesty: a task counts only if the DOM oracle passes after the LLM's
self-authored plan.
"""
import os
import json
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("ZS_MODEL", "qwen2.5:7b")
OUTDIR = Path("brain/zsweb"); OUTDIR.mkdir(parents=True, exist_ok=True)
RESULTS = Path("brain/zero_shot_results.json")

H = lambda body: "<!doctype html><meta charset='utf-8'>" + body

# goal + html + oracle (NO guide steps given to the model -- it must plan from the scan)
APPS = [
    {"id": "zs_checkboxes", "goal": "Turn on both checkboxes.",
     "html": H("<input id=cb1 type=checkbox aria-label='newsletter'><input id=cb2 type=checkbox aria-label='terms'>"),
     "oracle": lambda p: p.is_checked("#cb1") and p.is_checked("#cb2")},
    {"id": "zs_dropdown", "goal": "Choose the Banana option in the fruit dropdown.",
     "html": H("<select id=fruit aria-label='fruit'><option value=apple>Apple</option><option value=banana>Banana</option><option value=cherry>Cherry</option></select>"),
     "oracle": lambda p: p.input_value("#fruit") == "banana"},
    {"id": "zs_tabs", "goal": "Open the Settings tab.",
     "html": H("<div role=tablist><button role=tab aria-label='Home tab' aria-selected=true>Home</button><button id=tab2 role=tab aria-label='Settings tab' aria-selected=false>Settings</button></div><style>.hidden{display:none}</style><script>tab2.onclick=()=>{document.querySelectorAll('[role=tab]').forEach(t=>t.setAttribute('aria-selected','false'));tab2.setAttribute('aria-selected','true')}</script>"),
     "oracle": lambda p: p.get_attribute("#tab2", "aria-selected") == "true"},
    {"id": "zs_modal", "goal": "Open the dialog, type 'hello' into the note field, and confirm.",
     "html": H("<button id=openbtn aria-label='Open dialog'>Open</button><div id=dialog role=dialog class=hidden aria-label=Dialog><input id=note aria-label='note'><button id=ok aria-label='Confirm'>OK</button></div><div id=out></div><style>.hidden{display:none}</style><script>openbtn.onclick=()=>dialog.classList.remove('hidden');ok.onclick=()=>{out.textContent=note.value;dialog.classList.add('hidden')}</script>"),
     "oracle": lambda p: "hello" in (p.text_content("#out") or "")},
    {"id": "zs_todo", "goal": "Add a task 'buy milk' to the todo list.",
     "html": H("<input id=task aria-label='new task'><button id=add aria-label='Add task'>Add</button><ul id=list></ul><script>add.onclick=()=>{if(task.value){let li=document.createElement('li');li.className='todo';li.textContent=task.value;list.appendChild(li)}}</script>"),
     "oracle": lambda p: p.eval_on_selector_all("#list .todo", "e=>e.some(x=>x.textContent.includes('buy milk'))")},
]


def scan(page):
    """Stage-1 dynamic web Xerox: dump live interactive controls (label/tag/type)."""
    ctrls = []
    for el in page.query_selector_all("input, button, select, [role=tab], [role=dialog]"):
        ctrls.append({"label": el.get_attribute("aria-label") or el.get_attribute("id"),
                      "tag": el.evaluate("e=>e.tagName.toLowerCase()"),
                      "type": el.get_attribute("type")})
    return ctrls


def plan(goal, controls):
    """Zero-shot LLM decomposition -- given ONLY the goal + scanned controls (no guide)."""
    prompt = (f"GOAL: {goal}\nAVAILABLE CONTROLS (label/tag/type): {json.dumps(controls)}\n"
              "Emit a JSON array of steps to achieve the goal using ONLY those control labels. "
              "Each step: {\"action\": \"click|fill|select\", \"target\": \"<exact control label>\", \"value\": \"<text or option>\"}. "
              "Return JSON only.")
    body = json.dumps({"model": MODEL, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        raw = json.loads(urllib.request.urlopen(req, timeout=120).read())["response"]
        data = json.loads(raw)
        if isinstance(data, dict):                       # Ollama format=json wraps as {"steps":[...]}
            found = None
            for v in data.values():
                if isinstance(v, list):
                    found = v; break
            if found is None and ("action" in data or "target" in data):
                found = [data]                            # a single-step object
            data = found if found is not None else []
        return data if isinstance(data, list) else []
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:60]}"}


def execute(page, steps):
    for st in steps:
        if not isinstance(st, dict):
            continue
        label = str(st.get("target", "")).lower(); act = str(st.get("action", "")).lower()
        val = str(st.get("value", "") or "")
        el = None
        for cand in page.query_selector_all("input, button, select, [role=tab]"):
            lab = (cand.get_attribute("aria-label") or cand.get_attribute("id") or "").lower()
            if lab and (label in lab or lab in label):
                el = cand; break
        if el is None:
            continue
        try:
            if act == "click":
                el.click()
            elif act == "fill":
                el.fill(val)
            elif act == "select":
                page.select_option(f"#{el.get_attribute('id')}", val)
        except Exception:
            pass
        time.sleep(0.1)


def run():
    results = {"pass": 0, "n": len(APPS), "apps": []}
    with sync_playwright() as P:
        b = P.chromium.launch(channel="chrome", headless=True)
        for app in APPS:
            page = b.new_page()
            f = OUTDIR / f"{app['id']}.html"; f.write_text(app["html"], encoding="utf-8")
            page.goto(f.resolve().as_uri())
            controls = scan(page)
            (Path("brain") / f"ui_capability_map_{app['id']}.json").write_text(json.dumps(controls, indent=3), encoding="utf-8")
            steps = plan(app["goal"], controls)
            err = steps.get("error") if isinstance(steps, dict) else None
            if isinstance(steps, list):
                execute(page, steps)
            try:
                ok = bool(app["oracle"](page))
            except Exception:
                ok = False
            results["pass"] += int(ok)
            results["apps"].append({"id": app["id"], "goal": app["goal"], "controls": len(controls),
                                    "plan": steps if isinstance(steps, list) else steps,
                                    "planner_error": err, "verified": ok})
            print(f"[zs] {app['id']}: {'PASS' if ok else 'FAIL'} plan={json.dumps(steps)[:120]}")
            page.close()
        b.close()
    results["acc"] = round(results["pass"] / results["n"], 3)
    RESULTS.write_text(json.dumps(results, indent=3), encoding="utf-8")
    print(f"[zs] ZERO-SHOT (no guides): {results['pass']}/{results['n']} = {results['acc']}")
    return results


if __name__ == "__main__":
    run()
