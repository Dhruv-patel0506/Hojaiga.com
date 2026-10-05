import type { WorldSnapshotMessage } from "../ws/types";
import { ZONE_META, ALL_ZONE_IDS } from "../world/zones";

interface Props {
  snapshot: WorldSnapshotMessage | null;
}

export function HUD({ snapshot }: Props) {
  return (
    <>
      <div className="panel-card">
        <h2>Zones</h2>
        <div className="legend">
          {ALL_ZONE_IDS.map((zone) => (
            <span className="legend-item" key={zone}>
              <span className="legend-swatch" style={{ background: ZONE_META[zone].color }} />
              {ZONE_META[zone].label}
            </span>
          ))}
        </div>
      </div>

      <div className="panel-card">
        <h2>Registered Organs</h2>
        {snapshot ? (
          snapshot.registered_organs.map((o) => (
            <div className="registry-row" key={o.organ_id}>
              <span className="organ-id">ORG-{o.organ_id}</span>
              <span style={{ color: o.connected ? "#34d399" : "#6b7488" }}>
                {o.connected ? "online" : "offline"}
              </span>
            </div>
          ))
        ) : (
          <div className="registry-row"><span className="organ-id">awaiting snapshot…</span></div>
        )}
      </div>

      <div className="panel-card">
        <h2>Held Locks</h2>
        {snapshot && snapshot.held_locks.length > 0 ? (
          snapshot.held_locks.map((l) => (
            <div className="registry-row" key={l.lock_id}>
              <span className="organ-id">{l.lock_id}</span>
              <span>{l.holder}</span>
            </div>
          ))
        ) : (
          <div className="registry-row"><span className="organ-id">none</span></div>
        )}
      </div>
    </>

  );
}
