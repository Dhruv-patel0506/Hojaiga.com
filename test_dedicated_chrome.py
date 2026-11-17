import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = r"D:\chrome_automation_profile"

print("[*] Launching dedicated Chrome window alongside your personal Chrome...")

with sync_playwright() as p:
    # 1. Launches your real installed Google Chrome without touching existing Chrome processes
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",          # Uses your real installed Chrome
        headless=False,            # Visible window so you can watch and interact
        viewport=None,             # Full window size
        ignore_default_args=["--enable-automation"],  # Removes "Chrome is being controlled by automated software" banner
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized"
        ]
    )

    page = context.pages[0] if context.pages else context.new_page()

    print("[*] Navigating to LinkedIn...")
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    
    print("\n" + "=" * 70)
    print("👉 A DEDICATED CHROME WINDOW IS NOW OPEN!")
    print("   • Log in to LinkedIn / YouTube / GitHub manually in this window.")
    print("   • Your session will remain saved in D:\\chrome_automation_profile.")
    print("   • You have 45 seconds to log in (or press Enter in terminal when done).")
    print("=" * 70)

    try:
        input("\nPress ENTER here once you have logged in...")
    except Exception:
        time.sleep(30)

    print(f"\n✅ Active Page Title: {page.title()}")
    print(f"   • Current URL: {page.url}")
    print(f"   • Detected Buttons: {page.locator('button').count()}")
    print(f"   • Detected Inputs:  {page.locator('input').count()}")

    context.close()
    print("\n[*] Profile saved to disk. All future automation runs will open pre-authenticated!")