"use client";

export default function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
  className = "",
  compact = false,
}) {
  const controlOptions = Array.isArray(options) ? options : [];
  if (controlOptions.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div
        className="inline-flex max-w-full items-center gap-1 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.58)] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
        role="radiogroup"
        aria-label={ariaLabel}
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
          const enabledOptions = controlOptions.filter((option) => !option?.disabled);
          if (enabledOptions.length === 0) return;
          const selectedIndex = enabledOptions.findIndex((option) => (option?.value ?? option?.key) === value);
          const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
          const nextIndex = event.key === "Home"
            ? 0
            : event.key === "End"
            ? enabledOptions.length - 1
            : (currentIndex + (event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1) + enabledOptions.length) % enabledOptions.length;
          const nextValue = enabledOptions[nextIndex]?.value ?? enabledOptions[nextIndex]?.key;
          event.preventDefault();
          onChange(nextValue);
          Array.from(event.currentTarget.querySelectorAll("[data-segment-value]")).find(
            (node) => node.dataset.segmentValue === String(nextValue)
          )?.focus();
        }}
      >
        {controlOptions.map((option) => {
          const optionValue = option?.value ?? option?.key;
          const isActive = value === optionValue;

          return (
            <button
              key={optionValue}
              type="button"
              onClick={() => onChange(optionValue)}
              role="radio"
              aria-checked={isActive}
              aria-label={option?.ariaLabel}
              title={option?.title}
              disabled={option?.disabled}
              tabIndex={isActive ? 0 : -1}
              data-segment-value={optionValue}
              className={`min-w-0 rounded-full font-semibold leading-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 disabled:cursor-not-allowed disabled:opacity-40 ${
                compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-[11px] sm:px-4 sm:text-xs"
              } ${
                isActive
                  ? "bg-[rgba(20,184,166,0.16)] text-[var(--accent)] shadow-[inset_0_0_0_1px_rgba(94,234,212,0.2)]"
                  : "text-[var(--text-secondary)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="block truncate">{option?.label ?? optionValue}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
