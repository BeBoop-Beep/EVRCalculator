export default function SetRuntimeHeader({ selectedTarget, requestedTargetId, targets, targetHrefById, activeTab, onTargetChange }) {
  const name = selectedTarget?.name || selectedTarget?.label || requestedTargetId || "Pokemon Set";
  const logo = selectedTarget?.logo_url || selectedTarget?.logoUrl || selectedTarget?.image_url || null;
  return (
    <header className="px-4 py-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        {logo ? <img src={logo} alt="" className="h-12 w-20 shrink-0 object-contain" /> : null}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Pokemon Set</p>
          <h1 className="truncate text-xl font-bold text-[var(--text-primary)] sm:text-2xl">{name}</h1>
        </div>
        {targets.length > 0 ? (
          <label className="max-w-[13rem] text-xs font-semibold text-[var(--text-secondary)]">
            <span className="sr-only">Choose a set</span>
            <select
              value={requestedTargetId || selectedTarget?.target_id || ""}
              onChange={(event) => onTargetChange(event.target.value, targetHrefById?.[event.target.value], activeTab)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)]"
            >
              {targets.map((target) => {
                const id = String(target?.target_id || target?.id || "");
                return <option key={id} value={id}>{target?.name || id}</option>;
              })}
            </select>
          </label>
        ) : null}
      </div>
    </header>
  );
}
