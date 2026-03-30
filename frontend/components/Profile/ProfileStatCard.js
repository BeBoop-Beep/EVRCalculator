export default function ProfileStatCard({ label, value, hint, valueClassName = "", subValue }) {
  return (
    <div className="flex min-h-[158px] flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{label}</p>
      <p className={`mt-3 text-3xl font-semibold leading-tight text-[var(--text-primary)] ${valueClassName}`}>{value}</p>
      {subValue ? <p className="mt-2 text-xs font-medium text-[var(--text-secondary)]">{subValue}</p> : null}
      {hint ? <p className="mt-auto pt-4 text-xs text-[var(--text-secondary)]">{hint}</p> : null}
    </div>
  );
}
