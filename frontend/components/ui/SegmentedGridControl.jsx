"use client";

export default function SegmentedGridControl({
  items,
  selectedValue,
  onValueChange,
  ariaLabel,
  className = "",
  columnClassName = "",
  columnCount = null,
  desktopPill = false,
}) {
  const controlItems = Array.isArray(items) ? items.filter(Boolean) : [];
  if (controlItems.length === 0) {
    return null;
  }

  const resolvedColumnCount = Number.isFinite(columnCount) && columnCount > 0
    ? columnCount
    : controlItems.length;

  const handleKeyDown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    const enabledItems = controlItems.filter((item) => !item?.disabled);
    if (enabledItems.length === 0) {
      return;
    }
    const selectedIndex = enabledItems.findIndex((item) => item.value === selectedValue);
    const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
      ? enabledItems.length - 1
      : (currentIndex + (event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1) + enabledItems.length) % enabledItems.length;
    const nextValue = enabledItems[nextIndex]?.value;
    event.preventDefault();
    onValueChange?.(nextValue);
    Array.from(event.currentTarget.querySelectorAll("[data-segment-grid-value]"))
      .find((node) => node.dataset.segmentGridValue === String(nextValue))
      ?.focus();
  };

  return (
    <div className={className}>
      <div
        role="radiogroup"
        aria-label={ariaLabel}
        onKeyDown={handleKeyDown}
        className={[
          "grid min-w-0 w-full gap-1.5",
          columnClassName,
          desktopPill
            ? "desk:inline-flex desk:w-auto desk:items-center desk:gap-1 desk:rounded-full desk:border desk:border-[rgba(255,255,255,0.08)] desk:bg-[rgba(15,23,42,0.58)] desk:p-1"
            : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={
          columnClassName
            ? undefined
            : { gridTemplateColumns: `repeat(${resolvedColumnCount}, minmax(0, 1fr))` }
        }
      >
        {controlItems.map((item) => {
          const isActive = selectedValue === item.value;
          return (
            <button
              key={String(item.value)}
              type="button"
              role="radio"
              aria-checked={isActive}
              aria-label={item.ariaLabel || undefined}
              title={item.title || undefined}
              data-segment-grid-value={String(item.value)}
              disabled={item.disabled}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onValueChange?.(item.value)}
              className={[
                "min-w-0 rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition-colors",
                "max-desk:inline-flex max-desk:min-h-11 max-desk:items-center max-desk:justify-center max-desk:px-2",
                desktopPill
                  ? "desk:min-h-0 desk:rounded-full desk:px-3 desk:py-1.5 desk:text-[11px] desk:tracking-normal desk:normal-case"
                  : "",
                isActive
                  ? "border-[rgba(45,212,191,0.34)] bg-[rgba(45,212,191,0.10)] text-[rgb(45,212,191)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                isActive && desktopPill
                  ? "desk:shadow-[inset_0_0_0_1px_rgba(94,234,212,0.2)]"
                  : "",
                !isActive && desktopPill
                  ? "desk:hover:bg-[rgba(255,255,255,0.045)]"
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <span className="block truncate">{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
