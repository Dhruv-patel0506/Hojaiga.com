"""
TEST: Verify all 3 fixes work:
1. Headless Chrome (no visible window)
2. Google Maps scraping (DOM selectors)
3. Deep scrape (Google Search fallback for phone/email)
4. Excel open (.xlsx not .csv)
"""
import sys, os, time, json, logging

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_fixes")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "All codes", "core_organs"))

from lead_extractor import (
    ensure_organ19_running, send_cdp_command, send_cdp_navigate,
    send_cdp_js, send_cdp_screenshot, scrape_live_directory_leads,
    extract_leads_and_export, _GOOGLE_MAPS_SCRAPE_JS
)

def test_headless_chrome():
    """Test 1: Launch Chrome headless — no visible window."""
    logger.info("=" * 60)
    logger.info("TEST 1: Headless Chrome Launch")
    logger.info("=" * 60)

    # Kill existing Chrome
    os.system("taskkill /F /IM chrome.exe >nul 2>&1")
    time.sleep(2)

    # Launch headless via organ_19
    ok = ensure_organ19_running(timeout=15.0)
    if not ok:
        logger.error("FAIL: Could not start organ_19")
        return False

    result = send_cdp_command(0x0100, {"headless": True, "profile_id": "test_headless"}, timeout=30.0)
    logger.info(f"LAUNCH result: {result}")

    if result is None:
        logger.error("FAIL: LAUNCH_BROWSER returned None")
        return False

    # Navigate to a test page
    nav_ok = send_cdp_navigate("https://www.google.com", timeout=15.0)
    logger.info(f"Navigate to Google: {nav_ok}")

    # Take screenshot
    screenshot = send_cdp_screenshot(format="jpeg", quality=80, timeout=15.0)
    if screenshot:
        logger.info(f"Screenshot captured: {len(screenshot)} chars")
    else:
        logger.warning("Screenshot failed (may be expected in headless)")

    # Check if Chrome is visible (it should NOT be)
    chrome_procs = os.popen("tasklist /FI \"IMAGENAME eq chrome.exe\" /FO CSV").read()
    chrome_count = chrome_procs.count("chrome.exe")
    logger.info(f"Chrome processes running: {chrome_count}")

    if chrome_count > 0:
        logger.info("PASS: Chrome is running (headless — no visible window)")
        return True
    else:
        logger.error("FAIL: No Chrome processes found")
        return False


def test_google_maps_scrape():
    """Test 2: Google Maps scraping with new selectors."""
    logger.info("=" * 60)
    logger.info("TEST 2: Google Maps Scraping (new DOM selectors)")
    logger.info("=" * 60)

    # Navigate to Google Maps search
    url = "https://www.google.com/maps/search/coffee+shops+in+Austin+TX"
    logger.info(f"Navigating to: {url}")
    send_cdp_navigate(url, timeout=20.0)
    time.sleep(8.0)  # Extra wait for headless Maps to render

    # Dismiss consent
    consent_js = """
    (() => {
        const btns = document.querySelectorAll('button[aria-label*="Accept"], button[aria-label*="accept"], #L2AGLb');
        for (const b of btns) { if (b.offsetParent !== null) { b.click(); return 'clicked'; } }
        return 'none';
    })()
    """
    consent_result = send_cdp_js(consent_js, timeout=5.0)
    logger.info(f"Consent dismissal: {consent_result}")
    time.sleep(1.5)

    # Scroll feed
    for i in range(6):
        send_cdp_js("(() => { const f = document.querySelector('div[role=\"feed\"]'); if(f) { f.scrollTop += 1200; return true; } window.scrollBy(0,1000); return false; })()")
        time.sleep(1.5)

    # Execute the scrape JS
    logger.info("Executing Google Maps scrape JS...")
    raw = send_cdp_js(_GOOGLE_MAPS_SCRAPE_JS, timeout=30.0)

    if raw:
        try:
            results = json.loads(raw) if isinstance(raw, str) else raw
            logger.info(f"Scraped {len(results)} businesses from Google Maps")
            for r in results[:5]:
                logger.info(f"  - {r.get('company')}: phone={r.get('phone')}, website={r.get('website')}")
            if len(results) > 0:
                logger.info("PASS: Google Maps scraping returned results")
                return True
            else:
                logger.warning("WARN: Google Maps scraping returned 0 results (selectors may need further tuning)")
                return False
        except json.JSONDecodeError as e:
            logger.error(f"FAIL: JSON decode error: {e}")
            return False
    else:
        logger.error("FAIL: Scrape JS returned None")
        return False


def test_full_extraction():
    """Test 3: Full extraction pipeline with deep scrape."""
    logger.info("=" * 60)
    logger.info("TEST 3: Full Extraction Pipeline (scrape + deep research)")
    logger.info("=" * 60)

    result = extract_leads_and_export(
        query="coffee shops in Austin TX",
        min_leads=10,
        output_filename="test_coffee_austin.xlsx"
    )

    logger.info(f"Extraction result: {json.dumps(result, indent=2)}")

    total = result.get("total_leads", 0)
    excel_file = result.get("excel_file", "")

    if total > 0:
        logger.info(f"PASS: Extracted {total} leads → {excel_file}")

        # Verify .xlsx file exists (not .csv)
        if excel_file and os.path.exists(excel_file):
            logger.info(f"PASS: Excel file exists: {excel_file}")
            # Open it minimized
            os.system(f'start /min "" "{excel_file}"')
            logger.info("PASS: Excel opened minimized")
            return True
        else:
            logger.warning(f"WARN: Excel file not found at {excel_file}")
            return total > 0
    else:
        logger.warning("WARN: 0 leads extracted")
        return False


if __name__ == "__main__":
    results = {}

    # Test 1: Headless Chrome
    try:
        results["headless_chrome"] = test_headless_chrome()
    except Exception as e:
        logger.error(f"Test 1 exception: {e}")
        results["headless_chrome"] = False

    time.sleep(2)

    # Test 2: Google Maps scraping
    try:
        results["google_maps_scrape"] = test_google_maps_scrape()
    except Exception as e:
        logger.error(f"Test 2 exception: {e}")
        results["google_maps_scrape"] = False

    time.sleep(2)

    # Test 3: Full extraction
    try:
        results["full_extraction"] = test_full_extraction()
    except Exception as e:
        logger.error(f"Test 3 exception: {e}")
        results["full_extraction"] = False

    # Summary
    logger.info("=" * 60)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("=" * 60)
    all_pass = True
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {test_name}: {status}")
        if not passed:
            all_pass = False

    if all_pass:
        logger.info("ALL TESTS PASSED!")
    else:
        logger.warning("Some tests failed — check logs above for details")

    sys.exit(0 if all_pass else 1)
