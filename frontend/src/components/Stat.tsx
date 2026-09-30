type StatProps = { label: string; value: string; suffix?: string; trend: string };

export function Stat({ label, value, suffix, trend }: StatProps) {
  return (
    <div className="stat-card">
      <p className="eyebrow">{label}</p>
      <div className="stat-value">{value}<small>{suffix}</small></div>
      <span className="trend">↗ {trend}</span>
    </div>
  );
}
