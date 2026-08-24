"use client";


// React is imported explicitly (rather than relying on the bundler's automatic
// JSX runtime) so this control can be rendered directly under `tsx --test`,
// which compiles JSX to React.createElement.
import React from "react";
import { getCompactWindowLabel, needsAccessibleWindowLabel } from "../../lib/explore/compactWindowLabel.mjs";

export const TIME_RANGE_OPTIONS = [
  { key: "1D", desktopLabel: "1D", mobileLabel: "1D", ariaLabel: "1D" },
  { key: "7D", desktopLabel: "7D", mobileLabel: "7D", ariaLabel: "7D" },
  { key: "30D", desktopLabel: "30D", mobileLabel: "30D", ariaLabel: "30D" },
  { key: "3M", desktopLabel: "3M", mobileLabel: "3M", ariaLabel: "3M" },
  { key: "6M", desktopLabel: "6M", mobileLabel: "6M", ariaLabel: "6M" },
  { key: "1Y", desktopLabel: "1Y", mobileLabel: "1Y", ariaLabel: "1Y" },
  { key: "lifetime", desktopLabel: "All", mobileLabel: "All", ariaLabel: "All available history" },
];

const TIME_RANGE_OPTIONS_BY_KEY = new Map(TIME_RANGE_OPTIONS.map((entry) => [entry.key, entry]));
const VISIBLE_TIME_RANGE_LABELS = new Set(["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"]);

function normalizeRangeKey(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "lifetime") {
    return "lifetime";
  }
  const upper = normalized.toUpperCase();
  return TIME_RANGE_OPTIONS_BY_KEY.has(upper) ? upper : null;
}

function resolveVisibleWindowLabel(entry) {
  const knownOption = TIME_RANGE_OPTIONS_BY_KEY.get(normalizeRangeKey(entry?.key));
  if (knownOption) {
    return knownOption.mobileLabel;
  }

  const compactLabel = String(getCompactWindowLabel(entry?.key, entry?.label) || "").toUpperCase();
  if (VISIBLE_TIME_RANGE_LABELS.has(compactLabel)) {
    return compactLabel;
  }

  const normalized = String(entry?.label || entry?.key || "").toUpperCase().replace(/\s+/g, "");
  if (VISIBLE_TIME_RANGE_LABELS.has(normalized)) {
    return normalized;
  }
  if (normalized === "LIFETIME") {
    return "All";
  }
  return String(entry?.label || entry?.key || "").toUpperCase();
}

function resolveItems({ windows, supportedValues }) {
  const windowEntries = (Array.isArray(windows) ? windows : []).filter(Boolean);
  const windowEntryByKey = new Map(
    windowEntries
      .map((entry) => {
        const key = normalizeRangeKey(entry?.key);
        return key ? [key, entry] : null;
      })
      .filter(Boolean)
  );

  const supportedKeys = new Set(
    (Array.isArray(supportedValues) && supportedValues.length > 0 ? supportedValues : windowEntries.map((entry) => entry?.key))
      .map((value) => normalizeRangeKey(value))
      .filter(Boolean)
  );

  const keysToRender = supportedKeys.size > 0
    ? TIME_RANGE_OPTIONS.map((entry) => entry.key).filter((key) => supportedKeys.has(key))
    : TIME_RANGE_OPTIONS.map((entry) => entry.key);

  return keysToRender
    .map((key) => {
      const option = TIME_RANGE_OPTIONS_BY_KEY.get(key);
      const windowEntry = windowEntryByKey.get(key);
      const fallbackLabel = resolveVisibleWindowLabel(windowEntry || option || {});
      const ariaLabel =
        option?.ariaLabel ||
        (windowEntry && needsAccessibleWindowLabel(windowEntry.key, windowEntry.label) ? windowEntry.label : undefined) ||
        option?.desktopLabel ||
        fallbackLabel;

      return {
        key,
        desktopLabel: option?.desktopLabel || fallbackLabel,
        mobileLabel: option?.mobileLabel || fallbackLabel,
        ariaLabel,
        title: ariaLabel,
        disabled: Boolean(windowEntry?.disabled),
      };
    })
    .filter(Boolean);
}

export default function TimeRangeSelector({
  windows,
  supportedValues,
  selectedValue,
  onValueChange,
  ariaLabel = "Time range",
  ariaDescription,
  disabled = false,
  fullWidth = false,
  className = "",
}) {
  const items = resolveItems({ windows, supportedValues });
  const selectedKey = normalizeRangeKey(selectedValue);

  if (items.length <= 1) {
    return null;
  }

  const wrapperClassName = [fullWidth ? "w-full" : "w-full desk:w-auto", className].filter(Boolean).join(" ");

  const handleKeyDown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }

    const enabledItems = items.filter((item) => !item.disabled);
    if (enabledItems.length === 0) {
      return;
    }

    const selectedIndex = enabledItems.findIndex((item) => item.key === selectedKey);
    const currentIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabledItems.length - 1
        : (currentIndex + (event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1) + enabledItems.length) % enabledItems.length;
    const nextValue = enabledItems[nextIndex]?.key;
    event.preventDefault();
    onValueChange?.(nextValue);
    Array.from(event.currentTarget.querySelectorAll("[data-time-range-value]"))
      .find((node) => node.dataset.timeRangeValue === String(nextValue))
      ?.focus();
  };

  return (
    <div className={wrapperClassName}>
      <div
        role="radiogroup"
        aria-label={ariaLabel}
        aria-description={ariaDescription || undefined}
        onKeyDown={handleKeyDown}
        className={fullWidth
          ? "grid min-w-0 w-full grid-cols-7 gap-1.5"
          : "grid min-w-0 w-full grid-flow-col auto-cols-fr gap-1.5 desk:flex desk:w-auto desk:flex-wrap"}
      >
        {items.map((item) => {
          const isActive = selectedKey === item.key;

          return (
            <button
              key={`time-range:${item.key}`}
              type="button"
              role="radio"
              aria-checked={isActive}
              aria-label={item.ariaLabel || undefined}
              title={item.title || undefined}
              data-time-range-value={item.key}
              disabled={disabled || item.disabled}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onValueChange?.(item.key)}
              className={[
                "min-w-0 whitespace-nowrap rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition-colors",
                fullWidth ? "desk:px-1" : "",
                "max-desk:inline-flex max-desk:min-h-11 max-desk:items-center max-desk:justify-center max-desk:px-2",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] disabled:cursor-not-allowed disabled:opacity-40",
                isActive
                  ? "border-[rgba(45,212,191,0.34)] bg-[rgba(45,212,191,0.10)] text-[rgb(45,212,191)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              <span aria-hidden="true" className="hidden max-desk:inline">{item.desktopLabel}</span>
              <span aria-hidden="true" className="max-desk:hidden">{item.mobileLabel}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
