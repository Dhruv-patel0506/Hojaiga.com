/**
 * Wire contract with organ_99_visual_adapter.py (ws://127.0.0.1:8080).
 *
 * ASSUMPTION FLAGGED FOR REVIEW: the exact shape of Hojaiga's
 * `EventEnvelope` (as produced by organ_02_cns_single_file.py) was not
 * available when this was written. The fields below are a reasonable
 * best guess based on the brief's own vocabulary (event names, "organ",
 * "topic", "payload"). Once the real EventEnvelope class is shared,
 * reconcile it against this type -- the rest of the app only depends on
 * this interface, so a mismatch here is a one-file fix.
 */
export interface HojaigaEventEnvelope {
  event_id: string;
  /** Canonical event name, e.g. "EVENT_TASK_DISPATCHED", "SECURITY_CHECK". */
  event_type: string;
  /** Pub/sub topic the event was published on (adapter subscribes to "*"). */
  topic?: string;
  /** Organ id that emitted the event, e.g. "38". */
  organ_id?: string;
  /** Sanitized payload -- the adapter strips secrets before this ever exists. */
  payload: Record<string, unknown>;
  timestamp: string; // ISO 8601
}

export interface OrganStatus {
  organ_id: string;
  connected: boolean;
  last_seen?: string;
}

export interface LockInfo {
  lock_id: string;
  holder: string;
  acquired_at: string;
}

export interface SessionInfo {
  session_id: string;
  organ_id?: string;
  task_id?: string;
  started_at: string;
}

/** Sent once, immediately after a client connects (and on every reconnect). */
export interface WorldSnapshotMessage {
  type: "WORLD_SNAPSHOT";
  server_time: string;
  registered_organs: OrganStatus[];
  held_locks: LockInfo[];
  active_sessions: SessionInfo[];
}

export interface EventMessage {
  type: "EVENT";
  envelope: HojaigaEventEnvelope;
}

export interface HeartbeatMessage {
  type: "HEARTBEAT";
  server_time: string;
}

export type HojaigaServerMessage = WorldSnapshotMessage | EventMessage | HeartbeatMessage;

// Canonical event names from the brief's EVENT_TO_VISUAL_MAPPING.
export const HOJAIGA_EVENTS = {
  ORGAN_CONNECTED: "EVENT_ORGAN_CONNECTED",
  CNS_STARTED: "EVENT_CNS_STARTED",
  TASK_DISPATCHED: "EVENT_TASK_DISPATCHED",
  AGENTS_ASSIGNED: "AGENTS_ASSIGNED",
  SECURITY_CHECK: "SECURITY_CHECK",
  ACTION_FAILED: "ACTION_FAILED",
  REPLAN_SUBMITTED: "REPLAN_SUBMITTED",
  TASK_COMPLETED: "TASK_COMPLETED",
} as const;
