"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function RouteTabsNav({ items, ariaLabel }) {
  const pathname = usePathname();

  return (
    <nav aria-label={ariaLabel} className="mt-4">
      <div className="flex flex-wrap gap-2">
        {items.map((item) => {
          const exact = item.exact === true;
          const isActive = exact
            ? pathname === item.href
            : pathname === item.href || pathname?.startsWith(item.href + "/");

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={[
                "inline-flex items-center rounded-xl border px-4 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-[var(--border-subtle)] bg-[var(--surface-hover)] text-[var(--text-primary)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
