"use client";

import Link from "next/link";
import { useMemo } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthContext";
import { TCGS_NAV_HREF } from "@/lib/navigation/tcgsNav.mjs";

function getCleanText(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function normalizePath(value) {
  if (typeof value !== "string" || value.length === 0) {
    return "/";
  }

  const [pathOnly] = value.split("?");
  const withoutTrailingSlash = pathOnly.replace(/\/+$/, "");
  return withoutTrailingSlash || "/";
}

function isPathMatch(pathname, targets, { caseInsensitive = false } = {}) {
  if (!pathname) return false;

  const normalizedPathname = normalizePath(pathname);
  const source = caseInsensitive ? normalizedPathname.toLowerCase() : normalizedPathname;

  return targets.some((targetPath) => {
    const normalizedTarget = normalizePath(targetPath);
    const target = caseInsensitive ? normalizedTarget.toLowerCase() : normalizedTarget;

    return source === target || source.startsWith(`${target}/`);
  });
}

function navItemIcon(id, isActive) {
  const activeClass = isActive ? "text-[var(--accent)]" : "text-current";

  if (id === "market") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 18.5 9 13l3.5 3 7.5-9" />
        <path d="M15.5 7H20v4.5" />
      </svg>
    );
  }

  if (id === "articles") {
    // The open-book glyph carried over unchanged from the destination this
    // slot used to hold: same 24x24 grid, same h-5 w-5 box, same 1.85 stroke
    // and round caps/joins as every other icon here. Only the destination
    // changed, so the visual language must not.
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 5.5A3.5 3.5 0 0 1 8 2h4v17H8a3.5 3.5 0 0 0-3.5 3Z" />
        <path d="M19.5 5.5A3.5 3.5 0 0 0 16 2h-4v17h4a3.5 3.5 0 0 1 3.5 3Z" />
      </svg>
    );
  }

  if (id === "explore") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="7.75" />
        <path d="m9 15 1.85-5.55L16.4 7.6l-1.85 5.55Z" />
      </svg>
    );
  }

  if (id === "portfolio") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 7h15" />
        <path d="M7.5 12h9" />
        <path d="M10.5 17h3" />
        <rect x="3.75" y="4" width="16.5" height="16" rx="2.5" />
      </svg>
    );
  }

  if (id === "tcgs") {
    // Two offset card outlines. Same 24x24 grid, same h-5 w-5 box, same 1.85
    // stroke weight and round caps/joins as every other icon here - the recipe
    // is frozen, only the destination changed.
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3.25" y="6.5" width="11" height="14.5" rx="2" />
        <path d="M8.4 4.1 17.9 3l1.6 13.4" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 19.25c.9-3.2 3.2-4.75 7-4.75s6.1 1.55 7 4.75" />
    </svg>
  );
}

export default function GlobalMobileBottomNav() {
  const pathname = usePathname();
  const { user } = useAuth();
  const accountUsername = getCleanText(user?.username);
  const profileHref = accountUsername ? `/u/${encodeURIComponent(accountUsername)}/collection` : "/profile";
  const normalizedPathname = useMemo(() => normalizePath(pathname), [pathname]);

  const shouldHide = useMemo(() => {
    const hiddenPrefixes = ["/signup", "/checkout"];
    return isPathMatch(normalizedPathname, hiddenPrefixes);
  }, [normalizedPathname]);

  const items = useMemo(
    () => [
      {
        id: "explore",
        label: "Rankings",
        href: "/Rankings",
        isActive: isPathMatch(normalizedPathname, ["/Rankings", "/Explore"], { caseInsensitive: true }),
      },
      {
        id: "market",
        label: "Market",
        href: "/Market",
        isActive: isPathMatch(normalizedPathname, ["/Market"], { caseInsensitive: true }),
      },
      {
        id: "tcgs",
        label: "TCGs",
        href: TCGS_NAV_HREF,
        isActive: isPathMatch(normalizedPathname, ["/TCGs"], { caseInsensitive: true }),
      },
      {
        id: "articles",
        label: "Articles",
        href: "/Articles",
        isActive: isPathMatch(normalizedPathname, ["/Articles"], { caseInsensitive: true }),
      },
      {
        id: "portfolio",
        label: "Portfolio",
        href: "/my-collection/collection",
        isActive: isPathMatch(normalizedPathname, ["/my-collection", "/my-portfolio", "/portfolio"], { caseInsensitive: true }),
      },
      {
        id: "profile",
        label: "Profile",
        href: profileHref,
        isActive: isPathMatch(normalizedPathname, ["/profile", "/u", "/account-settings"], { caseInsensitive: true }),
      },
    ],
    [normalizedPathname, profileHref]
  );

  if (shouldHide) {
    return null;
  }

  return (
    <nav
      aria-label="Global navigation"
      className="fixed inset-x-0 bottom-0 z-[60] border-t border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 backdrop-blur lg:hidden"
      style={{ paddingBottom: "max(0.6rem, env(safe-area-inset-bottom))" }}
    >
      <div className="mx-auto grid max-w-xl grid-cols-6 gap-0.5 px-1.5 pt-2">
        {items.map((item) => (
          <Link
            key={item.id}
            href={item.href}
            aria-label={`Open ${item.label}`}
            aria-current={item.isActive ? "page" : undefined}
            className={[
              "flex min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-0.5 py-2 text-[10px] font-medium transition-colors duration-150 ease-out",
              item.isActive
                ? "text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span className={["transition-transform duration-150 ease-out", item.isActive ? "scale-110" : "scale-100"].join(" ")}>
              {navItemIcon(item.id, item.isActive)}
            </span>
            <span className="whitespace-nowrap">{item.label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}
