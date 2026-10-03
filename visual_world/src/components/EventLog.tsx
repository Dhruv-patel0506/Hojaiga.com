interface Props {
  lines: string[];
}

export function EventLog({ lines }: Props) {
  return (
    <div className="panel-card" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <h2>Event Feed</h2>
      <ul className="event-log">
        {lines.length === 0 && <li>Waiting for CNS activity…</li>}
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  );
}
