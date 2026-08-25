"use client";

// React is imported explicitly (not just its hooks) because the repo has no
// `jsx` compilerOption, so JSX compiles to the classic `React.createElement`
// runtime under the test transform and needs the binding in scope.
import React, { useEffect, useRef } from "react";

export default function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
  className = "",
  compact = false,
  variant = "pill",
  equalWidth = false,
  mobileFullWidth = false,
  // Opt-in, below 1200px only. Six options do not fit a phone at a readable
  // size, and letting them shrink truncates every label into an ellipsis — the
  // control stops naming its own views. Instead the options keep their full
  // length on one line and scroll when they overrun.
  //
  // How the leftover width is handled is a two-band decision:
  //
  //   below 600px  the pill spans the block and every option GROWS into an
  //                equal share of whatever is left, so the row ends where the
  //                controls end. Stretching the pill without stretching its
  //                contents is what left a dead zone on the right.
  //   600-1199px   the base `inline-flex` is kept, so the pill shrinks to its
  //                content — the same strip 1200px+ has always drawn. Six
  //                options fit here with room to spare, and stretching them
  //                across a tablet would only move the empty space inside the
  //                controls instead of removing it.
  //
  // Callers that fit (two- and three-way controls) pass nothing and are
  // untouched at every width.
  mobileScroll = false,
}) {
  const rowRef = useRef(null);
  const controlOptions = Array.isArray(options) ? options : [];
  const equalWidthLabelLength = equalWidth
    ? controlOptions.reduce((maxLength, option) => {
        const label = String(option?.label ?? option?.value ?? option?.key ?? "");
        return Math.max(maxLength, label.length);
      }, 0)
    : 0;
  const equalWidthStyle = equalWidth && equalWidthLabelLength > 0
    ? { minWidth: `${equalWidthLabelLength + 3}ch` }
    : undefined;

  // A scrolled-away active option is the same defect as a truncated one: the
  // control no longer shows what is selected. scrollLeft is adjusted directly
  // rather than via scrollIntoView, which would also scroll the PAGE vertically
  // when the control sits under the sticky tab bar.
  useEffect(() => {
    if (!mobileScroll) return;
    const row = rowRef.current;
    if (!row) return;
    const active = Array.from(row.querySelectorAll("[data-segment-value]")).find(
      (node) => node.dataset.segmentValue === String(value)
    );
    if (!active) return;
    const left = active.offsetLeft;
    const right = left + active.offsetWidth;
    if (left < row.scrollLeft) {
      row.scrollLeft = Math.max(0, left - 8);
    } else if (right > row.scrollLeft + row.clientWidth) {
      row.scrollLeft = right - row.clientWidth + 8;
    }
  }, [value, mobileScroll]);

  if (controlOptions.length === 0) {
    return null;
  }

  if (variant === "primary") {
    return (
      <div className={className}>
        <div className="grid w-full items-center gap-0.5 rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.72)] p-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_20px_rgba(2,6,23,0.18)] backdrop-blur-md" style={{ gridTemplateColumns: `repeat(${controlOptions.length}, minmax(0, 1fr))` }} role="radiogroup" aria-label={ariaLabel} onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
          const enabledOptions = controlOptions.filter((option) => !option?.disabled);
          if (!enabledOptions.length) return;
          const selectedIndex = enabledOptions.findIndex((option) => (option?.value ?? option?.key) === value);
          const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
          const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? enabledOptions.length - 1 : (currentIndex + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + enabledOptions.length) % enabledOptions.length;
          const nextValue = enabledOptions[nextIndex]?.value ?? enabledOptions[nextIndex]?.key;
          event.preventDefault();
          onChange(nextValue);
          event.currentTarget.querySelector(`[data-segment-value="${String(nextValue)}"]`)?.focus();
        }}>
          {controlOptions.map((option) => {
            const optionValue = option?.value ?? option?.key;
            const isActive = value === optionValue;
            return (
              <button key={optionValue} type="button" onClick={() => onChange(optionValue)} onPointerEnter={() => option?.onIntent?.()} onFocus={() => option?.onIntent?.()} onPointerDown={() => option?.onIntent?.()} role="radio" aria-checked={isActive} disabled={option?.disabled} tabIndex={isActive ? 0 : -1} data-segment-value={optionValue} className={`min-h-12 min-w-0 rounded-md px-1.5 py-1 text-[13px] font-semibold leading-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 disabled:cursor-not-allowed disabled:opacity-40 desk:min-h-0 desk:px-2 desk:py-1 desk:text-xs sm:px-2.5 sm:py-1.5 ${isActive ? "bg-[linear-gradient(135deg,rgba(16,185,129,0.95),rgba(20,184,166,0.78))] text-white shadow-[0_4px_12px_rgba(20,184,166,0.18),inset_0_1px_0_rgba(255,255,255,0.16)]" : "bg-transparent text-[color:color-mix(in_srgb,var(--text-secondary)_82%,transparent)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"}`}>
                <span className="block whitespace-nowrap">{option?.label ?? optionValue}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div
        ref={rowRef}
        className={`inline-flex max-w-full items-center gap-1 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.58)] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] ${
          mobileFullWidth ? "max-desk:flex max-desk:w-full" : ""
        } ${
          mobileScroll
            ? "max-tab:flex max-tab:w-full max-desk:snap-x max-desk:overflow-x-auto max-desk:[-ms-overflow-style:none] max-desk:[scrollbar-width:none] max-desk:[&::-webkit-scrollbar]:hidden"
            : ""
        }`}
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
          // A short label is a VISIBLE abbreviation only. The full name stays
          // the accessible name, so a screen reader still hears "Opening Profit
          // vs Cost" where the pill reads "OPvC".
          const shortLabel = option?.shortLabel || null;
          const accessibleName = option?.ariaLabel || (shortLabel ? option?.label : undefined);

          return (
            <button
              key={optionValue}
              type="button"
              onClick={() => onChange(optionValue)}
              role="radio"
              aria-checked={isActive}
              aria-label={accessibleName}
              title={option?.title || (shortLabel ? option?.label : undefined)}
              disabled={option?.disabled}
              tabIndex={isActive ? 0 : -1}
              data-segment-value={optionValue}
              style={equalWidthStyle}
              className={`min-w-0 rounded-full font-semibold leading-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/65 disabled:cursor-not-allowed disabled:opacity-40 ${
                compact ? "px-2.5 py-1 text-[10px] max-desk:min-h-11" : "px-3 py-1.5 text-[11px] max-desk:min-h-11 sm:px-4 sm:text-xs"
              } ${
                // `grow` + `shrink-0`, never `flex-none`: an option takes a
                // share of the slack when there is any, and keeps its natural
                // width when there is not — so the row fills without any label
                // ever being squeezed into an ellipsis.
                mobileScroll
                  ? "max-desk:min-h-9 max-desk:shrink-0 max-tab:grow max-desk:snap-start max-desk:px-3"
                  : mobileFullWidth
                    ? "max-desk:flex-1 max-desk:basis-0 max-desk:justify-center"
                  : ""
              } ${
                isActive
                  ? "bg-[rgba(20,184,166,0.16)] text-[var(--accent)] shadow-[inset_0_0_0_1px_rgba(94,234,212,0.2)]"
                  : "text-[var(--text-secondary)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"
              }`}
            >
              {shortLabel ? (
                // `whitespace-nowrap`, not `truncate`: inside a scroller the
                // option is allowed its full width, so there is nothing to
                // clip and no ellipsis to render.
                <>
                  <span className="hidden whitespace-nowrap desk:block">{option?.label ?? optionValue}</span>
                  <span className="block whitespace-nowrap desk:hidden">{shortLabel}</span>
                </>
              ) : (
                <span className="block truncate">{option?.label ?? optionValue}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
