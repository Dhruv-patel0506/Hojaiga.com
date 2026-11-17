import time
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

PROFILE_DIR = r"D:\chrome_automation_profile"
QUERY = "AI Engineer"

print("=" * 70)
print("HOJAIGA UNRESTRICTED MULTI-TAB BROWSER ENGINE")
print("=" * 70)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=False,
        viewport=None,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ],
    )

    # Tab 1: LinkedIn Live Search
    page1 = context.pages[0] if context.pages else context.new_page()
    if stealth_sync:
        stealth_sync(page1)

    print(f"\n[Tab 1] Executing direct LinkedIn search for '{QUERY}'...")
    encoded_query = urllib.parse.quote(QUERY)
    search_url = f"https://www.linkedin.com/search/results/all/?keywords={encoded_query}&origin=GLOBAL_SEARCH_HEADER"

    # Use wait_until="commit" so lingering background analytics never stall execution
    page1.goto(search_url, wait_until="commit")
    time.sleep(3)  # Allow DOM reconciliation

    print(f"  • Active URL : {page1.url}")
    print(f"  • Page Title : {page1.title()}")

    # Extract search result titles
    headings = page1.locator("span.entity-result__title-text, a.app-aware-link").all_inner_texts()
    clean_titles = [h.strip() for h in headings if len(h.strip()) > 3 and "\n" not in h][:6]

    print("\n[Tab 1 Results] Scraped from live feed:")
    if clean_titles:
        for idx, title in enumerate(clean_titles, 1):
            print(f"   [{idx}] {title}")
    else:
        print("   (No text-based cards found; session may be prompted for verification)")

    # Tab 2: Open a second tab (e.g., YouTube or Google Search) to verify zero buffering
    print("\n[Tab 2] Opening second tab simultaneously (YouTube)...")
    page2 = context.new_page()
    if stealth_sync:
        stealth_sync(page2)

    yt_url = f"https://www.youtube.com/results?search_query={encoded_query}"
    page2.goto(yt_url, wait_until="commit")
    time.sleep(2)

    print(f"  • Tab 2 URL   : {page2.url}")
    print(f"  • Tab 2 Title : {page2.title()}")

    yt_videos = page2.locator("#video-title").all_inner_texts()
    clean_yt = [v.strip() for v in yt_videos if v.strip()][:3]

    print("\n[Tab 2 Results] Live YouTube Videos:")
    for idx, title in enumerate(clean_yt, 1):
        print(f"   [{idx}] {title}")

    print("\n[*] Browser running freely without network hangs. Closing in 5 seconds...")
    time.sleep(5)
    context.close()

print("\n[+] Test complete.")