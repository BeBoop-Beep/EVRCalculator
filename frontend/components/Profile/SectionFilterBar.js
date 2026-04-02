"use client";

import { useState, useRef, useEffect } from "react";

/**
 * Filter bar component for collection sections
 * Supports multiple active filters with clear functionality
 */
export default function SectionFilterBar({
  filters = [],
  activeFilters = {},
  onFilterChange = () => {},
  isLoading = false,
  leadingControls = null,
  extraActiveSelections = [],
  onClearAll = null,
}) {
  const [openDropdown, setOpenDropdown] = useState(null);
  const dropdownRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpenDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleToggleFilter = (filterId, optionId) => {
    const currentValues = activeFilters[filterId] || [];
    const newValues = currentValues.includes(optionId)
      ? currentValues.filter((v) => v !== optionId)
      : [...currentValues, optionId];

    onFilterChange(filterId, newValues.length > 0 ? newValues : null);
  };

  const handleClearAll = () => {
    Object.keys(activeFilters).forEach((key) => {
      onFilterChange(key, null);
    });
    onClearAll?.();
  };

  const hasActiveFilters = Object.values(activeFilters).some((v) => v && v.length > 0);
  const hasExtraSelections = extraActiveSelections.length > 0;

  if (filters.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" ref={dropdownRef}>
        {leadingControls}

        {filters.map((filter) => (
          <div key={filter.id} className="relative">
            <button
              onClick={() =>
                setOpenDropdown(openDropdown === filter.id ? null : filter.id)
              }
              disabled={isLoading}
              className={`inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                activeFilters[filter.id] && activeFilters[filter.id].length > 0
                  ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
              }`}
            >
              <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
                {filter.label}
              </span>
              <svg
                className={`h-4 w-4 transition-transform ${
                  openDropdown === filter.id ? "rotate-180" : ""
                }`}
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

            {openDropdown === filter.id && (
              <div className="absolute left-0 top-full z-50 mt-2 w-48 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-lg">
                <div className="space-y-1 p-2">
                  {filter.options.map((option) => (
                    <label
                      key={option.id}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                    >
                      <input
                        type="checkbox"
                        checked={
                          activeFilters[filter.id]?.includes(option.id) || false
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
            )}
          </div>
        ))}

        {(hasActiveFilters || hasExtraSelections) && (
          <button
            onClick={handleClearAll}
            className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {(hasActiveFilters || hasExtraSelections) && (
        <div className="flex flex-wrap gap-2">
          {extraActiveSelections.map((selection) => (
            <div
              key={selection.id}
              className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)]/10 px-3 py-1 text-xs text-[var(--accent)]"
            >
              {selection.label}
              <button
                onClick={selection.onRemove}
                className="hover:opacity-70"
              >
                <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}

          {filters.map(
            (filter) =>
              activeFilters[filter.id] &&
              activeFilters[filter.id].length > 0 &&
              activeFilters[filter.id].map((optionId) => {
                const option = filter.options.find((o) => o.id === optionId);
                return (
                  <div
                    key={`${filter.id}-${optionId}`}
                    className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)]/10 px-3 py-1 text-xs text-[var(--accent)]"
                  >
                    {option?.label}
                    <button
                      onClick={() => handleToggleFilter(filter.id, optionId)}
                      className="hover:opacity-70"
                    >
                      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })
          )}
        </div>
      )}
    </div>
  );
}
