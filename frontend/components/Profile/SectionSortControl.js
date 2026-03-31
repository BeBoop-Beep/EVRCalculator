"use client";

import { useState, useRef, useEffect } from "react";

/**
 * Sort control dropdown for collection sections
 * Allows users to choose sort order
 */
export default function SectionSortControl({
  sortOptions = [],
  defaultSort = "recent",
  onSortChange = () => {},
  isLoading = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [selected, setSelected] = useState(defaultSort);
  const dropdownRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (optionId) => {
    setSelected(optionId);
    onSortChange(optionId);
    setIsOpen(false);
  };

  const selectedOption = sortOptions.find((opt) => opt.id === selected);
  const selectedLabel = selectedOption?.label || "Sort";

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-input)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
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
        <span className="hidden sm:inline">{selectedLabel}</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] shadow-lg z-10">
          <div className="p-2">
            {sortOptions.map((option) => (
              <button
                key={option.id}
                onClick={() => handleSelect(option.id)}
                className={`w-full px-3 py-2 text-left rounded-md text-sm transition-colors whitespace-nowrap ${
                  selected === option.id
                    ? "bg-[var(--accent)]/10 text-[var(--accent)] font-medium"
                    : "text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
