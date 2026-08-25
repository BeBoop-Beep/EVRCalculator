"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function PublicRipTierInfo() {
  const thresholds = [["S", "≥ 9.6"], ["A", "≥ 9.0"], ["B", "≥ 8.0"], ["C", "≥ 7.0"], ["D", "≥ 5.5"], ["F", "< 5.5"]];
  return (
    <div>
      <p>Tier grades the leader-curved Overall RIP score.</p>
      <ul className="mt-1 list-disc space-y-0 pl-4 tabular-nums">
        {thresholds.map(([tier, threshold]) => <li key={tier}><strong>{tier}</strong> {threshold}</li>)}
      </ul>
    </div>
  );
}

export default function InfoPopover({ text, children = null, learnMoreHref = null, learnMoreLabel = "Learn more" }) {
  const [open, setOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ top: 36, left: 16, mobile: true });
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);

  useEffect(() => {
    if (!open || typeof window === "undefined") {
      return undefined;
    }

    const updatePopoverPosition = () => {
      const triggerRect = triggerRef.current?.getBoundingClientRect();
      if (!triggerRect) {
        return;
      }

      const mobile = window.innerWidth < 640;
      const viewportPadding = 16;
      const desktopWidth = 256;
      const top = Math.round(triggerRect.bottom + 8);

      if (mobile) {
        setPopoverPosition({ top, left: Math.round(window.innerWidth / 2), mobile: true });
        return;
      }

      const preferredLeft = triggerRect.left;
      const maxLeft = Math.max(viewportPadding, window.innerWidth - desktopWidth - viewportPadding);
      const left = Math.round(Math.min(Math.max(preferredLeft, viewportPadding), maxLeft));
      setPopoverPosition({ top, left, mobile: false });
    };

    const closePopover = () => setOpen(false);
    const handlePointerDown = (event) => {
      if (!triggerRef.current?.contains(event.target) && !popoverRef.current?.contains(event.target)) closePopover();
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        closePopover();
        triggerRef.current?.focus();
      }
    };

    updatePopoverPosition();
    window.addEventListener("resize", closePopover);
    window.addEventListener("scroll", closePopover, true);
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("resize", closePopover);
      window.removeEventListener("scroll", closePopover, true);
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const popover = open ? (
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="Metric information"
      className="fixed z-[70] w-[min(22rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 text-left text-xs leading-relaxed text-[var(--text-secondary)] shadow-[0_8px_32px_rgba(0,0,0,0.45)] sm:w-64 sm:max-w-[min(20rem,calc(100vw-2rem))]"
      style={
        popoverPosition.mobile
          ? {
              top: `${popoverPosition.top}px`,
              left: `${popoverPosition.left}px`,
              transform: "translateX(-50%)",
            }
          : {
              top: `${popoverPosition.top}px`,
              left: `${popoverPosition.left}px`,
            }
      }
    >
      {children ?? <p>{text}</p>}
      {learnMoreHref ? (
        <a href={learnMoreHref} className="mt-2 inline-flex rounded font-semibold text-[var(--accent)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
          {learnMoreLabel} <span aria-hidden="true">→</span>
        </a>
      ) : null}
    </div>
  ) : null;

  return (
    <div className="relative flex-none">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More info"
        aria-expanded={open}
        aria-haspopup="dialog"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] transition-all hover:border-[rgba(20,184,166,0.6)] hover:text-[rgba(20,184,166,0.95)] hover:shadow-[0_0_6px_rgba(20,184,166,0.35)]"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
          <text x="6" y="9" textAnchor="middle" fontSize="7.5" fill="currentColor" fontWeight="600">i</text>
        </svg>
      </button>
      {open && typeof document !== "undefined" ? createPortal(popover, document.body) : null}
    </div>
  );
}
