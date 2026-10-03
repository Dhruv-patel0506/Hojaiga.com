"""
test_wirebox_cdp.py — WireBox (pyautogui+bs4+selenium) + Gatekeeper (brain+eye) + CDP black tab together on Chrome
"""
import time, json, socket, struct, re, pathlib

# WireBox common wire
import sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.gatekeeper_wire import WireBox

def send(op, payload, timeout=30):
    body=json.dumps(payload).encode()
    f=struct.pack('>H',op)+body
    s=socket.socket()
    s.settimeout(timeout)
    s.connect(('127.0.0.1',47619))
    s.sendall(struct.pack('>I',len(f))+f)
    h=s.recv(4)
    tot=struct.unpack('>I',h)[0]
    d=b''
    while len(d)<tot:
        d+=s.recv(tot-len(d))
    s.close()
    op2=struct.unpack('>H', d[:2])[0]
    js=json.loads(d[2:].decode()) if len(d)>2 else {}
    return op2, js

print("="*60)
print(" WireBox 3-in-a-box + Gatekeeper + CDP black tab test")
print("="*60)

# 1. WireBox
box=WireBox()
print(f"[1] WireBox attach -> {box.attach()}")
shot=box.screenshot_b64(max_size=512)
print(f"[1] pyautogui screenshot b64 len={len(shot)} (eye ready)")
html='<div class="hi">hello <b>world</b></div>'
soup=box.parse_html(html)
print(f"[1] bs4 parse -> '{soup.get_text(strip=True)}'")
print(f"[1] selenium available={box._HAS_SELENIUM if hasattr(box,'_HAS_SELENIUM') else 'via WireBox'}")

# 2. Gatekeeper small brain+eye
print("\n[2] Gatekeeper eye+brain popup helper")
# fake popup image: use current screenshot
eye_q="what is on screen? describe briefly"
eye_ans=box.eye_describe(shot, eye_q) if len(shot)>100 else "no image"
print(f" eye describe -> {eye_ans[:120]}")
brain_ans=box.brain_decide(eye_ans or "Confirm dialog with OK and Cancel")
print(f" brain decide -> {brain_ans[:80]}")
popup_btn=box.handle_popup(image_b64=shot, fallback_text="Confirm popup")
print(f" master helper handle_popup -> button '{popup_btn}'")

# 3. CDP black tab via Organ19 — reuse existing Chrome (avoid launch cooldown)
print("\n[3] CDP via Organ19 47619 — reuse Chrome")
sid=None
bid=None
try:
    op,js=send(0x0112, {})
    for t in js.get('result',{}).get('targets',[]):
        if t.get('type')=='page' and 'https://' in t.get('url',''):
            sid=t['session_id']
            print(f" reuse existing sid {sid[:8]} -> {t['url'][:50]}")
            break
    if not sid:
        op,js=send(0x0100, {'headless': False})
        print(f" LAUNCH {js.get('result',{}).get('browser_id','')[:8]} ws {js.get('result',{}).get('ws_url','')[:50]}")
        bid=js.get('result',{}).get('browser_id')
        if not bid:
            raise Exception(f"launch failed {js}")
        time.sleep(2)
        op,js=send(0x0110, {'browser_id': bid, 'url': 'https://en.wikipedia.org/wiki/Main_Page'})
        sid=js.get('result',{}).get('session_id')
        print(f" CREATE_TAB sid {sid[:8]} -> Wikipedia")
        time.sleep(5)
    else:
        time.sleep(1)
    # check black tab invisible initially (opacity 0) — if missing, inject Polish original via mycdp.dom path
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hitl-cdp-overlay') ? document.getElementById('hitl-cdp-overlay').style.opacity : 'missing'"})
    val=res.get('result',{}).get('value')
    print(f" black tab initial opacity (should be 0 invisible) -> {val}")
    if val=='missing':
        import re as _re
        code=open(r"D:\Polish-automation\automation_engine\hitl_pipeline.py", encoding="utf-8").read()
        m=_re.search(r'js_code = """(.*?)"""', code, re.S)
        js=m.group(1)  # original opacity 0 hidden until mousemove
        _, r2=send(0x0160, {'session_id': sid, 'expression': js})
        print(f" injected Polish hitl via mycdp.dom {r2.get('result',{}).get('value')}")
        _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hitl-cdp-overlay') ? document.getElementById('hitl-cdp-overlay').style.opacity : 'missing'"})
        print(f" after inject opacity -> {res.get('result',{}).get('value')}")
    # also Hojaiga capsule
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hojaiga-capsule') ? 'exists' : 'missing'"})
    print(f" Hojaiga capsule -> {res.get('result',{}).get('value')}")
    # trigger popup via JS modal on Wikipedia (create test modal)
    send(0x0160, {'session_id': sid, 'expression': """
let m=document.createElement('div'); m.id='test-popup'; m.style.position='fixed'; m.style.top='30%'; m.style.left='30%'; m.style.width='40%'; m.style.background='white'; m.style.color='black'; m.style.padding='20px'; m.style.zIndex='999999998'; m.style.border='2px solid red'; m.innerHTML='<h3>Confirm Action</h3><p>Are you sure you want to proceed?</p><button onclick=\"this.parentElement.remove()\" style=\"background:#00ffcc;padding:8px\">OK</button> <button onclick=\"this.parentElement.remove()\" style=\"background:#ffcc00;padding:8px\">Cancel</button>'; document.body.appendChild(m); 'popup created'
"""})
    print(" created test popup (white modal with OK/Cancel) on Wikipedia")
    time.sleep(1)
    # use WireBox eye+brain to decide
    # take CDP screenshot via WireBox? use pyautogui for eye
    shot2=box.screenshot_b64(max_size=512)
    btn=box.handle_popup(image_b64=shot2, fallback_text="Confirm Action Are you sure? OK Cancel")
    print(f" WireBox eye+brain decided -> click '{btn}' to dismiss popup")
    # click via CDP
    if btn.lower()=="ok":
        send(0x0160, {'session_id': sid, 'expression': "document.querySelector('#test-popup button')?.click(); 'clicked OK'"})
    else:
        send(0x0160, {'session_id': sid, 'expression': "document.querySelectorAll('#test-popup button')[1]?.click(); 'clicked Cancel'"})
    print(f" clicked {btn} via CDP")
    time.sleep(1)
    # verify popup gone
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('test-popup') ? 'still there' : 'popup removed'"})
    print(f" popup status -> {res.get('result',{}).get('value')}")
    # black tab should still be invisible unless mousemove
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hitl-cdp-overlay').style.opacity"})
    print(f" black tab opacity after popup handling (still 0 invisible) -> {res.get('result',{}).get('value')}")
    # simulate physical mousemove over automated window -> should become 1 for 2s
    send(0x0160, {'session_id': sid, 'expression': "let o=document.getElementById('hitl-cdp-overlay'); o.style.opacity='1'; setTimeout(()=>o.style.opacity='0',2000); 'mousemoved'"})
    print(" simulated physical mousemove -> black tab now visible 2s")
    time.sleep(1)
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hitl-cdp-overlay').style.opacity"})
    print(f" opacity during mousemove -> {res.get('result',{}).get('value')} (1 visible)")
    time.sleep(2.5)
    _, res=send(0x0160, {'session_id': sid, 'expression': "document.getElementById('hitl-cdp-overlay').style.opacity"})
    print(f" opacity after 2s idle -> {res.get('result',{}).get('value')} (0 invisible)")

    import win32gui, win32con
    def cb(hwnd,_):
        t=win32gui.GetWindowText(hwnd)
        if 'Wikipedia' in t:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            try: win32gui.SetForegroundWindow(hwnd)
            except: pass
            print(f" brought {hwnd} {t} to front")
        return True
    win32gui.EnumWindows(cb, None)
    print("\nCHECK Chrome now: Wikipedia with black bottom bar invisible (move physical mouse over window to see it 2s), popup handled by WireBox eye+brain, Hojaiga blue capsule at bottom-left")
    time.sleep(8)
    print("test complete - Chrome left open")
except Exception as e:
    import traceback; traceback.print_exc()
    print(f"CDP test error {e}")

print("="*60)
print(" Wire = pyautogui (screenshot) + bs4 (parse) + selenium (find/click)")
print(" all via common wire_box -> Gatekeeper 11435 (llama3 + moondream)")
print(" CDP black tab = original Polish hitl-cdp-overlay invisible idle, visible on mousemove, no pause")
print("="*60)
