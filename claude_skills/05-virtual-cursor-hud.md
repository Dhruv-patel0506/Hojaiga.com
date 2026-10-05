---
name: hojaiga-virtual-cursor-hud
description: Multi-agent virtual cursor and floating capsule HUD in visual_cursor.py - one full-screen layered overlay drawing N color-coded triangle sprites (one per temporary agent), magnetic stick/detach, 60fps UpdateLayeredWindow rendering.
---

# Skill 05 — Multi-Agent Virtual Cursor & Capsule (`visual_cursor.py`)

## What it physically is
ONE full-screen **layered transparent overlay window** (UpdateLayeredWindow + ARGB DIB),
redrawn at 60 fps on a daemon thread. It does NOT move the OS pointer and does NOT need
`SetCursorPos` — so it keeps working even when a foreign app (e.g. "Clicky") holds a
`ClipCursor` lock. The cursor is *drawn*, not *moved*.

## The shape (current spec)
`CursorShape.TRIANGLE_VERTICES` = a **simple flat right-pointing isosceles triangle**
(~54×60 px, tip at origin `(0,0)` so the drawn point sits exactly on the logical hotspot).
Flat single-color fill, pen matches brush (no white outline). Primary color
`COLOR = 0x00E8731A` (BGR bright blue). Buffering state rotates the triangle around the tip.
> Do not reintroduce the old 7-vertex arrow-pointer polygon — the user explicitly asked for
> the simple Clicky-style triangle.

## Per-agent duplication (the headline feature)
The single overlay draws **N independent `CursorSprite`s** — one per concurrent temporary
agent — each with its own bezier flight, trail, ripples, colour and name badge.

```python
from core_organs.visual_cursor import for_agent, release_agent, get_cursor
a = for_agent("agent-1", "Researcher")   # get-or-create, auto-picks a palette colour
a.fly_to(300, 300, label="reading")      # bezier glide; set_label updates its badge
a.set_label("typing", "working")
a.click(300, 300)                         # ripple + press state
release_agent("agent-1")                  # retire it; also auto-retires on idle TTL
get_cursor().list_cursors()               # [{id,name,color,pos,state,ttl,age}, ...]
```
- `AGENT_PALETTE` = 8 distinct BGR colours (primary blue omitted); assigned round-robin.
- Sprites are ticked every frame in `_anim_loop` and auto-retire when `tick()` returns True
  (idle past TTL). `_render_frame` draws the primary cursor then every live sprite.
- **Wiring:** `organ_01.operate_desktop_tool(..., agent_label=...)` calls `for_agent`
  so parallel agents each visibly own a distinct arrow. Pass a UNIQUE `agent_label`
  per concurrent agent.

## Status capsule ("the black floating tab" HUD)
A separate always-on-top pill shows agent state: `working` / `input_needed` / `done`.
`operate_desktop_tool._capsule(state, text)` logs it AND mirrors it onto the agent's sprite
badge. When you add a long-running tool, drive the capsule so the human always knows what
the bot is doing (this is a product requirement, not decoration).

## Rules
1. Overlay must be click-through (WS_EX_TRANSPARENT|LAYERED) — never steal focus or block input.
2. All sprite registry access under `self._sprite_lock` (render loop + tool threads race).
3. Guard every Win32 call; if the overlay can't init, the tool still runs headless (cursor
   calls are best-effort, wrapped in try/except).
4. Prove it works by drawing sprites + `list_cursors()` (independent of the OS clip), not
   by SetCursorPos — that path is env-fragile.
