"""
cookie_vault.py — session cookie vault for login bypass
Stores LinkedIn/Gmail cookies after first manual login, reloads via CDP/Selenium next run — no user disturb.
Uses Chrome user-data-dir (persistent profile) + JSON vault via gatekeeper_wire.
"""
import os, json, time
from pathlib import Path

VAULT_DIR = Path(r"D:\new_automation\var\hojaiga\cookie_vault")
VAULT_DIR.mkdir(parents=True, exist_ok=True)

def vault_path(site: str) -> Path:
    return VAULT_DIR / f"{site.lower()}.json"

def save_cookies_selenium(driver, site: str):
    """Call once after you manually log in — dumps driver.get_cookies() to vault."""
    cookies = driver.get_cookies()
    p = vault_path(site)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print(f"[Vault] saved {len(cookies)} cookies for {site} -> {p}")
    return p

def load_cookies_selenium(driver, site: str, domain_hint: str = ""):
    """Before navigate — injects vault cookies via Selenium add_cookie + CDP set."""
    p = vault_path(site)
    if not p.exists():
        print(f"[Vault] no vault for {site}, need first login")
        return False
    with open(p, encoding="utf-8") as f:
        cookies = json.load(f)
    # must be on domain before add_cookie
    if domain_hint:
        driver.get(domain_hint)
        time.sleep(2)
    added=0
    for c in cookies:
        try:
            # Selenium requires expiry as int
            if "expiry" in c:
                c["expiry"] = int(c["expiry"])
            driver.add_cookie({k: v for k,v in c.items() if k in ["name","value","domain","path","expiry","secure","httpOnly","sameSite"]})
            added+=1
        except Exception:
            pass
    print(f"[Vault] loaded {added}/{len(cookies)} cookies for {site}")
    return added>0

# CDP variant for Organ19
async def save_cookies_cdp(session_id: str, invoker, site: str):
    res = await invoker(session_id, "Storage.getCookies", {})
    cookies = res.get("cookies", [])
    p=vault_path(site)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print(f"[Vault CDP] saved {len(cookies)} for {site}")
    return p

async def load_cookies_cdp(session_id: str, invoker, site: str):
    p=vault_path(site)
    if not p.exists():
        return False
    cookies=json.load(open(p, encoding="utf-8"))
    await invoker(session_id, "Storage.setCookies", {"cookies": cookies})
    print(f"[Vault CDP] loaded {len(cookies)} for {site}")
    return True
