import time
from playwright.sync_api import sync_playwright

PROFILE_DIR = r"D:\chrome_automation_profile"
SEARCH_QUERY = "AI Engineer"

print(f"[*] Launching persistent Chrome profile to search for '{SEARCH_QUERY}'...")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=False,
        viewport=None,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_navigation_timeout(30000)
    page.set_default_timeout(15000)

    # 1. Navigate with wait_until="commit" so it never hangs on background WebSockets
    print("[*] Navigating to LinkedIn feed (instant commit)...")
    page.goto("https://www.linkedin.com/feed/", wait_until="commit")

    # 2. Wait for the search box to appear in the DOM
    print("[*] Locating search input...")
    search_input = page.wait_for_selector('input.search-global-typeahead__input, input[placeholder*="Search"]', state="visible", timeout=12000)
    
    if search_input:
        print(f"[*] Typing query '{SEARCH_QUERY}' into search bar...")
        search_input.click()
        search_input.fill("")
        search_input.type(SEARCH_QUERY, delay=50)
        
        # Submit the search
        page.keyboard.press("Enter")
        print("[*] Query submitted. Waiting for search results to render...")

        # 3. Wait specifically for result items rather than network idle
        try:
            page.wait_for_selector('div.search-results-container, ul.reusable-search__entity-result-list, div[data-view-name="search-entity-result"]', state="visible", timeout=10000)
            print("✅ Search results loaded successfully without buffering!")
        except Exception:
            # Fallback check if URL updated to search results
            page.wait_for_timeout(3000)
            print(f"[*] Current URL: {page.url}")

        # 4. Extract first 5 result titles
        results = page.locator('span[dir="ltr"] span[aria-hidden="true"]').all_text_contents()
        clean_results = [r.strip() for r in results if len(r.strip()) > 3][:5]
        
        print("\n" + "=" * 60)
        print("TOP SEARCH RESULTS EXTRACTED:")
        for idx, title in enumerate(clean_results, 1):
            print(f"  [{idx}] {title}")
        print("=" * 60)

    else:
        print("❌ Could not find search bar. Check if the session is still signed in.")

    time.sleep(3)
    context.close()
    print("[*] Test completed cleanly.")