"use client";

import { useEffect } from "react";

/**
 * Minimal confirmation dialog for destructive or irreversible actions.
 *
 * Props:
 *  isOpen        {boolean}  – controls visibility
 *  title         {string}   – short heading line
 *  body          {string}   – secondary detail line (optional)
 *  confirmLabel  {string}   – confirm button text (default "Confirm")
 *  cancelLabel   {string}   – cancel button text  (default "Cancel")
 *  onConfirm     {function} – called when confirm is clicked
 *  onCancel      {function} – called when cancel is clicked or backdrop pressed
 */
export default function ConfirmModal({
  isOpen,
  title = "Are you sure?",
  body = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}) {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKey = (e) => {
      if (e.key === "Escape") onCancel?.();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel?.();
      }}
      role="presentation"
    >
      {/* Dialog */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="w-full max-w-sm rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6 shadow-2xl"
      >
        <h2
          id="confirm-modal-title"
          className="text-sm font-semibold text-[var(--text-primary)]"
        >
          {title}
        </h2>

        {body ? (
          <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{body}</p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          {/* Cancel — default focus */}
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            {cancelLabel}
          </button>

          {/* Confirm — understated, not alarmingly red */}
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-red-500/40 hover:text-red-400"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
