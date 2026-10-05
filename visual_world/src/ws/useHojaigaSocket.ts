import { useEffect, useRef, useState } from "react";
import type { HojaigaServerMessage, WorldSnapshotMessage } from "./types";
import {
  applyHojaigaEvent,
  applyWorldSnapshot,
  initialFacilityState,
  tickAgents,
  type FacilityState,
} from "../world/agentEngine";

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

const DEFAULT_URL = "ws://127.0.0.1:8080";
const MAX_BACKOFF_MS = 10_000;
const BASE_BACKOFF_MS = 1_000;

export interface UseHojaigaSocketResult {
  state: FacilityState;
  status: ConnectionStatus;
  snapshot: WorldSnapshotMessage | null;
  lastError: string | null;
}

/**
 * Connects to the organ_99_visual_adapter WebSocket, applies the
 * WORLD_SNAPSHOT it sends immediately on connect, then folds every
 * subsequent EVENT through the pure agentEngine reducer.
 *
 * Reconnects with capped exponential backoff + jitter. Per rule #5 in
 * the brief, a refresh (remount) always re-fetches WORLD_SNAPSHOT before
 * resuming -- there is no client-side cache of prior state across a full
 * page reload, by design, so the visual world can never drift from the
 * real CNS state.
 */
export function useHojaigaSocket(
  url: string = import.meta.env.VITE_HOJAIGA_WS_URL ?? DEFAULT_URL
): UseHojaigaSocketResult {
  const [state, setState] = useState<FacilityState>(initialFacilityState());
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [snapshot, setSnapshot] = useState<WorldSnapshotMessage | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    stoppedRef.current = false;

    function scheduleReconnect() {
      if (stoppedRef.current) return;
      const attempt = ++attemptRef.current;
      const backoff = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** (attempt - 1));
      const jitter = Math.random() * 0.3 * backoff;
      setStatus("reconnecting");
      reconnectTimer.current = setTimeout(connect, backoff + jitter);
    }

    function connect() {
      if (stoppedRef.current) return;
      setStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");

      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch (err) {
        setLastError(String(err));
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setStatus("open");
        setLastError(null);
      };

      ws.onmessage = (event) => {
        let msg: HojaigaServerMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return; // ignore malformed frames rather than crash the world
        }

        if (msg.type === "WORLD_SNAPSHOT") {
          setSnapshot(msg);
          setState(applyWorldSnapshot(msg));
          return;
        }
        if (msg.type === "EVENT") {
          setState((prev) => applyHojaigaEvent(prev, msg.envelope));
          return;
        }
        // HEARTBEAT and anything else: no-op, connection liveness only.
      };

      ws.onerror = () => {
        setLastError("WebSocket error");
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (!stoppedRef.current) scheduleReconnect();
      };
    }

    connect();

    // Render-frame tick to interpolate agent movement between events.
    let lastFrame = performance.now();
    function frame(now: number) {
      if (now - lastFrame > 90) {
        // ~11fps tile-step cadence, independent of monitor refresh rate
        lastFrame = now;
        setState((prev) => tickAgents(prev, 1));
      }
      rafRef.current = requestAnimationFrame(frame);
    }
    rafRef.current = requestAnimationFrame(frame);

    return () => {
      stoppedRef.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      wsRef.current?.close();
      setStatus("closed");
    };
  }, [url]);

  return { state, status, snapshot, lastError };
}
