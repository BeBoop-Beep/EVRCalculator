"use client";

import { useState } from "react";

export default function InfoPopover({ text }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label="More info"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] transition-all hover:border-[rgba(20,184,166,0.6)] hover:text-[rgba(20,184,166,0.95)] hover:shadow-[0_0_6px_rgba(20,184,166,0.35)]"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
          <text x="6" y="9" textAnchor="middle" fontSize="7.5" fill="currentColor" fontWeight="600">i</text>
        </svg>
      </button>
      {open ? (
        <div
          role="tooltip"
          className="absolute left-0 top-7 z-20 w-64 max-w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-left text-xs leading-relaxed text-[var(--text-secondary)] shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
        >
          {text}
        </div>
      ) : null}
    </div>
  );
}
