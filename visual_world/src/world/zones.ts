import { ROOMS, type ZoneId, type Point } from "./grid";

export interface OrganAnchor extends Point {
  organId: string; // matches Hojaiga's organ id, e.g. "38"
  label: string;
  zone: ZoneId;
}

export interface ZoneMeta {
  label: string;
  color: string; // accent color when the zone's lights are ON
}

export const ZONE_META: Record<ZoneId, ZoneMeta> = {
  executive: { label: "Executive Suite", color: "#a78bfa" },
  dispatch: { label: "Dispatch Hub", color: "#38bdf8" },
  archives: { label: "Archives & Research", color: "#34d399" },
  execution: { label: "Execution Floor", color: "#fbbf24" },
  security: { label: "Security Checkpoint", color: "#f97316" },
  browserlab: { label: "Browser Lab", color: "#22d3ee" },
  recovery: { label: "Recovery Ward", color: "#f87171" },
};

// Physical "desks" for each organ. These are the exact tile coordinates
// agent sprites spawn at / walk to. All fall inside their ZoneId's room
// bounds from world/grid.ts.
export const ORGANS: OrganAnchor[] = [
  { organId: "01", label: "Brain", zone: "executive", x: 5, y: 5 },
  { organId: "37", label: "LLM Gateway", zone: "executive", x: 11, y: 7 },
  { organId: "02", label: "CNS", zone: "dispatch", x: 26, y: 6 },
  { organId: "03", label: "Memory", zone: "archives", x: 41, y: 5 },
  { organId: "04", label: "Knowledge", zone: "archives", x: 48, y: 7 },
  { organId: "18", label: "Capability Registry", zone: "security", x: 23, y: 21 },
  { organId: "07", label: "Security", zone: "security", x: 22, y: 23 }, // turnstile
  { organId: "10", label: "Agents", zone: "execution", x: 6, y: 25 },
  { organId: "38", label: "Task Orchestrator", zone: "execution", x: 12, y: 27 },
  { organId: "19", label: "Chrome CDP", zone: "browserlab", x: 33, y: 25 },
  { organId: "05", label: "Controllers", zone: "browserlab", x: 38, y: 23 },
  { organId: "06", label: "Automation", zone: "browserlab", x: 41, y: 27 },
  { organId: "25", label: "Error Catalog", zone: "recovery", x: 50, y: 24 },
];

const byOrganId = new Map(ORGANS.map((o) => [o.organId, o]));

export function organAnchor(organId: string): OrganAnchor | undefined {
  return byOrganId.get(organId);
}

export function zoneRoom(zone: ZoneId) {
  return ROOMS[zone];
}

// Well-known anchors the routing engine needs by name rather than by
// looking up an arbitrary organ id.
export const TASK_ORCHESTRATOR = organAnchor("38")!;
export const CHROME_CDP = organAnchor("19")!;
export const SECURITY_TURNSTILE = organAnchor("07")!;
export const ERROR_CATALOG = organAnchor("25")!;

export const ALL_ZONE_IDS = Object.keys(ROOMS) as ZoneId[];
