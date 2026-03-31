"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function PublicProfileTabs({ items, profileBaseHref }) {
  const pathname = usePathname();

  const tabs = items || [
    { label: "Overview", href: profileBaseHref, exact: true },
    { label: "Collection", href: `${profileBaseHref}/collection` },
    { label: "Binder", href: `${profileBaseHref}/binder` },
    { label: "Shelf", href: `${profileBaseHref}/shelf` },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  return (
    <nav aria-label="Public profile sections" className="dashboard-panel rounded-2xl p-3">
      {/* Mobile: 2-row grid (3 tabs per row) | Desktop: single-row horizontal nav */}
      <div className="grid grid-cols-3 gap-2 lg:flex lg:w-full lg:overflow-x-auto lg:overflow-hidden">
        {tabs.map((item) => {
          const isActive = item.exact
            ? pathname === item.href
            : pathname === item.href || pathname?.startsWith(`${item.href}/`);

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={[
                "inline-flex flex-none items-center justify-center rounded-lg border px-3 py-2.5 text-sm font-semibold transition-all duration-200 whitespace-nowrap",
                isActive
                  ? "border-[var(--border-prominent)] bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-sm"
                  : "border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--border-prominent)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-page)]",
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
