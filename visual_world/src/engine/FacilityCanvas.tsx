import { useEffect, useRef } from "react";
import { buildFacilityGrid, GRID_WIDTH, GRID_HEIGHT, TILE_SIZE, ROOMS } from "../world/grid";
import { ZONE_META, ORGANS, type OrganAnchor } from "../world/zones";
import type { FacilityState, AgentState } from "../world/agentEngine";
import type { ZoneId } from "../world/grid";

const STATUS_COLOR: Record<AgentState["status"], string> = {
  spawning: "#94a3b8",
  en_route: "#facc15",
  working: "#22d3ee",
  error: "#f87171",
  in_medbay: "#fb7185",
  returning: "#a3a3a3",
  idle_ambient: "#64748b",
};

function zoneOfTile(x: number, y: number): ZoneId | null {
  for (const [zone, room] of Object.entries(ROOMS)) {
    if (x >= room.x1 && x <= room.x2 && y >= room.y1 && y <= room.y2) {
      return zone as ZoneId;
    }
  }
  return null;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

interface Props {
  facility: FacilityState;
}

export function FacilityCanvas({ facility }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const grid = useRef(buildFacilityGrid());

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = GRID_WIDTH * TILE_SIZE;
    const height = GRID_HEIGHT * TILE_SIZE;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    ctx.fillStyle = "#05070c";
    ctx.fillRect(0, 0, width, height);

    // --- floor / walls ---
    for (let y = 0; y < GRID_HEIGHT; y++) {
      for (let x = 0; x < GRID_WIDTH; x++) {
        const walkable = grid.current[y][x] === 0;
        const zone = zoneOfTile(x, y);
        let fill = "#0a0d14"; // wall
        if (walkable) {
          if (zone && facility.litZones.has(zone)) {
            const [r, g, b] = hexToRgb(ZONE_META[zone].color);
            fill = `rgba(${r}, ${g}, ${b}, 0.10)`;
          } else {
            fill = "#10141d";
          }
        }
        ctx.fillStyle = fill;
        ctx.fillRect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE);

        if (walkable) {
          ctx.strokeStyle = "rgba(255,255,255,0.02)";
          ctx.strokeRect(x * TILE_SIZE + 0.5, y * TILE_SIZE + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);
        }
      }
    }

    // --- zone borders + labels ---
    ctx.font = "10px ui-monospace, monospace";
    for (const [zoneId, room] of Object.entries(ROOMS) as [ZoneId, typeof ROOMS[keyof typeof ROOMS]][]) {
      const meta = ZONE_META[zoneId];
      const lit = facility.litZones.has(zoneId);
      const [r, g, b] = hexToRgb(meta.color);
      ctx.strokeStyle = lit ? `rgba(${r},${g},${b},0.55)` : "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      ctx.strokeRect(
        room.x1 * TILE_SIZE,
        room.y1 * TILE_SIZE,
        (room.x2 - room.x1 + 1) * TILE_SIZE,
        (room.y2 - room.y1 + 1) * TILE_SIZE
      );

      ctx.fillStyle = lit ? `rgba(${r},${g},${b},0.9)` : "rgba(255,255,255,0.25)";
      ctx.fillText(meta.label.toUpperCase(), room.x1 * TILE_SIZE + 4, room.y1 * TILE_SIZE + 12);
    }

    // --- security turnstile marker ---
    const turnstile = ORGANS.find((o) => o.organId === "07")!;
    ctx.strokeStyle = "rgba(249,115,22,0.7)";
    ctx.lineWidth = 2;
    ctx.strokeRect(
      turnstile.x * TILE_SIZE - 3,
      turnstile.y * TILE_SIZE - 3,
      TILE_SIZE + 6,
      TILE_SIZE + 6
    );

    // --- organ desks ---
    for (const organ of ORGANS as OrganAnchor[]) {
      const lit = facility.litZones.has(organ.zone);
      const cx = organ.x * TILE_SIZE + TILE_SIZE / 2;
      const cy = organ.y * TILE_SIZE + TILE_SIZE / 2;
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fillStyle = lit ? ZONE_META[organ.zone].color : "#3a4152";
      ctx.fill();

      ctx.font = "9px ui-monospace, monospace";
      ctx.fillStyle = lit ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.2)";
      ctx.fillText(organ.organId, cx + 5, cy + 3);
    }

    // --- agents ---
    for (const agent of Object.values(facility.agents)) {
      const cx = agent.position.x * TILE_SIZE + TILE_SIZE / 2;
      const cy = agent.position.y * TILE_SIZE + TILE_SIZE / 2;
      const color = STATUS_COLOR[agent.status];

      ctx.beginPath();
      ctx.arc(cx, cy, 6, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;

      if (agent.status === "error" || agent.status === "in_medbay") {
        ctx.strokeStyle = "#f87171";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx - 4, cy - 10);
        ctx.lineTo(cx + 4, cy - 10);
        ctx.moveTo(cx, cy - 12);
        ctx.lineTo(cx, cy - 6);
        ctx.stroke();
      }

      ctx.font = "9px ui-monospace, monospace";
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.fillText(agent.id.slice(0, 8), cx + 8, cy - 8);
    }
  }, [facility]);

  return <canvas ref={canvasRef} aria-label="Hojaiga facility floor plan, live agent view" />;
}
