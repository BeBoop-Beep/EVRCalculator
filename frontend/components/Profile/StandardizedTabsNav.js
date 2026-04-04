"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function StandardizedTabsNav({
  items = [],
  ariaLabel,
  className = "",
} = {}) {
  const pathname = usePathname();

  return (
    <nav aria-label={ariaLabel} className={[
      "rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-2",
      "flex flex-wrap gap-2",
      className,
    ].filter(Boolean).join(" ")}>
      {items.map((item) => {
        const exact = item.exact === true;
        const isActive = exact
          ? pathname === item.href
          : pathname === item.href || pathname?.startsWith(`${item.href}/`);

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={[
              "inline-flex items-center justify-center rounded-lg border px-4 py-2 text-sm font-medium transition-colors whitespace-nowrap",
              isActive
                ? "border border-[var(--accent)] bg-[var(--surface-elevated)] text-[var(--accent)]"
                : "border border-transparent bg-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
            ].join(" ")}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
