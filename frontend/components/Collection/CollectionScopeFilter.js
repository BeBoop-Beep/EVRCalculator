"use client";

import { useState, useRef, useEffect } from "react";

/**
 * Collection Scope Filter Dropdown
 * Allows users to filter collection view by TCG (All, Pokemon, etc.)
 * When TCG changes, updates all dependent components (chart, stats, grid)
 * 
 * @component
 * @param {string[]} options - Available TCG options to display
 * @param {string} [props.initialValue="All"] - Initial selected TCG
 * @param {Function} props.onTCGChange - Callback when TCG selection changes
 * @param {boolean} [props.disabled=false] - Whether the filter is disabled
 */
export default function CollectionScopeFilter({
  options = ["All", "Pokemon"],
  selectedValues = ["All"],
  onTCGChange = () => {},
  disabled = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  const normalizedSelected = Array.isArray(selectedValues) && selectedValues.length > 0
    ? selectedValues
    : ["All"];
  const hasActiveSelection = normalizedSelected.some((value) => value !== "All");

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleToggle = (tcg) => {
    let nextValues = [];

    if (tcg === "All") {
      nextValues = ["All"];
    } else {
      const withoutAll = normalizedSelected.filter((value) => value !== "All");
      if (withoutAll.includes(tcg)) {
        nextValues = withoutAll.filter((value) => value !== tcg);
      } else {
        nextValues = [...withoutAll, tcg];
      }

      if (nextValues.length === 0) {
        nextValues = ["All"];
      }
    }

    onTCGChange(nextValues);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      setIsOpen(false);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setIsOpen(!isOpen);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setIsOpen(true);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
          disabled
            ? "cursor-not-allowed opacity-50 text-[var(--text-secondary)]"
            : hasActiveSelection
              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
              : "border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)] active:bg-[var(--surface-active)]"
        }`}
      >
        <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
          TCG
        </span>
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

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-2 w-40 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-lg">
          <ul
            role="listbox"
            className="space-y-1 p-2"
          >
            {options.map((tcg) => (
              <li key={tcg} role="option" aria-selected={normalizedSelected.includes(tcg)}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-hover)]">
                  <input
                    type="checkbox"
                    checked={normalizedSelected.includes(tcg)}
                    onChange={() => handleToggle(tcg)}
                    className="rounded border-[var(--border-subtle)]"
                  />
                  {tcg}
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
