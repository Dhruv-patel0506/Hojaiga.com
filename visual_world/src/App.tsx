import { useHojaigaSocket } from "./ws/useHojaigaSocket";
import { FacilityCanvas } from "./engine/FacilityCanvas";
import { HUD } from "./components/HUD";
import { EventLog } from "./components/EventLog";
import "./styles/theme.css";

const STATUS_LABEL: Record<string, string> = {
  connecting: "connecting",
  open: "live",
  reconnecting: "reconnecting",
  closed: "disconnected",
};

export default function App() {
  const { state, status, snapshot } = useHojaigaSocket();

  return (
    <div className="facility-app">
      <header className="facility-header">
        <div className="facility-title">
          Hojaiga <strong>The Autonomous Facility</strong>
          <span style={{ marginLeft: 10, color: "var(--text-faint)" }}>read-only observer</span>
        </div>
        <div className="status-pill" data-status={status}>
          <span className="status-dot" />
          {STATUS_LABEL[status] ?? status}
        </div>
      </header>

      <div className="canvas-panel">
        <FacilityCanvas facility={state} />
        <div className="canvas-scanlines" />
      </div>

      <div className="side-panel">
        <HUD snapshot={snapshot} />
        <EventLog lines={state.log} />
      </div>
    </div>
  );
}
