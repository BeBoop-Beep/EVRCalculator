"use client";

import { useEffect, useRef, useState } from "react";

export default function CollectionAddActionMenu({
  onAddCard = () => {},
  onAddSealedProduct = () => {},
  onImportCollection = () => {},
  isLoading = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const menuItems = [
    {
      id: "add-card",
      label: "Add Card",
      action: onAddCard,
      icon: (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <rect x="4" y="6" width="11" height="14" rx="2" strokeWidth="2" />
          <rect x="9" y="4" width="11" height="14" rx="2" strokeWidth="2" />
          <path d="M12 9h5" strokeWidth="2" strokeLinecap="round" />
          <path d="M12 12h5" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      id: "add-sealed",
      label: "Add Sealed Product",
      action: onAddSealedProduct,
      icon: (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path d="M3 8l9-5 9 5-9 5-9-5z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M3 8v8l9 5 9-5V8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
    },
    {
      id: "import-collection",
      label: "Import Collection",
      action: onImportCollection,
      icon: (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path d="M12 15V4" strokeWidth="2" strokeLinecap="round" />
          <path d="M8 8l4-4 4 4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ),
    },
  ];

  const handleItemClick = (action) => {
    setIsOpen(false);
    action();
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        disabled={isLoading}
        className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-input)] px-3 py-1.5 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 4v12m6-6H4" />
        </svg>
        <span>Add</span>
      </button>

      {isOpen ? (
        <div className="absolute right-0 z-20 mt-2 w-56 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1 shadow-md" role="menu">
          <div className="my-1 h-px bg-[var(--border-subtle)]" aria-hidden="true" />

          {menuItems.slice(0, 2).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => handleItemClick(item.action)}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
              role="menuitem"
            >
              <span className="text-[var(--text-secondary)]">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}

          <div className="my-1 h-px bg-[var(--border-subtle)]" aria-hidden="true" />

          <button
            type="button"
            onClick={() => handleItemClick(menuItems[2].action)}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
            role="menuitem"
          >
            <span className="text-[var(--text-secondary)]">{menuItems[2].icon}</span>
            <span>{menuItems[2].label}</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}