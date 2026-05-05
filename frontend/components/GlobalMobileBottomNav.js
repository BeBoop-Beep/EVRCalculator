"use client";

import Link from "next/link";
import { useMemo } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthContext";

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

  if (id === "home") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3.75 10.25 12 4l8.25 6.25" />
        <path d="M6.5 9.8V20h11V9.8" />
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

  if (id === "tools") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-5 w-5 ${activeClass}`} fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3.75v3" />
        <path d="M12 17.25v3" />
        <path d="M4.93 6.43 7.05 8.55" />
        <path d="M16.95 18.45 19.07 20.57" />
        <path d="M3.75 12h3" />
        <path d="M17.25 12h3" />
        <path d="M4.93 20.57 7.05 18.45" />
        <path d="M16.95 8.55 19.07 6.43" />
        <circle cx="12" cy="12" r="3.25" />
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
        id: "home",
        label: "Home",
        href: "/",
        isActive: normalizedPathname === "/",
      },
      {
        id: "explore",
        label: "Explore",
        href: "/Explore",
        isActive: isPathMatch(normalizedPathname, ["/Explore", "/explore"], { caseInsensitive: true }),
      },
      {
        id: "portfolio",
        label: "Portfolio",
        href: "/my-collection/collection",
        isActive: isPathMatch(normalizedPathname, ["/my-collection", "/my-portfolio", "/portfolio"], { caseInsensitive: true }),
      },
      {
        id: "tools",
        label: "Tools",
        href: "/tools",
        isActive: isPathMatch(normalizedPathname, ["/tools"], { caseInsensitive: true }),
      },
      {
        id: "profile",
        label: "Profile",
        href: profileHref,
        isActive: isPathMatch(normalizedPathname, ["/profile", "/u"], { caseInsensitive: true }),
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
      <div className="mx-auto grid max-w-xl grid-cols-5 gap-1 px-3 pt-2">
        {items.map((item) => (
          <Link
            key={item.id}
            href={item.href}
            aria-label={`Open ${item.label}`}
            aria-current={item.isActive ? "page" : undefined}
            className={[
              "flex flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 text-[11px] font-medium transition-colors duration-150 ease-out",
              item.isActive
                ? "text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span className={["transition-transform duration-150 ease-out", item.isActive ? "scale-110" : "scale-100"].join(" ")}>
              {navItemIcon(item.id, item.isActive)}
            </span>
            <span>{item.label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}
