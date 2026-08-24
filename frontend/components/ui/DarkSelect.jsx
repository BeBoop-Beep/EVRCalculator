"use client";

import { useEffect, useId, useRef, useState } from "react";

export default function DarkSelect({ ariaLabel, value, onChange, options = [], className = "" }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const optionRefs = useRef([]);
  const listboxId = useId();
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const selected = options[selectedIndex];

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  useEffect(() => {
    if (open) optionRefs.current[selectedIndex]?.focus();
  }, [open, selectedIndex]);

  const choose = (nextValue) => {
    onChange?.(nextValue);
    setOpen(false);
    const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => callback();
    schedule(() => triggerRef.current?.focus());
  };

  const move = (event, index) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(options[index]?.value);
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    optionRefs.current[next]?.focus();
  };

  return (
    <div ref={rootRef} className={`relative min-w-0 flex-1 ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-left text-xs text-[var(--text-primary)] transition-colors hover:border-[rgba(45,212,191,0.40)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] desk:min-h-0 desk:py-1.5"
      >
        <span className="truncate">{selected?.label || "Select"}</span>
        <span aria-hidden="true" className={`text-[var(--text-secondary)] transition-transform ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>
      {open ? (
        <ul id={listboxId} role="listbox" aria-label={ariaLabel} className="set-dropdown-glass absolute left-0 top-full z-[1200] mt-1 max-h-72 min-w-full overflow-y-auto rounded-lg py-1 text-xs shadow-xl">
          {options.map((option, index) => {
            const active = option.value === value;
            return (
              <li
                key={option.value}
                ref={(node) => { optionRefs.current[index] = node; }}
                role="option"
                aria-selected={active}
                tabIndex={index === selectedIndex ? 0 : -1}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => choose(option.value)}
                onKeyDown={(event) => move(event, index)}
                className={`flex cursor-pointer items-center justify-between gap-3 whitespace-nowrap px-3 py-2 outline-none transition-colors hover:bg-[rgba(45,212,191,0.10)] hover:text-[rgb(45,212,191)] focus:bg-[rgba(45,212,191,0.14)] focus:text-[rgb(45,212,191)] ${active ? "bg-[rgba(45,212,191,0.12)] text-[rgb(45,212,191)]" : "text-[var(--text-secondary)]"}`}
              >
                <span>{option.label}</span>
                {active ? <span aria-hidden="true">{"\u2713"}</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
