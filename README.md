# Hojaiga — The Autonomous Facility (Visual World)

A read-only, "Sims-like" visualization of the Hojaiga runtime: a Python
adapter that taps the CNS EventBus and a React/TypeScript canvas app that
turns Hojaiga events into agents walking around a pixel facility.

This was built and **tested inside a sandbox that does not have access to
your local `D:\new_automation\...` machine**, your `pixel-agents` clone, or
`organ_02_cns_single_file.py`. Section 1 below explains exactly what that
means for you before you run this for real.

---

## 0. What's in this delivery

```
observability/
  organ_99_visual_adapter.py   # Organ 99 — CNS bridge + WebSocket broadcaster
  requirements.txt
  pytest.ini
  conftest.py
  tests/
    test_sanitize.py           # credential/secret redaction
    test_snapshot.py           # WORLD_SNAPSHOT shape
    test_server.py             # reconnection, event forwarding, read-only isolation

visual_world/
  (Vite + React + TypeScript project)
  src/world/grid.ts            # facility floor plan (rooms, corridors, security spur)
  src/world/zones.ts           # organ-id -> physical desk mapping
  src/world/pathfinding.ts     # A*, grid-agnostic
  src/world/agentEngine.ts     # pure event -> agent-state reducer (the actual "brain")
  src/ws/useHojaigaSocket.ts   # WebSocket client, reconnect + snapshot resume
  src/engine/FacilityCanvas.tsx
  src/components/HUD.tsx, EventLog.tsx
  src/tests/                   # pathfinding, event-mapping, reconnection tests
```

Both halves were actually installed, type-checked, built, and run in this
environment — not just written. **23/23 frontend tests pass
(`vitest`), 16/16 backend tests pass (`pytest`)**, `tsc -b` and
`vite build` both succeed, and `organ_99_visual_adapter.py --mock` was run
live against a real WebSocket client to confirm the wire format actually
works end to end.

---

## 1. Three things this build could NOT verify against your real system

**1. `organ_02_cns_single_file.py` was never available to me.** The brief
names `connect_to_organ` as (probably) the entry point, so
`organ_99_visual_adapter.py` calls exactly that — but the function's real
signature, and the real shape of `EventEnvelope`, are unverified guesses.
Everything that touches the live CNS is isolated in one function,
`connect_real_cns()`, with `ASSUMPTION FLAGGED FOR REVIEW` comments. If the
real API differs, that's the only function you (or I, if you paste in the
relevant code) need to change — the WebSocket server, snapshot builder, and
sanitizer are written against a small `CNSHandle` protocol, not against
organ_02's concrete API.

**2. The `pixel-agents` repo wasn't reachable either** (not uploaded, and a
web search turned up nothing matching `webview-ui/src/office`), so the
canvas engine here is an original implementation — a tile grid, A*
pathfinder, and sprite/HUD renderer — rather than an adaptation of that
codebase's actual rendering code. If you can share that repo (or the
specific files under `webview-ui/src/office`), I can rework
`src/engine/FacilityCanvas.tsx` to match its patterns.

**3. I don't have access to your local filesystem.** I can't write directly
to `D:\new_automation\...` — everything above was built in an isolated
Linux sandbox and is being handed to you as files to place yourself, at:
- `D:\new_automation\All codes\observability\organ_99_visual_adapter.py`
- `D:\new_automation\visual_world\` (the whole `visual_world/` folder)

If you're doing this integration locally and want an assistant that can
read/write those paths directly and run the real servers, **Claude Code**
(desktop, VS Code, or terminal) is a better fit for the next step than this
chat — it operates on your actual filesystem.

None of this blocked building a complete, runnable, tested scaffold — it
just means the one CNS-facing function needs a final pass once you can
share `organ_02_cns_single_file.py` (even just the `connect_to_organ`
signature and `EventEnvelope` class would do it).

---

## 2. Startup instructions

### Backend (Organ 99)

```bash
cd observability
pip install -r requirements.txt

# Option A — against your real CNS (once connect_real_cns() is reconciled
# against your actual organ_02_cns_single_file.py):
#   1. Copy organ_99_visual_adapter.py next to organ_02_cns_single_file.py
#      (or put its directory on PYTHONPATH).
python organ_99_visual_adapter.py

# Option B — frontend development without a live CNS:
python organ_99_visual_adapter.py --mock
```

Run the backend tests:

```bash
cd observability
pytest -v
```

### Frontend (visual_world)

```bash
cd visual_world
npm install
npm run dev        # http://localhost:5173, connects to ws://127.0.0.1:8080
```

Run the frontend tests / typecheck / production build:

```bash
npm test            # vitest — 23 tests
npx tsc -b           # typecheck
npm run build        # production bundle
```

If your adapter runs somewhere other than `127.0.0.1:8080`, copy
`.env.example` to `.env.local` and set `VITE_HOJAIGA_WS_URL`.

---

## 3. How the absolute rules were kept

1. **Read-only, always.** `organ_99_visual_adapter.py`'s `CNSHandle`
   protocol has exactly five methods: `subscribe`, three `get_*` reads, and
   `close` — no write/command surface (asserted by
   `test_cns_handle_protocol_has_no_write_or_command_surface`). Inbound
   WebSocket frames from the React app are read and discarded on purpose
   (`test_server_ignores_inbound_client_messages`); there is no code path
   from the browser back into Hojaiga or into
   `organ_19_chrome_cdp_runtime.py`.
2. **Hojaiga's core organs were never touched.** Nothing here imports,
   patches, or vendors `organ_01_brain.py`, `organ_02_cns_single_file.py`,
   `organ_19_chrome_cdp_runtime.py`, or `organ_38_task_orchestrator.py` —
   `organ_02` is only ever `import`-ed, read-only, from the one connector
   function.
3. **Secrets are stripped before they exist in the UI.** `sanitize_payload`
   recursively redacts key-name patterns (`api_key`, `token`, `secret`,
   `cookie`, `authorization`, `credential`, etc. — see
   `SENSITIVE_KEY_MARKERS` in `organ_99_visual_adapter.py`) and truncates
   oversized strings (e.g. base64 screenshots), before anything is
   JSON-serialized to a client.
4. **No fake work.** `agentEngine.ts`'s `applyHojaigaEvent` is a pure
   reducer driven only by real `EventEnvelope`s off the WebSocket — there
   is no `setTimeout`-driven task simulation anywhere. The only timer-based
   loop is the render-frame *interpolation* between tiles a real event
   already committed an agent to (ambient idle animation, not fake task
   execution, as the brief allows).
5. **Reconnects resume from a fresh snapshot.** Every new WebSocket
   connection — including a reconnect after a refresh — gets its own
   `WORLD_SNAPSHOT` first (`test_reconnecting_client_gets_a_fresh_snapshot`,
   plus the frontend's own reconnect+resume test). The client never trusts
   stale local state across a reconnect.

---

## 4. Design notes worth knowing

- The facility floor plan (`world/grid.ts`) is a real walled tile grid, not
  just a waypoint graph: Execution Floor and Browser Lab have a short
  direct corridor, and the Security Checkpoint room is only reachable via
  two narrow spurs. A `SECURITY_CHECK` event routes the agent through the
  turnstile as an explicit, physically-real detour (two chained A* legs),
  exactly as the brief specifies — it's not a shortest-path fluke.
- `agentEngine.ts` is intentionally a pure function
  (`(state, event) -> state`), decoupled from rendering. That's what makes
  it possible to unit-test all six event mappings without a browser or a
  live socket.
- Visual language: dark control-room palette, per-zone accent colors that
  only render at full strength once that zone's lights are on
  (`EVENT_ORGAN_CONNECTED` / `EVENT_CNS_STARTED`), monospace organ-ID
  badges at each desk (`ORG-38`, `ORG-07`, …) matching Hojaiga's own
  numbering convention, and a subtle scanline overlay on the canvas.
