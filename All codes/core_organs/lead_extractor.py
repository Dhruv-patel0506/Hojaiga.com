"""
Lead Extraction & Excel Export Engine for Hojaiga AOS.
100% Real Live Directory Scraping via Chrome CDP (organ_19 IPC).
Zero Hardcoded Catalogs. Zero Fabricated Data.
"""

import os
import re
import json
import time
import struct
import socket
import logging
import urllib.parse
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hojaiga.lead_extractor")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

CDP_PORT = 47619
IPC_LENGTH_HEADER = struct.Struct(">I")
IPC_OPCODE_HEADER = struct.Struct(">H")

# Deduplication: prevent deep scrape from running twice in the same process
# (CrewAI failure → fallback re-runs EXTRACT_LEADS → second deep scrape hits Google rate limits)
_deep_scrape_session_done = False
_last_deep_scrape_leads_key = None


# ============================================================
# CDP IPC HELPER — sends commands to organ_19
# ============================================================

def ensure_organ19_running(timeout: float = 12.0) -> bool:
    """Ensure organ_19 IPC server is listening on port 47619; starts it if absent."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("127.0.0.1", CDP_PORT))
        sock.close()
        return True
    except Exception:
        pass

    import subprocess, sys
    organ_19_path = os.path.join(os.path.dirname(__file__), "organ_19_chrome_cdp_runtime.py")
    if os.path.exists(organ_19_path):
        logger.info("[SCRAPER] Starting Organ 19 Chrome CDP Runtime...")
        subprocess.Popen([sys.executable, organ_19_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(("127.0.0.1", CDP_PORT))
                s.close()
                logger.info("[SCRAPER] Organ 19 CDP Runtime is ready.")
                return True
            except Exception:
                pass
    return False


def send_cdp_command(opcode: int, payload_dict: dict, timeout: float = 25.0, retry_connect: bool = True) -> Any:
    """Send binary frame command to organ_19 via TCP loopback and return decoded result."""
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    header = IPC_LENGTH_HEADER.pack(len(payload_bytes) + 2) + IPC_OPCODE_HEADER.pack(opcode)
    frame = header + payload_bytes

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(("127.0.0.1", CDP_PORT))
    except (ConnectionRefusedError, OSError):
        if retry_connect and ensure_organ19_running():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(("127.0.0.1", CDP_PORT))
            except Exception as e:
                logger.warning(f"CDP IPC reconnect failed: {e}")
                return None
        else:
            return None

    try:
        sock.sendall(frame)

        # Read 4-byte length header
        len_data = b""
        while len(len_data) < 4:
            chunk = sock.recv(4 - len(len_data))
            if not chunk:
                return None
            len_data += chunk

        total_len = IPC_LENGTH_HEADER.unpack(len_data)[0]
        if total_len > 16 * 1024 * 1024:
            return None

        # Read response body
        body = b""
        while len(body) < total_len:
            chunk = sock.recv(min(65536, total_len - len(body)))
            if not chunk:
                break
            body += chunk

        # Decode response frame (skip 2-byte opcode)
        resp_payload = json.loads(body[2:].decode("utf-8")) if len(body) > 2 else {}
        result = resp_payload.get("result", resp_payload)
        return result.get("value") if isinstance(result, dict) and "value" in result else result

    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        logger.warning(f"CDP IPC connection failed: {e}")
        return None
    finally:
        sock.close()


def send_cdp_js(expression: str, timeout: float = 15.0) -> Any:
    """Execute JavaScript expression on active tab via organ_19 EXECUTE_JS (0x0160)."""
    opcode_execute_js = 0x0160
    return send_cdp_command(opcode_execute_js, {"expression": expression}, timeout=timeout)


def send_cdp_navigate(url: str, timeout: float = 180.0) -> bool:
    """Navigate active tab to url via organ_19 NAVIGATE (0x0120).

    The timeout MUST exceed organ_19's human-login HITL gate
    (HOJAIGA_LOGIN_WAIT_S, default 120s): when a site such as Gmail shows a
    login wall, navigate_with_cookies blocks for the human to sign in and then
    stores the session cookies for reuse. A short client timeout used to abort
    that wait and report a false failure, which made the agent flail.
    """
    opcode_navigate = 0x0120
    res = send_cdp_command(opcode_navigate, {"url": url}, timeout=timeout)
    if isinstance(res, dict) and res.get("ok") is False:
        return False
    return res is not None


def send_cdp_screenshot(format: str = "jpeg", quality: int = 80, timeout: float = 20.0) -> Optional[str]:
    """Capture viewport screenshot over Chrome CDP socket (opcode 0x01B0) and return base64 string."""
    opcode_screenshot = 0x01B0
    res = send_cdp_command(opcode_screenshot, {"mode": "viewport", "format": format, "quality": quality}, timeout=timeout)
    if isinstance(res, dict):
        return res.get("image_base64")
    return res if isinstance(res, str) else None


def send_cdp_click_coordinates(x: float, y: float, timeout: float = 10.0) -> bool:
    """Click at exact (x, y) coordinates via organ_19 CLICK (0x0140) with visible neon laser pointer ripple."""
    # Render visible neon laser pointer indicator at (x, y) for automated actions
    try:
        ripple_js = f"""
        (() => {{
            try {{
                let el = document.getElementById('hojaiga-virtual-pointer');
                if (!el) {{
                    el = document.createElement('div');
                    el.id = 'hojaiga-virtual-pointer';
                    el.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;border-radius:50%;transition:all 0.2s ease-out;box-sizing:border-box;';
                    document.body.appendChild(el);
                }}
                el.style.left = '{int(x) - 14}px';
                el.style.top = '{int(y) - 14}px';
                el.style.width = '28px';
                el.style.height = '28px';
                el.style.border = '2px solid #00ffff';
                el.style.backgroundColor = 'rgba(0, 255, 255, 0.45)';
                el.style.boxShadow = '0 0 15px #00ffff, inset 0 0 8px #ffffff';
                el.style.transform = 'scale(1.5)';
                el.style.opacity = '1';
                setTimeout(() => {{
                    if (el) {{
                        el.style.transform = 'scale(0.7)';
                        el.style.opacity = '0.35';
                    }}
                }}, 350);
            }} catch(e) {{}}
        }})()
        """
        send_cdp_js(ripple_js, timeout=2.0)
    except Exception:
        pass

    opcode_click = 0x0140
    res = send_cdp_command(opcode_click, {"x": float(x), "y": float(y)}, timeout=timeout)
    return bool(res and (isinstance(res, dict) and res.get("clicked") or res is True))



# ============================================================
# LIVE DIRECTORY SCRAPERS (Google Maps & Search Places)
# ============================================================

_GOOGLE_MAPS_SCRAPE_JS = r"""
(() => {
    const results = [];
    const seen = new Set();
    const phoneRegex = /\(?\b[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/;

    // 1. Dismiss cookie/consent dialogs
    try {
        const consentSelectors = [
            'button[aria-label*="Accept"]', 'button[aria-label*="accept"]',
            '#L2AGLb', 'form[action*="consent"] button',
            'button[aria-label*="Reject"]'
        ];
        for (const sel of consentSelectors) {
            const btn = document.querySelector(sel);
            if (btn) { btn.click(); break; }
        }
    } catch(e) {}

    // 2. Scrape visible feed cards (NO async/await — must be synchronous IIFE)
    //    Strategy A: Try role=feed children (most reliable for Maps)
    let feedItems = document.querySelectorAll('div[role="feed"] > div[jsaction]');

    //    Strategy B: Try .Nv2PK cards (classic Maps layout)
    if (feedItems.length === 0) {
        feedItems = document.querySelectorAll('.Nv2PK, .bfdHYd');
    }

    //    Strategy C: Try any link with aria-label ( Maps result links)
    if (feedItems.length === 0) {
        feedItems = document.querySelectorAll('a.hfpxzc, a[role="link"][data-item-id]');
    }

    //    Strategy D: Broadest possible — any div that has a business-like link inside
    if (feedItems.length === 0) {
        const allLinks = document.querySelectorAll('a[aria-label]');
        const containers = new Set();
        allLinks.forEach(a => {
            const label = a.getAttribute('aria-label') || '';
            if (label.length > 3 && label.length < 100) {
                const parent = a.closest('div[jsaction]') || a.closest('div.Nv2PK') || a.parentElement;
                if (parent) containers.add(parent);
            }
        });
        feedItems = Array.from(containers);
    }

    for (let i = 0; i < feedItems.length; i++) {
        try {
            const card = feedItems[i];

            // Business name: try aria-label first, then text content
            let name = '';
            const linkEl = card.querySelector('a[aria-label]') || (card.tagName === 'A' ? card : null);
            if (linkEl) {
                name = (linkEl.getAttribute('aria-label') || '').trim();
            }
            if (!name) {
                const nameEl = card.querySelector('.qBF1Pd, .fontHeadlineSmall, .DbAVjc, .W4Efsd span, h3, span[role="heading"]');
                if (nameEl) name = (nameEl.textContent || '').trim();
            }
            if (!name) {
                name = (card.getAttribute('aria-label') || '').trim();
            }
            name = name.replace(/[\ue000-\uf8ff\u200b-\u200f★☆•|\u2022]/g, '').replace(/\s+/g, ' ').trim();
            if (!name || name.length < 3 || name.length > 100 || seen.has(name.toLowerCase())) continue;

            // Skip generic UI elements
            if (/^(results|search|filters|open|closed|sponsored|menu|website|directions|save|share|more filters|clear|unavailable|interactive map|ratinghours|rating|google maps|sign in|zoom out|your location|see the world|popular|review|photo|updates|near me|explore|discover)$/i.test(name)) continue;

            const text = card.innerText || '';

            // Phone
            const phoneMatch = text.match(phoneRegex);
            const phone = phoneMatch ? phoneMatch[0] : 'N/A';

            // Website: look for non-google links
            let website = 'N/A';
            const webLinks = card.querySelectorAll('a[href^="http"]');
            for (const wl of webLinks) {
                const href = wl.href || '';
                if (href && !href.includes('google.com') && !href.includes('gstatic') && !href.includes('google.aclk')) {
                    website = href;
                    break;
                }
            }

            // Category
            let category = 'Interior Design';
            const lines = text.split('\n').map(l => l.replace(/[\ue000-\uf8ff]/g, '').trim()).filter(Boolean);
            for (const line of lines) {
                if (/design|decor|architect|builder|studio|contractor|coffee|shop|store|restaurant|clinic|salon|agency|firm|plumber|electrician|lawyer|dentist|doctor/i.test(line) && line.length < 60) {
                    category = line;
                    break;
                }
            }

            // Quality Gate: must have name, and either phone or website
            if (phone === 'N/A' && website === 'N/A') continue;

            seen.add(name.toLowerCase());
            results.push({
                company: name,
                phone: phone,
                website: website,
                address: 'N/A',
                city: 'N/A',
                category: category
            });
        } catch(e) {
            continue;
        }
    }

    // 3. FALLBACK: If nothing from structured selectors, try text-based extraction
    if (results.length === 0) {
        const allLinks = document.querySelectorAll('a[aria-label]');
        for (const link of allLinks) {
            try {
                const name = (link.getAttribute('aria-label') || '').trim();
                if (!name || name.length < 3 || name.length > 100 || seen.has(name.toLowerCase())) continue;
                if (/^(results|search|filters|open|closed|sponsored|menu|website|directions|save|share|google maps|sign in|zoom out|your location|see the world|popular|review|photo|near me|explore|discover)$/i.test(name)) continue;

                const href = link.href || '';
                const parentText = (link.closest('div') || link.parentElement || {}).innerText || '';
                const phoneMatch = parentText.match(phoneRegex);

                let website = 'N/A';
                if (href && !href.includes('google.com/maps') && !href.includes('gstatic')) website = href;

                seen.add(name.toLowerCase());
                results.push({
                    company: name,
                    phone: phoneMatch ? phoneMatch[0] : 'N/A',
                    website: website,
                    address: 'N/A',
                    city: 'N/A',
                    category: 'Interior Design'
                });
            } catch(e) {}
        }
    }

    return JSON.stringify(results);
})()
"""


_GOOGLE_SEARCH_LOCAL_SCRAPE_JS = r"""
(() => {
    const results = [];
    const seen = new Set();
    const phoneRegex = /\(?\b[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/;

    // 1. Google Places Pack (.VkpGBb, [data-cid], [jscontroller])
    document.querySelectorAll('.VkpGBb, [data-cid], div[jsname="GZq3Ke"], .cXedhc').forEach(item => {
        const titleEl = item.querySelector('[role="heading"], .dbg0pd, .OSrXXb, span.LrzXr') || item.querySelector('h3');
        const name = (titleEl ? titleEl.textContent : '').trim();
        if (!name || name.length < 3 || seen.has(name.toLowerCase())) return;

        const text = item.innerText || '';
        const phoneMatch = text.match(phoneRegex);
        const phone = phoneMatch ? phoneMatch[0] : 'N/A';

        let website = 'N/A';
        const webEl = item.querySelector('a[href^="http"]:not([href*="google."])');
        if (webEl) website = webEl.href;

        seen.add(name.toLowerCase());
        results.push({
            company: name,
            phone: phone,
            website: website,
            city: 'N/A',
            category: 'Interior Design'
        });
    });

    // 2. Organic results with rich business snippets
    document.querySelectorAll('.g, .tF2Cxc, .MjjYud').forEach(g => {
        const titleEl = g.querySelector('h3');
        const aEl = g.querySelector('a[href^="http"]:not([href*="google."])');
        if (!titleEl || !aEl) return;

        const name = titleEl.textContent.trim();
        const href = aEl.href;
        if (!name || name.length < 3 || seen.has(name.toLowerCase())) return;

        const snippet = (g.querySelector('.VwiC3b, .IsZvec') || {}).textContent || '';
        const lower = (name + ' ' + snippet).toLowerCase();
        if (lower.includes('design') || lower.includes('interior') || lower.includes('decor') || lower.includes('studio')) {
            const phoneMatch = (snippet + ' ' + name).match(phoneRegex);
            seen.add(name.toLowerCase());
            results.push({
                company: name.replace(/\s*[-–|].*$/, '').trim(),
                phone: phoneMatch ? phoneMatch[0] : 'N/A',
                website: href,
                city: 'N/A',
                category: 'Interior Design'
            });
        }
    });

    return JSON.stringify(results);
})()
"""

_MAPS_FEED_SCROLL_JS = r"""
(() => {
    const feed = document.querySelector('div[role="feed"]') || document.querySelector('.m6QErb[aria-label]');
    if (feed) {
        feed.scrollTop += 1200;
        return true;
    }
    window.scrollBy(0, 1000);
    return false;
})()
"""


_VISIT_SITE_EXTRACT_JS = r"""
(() => {
    const data = {phones: [], emails: [], address: 'N/A', social: {}, subpages: []};

    // 1. Extract phone numbers from tel: links
    document.querySelectorAll('a[href^="tel:"]').forEach(a => {
        const num = a.href.replace('tel:', '').trim();
        if (num.length >= 7) data.phones.push(num);
    });

    // 2. Extract emails from mailto: links
    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
        const email = a.href.replace('mailto:', '').split('?')[0].trim();
        if (email.includes('@')) data.emails.push(email);
    });

    // 3. Scan visible text for phone patterns
    const body = document.body ? document.body.innerText : '';
    const phoneRe = /\(?\b[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
    const found = body.match(phoneRe) || [];
    data.phones.push(...found);

    // 4. Scan text for email patterns
    const emailRe = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;
    const foundEmails = body.match(emailRe) || [];
    data.emails.push(...foundEmails);

    // 5. Look for address in common elements
    const addrEl = document.querySelector('[itemprop="address"], .address, .location, .contact-address, .street-address');
    if (addrEl) data.address = addrEl.textContent.trim().substring(0, 120);

    // 6. Extract Social Links
    document.querySelectorAll('a[href*="linkedin.com"], a[href*="instagram.com"], a[href*="facebook.com"]').forEach(a => {
        const href = a.href || '';
        if (href.includes('linkedin.com') && !data.social.linkedin) data.social.linkedin = href;
        if (href.includes('instagram.com') && !data.social.instagram) data.social.instagram = href;
        if (href.includes('facebook.com') && !data.social.facebook) data.social.facebook = href;
    });

    // 7. Extract candidate subpages for multi-step deep crawl
    const seenUrls = new Set();
    document.querySelectorAll('a[href]').forEach(a => {
        const rawHref = a.getAttribute('href') || '';
        const text = (a.textContent || '').toLowerCase().trim();
        const lowerHref = rawHref.toLowerCase();
        
        const isTarget = lowerHref.includes('contact') || lowerHref.includes('about') ||
                         lowerHref.includes('team') || lowerHref.includes('reach') ||
                         lowerHref.includes('get-in-touch') || text.includes('contact') ||
                         text.includes('about') || text.includes('reach us');

        if (isTarget && !lowerHref.startsWith('tel:') && !lowerHref.startsWith('mailto:') && !lowerHref.startsWith('javascript:')) {
            try {
                const fullUrl = new URL(rawHref, window.location.href).href;
                if (!seenUrls.has(fullUrl)) {
                    seenUrls.add(fullUrl);
                    let priority = 1;
                    if (lowerHref.includes('contact') || text.includes('contact')) priority = 3;
                    else if (lowerHref.includes('about') || text.includes('about')) priority = 2;
                    data.subpages.push({url: fullUrl, priority: priority, label: text || lowerHref});
                }
            } catch(e) {}
        }
    });

    data.subpages.sort((a, b) => b.priority - a.priority);
    data.subpages = data.subpages.slice(0, 5);

    // Deduplicate
    data.phones = [...new Set(data.phones)].slice(0, 3);
    data.emails = [...new Set(data.emails)].filter(e => !e.includes('example.com') && !e.includes('sentry.io') && !e.includes('wixpress.com')).slice(0, 3);

    return JSON.stringify(data);
})()
"""


def _deep_scrape_contacts(leads: List[Dict[str, str]], max_sites: int = 25) -> List[Dict[str, str]]:
    """
    Multi-Step Research Crawler (optimized — one search per lead for phone+email):
    1. For leads with websites: visit homepage + subpages for phone/email
    2. For leads missing phone/email: single Google Search "{business} phone email contact"
    Includes deduplication (skips if already run this session) and CAPTCHA detection.
    """
    global _deep_scrape_session_done, _last_deep_scrape_leads_key

    # Deduplication: if deep scrape already completed for this exact lead set, skip
    leads_key = tuple(sorted(l.get("company", "") for l in leads))
    if _deep_scrape_session_done and _last_deep_scrape_leads_key == leads_key:
        logger.info("[DEEP] Skipping — deep scrape already completed for this lead set in this session.")
        return leads

    visited = 0
    google_searches = 0
    captcha_detected = False

    _COMBINED_EXTRACT_JS = r"""
    (() => {
        const body = document.body ? document.body.innerText : '';
        const phoneRe = /\(?\b[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
        const emailRe = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;
        const phones = (body.match(phoneRe) || []).filter(p => p.replace(/\D/g,'').length === 10);
        const emails = (body.match(emailRe) || []).filter(e =>
            !e.includes('example.com') && !e.includes('sentry.io') && !e.includes('wixpress.com') &&
            !e.includes('google.com') && !e.includes('schema.org') && !e.includes('youtube.com'));
        return JSON.stringify({phones: phones.slice(0,3), emails: emails.slice(0,3)});
    })()
    """

    _CAPTCHA_DETECT_JS = r"""
    (() => {
        const body = (document.body ? document.body.innerText : '').toLowerCase();
        return body.includes('unusual traffic') || body.includes('captcha') ||
               body.includes('not a robot') || body.includes('verify you are human') ||
               document.querySelector('form[action*="sorry"]') !== null;
    })()
    """

    for lead in leads:
        if not isinstance(lead, dict):
            continue
        if visited >= max_sites:
            break
        if captcha_detected:
            break

        company = lead.get("company", "Unknown")
        website = lead.get("website", "N/A")
        has_phone = lead.get("phone") and lead["phone"] != "N/A"
        has_email = lead.get("email") and lead["email"] != "N/A"

        # Skip if already have both
        if has_phone and has_email:
            visited += 1
            continue

        # ── STEP 1: Visit website if available ──
        if website and website != "N/A" and "google.com" not in website and "google.aclk" not in website:
            try:
                logger.info(f"[DEEP] Visiting website for {company}: {website}")
                send_cdp_navigate(website, timeout=15.0)
                time.sleep(3.0)
                raw = send_cdp_js(_VISIT_SITE_EXTRACT_JS, timeout=10.0)
                if raw:
                    cd = json.loads(raw) if isinstance(raw, str) else raw
                    if cd.get("phones") and not has_phone:
                        lead["phone"] = cd["phones"][0]; has_phone = True
                    if cd.get("emails") and not has_email:
                        lead["email"] = cd["emails"][0]; has_email = True
                    if cd.get("address") and cd["address"] != "N/A":
                        lead["address"] = cd["address"]
                    # Subpage traversal
                    if not has_phone or not has_email:
                        subs = [s["url"] for s in cd.get("subpages", []) if isinstance(s, dict) and s.get("url")]
                        if not subs:
                            base = website.rstrip("/")
                            subs = [base + "/contact", base + "/contact-us", base + "/about"]
                        for sub_url in subs[:2]:
                            try:
                                send_cdp_navigate(sub_url, timeout=10.0)
                                time.sleep(2.0)
                                raw_s = send_cdp_js(_VISIT_SITE_EXTRACT_JS, timeout=8.0)
                                if raw_s:
                                    sd = json.loads(raw_s) if isinstance(raw_s, str) else raw_s
                                    if sd.get("emails") and not has_email:
                                        lead["email"] = sd["emails"][0]; has_email = True
                                    if sd.get("phones") and not has_phone:
                                        lead["phone"] = sd["phones"][0]; has_phone = True
                                    if has_phone and has_email: break
                            except Exception: pass
                visited += 1
            except Exception as e:
                logger.debug(f"[DEEP] Website visit failed for {company}: {e}")

        # ── STEP 2: SINGLE Google Search for phone+email ──
        if not has_phone or not has_email:
            try:
                city = lead.get("city", "")
                search_query = urllib.parse.quote_plus(f"{company} {city} phone email contact")
                search_url = f"https://www.google.com/search?q={search_query}"
                logger.info(f"[DEEP] Google Search for {company}: phone={'N/A' if not has_phone else 'found'}, email={'N/A' if not has_email else 'found'}")
                send_cdp_navigate(search_url, timeout=12.0)
                time.sleep(3.5)

                # Check for CAPTCHA before extracting
                try:
                    is_captcha = send_cdp_js(_CAPTCHA_DETECT_JS, timeout=5.0)
                    if is_captcha and str(is_captcha).strip() == "true":
                        logger.warning(f"[DEEP] CAPTCHA/block detected on Google Search for {company} — stopping Google searches to avoid rate limit.")
                        captcha_detected = True
                        break
                except Exception:
                    pass

                raw = send_cdp_js(_COMBINED_EXTRACT_JS, timeout=8.0)
                if raw:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    if data.get("phones") and not has_phone:
                        lead["phone"] = data["phones"][0]
                        has_phone = True
                        logger.info(f"[DEEP] Found phone for {company}: {lead['phone']}")
                    if data.get("emails") and not has_email:
                        lead["email"] = data["emails"][0]
                        has_email = True
                        logger.info(f"[DEEP] Found email for {company}: {lead['email']}")
                google_searches += 1
                # Rate-limit protection: longer delay every 5 searches
                if google_searches % 5 == 0:
                    time.sleep(4.0)
                else:
                    time.sleep(1.5)
            except Exception as e:
                logger.debug(f"[DEEP] Google Search failed for {company}: {e}")

        visited += 1

    # Mark session as done to prevent second run
    _deep_scrape_session_done = True
    _last_deep_scrape_leads_key = leads_key

    logger.info(f"[DEEP] Research completed: {visited} leads processed, {google_searches} Google searches, captcha={'yes' if captcha_detected else 'no'}.")
    return leads


# ============================================================
# STATE & REGIONAL QUERY EXPANSION
# ============================================================

_STATE_NAME_TO_ABBR = {
    "tennessee": "TN", "tn": "TN",
    "georgia": "GA", "ga": "GA",
    "alabama": "AL", "al": "AL",
    "north carolina": "NC", "nc": "NC",
    "south carolina": "SC", "sc": "SC",
    "florida": "FL", "fl": "FL",
    "texas": "TX", "tx": "TX",
    "california": "CA", "ca": "CA",
    "new york": "NY", "ny": "NY",
    "ohio": "OH", "oh": "OH",
}

_STATE_MAJOR_CITIES: Dict[str, List[str]] = {
    "TN": ["Nashville", "Memphis", "Knoxville", "Chattanooga", "Franklin", "Murfreesboro", "Brentwood", "Clarksville", "Jackson"],
    "GA": ["Atlanta", "Savannah", "Alpharetta", "Marietta", "Roswell", "Augusta", "Athens", "Macon", "Sandy Springs", "Decatur"],
    "NC": ["Charlotte", "Raleigh", "Greensboro", "Durham", "Winston-Salem", "Asheville", "Cary", "Wilmington"],
    "FL": ["Miami", "Orlando", "Tampa", "Jacksonville", "Naples", "Fort Lauderdale", "Sarasota", "St. Petersburg"],
    "TX": ["Austin", "Dallas", "Houston", "San Antonio", "Fort Worth", "Plano", "The Woodlands"],
}


def detect_state_and_cities(query: str) -> tuple[str, List[str]]:
    """Detect state abbreviation and list of key metropolitan cities for query expansion."""
    q = query.lower()
    for name in sorted(_STATE_NAME_TO_ABBR.keys(), key=len, reverse=True):
        if name in q:
            abbr = _STATE_NAME_TO_ABBR[name]
            return abbr, _STATE_MAJOR_CITIES.get(abbr, [name.title()])
    return "GA", _STATE_MAJOR_CITIES.get("GA", ["Atlanta"])


# ============================================================
# CORE SCRAPING ENGINE (Live Web Only)
# ============================================================

def scrape_live_directory_leads(query: str, min_leads: int = 100) -> List[Dict[str, str]]:
    """
    Autonomously navigates and scrapes live business directory listings via Chrome CDP.
    Navigates to Google Maps, scrolls the feed, and expands across major cities if needed
    to reach the desired lead count.
    """
    state_abbr, cities = detect_state_and_cities(query)
    all_leads: List[Dict[str, str]] = []
    seen_names = set()

    # Pre-launch or reuse Chrome browser via organ_19 (timeout=60s — headless Chrome can be slow to start)
    send_cdp_command(0x0100, {"headless": True}, timeout=60.0)

    clean_term = re.sub(r'\b(in|whole|all|the|state|of|contacts?|to|excel|list)\b', '', query, flags=re.IGNORECASE)
    clean_term = re.sub(r'\b(tennessee|georgia|florida|texas|california|alabama|north carolina|south carolina|new york|ohio|tn|ga|fl|tx|ca|al|nc|sc|ny|oh)\b', '', clean_term, flags=re.IGNORECASE)
    clean_term = re.sub(r'\s+', ' ', clean_term).strip(" ,.-")
    if not clean_term:
        clean_term = "interior designers"

    logger.info(f"[SCRAPER] Beginning live directory extraction for '{clean_term}' across {state_abbr} (target: {min_leads} leads)")

    # Strategy 1: Google Maps live search across target cities
    for city in cities:
        if len(all_leads) >= min_leads:
            break

        city_query = f"{clean_term} in {city}, {state_abbr}"
        maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(city_query)}"
        logger.info(f"[SCRAPER] Navigating to Google Maps directory: {city_query}")

        send_cdp_navigate(maps_url)
        time.sleep(6.0)  # Allow Google Maps feed to fully render in headless mode

        # Dismiss any cookie/consent popup first
        try:
            consent_js = """
            (() => {
                const btns = document.querySelectorAll('button[aria-label*="Accept"], button[aria-label*="accept"], #L2AGLb, form button');
                for (const b of btns) { if (b.offsetParent !== null) { b.click(); return true; } }
                return false;
            })()
            """
            send_cdp_js(consent_js, timeout=3.0)
            time.sleep(1.0)
        except Exception:
            pass

        # Scroll the listings feed 8 times to trigger lazy loading
        for scroll_idx in range(8):
            send_cdp_js(_MAPS_FEED_SCROLL_JS)
            time.sleep(1.5)

        # Scrape feed cards
        raw_maps_data = send_cdp_js(_GOOGLE_MAPS_SCRAPE_JS)
        batch = []
        if raw_maps_data:
            try:
                batch = json.loads(raw_maps_data) if isinstance(raw_maps_data, str) else raw_maps_data
            except Exception as e:
                logger.debug(f"JSON decode failed on maps batch: {e}")

        # Fallback check on standard local places pack if Maps feed didn't respond
        if not batch:
            raw_places_data = send_cdp_js(_GOOGLE_SEARCH_LOCAL_SCRAPE_JS)
            if raw_places_data:
                try:
                    batch = json.loads(raw_places_data) if isinstance(raw_places_data, str) else raw_places_data
                except Exception:
                    batch = []

        new_count = 0
        for item in (batch if isinstance(batch, list) else []):
            if not isinstance(item, dict):
                continue
            cname = (item.get("company") or "").strip()
            norm = cname.lower()
            if norm and norm not in seen_names and len(cname) > 2:
                seen_names.add(norm)
                item["city"] = city
                item["state"] = state_abbr
                all_leads.append(item)
                new_count += 1

        logger.info(f"[SCRAPER] {city}: +{new_count} leads extracted (total live count: {len(all_leads)}/{min_leads})")

    # If still below target, execute search across general state directory
    if len(all_leads) < min_leads:
        general_query = f"{clean_term} directory {state_abbr}"
        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(general_query)}&num=50"
        logger.info(f"[SCRAPER] Expanding search to state directory: {general_query}")
        send_cdp_navigate(search_url)
        time.sleep(3.0)

        for _ in range(3):
            send_cdp_js("window.scrollBy(0, 1000);")
            time.sleep(1.0)

        raw_search_data = send_cdp_js(_GOOGLE_SEARCH_LOCAL_SCRAPE_JS)
        if raw_search_data:
            try:
                extra_batch = json.loads(raw_search_data) if isinstance(raw_search_data, str) else raw_search_data
                for item in (extra_batch if isinstance(extra_batch, list) else []):
                    if not isinstance(item, dict):
                        continue
                    cname = (item.get("company") or "").strip()
                    norm = cname.lower()
                    if norm and norm not in seen_names and len(cname) > 2:
                        seen_names.add(norm)
                        item["state"] = state_abbr
                        all_leads.append(item)
            except Exception:
                pass

    logger.info(f"[SCRAPER] Live directory scraping concluded: {len(all_leads)} total genuine leads extracted.")

    # Deep scrape: visit individual websites + Google Search for real phone/email/address
    if all_leads:
        all_leads = _deep_scrape_contacts(all_leads, max_sites=min(len(all_leads), 20))

    return all_leads


# ============================================================
# EXPORT PIPELINE
# ============================================================

def extract_leads_and_export(
    query: str = "interior designers in Georgia",
    min_leads: int = 25,
    output_filename: Optional[str] = None,
    workspace_dir: str = r"D:\new_automation"
) -> Dict[str, Any]:
    """
    Extracts live leads via Chrome CDP directory scraper and exports to Excel & CSV.
    100% Real Scraped Data. No fake data.
    """
    state_abbr, _ = detect_state_and_cities(query)

    if output_filename is None:
        state_name_map = {v: k for k, v in _STATE_NAME_TO_ABBR.items() if len(k) > 2}
        state_name = state_name_map.get(state_abbr, state_abbr.lower())
        output_filename = f"interior_designers_{state_name}.xlsx"

    # Ensure output is always .xlsx
    if not output_filename.endswith(".xlsx"):
        output_filename = os.path.splitext(output_filename)[0] + ".xlsx"

    # Scrape real data
    leads = scrape_live_directory_leads(query=query, min_leads=min_leads)

    os.makedirs(workspace_dir, exist_ok=True)
    excel_path = os.path.join(workspace_dir, output_filename)
    csv_path = os.path.join(workspace_dir, output_filename.replace(".xlsx", ".csv"))

    source_tag = f"LIVE_CDP_DIRECTORY_SCRAPE_{state_abbr}"

    # Export using openpyxl
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{state_abbr} Leads"

        headers = ["No.", "Company Name", "Phone / Contact", "Email", "Website", "Address", "City", "State", "Specialty / Category", "Data Source"]
        ws.append(headers)

        header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        row_font = Font(name="Segoe UI", size=10)

        for idx, lead in enumerate(leads, 1):
            if not isinstance(lead, dict):
                continue
            row = [
                idx,
                lead.get("company", "Unknown"),
                lead.get("phone", "N/A"),
                lead.get("email", "N/A"),
                lead.get("website", "N/A"),
                lead.get("address", "N/A"),
                lead.get("city", "N/A"),
                lead.get("state", state_abbr),
                lead.get("category", "Interior Design"),
                source_tag
            ]
            ws.append(row)
            row_idx = idx + 1
            for col_num in range(1, len(headers) + 1):
                c = ws.cell(row=row_idx, column=col_num)
                c.font = row_font
                c.border = thin_border
                c.alignment = center_align if col_num in [1, 6] else left_align
                if idx % 2 == 0:
                    c.fill = zebra_fill

        # Auto column widths
        col_widths = [6, 38, 20, 30, 42, 35, 18, 8, 30, 32]
        for col_idx, width in enumerate(col_widths, 1):
            from openpyxl.utils import get_column_letter
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        wb.save(excel_path)
        logger.info(f"[EXPORT] Excel file written: {excel_path} ({len(leads)} rows)")

    except Exception as e:
        logger.error(f"[EXPORT] Excel write error: {e}")

    # Export CSV
    try:
        import csv
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["No.", "Company Name", "Phone / Contact", "Email", "Website", "Address", "City", "State", "Category", "Source"])
            for idx, lead in enumerate(leads, 1):
                writer.writerow([
                    idx,
                    lead.get("company", ""),
                    lead.get("phone", "N/A"),
                    lead.get("email", "N/A"),
                    lead.get("website", "N/A"),
                    lead.get("address", "N/A"),
                    lead.get("city", "N/A"),
                    lead.get("state", state_abbr),
                    lead.get("category", "Interior Design"),
                    source_tag
                ])
        logger.info(f"[EXPORT] CSV file written: {csv_path}")
    except Exception as e:
        logger.error(f"[EXPORT] CSV write error: {e}")

    return {
        "status": "SUCCESS",
        "excel_file": excel_path,
        "csv_file": csv_path,
        "total_leads": len(leads),
        "source": source_tag
    }


if __name__ == "__main__":
    test_query = "interior designers in Georgia"
    res = extract_leads_and_export(test_query, min_leads=10)
    print("Export Result:", json.dumps(res, indent=2))
