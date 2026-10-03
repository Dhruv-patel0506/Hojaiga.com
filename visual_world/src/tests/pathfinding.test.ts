import { describe, it, expect } from "vitest";
import { findPath, chainPaths } from "../world/pathfinding";
import { buildFacilityGrid } from "../world/grid";
import { TASK_ORCHESTRATOR, CHROME_CDP, SECURITY_TURNSTILE } from "../world/zones";

describe("findPath", () => {
  const grid = buildFacilityGrid();

  it("finds a direct route from Task Orchestrator to Chrome CDP", () => {
    const path = findPath(
      grid,
      { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y },
      { x: CHROME_CDP.x, y: CHROME_CDP.y }
    );
    expect(path.length).toBeGreaterThan(0);
    expect(path[0]).toEqual({ x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y });
    expect(path[path.length - 1]).toEqual({ x: CHROME_CDP.x, y: CHROME_CDP.y });
  });

  it("never steps onto a wall tile (collision safety)", () => {
    const path = findPath(
      grid,
      { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y },
      { x: CHROME_CDP.x, y: CHROME_CDP.y }
    );
    for (const p of path) {
      expect(grid[p.y][p.x]).toBe(0);
    }
  });

  it("only moves one tile (4-directionally) between consecutive path steps", () => {
    const path = findPath(
      grid,
      { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y },
      { x: CHROME_CDP.x, y: CHROME_CDP.y }
    );
    for (let i = 1; i < path.length; i++) {
      const dx = Math.abs(path[i].x - path[i - 1].x);
      const dy = Math.abs(path[i].y - path[i - 1].y);
      expect(dx + dy).toBe(1);
    }
  });

  it("returns [] when the goal is unreachable (walled off)", () => {
    const blocked = grid.map((row) => [...row]);
    // Seal every walkable neighbor around the goal.
    const { x, y } = CHROME_CDP;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      blocked[y + dy][x + dx] = 1;
    }
    const path = findPath(blocked, { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y }, { x, y });
    expect(path).toEqual([]);
  });

  it("returns a single-tile path when start equals goal", () => {
    const path = findPath(grid, { x: 5, y: 5 }, { x: 5, y: 5 });
    expect(path).toEqual([{ x: 5, y: 5 }]);
  });

  it("routes through the Security Checkpoint room when chained via the turnstile", () => {
    const leg1 = findPath(
      grid,
      { x: TASK_ORCHESTRATOR.x, y: TASK_ORCHESTRATOR.y },
      { x: SECURITY_TURNSTILE.x, y: SECURITY_TURNSTILE.y }
    );
    const leg2 = findPath(
      grid,
      { x: SECURITY_TURNSTILE.x, y: SECURITY_TURNSTILE.y },
      { x: CHROME_CDP.x, y: CHROME_CDP.y }
    );
    expect(leg1.length).toBeGreaterThan(0);
    expect(leg2.length).toBeGreaterThan(0);

    const full = chainPaths(leg1, leg2);
    // The chained route must actually visit the turnstile tile.
    expect(full).toContainEqual({ x: SECURITY_TURNSTILE.x, y: SECURITY_TURNSTILE.y });
  });
});

describe("chainPaths", () => {
  it("de-duplicates the shared joining tile between legs", () => {
    const legA = [{ x: 0, y: 0 }, { x: 1, y: 0 }];
    const legB = [{ x: 1, y: 0 }, { x: 2, y: 0 }];
    expect(chainPaths(legA, legB)).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
    ]);
  });

  it("handles empty legs gracefully", () => {
    expect(chainPaths([], [{ x: 1, y: 1 }])).toEqual([{ x: 1, y: 1 }]);
  });
});
