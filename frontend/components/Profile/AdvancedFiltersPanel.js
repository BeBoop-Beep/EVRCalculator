"use client";

import { useState, useRef, useEffect } from "react";

/**
 * Advanced Filters Panel Component (LAYER 3)
 * Collapsible panel containing non-type filters
 * Shows count of active filters on the button
 */
export default function AdvancedFiltersPanel({
  filters = [],
  activeFilters = {},
  onFilterChange = () => {},
  onClearAll = () => {},
  isLoading = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Count active filters
  const activeFilterCount = Object.values(activeFilters).reduce(
    (count, values) => count + (values && values.length > 0 ? 1 : 0),
    0
  );

  const handleToggleFilter = (filterId, optionId) => {
    const currentValues = activeFilters[filterId] || [];
    const newValues = currentValues.includes(optionId)
      ? currentValues.filter((v) => v !== optionId)
      : [...currentValues, optionId];

    onFilterChange(filterId, newValues.length > 0 ? newValues : null);
  };

  const handleClearAllClick = () => {
    Object.keys(activeFilters).forEach((key) => {
      onFilterChange(key, null);
    });
    onClearAll?.();
  };

  if (filters.length === 0) {
    return null;
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className={`inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
          activeFilterCount > 0
            ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
            : "bg-[var(--surface-panel)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
        }`}
      >
        <svg
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
          />
        </svg>
        <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
          Filters
        </span>
        {activeFilterCount > 0 && (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
            {activeFilterCount}
          </span>
        )}
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 14l-7 7m0 0l-7-7m7 7V3"
          />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-lg">
          <div className="space-y-3 p-4">
            {/* Filter controls */}
            <div className="space-y-3">
              {filters.map((filter) => (
                <div key={filter.id} className="space-y-2">
                  <label className="block text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
                    {filter.label}
                  </label>
                  <div className="space-y-1">
                    {filter.options.map((option) => (
                      <label
                        key={option.id}
                        className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                      >
                        <input
                          type="checkbox"
                          checked={
                            activeFilters[filter.id]?.includes(option.id) ||
                            false
                          }
                          onChange={() =>
                            handleToggleFilter(filter.id, option.id)
                          }
                          className="rounded border-[var(--border-subtle)]"
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Clear All button */}
            {activeFilterCount > 0 && (
              <button
                onClick={handleClearAllClick}
                className="w-full rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                Clear All
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
