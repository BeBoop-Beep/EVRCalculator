"use client";

export function ExplorerSelectionCheck({ selected, disabled = false }) {
  return (
    <span aria-hidden="true" data-explorer-selection-check={selected ? "selected" : "unselected"} className={["flex h-4 w-4 flex-none items-center justify-center rounded-[4px] border transition-colors", selected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.18)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] bg-[var(--surface-page)]/60 text-transparent", disabled ? "opacity-40" : ""].join(" ")}>
      <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 6.4 4.6 9 10 3.2" /></svg>
    </span>
  );
}

export function explorerSelectableRowClassName({ selected, available = true, disabled = false }) {
  return [
    "group flex min-h-9 min-w-0 items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] focus-within:outline-none focus-within:ring-2 focus-within:ring-[rgba(45,212,191,0.65)]",
    selected ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(45,212,191,0.15)]" : available ? "border-transparent bg-[var(--surface-page)]/30 text-[var(--text-primary)] hover:border-[rgba(45,212,191,0.38)] hover:bg-[rgba(45,212,191,0.06)]" : "border-transparent bg-[var(--surface-page)]/20 text-[var(--text-secondary)]",
    disabled ? "cursor-default" : "cursor-pointer",
  ].join(" ");
}

export default function ExplorerSelectableRow({ selected = false, locked = false, onClick, children, className = "", ...props }) {
  return (
    <button type="button" aria-pressed={selected} onClick={onClick} className={`${explorerSelectableRowClassName({ selected, available: !locked, disabled: locked })} ${className}`} {...props}>
      <ExplorerSelectionCheck selected={selected} disabled={locked} />
      <span className="min-w-0 flex-1">{children}</span>
    </button>
  );
}
