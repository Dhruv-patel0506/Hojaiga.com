---
name: hojaiga-web-automation
description: Web and browser automation - direct Chrome launch without profile picker, CDP session on port 9222, session cookie seeding, dynamic web detection and tool wiring, and URL derivation guards against fake domains.
---

# Skill 11 — Web & Browser Automation (CDP, Chrome, cookies)

Web is a first-class citizen next to desktop, and it shares the SAME element contract
(skill 01) so organ_01 holds one mental model for Chrome and Blender alike.

## The one browser rule
**Launch Chrome once with remote debugging and reuse it.** Never relaunch per step.
```
chrome.exe --remote-debugging-port=9222 --user-data-dir=<isolated profile dir>
```
- Connect over CDP to `http://127.0.0.1:9222` (organ_19 scanner / Playwright connect_over_cdp).
- The dedicated `--user-data-dir` prevents the **profile-picker** dialog (pitfall P-7) that
  otherwise blocks automation, and gives each agent an isolated profile.

## Direct, picker-free launch (organ_40)
Resolve the app to its real exe and launch directly with the flags above. Do NOT drive
Chrome through the Windows search bar (spawns first-run / account pickers).

## Web perception
- organ_19 walks the CDP accessibility snapshot → emits `{id,name,role,bbox,tier,confidence}`
  exactly like the desktop tiers. `aria-modal`, `<dialog>`, cookie banners, SweetAlert/MUI
  modals are detected by organ_29's `find_in_window_modals` (framework/web modal classes).

## Login walls & cookies
1. `_detect_login_page` recognises an auth gate (password field + submit, OAuth redirect…).
2. Do NOT try to auto-fill credentials. Flip capsule to `input_needed`, bounded HITL wait
   (~120 s) for the human to log in once.
3. After login, **extract session cookies** and store them in the local DB vault
   (`session_cookies` table, site→cookies_json).
4. On a later run, **seed the cookies** into the fresh profile so the bot starts already
   authenticated — no password ever stored or transmitted remotely (local vault only).
- CDP `navigate` must tolerate `networkidle` never arriving behind a login gate (pitfall P-8):
  don't raise on the first timeout; detect the gate and handle it.

## Mixed web + desktop tasks
- organ_36 compiles a step graph with `kind: web|desktop` per step; the executor hands off
  per step. Browser steps use CDP `:9222`; desktop steps use the grounding loop.
- Ensure the compiler **never drops web/Gmail steps** (pitfall P-9) — step count in == out.
- URL targets must pass `_is_site_like_target`; a fuzzy target is an app name, not a URL
  (pitfall P-6, the fake-domain bug).

## Safety on the web
- Payment / ToS / "Buy" / consent-to-binding dialogs are `need_human` (skill 08) — never
  auto-accepted, same as UAC.
- Cookie banners: Tier-1 semantic button ("Accept"/"Reject non-essential") if present, else
  Tier-2.5 `key:escape`. Prefer the least-committal safe action.
