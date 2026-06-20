"use client";

export default function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
  className = "",
}) {
  const controlOptions = Array.isArray(options) ? options : [];
  if (controlOptions.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div
        className="inline-flex max-w-full items-center gap-1 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.58)] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
        role="group"
        aria-label={ariaLabel}
      >
        {controlOptions.map((option) => {
          const optionValue = option?.value ?? option?.key;
          const isActive = value === optionValue;

          return (
            <button
              key={optionValue}
              type="button"
              onClick={() => onChange(optionValue)}
              aria-pressed={isActive}
              aria-label={option?.ariaLabel}
              title={option?.title}
              className={`min-w-0 rounded-full px-3 py-1.5 text-[11px] font-semibold leading-none transition-all duration-200 sm:px-4 sm:text-xs ${
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
