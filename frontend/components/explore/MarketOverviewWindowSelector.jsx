"use client";

import { describeUnavailableWindow } from "@/lib/explore/marketOverviewPresentation.mjs";

// The global Market Overview windows are 1D…1Y plus "All" (Since Tracking),
// and each one carries backend-declared availability. TimeRangeSelector's
// option table is fixed to the per-set vocabulary (…, "LT"/lifetime) and has no
// notion of a window the snapshot cannot support, so forcing this data through
// it would mean renaming a backend window in the UI. This selector reuses that
// component's styling and radiogroup/roving-arrow interaction instead.
export default function MarketOverviewWindowSelector({ options = [], value, onChange, ariaDescription }) {
  const items = (Array.isArray(options) ? options : []).filter(Boolean);
  const descriptionId = "market-window-selector-description";
  if (items.length <= 1) return null;

  const handleKeyDown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    const enabled = items.filter((item) => item.available);
    if (enabled.length === 0) return;
    const selectedIndex = enabled.findIndex((item) => item.key === value);
    const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabled.length - 1
        : (currentIndex + (event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
    const nextValue = enabled[nextIndex]?.key;
    event.preventDefault();
    onChange?.(nextValue);
    Array.from(event.currentTarget.querySelectorAll("[data-market-window-value]"))
      .find((node) => node.dataset.marketWindowValue === String(nextValue))
      ?.focus();
  };

  return (
    <>
      {ariaDescription ? <span id={descriptionId} className="sr-only">{ariaDescription}</span> : null}
      <div
      role="radiogroup"
      aria-label="Market performance time range"
      aria-describedby={ariaDescription ? descriptionId : undefined}
      onKeyDown={handleKeyDown}
      className="grid min-w-0 w-full grid-cols-7 gap-1.5 desk:flex desk:w-auto desk:flex-wrap"
    >
      {items.map((item) => {
        const isActive = value === item.key;
        return (
          <button
            key={`market-window:${item.key}`}
            type="button"
            role="radio"
            aria-checked={isActive}
            aria-label={item.available ? item.ariaLabel : describeUnavailableWindow(item.label)}
            aria-disabled={item.available ? undefined : "true"}
            title={item.available ? item.ariaLabel : describeUnavailableWindow(item.label)}
            data-market-window-value={item.key}
            data-market-window-available={item.available ? "true" : "false"}
            disabled={!item.available}
            tabIndex={isActive ? 0 : -1}
            onClick={() => { if (item.available) onChange?.(item.key); }}
            className={[
              "min-w-0 whitespace-nowrap rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition-colors",
              "max-desk:inline-flex max-desk:min-h-11 max-desk:items-center max-desk:justify-center max-desk:px-2 desk:px-2.5",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 disabled:cursor-not-allowed disabled:opacity-40",
              isActive
                ? "border-[rgba(45,212,191,0.34)] bg-[rgba(45,212,191,0.10)] text-[rgb(45,212,191)]"
                : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span aria-hidden="true">{item.label}</span>
          </button>
        );
      })}
      </div>
    </>
  );
}
