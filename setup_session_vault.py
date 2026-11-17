import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

PROFILE_DIR = r"D:\chrome_automation_profile"
Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

print("=" * 75)
print("HOJAIGA SESSION VAULT: INTERACTIVE AUTHENTICATION SETUP")
print("=" * 75)
print("1. Chrome will open with tabs for LinkedIn, YouTube, and Google/Gmail.")
print("2. The browser WILL NOT close automatically. Take all the time you need.")
print("3. Log in to your accounts manually.")
print("4. When you are fully logged in across tabs, return here and press ENTER.")
print("=" * 75)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=False,
        viewport=None,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ],
    )

    # Tab 1: LinkedIn
    page_linkedin = context.pages[0] if context.pages else context.new_page()
    if stealth_sync:
        stealth_sync(page_linkedin)
    print("\n[*] Opening LinkedIn on Tab 1...")
    page_linkedin.goto("https://www.linkedin.com/login", wait_until="load")

    # Tab 2: YouTube
    page_yt = context.new_page()
    if stealth_sync:
        stealth_sync(page_yt)
    print("[*] Opening YouTube on Tab 2...")
    page_yt.goto("https://www.youtube.com", wait_until="load")

    # Tab 3: Google / Gmail
    page_google = context.new_page()
    if stealth_sync:
        stealth_sync(page_google)
    print("[*] Opening Google Login on Tab 3...")
    page_google.goto("https://accounts.google.com", wait_until="load")

    print("\n" + "#" * 60)
    print("👉 BROWSER IS READY & WAITING FOR YOU.")
    print("   Switch to Chrome, complete your logins, and solve any 2FA/prompts.")
    print("#" * 60)

    # Wait indefinitely for user to press Enter
    input("\n===> Press [ENTER] in this terminal ONLY after you have finished logging in: ")

    print("\n[*] Auditing session cookies & active states...")

    # Validate LinkedIn
    page_linkedin.bring_to_front()
    page_linkedin.wait_for_timeout(1000)
    li_logged_in = "feed" in page_linkedin.url or page_linkedin.locator("nav.global-nav").count() > 0

    # Validate YouTube
    page_yt.bring_to_front()
    page_yt.wait_for_timeout(1000)
    yt_logged_in = page_yt.locator("button#avatar-btn, ytd-topbar-menu-button-renderer").count() > 0

    # Extract all cookies
    cookies = context.cookies()
    domain_summary = {}
    for c in cookies:
        domain = c.get("domain", "")
        domain_summary[domain] = domain_summary.get(domain, 0) + 1

    print("\n" + "=" * 60)
    print("SESSION VAULT AUDIT RESULTS:")
    print("=" * 60)
    print(f"  • LinkedIn Logged In  : {'✅ YES' if li_logged_in else '⚠️ NOT DETECTED (Check if still on login page)'}")
    print(f"  • YouTube Logged In   : {'✅ YES' if yt_logged_in else '⚠️ NOT DETECTED'}")
    print(f"  • Total Cookies Saved : {len(cookies)}")
    print("  • Saved Domains Breakdown:")
    for dom, count in sorted(domain_summary.items(), key=lambda x: -x[1])[:8]:
        print(f"     - {dom}: {count} cookies")
    print("=" * 60)

    # Save cookie backup manifest
    backup_file = Path(r"D:\new_automation\reports\saved_cookies_manifest.json")
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    print(f"[*] Cookie manifest backed up to: {backup_file}")

    print("\n[*] Closing browser safely to flush cookies to disk...")
    context.close()
    print("✅ All sessions are permanently saved in D:\\chrome_automation_profile!")