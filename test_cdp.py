import sys
from playwright.sync_api import sync_playwright

print("[*] Connecting to live Chrome on port 9222...")

try:
    with sync_playwright() as p:
        # Attaches directly to your open Chrome window
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        print("[*] Navigating to LinkedIn Feed inside your live Chrome session...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        
        print("\n✅ SUCCESSFUL CDP ATTACHMENT!")
        print(f"  • Live Window Title : {page.title()}")
        print(f"  • Current URL       : {page.url}")

        # Scan interactive elements as a logged-in user
        buttons = page.locator("button").count()
        inputs = page.locator("input").count()
        print(f"  • Visible Buttons   : {buttons}")
        print(f"  • Visible Inputs    : {inputs}")

except Exception as e:
    print(f"\n❌ FAILED TO CONNECT: {e}")
    print("Ensure Chrome was launched with --remote-debugging-port=9222 and is still running.")