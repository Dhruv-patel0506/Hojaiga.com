export interface Point { x: number; y: number; }

export function findPath(start: Point, end: Point, isBlocked: (x: number, y: number) => boolean): Point[] {
    const queue = [[start]];
    const seen = new Set([`${start.x},${start.y}`]);
    const dirs = [[0, 1], [1, 0], [0, -1], [-1, 0]]; // Down, Right, Up, Left

    while (queue.length > 0) {
        const path = queue.shift()!;
        const { x, y } = path[path.length - 1];

        if (x === end.x && y === end.y) return path.slice(1);

        for (const [dx, dy] of dirs) {
            const nx = x + dx, ny = y + dy;
            const key = `${nx},${ny}`;
            
            if (!seen.has(key) && !isBlocked(nx, ny)) {
                seen.add(key);
                queue.push([...path, { x: nx, y: ny }]);
            }
        }
    }
    return []; // Returns an empty array if no path exists
}
