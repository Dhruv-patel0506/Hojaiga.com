// The physical floor plan of the Autonomous Facility.
// 0 = walkable floor, 1 = wall. This is deliberately a real, walled layout
// (not just a waypoint graph) so that "pathfind through the Security
// turnstile" is a genuine geometric detour an agent sprite walks through,
// not a scripted animation.

export type Cell = 0 | 1;

export interface Point {
  x: number;
  y: number;
}

export interface RoomRect {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export const GRID_WIDTH = 56;
export const GRID_HEIGHT = 34;
export const TILE_SIZE = 18; // px, used by the canvas renderer

// Room interiors. Anchors in zones.ts must fall inside these bounds.
export const ROOMS = {
  executive: { x1: 2, y1: 2, x2: 15, y2: 11 },
  dispatch: { x1: 19, y1: 2, x2: 34, y2: 11 },
  archives: { x1: 38, y1: 2, x2: 53, y2: 11 },
  execution: { x1: 2, y1: 21, x2: 17, y2: 31 },
  security: { x1: 20, y1: 21, x2: 25, y2: 25 },
  browserlab: { x1: 29, y1: 21, x2: 44, y2: 31 },
  recovery: { x1: 47, y1: 21, x2: 53, y2: 29 },
} as const satisfies Record<string, RoomRect>;

export type ZoneId = keyof typeof ROOMS;

function emptyGrid(): Cell[][] {
  return Array.from({ length: GRID_HEIGHT }, () =>
    Array.from({ length: GRID_WIDTH }, () => 1 as Cell)
  );
}

function carve(grid: Cell[][], r: RoomRect) {
  for (let y = r.y1; y <= r.y2; y++) {
    for (let x = r.x1; x <= r.x2; x++) {
      grid[y][x] = 0;
    }
  }
}

let _cached: Cell[][] | null = null;

/**
 * Builds (and memoizes) the facility floor plan.
 *
 * Layout notes:
 * - Corridor A (y=12) runs directly beneath the top zones (Executive,
 *   Dispatch, Archives), which end at y=11 -- no extra door tile needed.
 * - Corridor B (y=20) runs directly above the bottom zones (Execution,
 *   Security, Browser Lab, Recovery), which start at y=21.
 * - A vertical spine (x=27) links corridor A to corridor B.
 * - Execution Floor <-> Browser Lab has a SHORT DIRECT path via corridor B.
 * - The Security Checkpoint room is only reachable via two narrow spurs,
 *   one from Execution Floor's east wall and one into Browser Lab's west
 *   wall. It is a genuine detour: an agent only enters it if explicitly
 *   routed there (see world/routing.ts), it is never on the shortest path.
 */
export function buildFacilityGrid(): Cell[][] {
  if (_cached) return _cached;
  const grid = emptyGrid();

  Object.values(ROOMS).forEach((r) => carve(grid, r));

  carve(grid, { x1: 2, y1: 12, x2: 53, y2: 12 }); // corridor A
  carve(grid, { x1: 2, y1: 20, x2: 53, y2: 20 }); // corridor B
  carve(grid, { x1: 27, y1: 12, x2: 27, y2: 20 }); // vertical spine

  carve(grid, { x1: 18, y1: 23, x2: 19, y2: 23 }); // execution -> security spur
  carve(grid, { x1: 26, y1: 23, x2: 28, y2: 23 }); // security -> browser lab spur

  _cached = grid;
  return grid;
}

export function isWalkable(grid: Cell[][], p: Point): boolean {
  if (p.y < 0 || p.y >= GRID_HEIGHT || p.x < 0 || p.x >= GRID_WIDTH) return false;
  return grid[p.y][p.x] === 0;
}
