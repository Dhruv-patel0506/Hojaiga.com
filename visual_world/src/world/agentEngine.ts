import { buildFacilityGrid, type Point, type ZoneId } from "./grid";
import { findPath, chainPaths } from "./pathfinding";
import {
  organAnchor,
  TASK_ORCHESTRATOR,
  CHROME_CDP,
  SECURITY_TURNSTILE,
  ERROR_CATALOG,
} from "./zones";
import { HOJAIGA_EVENTS, type HojaigaEventEnvelope, type WorldSnapshotMessage } from "../ws/types";

export type AgentStatus =
  | "spawning"
  | "en_route"
  | "working"
  | "error"
  | "in_medbay"
  | "returning"
  | "idle_ambient";

export interface AgentState {
  id: string;
  organId: string; // organ the agent currently represents / is headed to
  status: AgentStatus;
  path: Point[]; // remaining tiles to walk, consumed by the render loop
  position: Point; // current tile-space position
  errorMessage?: string;
  /** status to apply once `path` is fully consumed by the render loop */
  onArrival?: AgentStatus | "despawn";
}

export interface FacilityState {
  agents: Record<string, AgentState>;
  litZones: Set<ZoneId>;
  log: string[]; // human-readable trailing event log, newest first
}

export function initialFacilityState(): FacilityState {
  return {
    agents: {
      "ambient-1": { id: "ambient-1", organId: "01", status: "idle_ambient", path: [{x: 4, y: 3}], position: {x: 4, y: 3} },
      "ambient-2": { id: "ambient-2", organId: "03", status: "idle_ambient", path: [{x: 10, y: 6}], position: {x: 10, y: 6} },
      "ambient-3": { id: "ambient-3", organId: "04", status: "idle_ambient", path: [{x: 10, y: 14}], position: {x: 10, y: 14} },
      "ambient-4": { id: "ambient-4", organId: "38", status: "idle_ambient", path: [{x: 4, y: 14}], position: {x: 4, y: 14} },
    },
    litZones: new Set(["executive", "dispatch", "archives", "execution", "security", "browserlab", "recovery"]),
    log: ["System initializing...", "Waiting for connection..."],
  };
}

/** Best-effort extraction of "which agent does this event refer to". */
function correlationId(envelope: HojaigaEventEnvelope): string {
  const p = envelope.payload ?? {};
  return (
    (p.task_id as string) ||
    (p.session_id as string) ||
    (p.agent_id as string) ||
    envelope.event_id
  );
}

function withLog(state: FacilityState, line: string, max = 40): string[] {
  return [line, ...state.log].slice(0, max);
}

function cloneState(state: FacilityState): FacilityState {
  return {
    agents: { ...state.agents },
    litZones: new Set(state.litZones),
    log: state.log,
  };
}

/**
 * Pure reducer: (current world, one Hojaiga event) -> next world.
 * Never mutates its input. No timers, no randomness, no fake work --
 * every state change here is caused by a real EventEnvelope.
 */
export function applyHojaigaEvent(
  state: FacilityState,
  envelope: HojaigaEventEnvelope
): FacilityState {
  const grid = buildFacilityGrid();
  const next = cloneState(state);
  const id = correlationId(envelope);

  switch (envelope.event_type) {
    case HOJAIGA_EVENTS.CNS_STARTED: {
      // Facility-wide power-on.
      for (const zone of Object.keys({
        executive: 0,
        dispatch: 0,
        archives: 0,
        execution: 0,
        security: 0,
        browserlab: 0,
        recovery: 0,
      }) as ZoneId[]) {
        next.litZones.add(zone);
      }
      next.log = withLog(next, "CNS online -- facility power restored.");
      return next;
    }

    case HOJAIGA_EVENTS.ORGAN_CONNECTED: {
      const organId = envelope.organ_id ?? (envelope.payload?.organ_id as string);
      const anchor = organId ? organAnchor(organId) : undefined;
      if (anchor) next.litZones.add(anchor.zone);
      next.log = withLog(next, `Organ ${organId ?? "?"} connected -- lights on.`);
      return next;
    }

    case HOJAIGA_EVENTS.TASK_DISPATCHED:
    case HOJAIGA_EVENTS.AGENTS_ASSIGNED: {
      const existing = next.agents[id];
      const start = existing ? existing.position : { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y };
      const path = findPath(grid, start, { x: CHROME_CDP.x, y: CHROME_CDP.y });

      next.agents[id] = {
        id,
        organId: CHROME_CDP.organId,
        status: "en_route",
        path,
        position: start,
        onArrival: "working",
      };
      next.log = withLog(next, `Task ${id} dispatched -- agent en route to Chrome CDP.`);
      return next;
    }

    case HOJAIGA_EVENTS.SECURITY_CHECK: {
      const agent = next.agents[id];
      if (!agent) return next; // unknown agent, ignore rather than guess

      const toTurnstile = findPath(grid, agent.position, {
        x: SECURITY_TURNSTILE.x,
        y: SECURITY_TURNSTILE.y,
      });
      const toBrowserLab = findPath(
        grid,
        { x: SECURITY_TURNSTILE.x, y: SECURITY_TURNSTILE.y },
        { x: CHROME_CDP.x, y: CHROME_CDP.y }
      );

      next.agents[id] = {
        ...agent,
        status: "en_route",
        path: chainPaths(toTurnstile, toBrowserLab),
        onArrival: "working",
      };
      next.log = withLog(next, `Task ${id} rerouted through Security checkpoint.`);
      return next;
    }

    case HOJAIGA_EVENTS.ACTION_FAILED: {
      const agent = next.agents[id];
      const start = agent ? agent.position : { x: CHROME_CDP.x, y: CHROME_CDP.y };
      const path = findPath(grid, start, { x: ERROR_CATALOG.x, y: ERROR_CATALOG.y });
      const message = (envelope.payload?.error as string) || (envelope.payload?.message as string) || "Action failed.";

      next.agents[id] = {
        id,
        organId: agent?.organId ?? ERROR_CATALOG.organId,
        status: "error",
        path,
        position: start,
        errorMessage: message,
        onArrival: "in_medbay",
      };
      next.log = withLog(next, `Task ${id} failed -- routing to Recovery Ward.`);
      return next;
    }

    case HOJAIGA_EVENTS.REPLAN_SUBMITTED: {
      const agent = next.agents[id];
      if (!agent) return next;

      const path = findPath(grid, agent.position, { x: CHROME_CDP.x, y: CHROME_CDP.y });
      next.agents[id] = {
        ...agent,
        status: "en_route",
        path,
        errorMessage: undefined,
        onArrival: "working",
      };
      next.log = withLog(next, `Replan submitted for ${id} -- agent leaving Recovery Ward.`);
      return next;
    }

    case HOJAIGA_EVENTS.TASK_COMPLETED: {
      const agent = next.agents[id];
      if (!agent) return next;

      const path = findPath(grid, agent.position, {
        x: TASK_ORCHESTRATOR.x,
        y: TASK_ORCHESTRATOR.y,
      });
      next.agents[id] = {
        ...agent,
        status: "returning",
        path,
        errorMessage: undefined,
        onArrival: "despawn",
      };
      next.log = withLog(next, `Task ${id} completed -- agent returning to Orchestrator.`);
      return next;
    }

    default:
      // Unknown/irrelevant event type -- ignore rather than guess at intent.
      return state;
  }
}

/**
 * Rebuilds facility state from a WORLD_SNAPSHOT (sent on every connect /
 * reconnect). This is a best-effort resume: the snapshot contract in the
 * brief only guarantees registered organs, held locks, and active
 * sessions -- it does not specify in-flight sprite positions or paths.
 * ASSUMPTION FLAGGED FOR REVIEW: agents rehydrated from a snapshot are
 * placed directly at their target organ in "working" status rather than
 * mid-corridor, since we cannot know where they actually were walking.
 * If organ_02_cns_single_file.py can expose in-flight task position/route,
 * thread it through WORLD_SNAPSHOT and rehydrate exactly here instead.
 */
export function applyWorldSnapshot(snapshot: WorldSnapshotMessage): FacilityState {
  const state = initialFacilityState();

  for (const organ of snapshot.registered_organs) {
    if (!organ.connected) continue;
    const anchor = organAnchor(organ.organ_id);
    if (anchor) state.litZones.add(anchor.zone);
  }

  for (const session of snapshot.active_sessions) {
    const anchor = session.organ_id ? organAnchor(session.organ_id) : undefined;
    const target = anchor ?? CHROME_CDP;
    const id = session.task_id || session.session_id;
    state.agents[id] = {
      id,
      organId: target.organId,
      status: "working",
      path: [{ x: target.x, y: target.y }],
      position: { x: target.x, y: target.y },
    };
  }

  state.log = [`Resumed from snapshot -- ${snapshot.active_sessions.length} active session(s).`];
  return state;
}

/** Advances every agent one interpolation step; called once per render frame. */
export function tickAgents(state: FacilityState, stepsPerTile: number): FacilityState {
  let changed = false;
  const nextAgents: Record<string, AgentState> = { ...state.agents };

  for (const [id, agent] of Object.entries(state.agents)) {
    if (agent.path.length <= 1) continue;
    changed = true;

    // Consume `stepsPerTile` calls to move one tile (kept simple & testable;
    // the canvas layer does the actual sub-tile pixel interpolation).
    void stepsPerTile;
    const [, nextTile, ...rest] = agent.path;
    const arrived = rest.length === 0;

    if (arrived && agent.onArrival === "despawn") {
      delete nextAgents[id];
      continue;
    }

    nextAgents[id] = {
      ...agent,
      position: nextTile,
      path: [nextTile, ...rest],
      status: arrived && agent.onArrival ? (agent.onArrival as AgentStatus) : agent.status,
      onArrival: arrived ? undefined : agent.onArrival,
    };
  }

  if (!changed) return state;
  return { ...state, agents: nextAgents };
}
