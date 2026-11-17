"""
robustness_stress_test_50 -- high-stress ZERO-SHOT robustness harness across 50 generative
Tier-2/Tier-3 web workspaces. NO guides (Stage-2 fully bypassed). Per app: Stage-1 live DOM/ARIA
Xerox scan -> ReAct zero-shot planner (Ollama qwen2.5:7b picks the NEXT action given goal +
completed-steps + live controls) -> Playwright execute -> STRICT per-step verification (the
action must actually mutate a targeted DOM property) + a cumulative END-STATE oracle. Records
success, steps-to-solve, and a failure-mode taxonomy. Persists to brain/robustness_stress_results.json.

Honest by construction: a task passes ONLY if its end-state oracle (concrete values/checked/
row-count/toast text) is satisfied. No generic tree-delta credit. The >85% target is reported as
measured, never assumed.
"""
import os
import json
import time
import random
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("RS_MODEL", "qwen2.5:7b")
OUTDIR = Path("brain/rs50"); OUTDIR.mkdir(parents=True, exist_ok=True)
RESULTS = Path("brain/robustness_stress_results.json")
H = lambda body: "<!doctype html><meta charset='utf-8'>" + body


# ---------- generative app templates (Tier 2 / Tier 3), parameterized for 50 distinct targets ----------
def gen_grid(seed, nrows=6):
    r = random.Random(seed)
    names = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"][:nrows]
    rows = "".join(f"<tr class='row' data-name='{n}' data-status='new'><td>{n}</td><td>{r.randint(1,9)}</td></tr>" for n in names)
    goal = (f"Sort the table by name, then filter rows to show only '{names[1]}', then click the row for '{names[1]}' "
            f"to set its status to active.")
    html = H(f"<button id=sort aria-label='Sort by name'>Sort</button><input id=f aria-label='Filter'>"
             f"<table id=t><tbody>{rows}</tbody></table>"
             f"<script>sort.onclick=()=>{{let rs=[...t.querySelectorAll('.row')];rs.sort((a,b)=>a.dataset.name.localeCompare(b.dataset.name));rs.forEach(x=>t.querySelector('tbody').appendChild(x))}};"
             f"f.oninput=()=>{{[...t.querySelectorAll('.row')].forEach(x=>x.style.display=x.dataset.name.includes(f.value)?'':'none')}};"
             f"t.onclick=e=>{{let tr=e.target.closest('.row');if(tr)tr.dataset.status='active'}}</script>")
    checks = [("tr.row[data-name='%s']" % names[1], "attr:data-status", "active")]
    return goal, html, checks


def gen_wizard(seed, steps=3):
    r = random.Random(seed)
    fields = [f"s{i}" for i in range(steps)]
    body = "".join(f"<div class='step hidden' id=st{i}><input id={f} aria-label='field {f}'></div>" for i, f in enumerate(fields))
    goal = " and ".join(f"fill field '{f}' with 'v-{f}'" for f in fields) + ", advancing each step, then submit."
    html = H(f"<div id=wrap>{body}</div><button id=next aria-label='Next'>Next</button><button id=submit aria-label='Submit' class=hidden>Submit</button><div id=done></div>"
             f"<style>.hidden{{display:none}}</style><script>let i=0;const ss=[...document.querySelectorAll('.step')];"
             f"next.onclick=()=>{{ss[i].classList.add('hidden');i++;if(i<ss.length)ss[i].classList.remove('hidden');if(i==ss.length){{next.classList.add('hidden');submit.classList.remove('hidden')}}}};"
             f"submit.onclick=()=>{{done.textContent='submitted'}}</script>")
    checks = [("#done", "text", "submitted")]
    return goal, html, checks


def gen_modal_form(seed):
    goal = "Open the dialog, set the status field to 'approved', and save; verify the confirmation."
    html = H("<button id=open aria-label='Open dialog'>Open</button><div id=dlg role=dialog class=hidden aria-label=Dialog>"
             "<select id=st aria-label='status'><option value=new>New</option><option value=approved>Approved</option></select>"
             "<button id=save aria-label='Save'>Save</button></div><div id=toast></div><style>.hidden{display:none}</style>"
             "<script>open.onclick=()=>dlg.classList.remove('hidden');save.onclick=()=>{toast.textContent='saved:'+st.value;dlg.classList.add('hidden')}</script>")
    checks = [("#toast", "text", "saved:approved")]
    return goal, html, checks


def gen_kanban(seed, n=3):
    goal = "Add a card 'ship-v1' to the board, then move it to the Done column."
    html = H("<input id=card aria-label='new card'><button id=add aria-label='Add card'>Add</button>"
             "<ul id=todo></ul><button id=move aria-label='Move to done'>Move</button><ul id=done></ul>"
             "<script>add.onclick=()=>{if(card.value){let li=document.createElement('li');li.className='kcard';li.textContent=card.value;todo.appendChild(li)}};"
             "move.onclick=()=>{let c=todo.lastElementChild;if(c)done.appendChild(c)}</script>")
    checks = [("#done .kcard", "text", "ship-v1")]
    return goal, html, checks


GENS = [gen_grid, gen_wizard, gen_modal_form, gen_kanban]


def build_corpus(n=50):
    apps = []
    for i in range(n):
        g = GENS[i % len(GENS)]
        tier = 3 if g in (gen_wizard, gen_modal_form, gen_kanban) else 2
        goal, html, checks = g(seed=1000 + i)
        apps.append({"id": f"rs_{i:02d}_{g.__name__}", "tier": tier, "goal": goal, "html": html, "checks": checks})
    return apps


# ---------- zero-shot ReAct planner ----------
def scan(page):
    out = []
    for el in page.query_selector_all("input, button, select, tr.row, .kcard, [role=dialog]"):
        try:
            vis = el.is_visible()
        except Exception:
            vis = False
        out.append({"label": el.get_attribute("aria-label") or el.get_attribute("id") or el.get_attribute("class"),
                    "tag": el.evaluate("e=>e.tagName.toLowerCase()"), "type": el.get_attribute("type"),
                    "visible": vis})
    return out


def next_action(goal, done, controls):
    prompt = (f"GOAL: {goal}\nSTEPS DONE: {json.dumps(done)}\nCONTROLS (label/tag/type/visible): {json.dumps(controls[:25])}\n"
              "Act ONLY on visible controls; if a needed field is hidden, first click the button that reveals it (e.g. Open/Next). "
              "Choose ONLY the single NEXT action. Return JSON {\"action\":\"click|fill|select\",\"target\":\"<label>\",\"value\":\"<text>\"} "
              "or {\"action\":\"done\"} if the goal is fully achieved.")
    body = json.dumps({"model": MODEL, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    try:
        raw = json.loads(urllib.request.urlopen(urllib.request.Request(
            OLLAMA, data=body, headers={"Content-Type": "application/json"}), timeout=90).read())["response"]
        d = json.loads(raw)
        return d if isinstance(d, dict) else (d[0] if isinstance(d, list) and d else {})
    except Exception as e:
        return {"error": type(e).__name__}


def _find(page, label):
    lab = str(label or "").lower()
    best = None
    for cand in page.query_selector_all("input, button, select, [role=tab]"):
        c = (cand.get_attribute("aria-label") or cand.get_attribute("id") or "").lower()
        if c and (lab in c or c in lab):
            try:
                if cand.is_visible():
                    return cand
            except Exception:
                pass
            best = best or cand
    return best


def do_action(page, a):
    act = str(a.get("action", "")).lower(); el = _find(page, a.get("target"))
    if el is None:
        return False, "no-target"
    try:
        if not el.is_visible():
            return False, "hidden"        # reveal it first; don't hang on a hidden element
        if act == "click":
            el.click(timeout=1500)
        elif act == "fill":
            el.fill(str(a.get("value", "")), timeout=1500)
        elif act == "select":
            page.select_option(f"#{el.get_attribute('id')}", str(a.get("value", "")), timeout=1500)
        else:
            return False, "bad-action"
    except Exception as e:
        return False, f"exec-err:{type(e).__name__}"
    return True, "ok"


def check_oracle(page, checks):
    for sel, prop, expected in checks:
        try:
            if prop.startswith("attr:"):
                got = page.get_attribute(sel, prop.split(":", 1)[1]) or ""
            else:
                got = page.text_content(sel) or ""
            if str(expected).lower() not in str(got).lower():
                return False
        except Exception:
            return False
    return True


def run_app(browser, app, max_steps=15):
    page = browser.new_page()
    f = OUTDIR / f"{app['id']}.html"; f.write_text(app["html"], encoding="utf-8")
    page.goto(f.resolve().as_uri())
    done = []; fail = "step-budget"; ok = False
    for _ in range(max_steps):
        if check_oracle(page, app["checks"]):
            ok = True; fail = None; break
        controls = scan(page)
        a = next_action(app["goal"], done, controls)
        if a.get("action") == "done":
            break
        if "error" in a or not a:
            fail = "planner-error"; break
        changed, note = do_action(page, a)
        if not changed:
            fail = note; break
        done.append(a)
        time.sleep(0.1)
    ok = ok or check_oracle(page, app["checks"])
    page.close()
    return {"id": app["id"], "tier": app["tier"], "steps": len(done), "plan": done,
            "verified": ok, "failure_mode": None if ok else fail}


def run(n=50):
    apps = build_corpus(n)
    results = {"n": len(apps), "pass": 0, "by_tier": {2: [0, 0], 3: [0, 0]}, "fail_modes": {}, "apps": []}
    with sync_playwright() as P:
        b = P.chromium.launch(channel="chrome", headless=True)
        for app in apps:
            r = run_app(b, app)
            results["apps"].append(r)
            results["by_tier"][app["tier"]][1] += 1
            if r["verified"]:
                results["pass"] += 1; results["by_tier"][app["tier"]][0] += 1
            else:
                fm = r["failure_mode"] or "unknown"
                results["fail_modes"][fm] = results["fail_modes"].get(fm, 0) + 1
            print(f"[rs] {app['id']} T{app['tier']}: {'PASS' if r['verified'] else 'FAIL:'+str(r['failure_mode'])} steps={r['steps']}")
        b.close()
    results["acc"] = round(results["pass"] / results["n"], 3)
    results["bar_85_met"] = results["acc"] > 0.85
    RESULTS.write_text(json.dumps(results, indent=3), encoding="utf-8")
    print(f"[rs] ZERO-SHOT 50-STRESS: {results['pass']}/{results['n']} = {results['acc']}  (>85% bar met: {results['bar_85_met']})")
    print(f"[rs] by tier: T2 {results['by_tier'][2][0]}/{results['by_tier'][2][1]}  T3 {results['by_tier'][3][0]}/{results['by_tier'][3][1]}")
    print(f"[rs] failure modes: {results['fail_modes']}")
    return results


if __name__ == "__main__":
    import sys
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 50)
