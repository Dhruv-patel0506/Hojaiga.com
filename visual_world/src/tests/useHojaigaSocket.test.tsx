import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useHojaigaSocket } from "../ws/useHojaigaSocket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  triggerOpen() {
    this.readyState = 1;
    this.onopen?.();
  }
  triggerMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  triggerClose() {
    this.readyState = 3;
    this.onclose?.();
  }
}

const SNAPSHOT_1 = {
  type: "WORLD_SNAPSHOT" as const,
  server_time: "2026-01-01T00:00:00Z",
  registered_organs: [{ organ_id: "38", connected: true }],
  held_locks: [],
  active_sessions: [],
};

const SNAPSHOT_2 = {
  type: "WORLD_SNAPSHOT" as const,
  server_time: "2026-01-01T00:01:00Z",
  registered_organs: [
    { organ_id: "38", connected: true },
    { organ_id: "19", connected: true },
  ],
  held_locks: [{ lock_id: "chrome-cdp-lock", holder: "task-7", acquired_at: "2026-01-01T00:00:30Z" }],
  active_sessions: [],
};

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
  // Only fake the timers the reconnect backoff actually uses. Leaving
  // requestAnimationFrame/performance real avoids deadlocking against
  // testing-library's own scheduling.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useHojaigaSocket", () => {
  it("never sends any data -- strictly a read-only observer of the CNS", () => {
    const { result } = renderHook(() => useHojaigaSocket("ws://127.0.0.1:8080"));
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.triggerOpen();
      ws.triggerMessage(SNAPSHOT_1);
      ws.triggerMessage({
        type: "EVENT",
        envelope: {
          event_id: "e1",
          event_type: "EVENT_TASK_DISPATCHED",
          payload: { task_id: "task-1" },
          timestamp: "2026-01-01T00:00:05Z",
        },
      });
    });

    expect(result.current.status).toBe("open");
    expect(ws.sent).toHaveLength(0);
  });

  it("applies WORLD_SNAPSHOT immediately on connect", () => {
    const { result } = renderHook(() => useHojaigaSocket("ws://127.0.0.1:8080"));
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.triggerOpen();
      ws.triggerMessage(SNAPSHOT_1);
    });

    expect(result.current.snapshot).not.toBeNull();
    expect(result.current.snapshot?.registered_organs[0].organ_id).toBe("38");
  });

  it("reconnects with backoff after the socket closes, and resumes from a fresh snapshot", () => {
    const { result } = renderHook(() => useHojaigaSocket("ws://127.0.0.1:8080"));
    const first = MockWebSocket.instances[0];

    act(() => {
      first.triggerOpen();
      first.triggerMessage(SNAPSHOT_1);
    });
    expect(result.current.status).toBe("open");

    act(() => {
      first.triggerClose();
    });
    expect(result.current.status).toBe("reconnecting");

    // Advance past the first backoff window (base 1s + up to 30% jitter).
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(MockWebSocket.instances.length).toBe(2);

    const second = MockWebSocket.instances[1];
    act(() => {
      second.triggerOpen();
      second.triggerMessage(SNAPSHOT_2);
    });

    expect(result.current.status).toBe("open");
    // The world resumed from the NEW snapshot, not a merge with stale state.
    expect(result.current.snapshot?.held_locks).toHaveLength(1);
    expect(result.current.snapshot?.registered_organs).toHaveLength(2);
  });

  it("caps reconnect backoff and keeps retrying across repeated failures", () => {
    renderHook(() => useHojaigaSocket("ws://127.0.0.1:8080"));

    for (let i = 0; i < 5; i++) {
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
      act(() => {
        ws.triggerClose();
        vi.advanceTimersByTime(15_000); // more than enough for the capped backoff
      });
    }

    // Repeated failures keep producing new connection attempts (capped
    // backoff, not an unbounded/abandoned retry loop).
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(5);
  });
});
