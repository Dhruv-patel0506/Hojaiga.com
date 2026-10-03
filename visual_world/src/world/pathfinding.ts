import { GRID_WIDTH, GRID_HEIGHT, type Cell, type Point } from "./grid";

interface AStarNode {
  x: number;
  y: number;
  g: number;
  h: number;
  f: number;
  parent: AStarNode | null;
}

const key = (x: number, y: number) => x * GRID_HEIGHT + y;

const DIRECTIONS = [
  { dx: 1, dy: 0 },
  { dx: -1, dy: 0 },
  { dx: 0, dy: 1 },
  { dx: 0, dy: -1 },
];

function heuristic(a: Point, b: Point): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); // Manhattan (4-directional movement)
}

function inBounds(p: Point): boolean {
  return p.x >= 0 && p.x < GRID_WIDTH && p.y >= 0 && p.y < GRID_HEIGHT;
}

function reconstruct(node: AStarNode): Point[] {
  const path: Point[] = [];
  let cur: AStarNode | null = node;
  while (cur) {
    path.unshift({ x: cur.x, y: cur.y });
    cur = cur.parent;
  }
  return path;
}

/**
 * Grid-agnostic A* over a 4-directional walkable tile grid.
 * Returns an ordered list of tiles from `start` to `goal` inclusive,
 * or [] if no path exists (e.g. a collision blocks every route).
 *
 * Not optimized with a binary heap -- fine for this facility's ~1,900
 * tile grid and the handful of concurrently-moving agents it renders.
 */
export function findPath(grid: Cell[][], start: Point, goal: Point): Point[] {
  if (!inBounds(start) || !inBounds(goal)) return [];
  if (grid[start.y][start.x] === 1 || grid[goal.y][goal.x] === 1) return [];
  if (start.x === goal.x && start.y === goal.y) return [{ ...start }];

  const open = new Map<number, AStarNode>();
  const closed = new Set<number>();

  const startNode: AStarNode = {
    x: start.x,
    y: start.y,
    g: 0,
    h: heuristic(start, goal),
    f: 0,
    parent: null,
  };
  startNode.f = startNode.h;
  open.set(key(start.x, start.y), startNode);

  const maxIterations = GRID_WIDTH * GRID_HEIGHT * 4;
  let iterations = 0;

  while (open.size > 0) {
    if (++iterations > maxIterations) return []; // safety valve

    let current: AStarNode | null = null;
    for (const node of open.values()) {
      if (!current || node.f < current.f) current = node;
    }
    if (!current) break;

    if (current.x === goal.x && current.y === goal.y) {
      return reconstruct(current);
    }

    open.delete(key(current.x, current.y));
    closed.add(key(current.x, current.y));

    for (const { dx, dy } of DIRECTIONS) {
      const nx = current.x + dx;
      const ny = current.y + dy;
      if (!inBounds({ x: nx, y: ny })) continue;
      if (grid[ny][nx] === 1) continue; // wall / collision
      const k = key(nx, ny);
      if (closed.has(k)) continue;

      const tentativeG = current.g + 1;
      const existing = open.get(k);
      if (!existing || tentativeG < existing.g) {
        const node: AStarNode = {
          x: nx,
          y: ny,
          g: tentativeG,
          h: heuristic({ x: nx, y: ny }, goal),
          f: 0,
          parent: current,
        };
        node.f = node.g + node.h;
        open.set(k, node);
      }
    }
  }

  return [];
}

/** Concatenates two path legs, dropping the duplicate joining tile. */
export function chainPaths(...legs: Point[][]): Point[] {
  const result: Point[] = [];
  for (const leg of legs) {
    if (leg.length === 0) continue;
    if (result.length > 0) {
      const last = result[result.length - 1];
      const first = leg[0];
      if (last.x === first.x && last.y === first.y) {
        result.push(...leg.slice(1));
        continue;
      }
    }
    result.push(...leg);
  }
  return result;
}
