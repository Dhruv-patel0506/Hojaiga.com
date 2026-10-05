import { describe, it, expect } from "vitest";
import {
  applyHojaigaEvent,
  applyWorldSnapshot,
  initialFacilityState,
  tickAgents,
} from "../world/agentEngine";
import { HOJAIGA_EVENTS, type HojaigaEventEnvelope, type WorldSnapshotMessage } from "../ws/types";
import { TASK_ORCHESTRATOR, CHROME_CDP, SECURITY_TURNSTILE, ERROR_CATALOG } from "../world/zones";

function envelope(partial: Partial<HojaigaEventEnvelope>): HojaigaEventEnvelope {
  return {
    event_id: "evt-1",
    event_type: "EVENT_UNKNOWN",
    payload: {},
    timestamp: new Date().toISOString(),
    ...partial,
  };
}

function runToCompletion(state: ReturnType<typeof initialFacilityState>, id: string, maxSteps = 500) {
  let s = state;
  for (let i = 0; i < maxSteps && s.agents[id]?.path.length > 1; i++) {
    s = tickAgents(s, 1);
  }
  return s;
}

describe("applyHojaigaEvent", () => {
  it("EVENT_CNS_STARTED lights every zone", () => {
    const state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.CNS_STARTED })
    );
    expect(state.litZones.size).toBe(7);
  });

  it("EVENT_ORGAN_CONNECTED lights only that organ's zone", () => {
    const state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.ORGAN_CONNECTED, organ_id: "19" })
    );
    expect(state.litZones.has("browserlab")).toBe(true);
    expect(state.litZones.has("executive")).toBe(false);
  });

  it("EVENT_TASK_DISPATCHED spawns an agent at the Orchestrator, en route to Chrome CDP", () => {
    const state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    const agent = state.agents["task-1"];
    expect(agent).toBeDefined();
    expect(agent.status).toBe("en_route");
    expect(agent.position).toEqual({ x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y });
    expect(agent.path[agent.path.length - 1]).toEqual({ x: CHROME_CDP.x, y: CHROME_CDP.y });
  });

  it("agent reaches 'working' status after walking the full path to Chrome CDP", () => {
    let state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    state = runToCompletion(state, "task-1");
    state = tickAgents(state, 1); // final step applies onArrival
    expect(state.agents["task-1"].status).toBe("working");
    expect(state.agents["task-1"].position).toEqual({ x: CHROME_CDP.x, y: CHROME_CDP.y });
  });

  it("SECURITY_CHECK routes an in-flight agent through the turnstile before Chrome CDP", () => {
    let state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    state = applyHojaigaEvent(
      state,
      envelope({ event_type: HOJAIGA_EVENTS.SECURITY_CHECK, payload: { task_id: "task-1" } })
    );
    const agent = state.agents["task-1"];
    expect(agent.path).toContainEqual({ x: SECURITY_TURNSTILE.x, y: SECURITY_TURNSTILE.y });
    // Turnstile must be visited before the agent reaches Chrome CDP.
    const turnstileIdx = agent.path.findIndex(
      (p) => p.x === SECURITY_TURNSTILE.x && p.y === SECURITY_TURNSTILE.y
    );
    const goalIdx = agent.path.length - 1;
    expect(turnstileIdx).toBeGreaterThan(-1);
    expect(turnstileIdx).toBeLessThan(goalIdx);
  });

  it("SECURITY_CHECK for an unknown agent id is a safe no-op", () => {
    const before = initialFacilityState();
    const after = applyHojaigaEvent(
      before,
      envelope({ event_type: HOJAIGA_EVENTS.SECURITY_CHECK, payload: { task_id: "ghost" } })
    );
    expect(after.agents).toEqual({});
  });

  it("ACTION_FAILED marks the agent errored and routes it to the Error Catalog / Recovery Ward", () => {
    let state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    state = applyHojaigaEvent(
      state,
      envelope({
        event_type: HOJAIGA_EVENTS.ACTION_FAILED,
        payload: { task_id: "task-1", error: "Selector not found" },
      })
    );
    const agent = state.agents["task-1"];
    expect(agent.status).toBe("error");
    expect(agent.errorMessage).toBe("Selector not found");
    expect(agent.path[agent.path.length - 1]).toEqual({ x: ERROR_CATALOG.x, y: ERROR_CATALOG.y });
  });

  it("REPLAN_SUBMITTED clears the error and sends the agent back to work", () => {
    let state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    state = applyHojaigaEvent(
      state,
      envelope({ event_type: HOJAIGA_EVENTS.ACTION_FAILED, payload: { task_id: "task-1", error: "boom" } })
    );
    state = runToCompletion(state, "task-1");
    state = tickAgents(state, 1); // arrive at Recovery Ward -> in_medbay

    state = applyHojaigaEvent(
      state,
      envelope({ event_type: HOJAIGA_EVENTS.REPLAN_SUBMITTED, payload: { task_id: "task-1" } })
    );
    const agent = state.agents["task-1"];
    expect(agent.status).toBe("en_route");
    expect(agent.errorMessage).toBeUndefined();
  });

  it("TASK_COMPLETED sends the agent back to the Orchestrator and despawns it on arrival", () => {
    let state = applyHojaigaEvent(
      initialFacilityState(),
      envelope({ event_type: HOJAIGA_EVENTS.TASK_DISPATCHED, payload: { task_id: "task-1" } })
    );
    state = runToCompletion(state, "task-1");
    state = tickAgents(state, 1); // now "working" at Chrome CDP

    state = applyHojaigaEvent(
      state,
      envelope({ event_type: HOJAIGA_EVENTS.TASK_COMPLETED, payload: { task_id: "task-1" } })
    );
    expect(state.agents["task-1"].status).toBe("returning");

    state = runToCompletion(state, "task-1");
    state = tickAgents(state, 1); // arrival triggers despawn
    expect(state.agents["task-1"]).toBeUndefined();
  });

  it("ignores unrecognized event types instead of guessing", () => {
    const before = initialFacilityState();
    const after = applyHojaigaEvent(before, envelope({ event_type: "SOMETHING_NEW" }));
    expect(after).toBe(before); // reference-equal: truly a no-op
  });
});

describe("applyWorldSnapshot", () => {
  it("lights zones for connected organs and rehydrates active sessions", () => {
    const snapshot: WorldSnapshotMessage = {
      type: "WORLD_SNAPSHOT",
      server_time: new Date().toISOString(),
      registered_organs: [
        { organ_id: "19", connected: true },
        { organ_id: "25", connected: false },
      ],
      held_locks: [],
      active_sessions: [
        { session_id: "sess-1", organ_id: "19", task_id: "task-9", started_at: new Date().toISOString() },
      ],
    };
    const state = applyWorldSnapshot(snapshot);
    expect(state.litZones.has("browserlab")).toBe(true);
    expect(state.litZones.has("recovery")).toBe(false); // organ 25 reported offline
    expect(state.agents["task-9"]).toBeDefined();
    expect(state.agents["task-9"].status).toBe("working");
  });
});
