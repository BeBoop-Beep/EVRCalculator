const badgeToneClasses = {
  positive: "border-[var(--success)]/35 bg-[var(--success)]/12 text-[var(--success)]",
  negative: "border-[var(--danger)]/35 bg-[var(--danger)]/12 text-[var(--danger)]",
  warning: "border-[var(--warning)]/35 bg-[var(--warning)]/12 text-[var(--warning)]",
  neutral: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)]",
};

export default function ProfileStatCard({
  label,
  value,
  hint,
  valueClassName = "",
  subValue,
  compact = false,
  badge,
  badgeTone = "neutral",
  className = "",
}) {
  const spacingClasses = compact ? "min-h-[136px] p-5" : "min-h-[158px] p-6";
  const valueSpacingClasses = compact ? "mt-3 text-2xl" : "mt-4 text-3xl";
  const badgeToneClass = badgeToneClasses[badgeTone] || badgeToneClasses.neutral;

  return (
    <div className={`dashboard-panel flex flex-col rounded-2xl ${spacingClasses} ${className}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="metric-label text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{label}</p>
        {badge ? (
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${badgeToneClass}`}>
            {badge}
          </span>
        ) : null}
      </div>
      <p className={`metric-value ${valueSpacingClasses} font-semibold leading-tight text-[var(--text-primary)] ${valueClassName}`}>{value}</p>
      {subValue ? <p className="mt-2.5 text-xs font-medium text-[var(--text-secondary)]">{subValue}</p> : null}
      {hint ? <p className="mt-auto pt-4 text-xs text-[var(--text-secondary)]">{hint}</p> : null}
    </div>
  );
}
