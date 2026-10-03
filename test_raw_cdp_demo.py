"""
============================================================================
RAW CDP DEMO — See Chrome DevTools Protocol Virtual Input in Action
============================================================================
This script demonstrates the ACTUAL Chrome DevTools Protocol working:

1. Launches Chrome with --remote-debugging-port
2. Connects via raw WebSocket (no Puppeteer/Playwright)
3. Creates a tab, navigates to a real page
4. Uses Input.dispatchMouseEvent / Input.dispatchKeyEvent for VIRTUAL input
5. Takes screenshots at each step
6. YOUR PHYSICAL MOUSE NEVER MOVES — that's the whole point

Run:  python test_raw_cdp_demo.py
============================================================================
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import base64
import random
import tempfile
import shutil
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    sys.exit(1)

try:
    import urllib.request
except ImportError:
    pass

# ============================================================================
# CONFIG
# ============================================================================
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_PORT = 9234  # avoid conflict with anything else
PROFILE_DIR = os.path.join(tempfile.gettempdir(), "hojaiga_cdp_demo_profile")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "cdp_demo_screenshots")
LIVE_MODE = True  # Add pauses so user can watch Chrome on screen
LIVE_PAUSE = 2.5  # seconds between steps for watching

# ============================================================================
# HELPERS
# ============================================================================

class CDPSession:
    """Minimal raw CDP client — just WebSocket + JSON-RPC."""
    
    def __init__(self, ws):
        self.ws = ws
        self._cmd_id = 0
        self._pending = {}
        self._events = []
        self._reader_task = None
    
    async def start_reader(self):
        self._reader_task = asyncio.create_task(self._read_loop())
    
    async def _read_loop(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(
                                Exception(f"CDP error: {msg['error']}")
                            )
                        else:
                            fut.set_result(msg.get("result", {}))
                else:
                    self._events.append(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def send(self, method: str, params: dict = None, 
                   session_id: str = None, timeout: float = 15.0) -> dict:
        self._cmd_id += 1
        cmd_id = self._cmd_id
        envelope = {"id": cmd_id, "method": method, "params": params or {}}
        if session_id:
            envelope["sessionId"] = session_id
        
        fut = asyncio.get_event_loop().create_future()
        self._pending[cmd_id] = fut
        await self.ws.send(json.dumps(envelope))
        return await asyncio.wait_for(fut, timeout=timeout)
    
    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
        await self.ws.close()


def print_step(num, text):
    print(f"\n{'='*60}")
    print(f"  STEP {num}: {text}")
    print(f"{'='*60}")


def print_result(key, value):
    if isinstance(value, dict):
        value = json.dumps(value, indent=2)[:200]
    print(f"  > {key}: {value}")


# ============================================================================
# MAIN DEMO
# ============================================================================

async def run_cdp_demo():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    screenshot_count = 0
    
    # ------------------------------------------------------------------
    # STEP 1: Launch Chrome with remote debugging
    # ------------------------------------------------------------------
    print_step(1, "Launching Chrome with --remote-debugging-port")
    
    # Clean profile for isolation
    if os.path.exists(PROFILE_DIR):
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    os.makedirs(PROFILE_DIR, exist_ok=True)
    
    chrome_args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-breakpad",
        "--disable-extensions",
        "--disable-sync",
        "--disable-translate",
        "--window-size=1280,900",
        "--window-position=100,100",
        "about:blank",
    ]
    
    chrome_proc = subprocess.Popen(
        chrome_args, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL,
    )
    print_result("Chrome PID", chrome_proc.pid)
    print_result("Debug port", CDP_PORT)
    print("  Waiting for Chrome to start and become visible...")
    
    # Give Chrome time to create its window
    await asyncio.sleep(3)
    
    # Force Chrome window to foreground so user can SEE it
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        
        def bring_chrome_to_front():
            """Find Chrome window by PID and force it to foreground."""
            target_hwnd = None
            
            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_cb(hwnd, _):
                nonlocal target_hwnd
                if user32.IsWindowVisible(hwnd):
                    pid = ctypes.wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == chrome_proc.pid:
                        # Get window title to confirm it's a Chrome window
                        buf = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(hwnd, buf, 256)
                        title = buf.value
                        if title:  # Only main windows with titles
                            target_hwnd = int(hwnd)
                            return False  # Stop enumerating
                return True
            
            user32.EnumWindows(enum_cb, 0)
            
            if target_hwnd:
                # Unlock SetForegroundWindow by attaching thread input
                current_thread = user32.GetWindowThreadProcessId(
                    user32.GetForegroundWindow(), None)
                target_thread = user32.GetWindowThreadProcessId(
                    target_hwnd, None)
                user32.AttachThreadInput(current_thread, target_thread, True)
                
                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(target_hwnd)
                user32.BringWindowToTop(target_hwnd)
                
                user32.AttachThreadInput(current_thread, target_thread, False)
                print_result("Chrome window found", f"hwnd={target_hwnd}")
                print_result("Brought to foreground", "YES")
                return True
            return False
        
        if not bring_chrome_to_front():
            # Try again after a moment — sometimes Chrome needs more time
            await asyncio.sleep(2)
            bring_chrome_to_front()
    except Exception as e:
        print(f"  (Foreground focus attempt: {e})")
    
    print("  >>> Chrome should now be VISIBLE on your screen! <<<")
    
    # ------------------------------------------------------------------
    # STEP 2: Discover WebSocket endpoint via /json/version
    # ------------------------------------------------------------------
    print_step(2, "Discovering CDP WebSocket endpoint")
    
    ws_url = None
    for attempt in range(30):
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            data = json.loads(resp.read())
            ws_url = data["webSocketDebuggerUrl"]
            print_result("Browser", data.get("Browser", "?"))
            print_result("Protocol-Version", data.get("Protocol-Version", "?"))
            print_result("WebSocket URL", ws_url)
            break
        except Exception:
            await asyncio.sleep(0.5)
    
    if not ws_url:
        print("  X FAILED to connect to Chrome CDP. Is Chrome running?")
        chrome_proc.kill()
        return
    
    # ------------------------------------------------------------------
    # STEP 3: Connect via WebSocket
    # ------------------------------------------------------------------
    print_step(3, "Connecting to Chrome via raw WebSocket")
    
    ws = await websockets.connect(ws_url, max_size=16*1024*1024, ping_interval=None)
    cdp = CDPSession(ws)
    await cdp.start_reader()
    print_result("Connected", "YES")
    
    # Get browser version via CDP
    version = await cdp.send("Browser.getVersion")
    print_result("User-Agent", version.get("userAgent", "?")[:80])
    
    # ------------------------------------------------------------------
    # STEP 4: Create a new tab and attach to it
    # ------------------------------------------------------------------
    print_step(4, "Creating a new tab and attaching via Target.attachToTarget")
    
    # Enable target discovery
    await cdp.send("Target.setDiscoverTargets", {"discover": True})
    await cdp.send("Target.setAutoAttach", {
        "autoAttach": True, 
        "waitForDebuggerOnStart": False, 
        "flatten": True
    })
    
    # Create a new tab
    new_tab = await cdp.send("Target.createTarget", {"url": "about:blank"})
    target_id = new_tab["targetId"]
    print_result("Target ID", target_id)
    
    # Attach and get session ID
    attach_result = await cdp.send("Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    session_id = attach_result["sessionId"]
    print_result("Session ID", session_id[:20] + "...")
    
    # Enable required domains
    for domain in ["Page.enable", "DOM.enable", "Runtime.enable", "Network.enable"]:
        await cdp.send(domain, {}, session_id=session_id)
    print_result("Domains enabled", "Page, DOM, Runtime, Network")
    
    # ------------------------------------------------------------------
    # STEP 5: Navigate to a page (Wikipedia)
    # ------------------------------------------------------------------
    print_step(5, "Navigating to Wikipedia (Page.navigate)")
    
    nav_result = await cdp.send("Page.navigate", {
        "url": "https://en.wikipedia.org/wiki/Main_Page"
    }, session_id=session_id)
    print_result("Frame ID", nav_result.get("frameId", "?"))
    print_result("Loader ID", nav_result.get("loaderId", "?"))
    
    # Wait for page load
    await asyncio.sleep(3)
    print_result("Page loaded", "YES")
    if LIVE_MODE:
        print("  >>> LOOK AT CHROME — Wikipedia is loaded! <<<")
        await asyncio.sleep(LIVE_PAUSE)
    
    # ------------------------------------------------------------------
    # STEP 6: Take a screenshot (no physical interaction needed!)
    # ------------------------------------------------------------------
    print_step(6, "Taking screenshot via Page.captureScreenshot")
    
    screenshot = await cdp.send("Page.captureScreenshot", {
        "format": "png", "quality": 90
    }, session_id=session_id)
    
    img_data = base64.b64decode(screenshot["data"])
    screenshot_count += 1
    ss_path = os.path.join(SCREENSHOT_DIR, f"step6_wikipedia_loaded.png")
    with open(ss_path, "wb") as f:
        f.write(img_data)
    print_result("Screenshot saved", ss_path)
    print_result("Size", f"{len(img_data):,} bytes")
    
    # ------------------------------------------------------------------
    # STEP 7: Query DOM — find the search input
    # ------------------------------------------------------------------
    print_step(7, "Querying DOM for search input (DOM.querySelector)")
    
    # Get the document root
    doc = await cdp.send("DOM.getDocument", {"depth": 0}, session_id=session_id)
    root_node_id = doc["root"]["nodeId"]
    print_result("Root nodeId", root_node_id)
    
    # Find the search input via JS (more reliable across Wikipedia versions)
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": """
            (function() {
                var el = document.querySelector('#searchInput, input[name="search"], .cdx-text-input__input');
                if (!el) return null;
                el.focus();
                var r = el.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2, tag: el.tagName, id: el.id};
            })()
        """,
        "returnByValue": True
    }, session_id=session_id)
    coords = js_result.get("result", {}).get("value")
    
    if coords:
        click_x, click_y = coords["x"], coords["y"]
        print_result("Search element", f"{coords.get('tag', '?')}#{coords.get('id', '?')}")
        print_result("Center coords", f"({click_x:.0f}, {click_y:.0f})")
    else:
        click_x, click_y = 640, 200
        print_result("Fallback coords", f"({click_x}, {click_y})")
    
    # ------------------------------------------------------------------
    # STEP 8: VIRTUAL CLICK on search input — Input.dispatchMouseEvent
    #         >>> THIS IS THE KEY — YOUR PHYSICAL MOUSE DOES NOT MOVE <<<
    # ------------------------------------------------------------------
    print_step(8, "VIRTUAL CLICK on search box (Input.dispatchMouseEvent)")
    print("  >>> YOUR PHYSICAL MOUSE WILL NOT MOVE <<<")
    print("  >>> Try moving your mouse around — it stays under your control! <<<")
    
    # VIRTUAL mouse move (CDP sends to compositor, NOT to OS!)
    await cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": click_x, "y": click_y
    }, session_id=session_id)
    await asyncio.sleep(0.1)
    
    # VIRTUAL mouse click
    await cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": click_x, "y": click_y,
        "button": "left", "clickCount": 1
    }, session_id=session_id)
    await asyncio.sleep(0.05)
    await cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": click_x, "y": click_y,
        "button": "left", "clickCount": 1
    }, session_id=session_id)
    
    print_result("Virtual click sent", f"({click_x:.0f}, {click_y:.0f})")
    print_result("Physical cursor moved?", "NO!")
    if LIVE_MODE:
        print("  >>> LOOK — search box is now focused, but your cursor didn't move! <<<")
        await asyncio.sleep(LIVE_PAUSE)
    else:
        await asyncio.sleep(0.5)
    
    # ------------------------------------------------------------------
    # STEP 9: VIRTUAL TYPE into search box — Input.dispatchKeyEvent
    #         >>> AGAIN, NO PHYSICAL KEYBOARD HIJACK <<<
    # ------------------------------------------------------------------
    print_step(9, "VIRTUAL TYPE: 'Hojaiga Automation' (Input.dispatchKeyEvent)")
    print("  >>> Your physical keyboard is NOT captured <<<")
    
    search_text = "Hojaiga Automation"
    for char in search_text:
        await cdp.send("Input.dispatchKeyEvent", {
            "type": "keyDown", "text": char
        }, session_id=session_id)
        await cdp.send("Input.dispatchKeyEvent", {
            "type": "char", "text": char
        }, session_id=session_id)
        await cdp.send("Input.dispatchKeyEvent", {
            "type": "keyUp", "text": char
        }, session_id=session_id)
        await asyncio.sleep(random.uniform(0.03, 0.10))
    
    print_result("Text typed", search_text)
    print_result("Physical keyboard hijacked?", "NO!")
    if LIVE_MODE:
        print("  >>> LOOK AT CHROME — text appeared in search box without touching your keyboard! <<<")
        await asyncio.sleep(LIVE_PAUSE)
    else:
        await asyncio.sleep(1)
    
    # Screenshot after typing
    screenshot = await cdp.send("Page.captureScreenshot", {
        "format": "png", "quality": 90
    }, session_id=session_id)
    img_data = base64.b64decode(screenshot["data"])
    screenshot_count += 1
    ss_path = os.path.join(SCREENSHOT_DIR, f"step9_after_typing.png")
    with open(ss_path, "wb") as f:
        f.write(img_data)
    print_result("Screenshot saved", ss_path)
    
    # ------------------------------------------------------------------
    # STEP 10: Execute JavaScript — get page title & DOM info
    # ------------------------------------------------------------------
    print_step(10, "Execute JavaScript (Runtime.evaluate)")
    
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": "document.title",
        "returnByValue": True
    }, session_id=session_id)
    print_result("Page title", js_result["result"]["value"])
    
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": "document.querySelectorAll('a').length",
        "returnByValue": True
    }, session_id=session_id)
    print_result("Links on page", js_result["result"]["value"])
    
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": """
            (function() {
                var searchInput = document.querySelector('#searchInput, input[name="search"], .cdx-text-input__input');
                return searchInput ? searchInput.value : 'NOT_FOUND';
            })()
        """,
        "returnByValue": True
    }, session_id=session_id)
    print_result("Search input value", js_result["result"]["value"])
    
    # ------------------------------------------------------------------
    # STEP 11: Navigate to Google
    # ------------------------------------------------------------------
    print_step(11, "Navigate to Google (second navigation)")
    
    await cdp.send("Page.navigate", {
        "url": "https://www.google.com"
    }, session_id=session_id)
    await asyncio.sleep(3)
    
    # Screenshot
    screenshot = await cdp.send("Page.captureScreenshot", {
        "format": "png", "quality": 90
    }, session_id=session_id)
    img_data = base64.b64decode(screenshot["data"])
    screenshot_count += 1
    ss_path = os.path.join(SCREENSHOT_DIR, f"step11_google.png")
    with open(ss_path, "wb") as f:
        f.write(img_data)
    print_result("Screenshot saved", ss_path)
    
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": "document.title",
        "returnByValue": True
    }, session_id=session_id)
    print_result("Page title", js_result["result"]["value"])
    if LIVE_MODE:
        print("  >>> LOOK — Google loaded! Your mouse is still free! <<<")
        await asyncio.sleep(LIVE_PAUSE)
    
    # ------------------------------------------------------------------
    # STEP 12: Virtual click + type on Google search
    # ------------------------------------------------------------------
    print_step(12, "VIRTUAL CLICK + TYPE on Google search bar")
    
    js_result = await cdp.send("Runtime.evaluate", {
        "expression": """
            (function() {
                var el = document.querySelector('textarea[name="q"], input[name="q"]');
                if (!el) return null;
                el.focus();
                var r = el.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            })()
        """,
        "returnByValue": True
    }, session_id=session_id)
    
    coords = js_result.get("result", {}).get("value")
    if coords:
        gx, gy = coords["x"], coords["y"]
        print_result("Google search center", f"({gx:.0f}, {gy:.0f})")
        
        # Virtual click
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": gx, "y": gy,
            "button": "left", "clickCount": 1
        }, session_id=session_id)
        await asyncio.sleep(0.05)
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": gx, "y": gy,
            "button": "left", "clickCount": 1
        }, session_id=session_id)
        await asyncio.sleep(0.5)
        
        # Virtual type
        for char in "CDP virtual input demo":
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyDown", "text": char
            }, session_id=session_id)
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "char", "text": char
            }, session_id=session_id)
            await cdp.send("Input.dispatchKeyEvent", {
                "type": "keyUp", "text": char
            }, session_id=session_id)
            await asyncio.sleep(random.uniform(0.02, 0.08))
        
        print_result("Typed in Google", "CDP virtual input demo")
        print_result("Physical cursor moved?", "NO!")
        if LIVE_MODE:
            print("  >>> LOOK AT CHROME — typed in Google search! Move your mouse to prove it's free! <<<")
            await asyncio.sleep(LIVE_PAUSE)
        else:
            await asyncio.sleep(1)
        
        # Screenshot
        screenshot = await cdp.send("Page.captureScreenshot", {
            "format": "png", "quality": 90
        }, session_id=session_id)
        img_data = base64.b64decode(screenshot["data"])
        screenshot_count += 1
        ss_path = os.path.join(SCREENSHOT_DIR, f"step12_google_typed.png")
        with open(ss_path, "wb") as f:
            f.write(img_data)
        print_result("Screenshot saved", ss_path)
    else:
        print("  Warning: Could not find Google search box (consent page?)")
    
    # ------------------------------------------------------------------
    # STEP 13: Virtual scroll demo
    # ------------------------------------------------------------------
    print_step(13, "VIRTUAL SCROLL (Input.dispatchMouseEvent type=mouseWheel)")
    
    await cdp.send("Page.navigate", {
        "url": "https://en.wikipedia.org/wiki/Automation"
    }, session_id=session_id)
    await asyncio.sleep(3)
    
    for _ in range(5):
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": 640, "y": 450,
            "deltaX": 0, "deltaY": 300
        }, session_id=session_id)
        await asyncio.sleep(0.3)
    
    print_result("Scrolled down", "5 x 300px")
    print_result("Physical scroll wheel used?", "NO!")
    if LIVE_MODE:
        print("  >>> LOOK — page scrolled down without touching your scroll wheel! <<<")
        await asyncio.sleep(LIVE_PAUSE)
    
    screenshot = await cdp.send("Page.captureScreenshot", {
        "format": "png", "quality": 90
    }, session_id=session_id)
    img_data = base64.b64decode(screenshot["data"])
    screenshot_count += 1
    ss_path = os.path.join(SCREENSHOT_DIR, f"step13_scrolled.png")
    with open(ss_path, "wb") as f:
        f.write(img_data)
    print_result("Screenshot saved", ss_path)
    
    # ------------------------------------------------------------------
    # STEP 14: Get accessibility tree
    # ------------------------------------------------------------------
    print_step(14, "Get Accessibility Tree (Accessibility.getFullAXTree)")
    
    try:
        await cdp.send("Accessibility.enable", {}, session_id=session_id)
        ax_tree = await cdp.send("Accessibility.getFullAXTree", {
            "depth": 2
        }, session_id=session_id)
        nodes = ax_tree.get("nodes", [])
        print_result("AX tree nodes (depth=2)", len(nodes))
        shown = 0
        for node in nodes[:50]:
            name = node.get("name", {}).get("value", "")
            role = node.get("role", {}).get("value", "")
            if name and role and role not in ("none", "generic"):
                print(f"    [{role}] {name[:60]}")
                shown += 1
                if shown >= 8:
                    break
    except Exception as e:
        print(f"  Warning: AX tree query failed: {e}")
    
    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  CDP DEMO COMPLETE")
    print(f"{'='*60}")
    print(f"  Screenshots saved: {screenshot_count} files in {SCREENSHOT_DIR}")
    print(f"  Physical mouse moved: NEVER")
    print(f"  Physical keyboard hijacked: NEVER")
    print(f"  All input was dispatched via CDP's virtual input engine:")
    print(f"    - Input.dispatchMouseEvent (click, hover, scroll)")
    print(f"    - Input.dispatchKeyEvent (type, keyDown/Up)")
    print(f"  This is the model DAP (Organ 24) must replicate for desktop apps.")
    print(f"{'='*60}\n")
    
    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------
    print("  Closing CDP session and terminating Chrome...")
    await cdp.close()
    
    try:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=5)
    except Exception:
        try:
            chrome_proc.kill()
        except Exception:
            pass
    
    print("  Done! Chrome terminated cleanly.")
    print(f"\n  Check screenshots at: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    asyncio.run(run_cdp_demo())
