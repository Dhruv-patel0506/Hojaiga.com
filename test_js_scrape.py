"""
Quick test: Verify Google Maps scrape JS works (no async/await bug)
"""
import sys, os, time, json, logging

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_js")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "All codes", "core_organs"))

from lead_extractor import (
    ensure_organ19_running, send_cdp_command, send_cdp_navigate,
    send_cdp_js, _GOOGLE_MAPS_SCRAPE_JS, _MAPS_FEED_SCROLL_JS
)

# Step 1: Kill old Chrome, start fresh
logger.info("Killing old Chrome processes...")
os.system("taskkill /F /IM chrome.exe >nul 2>&1")
time.sleep(2)

# Step 2: Start organ_19 and launch headless Chrome
logger.info("Starting organ_19 CDP Runtime...")
ok = ensure_organ19_running(timeout=20.0)
logger.info(f"organ_19 running: {ok}")

if not ok:
    logger.error("organ_19 not running, exiting")
    sys.exit(1)

# Step 3: Launch Chrome headless
logger.info("Launching Chrome HEADLESS...")
launch_result = send_cdp_command(0x0100, {"headless": True, "profile_id": "test_qa"}, timeout=60.0)
logger.info(f"Launch result: {launch_result}")

if not launch_result:
    logger.error("Chrome launch failed!")
    sys.exit(1)

# Step 4: Navigate to Google Maps
url = "https://www.google.com/maps/search/coffee+shops+in+Austin+TX"
logger.info(f"Navigating to: {url}")
nav_ok = send_cdp_navigate(url, timeout=25.0)
logger.info(f"Navigation: {nav_ok}")

# Step 5: Wait for Maps to fully render
logger.info("Waiting 10s for Google Maps to render...")
time.sleep(10.0)

# Step 6: Dismiss consent popup
logger.info("Dismissing consent popup...")
consent_js = """
(() => {
    const btns = document.querySelectorAll('button[aria-label*="Accept"], button[aria-label*="accept"], #L2AGLb, form button');
    for (const b of btns) { if (b.offsetParent !== null) { b.click(); return 'clicked'; } }
    return 'none';
})()
"""
consent = send_cdp_js(consent_js, timeout=5.0)
logger.info(f"Consent: {consent}")
time.sleep(2.0)

# Step 7: Scroll feed 8 times
logger.info("Scrolling feed 8 times...")
for i in range(8):
    res = send_cdp_js(_MAPS_FEED_SCROLL_JS, timeout=5.0)
    logger.info(f"  Scroll {i+1}: {res}")
    time.sleep(1.5)

# Step 8: Debug — check what DOM elements exist
logger.info("Debug: checking DOM elements...")
debug_js = """
(() => {
    const feed = document.querySelectorAll('div[role="feed"] > div');
    const nv2pk = document.querySelectorAll('.Nv2PK');
    const hfpxzc = document.querySelectorAll('a.hfpxzc');
    const ariaLinks = document.querySelectorAll('a[aria-label]');
    const url = window.location.href;
    const title = document.title;
    return JSON.stringify({
        url: url,
        title: title,
        feed_children: feed.length,
        Nv2PK: nv2pk.length,
        hfpxzc: hfpxzc.length,
        aria_links: ariaLinks.length,
        body_length: (document.body ? document.body.innerText : '').length
    });
})()
"""
debug_result = send_cdp_js(debug_js, timeout=10.0)
logger.info(f"DOM debug: {debug_result}")

# Step 9: Execute the scrape JS
logger.info("Executing scrape JS...")
raw = send_cdp_js(_GOOGLE_MAPS_SCRAPE_JS, timeout=30.0)
logger.info(f"Raw scrape result type: {type(raw)}, length: {len(str(raw)) if raw else 0}")

if raw:
    try:
        results = json.loads(raw) if isinstance(raw, str) else raw
        logger.info(f"Scraped {len(results)} businesses!")
        for r in results[:10]:
            logger.info(f"  -> {r.get('company')}: phone={r.get('phone')}, web={r.get('website')}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Raw content (first 500 chars): {str(raw)[:500]}")
else:
    logger.error("Scrape returned None or empty")

# Step 10: Also take a screenshot for debugging
logger.info("Taking screenshot for debug...")
screenshot = send_cdp_screenshot(format="jpeg", quality=60, timeout=15.0)
if screenshot:
    # Save screenshot to file
    import base64
    ss_path = os.path.join(os.path.dirname(__file__), "debug_maps_screenshot.jpg")
    with open(ss_path, "wb") as f:
        f.write(base64.b64decode(screenshot))
    logger.info(f"Screenshot saved: {ss_path}")
else:
    logger.warning("Screenshot failed")

logger.info("DONE")
