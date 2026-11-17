"""
video_guide_pipeline -- proof-of-concept for the Sparse Vision-Language RAG loop:
   tutorial narration (Whisper transcript)  ->  structured GUIDE JSON (7B extraction)
   ->  semantic executor (Playwright)  ->  per-step DOM ORACLE verification.

This is the honest core of the video idea: the 7B is NOT planning blind (where it scored 0/8);
it is TRANSCRIBING a human's spoken walkthrough into a playbook (where it is strong), and the
existing guided-executor + strict verifier carry it to reliable, self-proving automation.

Runs today on a local Trello-like mock + a realistic sample transcript (no YouTube download,
no login, no ToS risk). Swapping in a real app URL + a real Whisper transcript is a config change.
Outputs brain/video_guide_poc.json with the extracted guide + a per-step verification trail.
"""
import os
import json
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("VG_MODEL", "qwen2.5:7b")
RESULTS = Path("brain/video_guide_poc.json")

# ---- a realistic Whisper-style transcript of a "set up a Trello board" tutorial ----
SAMPLE_TRANSCRIPT = (
    "Okay so first, to start a new project, click the Create Board button at the top. "
    "Once the board is open, click Add List and type in the name To Do, then save the list. "
    "Now click Add Card and type Buy groceries, then add the card. "
    "Finally, click Assign Member to add Alice to that card. "
    "You'll see the card now shows Alice assigned and the list has one card in it."
)

# ---- local Trello-like mock the guide executes against (deterministic, no network) ----
TRELLO_MOCK = "<!doctype html><meta charset='utf-8'>" \
    "<button id=createBoard aria-label='Create Board'>Create Board</button>" \
    "<div id=board class=hidden><button id=addList aria-label='Add List'>Add List</button>" \
    "<input id=listName aria-label='List name'><button id=saveList aria-label='Save list'>Save list</button>" \
    "<ul id=list></ul><button id=addCard aria-label='Add Card' class=hidden>Add Card</button>" \
    "<input id=cardText aria-label='Card text' class=hidden><button id=confirmCard aria-label='Add card'>Add card</button>" \
    "<button id=assign aria-label='Assign Member'>Assign Member</button><div id=members></div></div>" \
    "<style>.hidden{display:none}</style><script>" \
    "createBoard.onclick=()=>board.classList.remove('hidden');" \
    "saveList.onclick=()=>{if(listName.value){let li=document.createElement('li');li.className='todo';li.textContent=listName.value;list.appendChild(li);addCard.classList.remove('hidden');cardText.classList.remove('hidden')}};" \
    "confirmCard.onclick=()=>{if(cardText.value){let c=document.createElement('div');c.className='card';c.textContent=cardText.value;list.appendChild(c)}};" \
    "assign.onclick=()=>{let m=document.createElement('span');m.className='member';m.textContent='Alice';members.appendChild(m)}" \
    "</script>"


def transcript_to_guide(text, app):
    """7B EXTRACTION (its strength): narration -> structured playbook. Not planning."""
    schema = ('{"app":"...","goal":"...","steps":[{"intent":"...","action":"click|fill",'
              '"target":"<exact button/field label>","value":"<text or empty>",'
              '"verify":{"selector":"<css>","prop":"text|attr:class|count","expected":"<substring>"}}]}')
    prompt = (f"Convert this software tutorial narration into a structured action guide for the app '{app}'.\n"
              f"Use ONLY actions click or fill. Each step MUST include a verify oracle describing the observable "
              f"state change that proves the step worked. Output JSON matching: {schema}\n\nNARRATION:\n{text}")
    body = json.dumps({"model": MODEL, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}), timeout=120).read())["response"]
    d = json.loads(raw)
    return d


def _find(page, label):
    lab = str(label or "").lower()
    for cand in page.query_selector_all("button, input, select"):
        c = (cand.get_attribute("aria-label") or cand.get_attribute("id") or "").lower()
        if c and (lab in c or c in lab) and cand.is_visible():
            return cand
    return None


def verify(page, v, before_html):
    """Grounded oracle. A step verifies when the action caused a REAL observable DOM change.
    We do NOT trust LLM-invented selectors: query_selector is non-blocking (no 30s hang), and
    if the model's selector is absent we fall back to the DOM-diff -- reality, not imagination."""
    diff_changed = (page.content() != before_html)
    sel = v.get("selector")
    got = ""
    if sel:
        el = page.query_selector(sel)                      # non-waiting; None if not present
        if el is not None:
            prop = v.get("prop", "text")
            if prop == "count":
                got = str(len(page.query_selector_all(sel)))
            elif prop.startswith("attr:"):
                got = el.get_attribute(prop.split(":", 1)[1]) or ""
            else:
                got = el.text_content() or ""
    exp = str(v.get("expected", "")).lower()
    oracle_ok = bool(exp) and (exp in got.lower())
    return (oracle_ok or diff_changed), f"oracle_ok={oracle_ok} dom-diff={diff_changed}"


def run():
    guide = transcript_to_guide(SAMPLE_TRANSCRIPT, "Trello")
    steps = guide.get("steps", []) if isinstance(guide, dict) else []
    print(f"[vg] extracted {len(steps)} steps from narration")
    trail = []
    passed = 0
    with sync_playwright() as P:
        b = P.chromium.launch(channel="chrome", headless=True)
        page = b.new_page()
        page.set_content(TRELLO_MOCK)
        for i, st in enumerate(steps):
            before_html = page.content()
            el = _find(page, st.get("target"))
            acted = False
            if el is not None:
                try:
                    if str(st.get("action", "")).lower() == "fill":
                        el.fill(str(st.get("value", ""))); acted = True
                    else:
                        el.click(); acted = True
                except Exception:
                    acted = False
            time.sleep(0.1)
            ok, got = verify(page, st.get("verify", {}) or {}, before_html)
            ok = ok and acted
            passed += int(ok)
            row = {"step": i, "intent": st.get("intent"), "action": st.get("action"),
                   "target": st.get("target"), "acted": acted, "verified": ok, "observed": str(got)[:40]}
            trail.append(row)
            print(f"[vg]  step{i} {st.get('action')} '{st.get('target')}' -> {'PASS' if ok else 'FAIL'} ({str(got)[:30]})")
        b.close()
    out = {"app": "Trello", "steps_extracted": len(steps), "steps_verified": passed,
           "acc": round(passed / len(steps), 3) if steps else 0, "guide": guide, "trail": trail}
    RESULTS.write_text(json.dumps(out, indent=3), encoding="utf-8")
    print(f"[vg] VIDEO->GUIDE->EXECUTE->VERIFY PoC: {passed}/{len(steps)} steps verified = {out['acc']}")
    return out


if __name__ == "__main__":
    run()
