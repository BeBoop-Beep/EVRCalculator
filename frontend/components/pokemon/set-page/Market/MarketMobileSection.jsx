"use client";

import React from "react";

// ---------------------------------------------------------------------------
// The one panel every mobile Market section is built from.
//
// The mobile Market tab is a vertical dashboard, not a feed: each module has to
// read as its own elevated surface with a consistent rhythm between them, which
// is exactly what a single shared shell buys. It reuses `.set-glass-surface` —
// the same elevated glass the desktop Market cards sit on — so the two
// compositions belong to one visual system rather than merely resembling each
// other.
//
// The eyebrow/title/action row is fixed here on purpose. Every section states
// its name the same way, at the same size, with its optional "See all" on the
// same baseline, so scanning down the page never costs a re-read.
// ---------------------------------------------------------------------------

export default function MarketMobileSection({
  id,
  title,
  eyebrow = null,
  action = null,
  headerAside = null,
  bodyClassName = "mt-3",
  className = "",
  children,
  ...rest
}) {
  return (
    <section
      id={id}
      data-market-mobile-section
      className={[
        "set-glass-surface relative min-w-0 overflow-visible rounded-2xl border border-[var(--border-subtle)] px-3.5 py-3.5",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-labelledby={id ? `${id}-heading` : undefined}
      {...rest}
    >
      <div className="flex min-w-0 items-start gap-2">
        <div className="min-w-0 flex-1">
          {eyebrow ? (
            <p className="text-[10px] font-bold uppercase leading-none tracking-[0.115em] text-[rgba(199,214,234,0.62)]">
              {eyebrow}
            </p>
          ) : null}
          <h2
            id={id ? `${id}-heading` : undefined}
            className="min-w-0 text-[15px] font-semibold leading-tight tracking-[-0.01em] text-[var(--text-primary)]"
          >
            {title}
          </h2>
        </div>
        {headerAside}
        {action}
      </div>
      <div className={["min-w-0", bodyClassName].filter(Boolean).join(" ")}>{children}</div>
    </section>
  );
}

/** The shared "See all" affordance. Renders nothing without a destination. */
export function MarketMobileSectionLink({ href, label = "See all" }) {
  if (!href) return null;
  return (
    <a
      href={href}
      className="-my-1.5 -mr-1.5 inline-flex min-h-11 flex-none items-center gap-1 rounded-lg px-2 text-[11px] font-semibold text-[rgb(45,212,191)] transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]"
    >
      {label}
      <svg viewBox="0 0 20 20" aria-hidden="true" className="h-3.5 w-3.5">
        <path
          d="m7.5 4.5 5 5-5 5"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </a>
  );
}
