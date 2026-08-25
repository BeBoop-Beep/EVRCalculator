"use client";

import { useEffect, useId, useRef, useState } from "react";

export default function DarkSelect({ ariaLabel, value, onChange, options = [], className = "", triggerVariant = "default", eyebrow = null, triggerIcon = null }) {
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
        data-trigger-variant={triggerVariant}
        className={`flex items-center justify-between gap-2 rounded-lg text-left text-xs text-[var(--text-primary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)] ${triggerVariant === "budget" ? "min-h-14 w-full border border-[rgba(45,212,191,0.38)] bg-[linear-gradient(135deg,rgba(45,212,191,0.12),rgba(15,23,42,0.72))] px-3 py-1.5 shadow-[inset_0_0_18px_rgba(45,212,191,0.05)] hover:border-[rgba(45,212,191,0.62)]" : triggerVariant === "sort" ? "h-11 w-11 flex-none justify-center border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0 hover:border-[rgba(45,212,191,0.40)]" : "min-h-11 w-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 hover:border-[rgba(45,212,191,0.40)] desk:min-h-0 desk:py-1.5"}`}
      >
        {triggerVariant === "sort" ? <span aria-hidden="true" className="text-lg leading-none">{triggerIcon || "⇅"}</span> : <span className="min-w-0"><span className="block truncate">{eyebrow ? <span className="block text-[9px] font-bold uppercase tracking-[0.14em] text-[rgb(94,234,212)]">{eyebrow}</span> : null}{selected?.label || "Select"}</span></span>}
        {triggerVariant !== "sort" ? <span aria-hidden="true" className={`text-[var(--text-secondary)] transition-transform ${open ? "rotate-180" : ""}`}>⌄</span> : null}
      </button>
      {open ? (
        <ul id={listboxId} role="listbox" aria-label={ariaLabel} className={`set-dropdown-glass absolute top-full z-[1200] mt-1 max-h-72 overflow-y-auto rounded-lg py-1 text-xs shadow-xl ${triggerVariant === "sort" ? "right-0 min-w-56" : "left-0 min-w-full"}`}>
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
