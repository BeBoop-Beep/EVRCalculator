"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

const COLLECTION_SORT_OPTIONS = [
  { id: "recent", label: "Recently Added" },
  { id: "value-desc", label: "Value (High to Low)" },
  { id: "value-asc", label: "Value (Low to High)" },
  { id: "name-asc", label: "Name (A-Z)" },
  { id: "name-desc", label: "Name (Z-A)" },
];

const COLLECTION_VIEW_OPTIONS = [
  { id: "continuous", label: "Continuous" },
  { id: "binder", label: "Binder" },
];

const COLLECTION_TYPE_OPTIONS = [
  { id: "", label: "All Types" },
  { id: "cards", label: "Cards" },
  { id: "sealed", label: "Sealed" },
  { id: "merchandise", label: "Merchandise" },
];

const COLLECTION_CONDITION_OPTIONS = [
  { id: "", label: "All Conditions" },
  { id: "mint", label: "Mint" },
  { id: "near-mint", label: "Near Mint" },
  { id: "lightly-played", label: "Lightly Played" },
  { id: "moderately-played", label: "Moderately Played" },
  { id: "heavily-played", label: "Heavily Played" },
  { id: "sealed", label: "Sealed" },
];

const COLLECTION_TCG_OPTIONS = [
  { id: "", label: "All TCGs" },
  { id: "Pokemon", label: "Pokemon" },
];

export default function PublicProfileLocalScaffold({ profileBaseHref, children }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isToolsOpen, setIsToolsOpen] = useState(false);
  const [desktopFiltersOpen, setDesktopFiltersOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const sectionItems = [
    { label: "Collection", href: `${profileBaseHref}/collection`, exact: true },
    { label: "Performance", href: `${profileBaseHref}/performance` },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  const collectionHref = `${profileBaseHref}/collection`;

  const mobileNavItems = [
    {
      label: "Collection",
      href: `${profileBaseHref}/collection`,
      exact: true,
      icon: (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 10h18" />
          <path d="M8 14h3" />
        </svg>
      ),
    },
    {
      label: "Performance",
      href: `${profileBaseHref}/performance`,
      icon: (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 18h16" />
          <path d="M6 15l4-4 3 2 5-6" />
        </svg>
      ),
    },
    {
      label: "Wishlist",
      href: `${profileBaseHref}/wishlist`,
      icon: (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 20s-6.5-3.7-8.4-7.4A5 5 0 0 1 12 7a5 5 0 0 1 8.4 5.6C18.5 16.3 12 20 12 20Z" />
        </svg>
      ),
    },
    {
      label: "Activity",
      href: `${profileBaseHref}/activity`,
      icon: (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 12h4l2.5-5 4 10 2.5-5H21" />
        </svg>
      ),
    },
  ];

  const isSectionActive = (item) =>
    item.exact
      ? pathname === item.href
      : pathname === item.href || pathname?.startsWith(`${item.href}/`);

  const isCollectionSection = pathname === collectionHref || pathname?.startsWith(`${collectionHref}/`);

  const localToolState = useMemo(() => ({
    q: searchParams.get("q") || "",
    sort: searchParams.get("sort") || "recent",
    view: searchParams.get("view") || "continuous",
    type: searchParams.get("type") || "",
    condition: searchParams.get("condition") || "",
    tcg: searchParams.get("tcg") || "",
  }), [searchParams]);

  useEffect(() => {
    setSearchDraft(localToolState.q);
  }, [localToolState.q]);

  useEffect(() => {
    if (!isCollectionSection && isToolsOpen) {
      setIsToolsOpen(false);
    }
  }, [isCollectionSection, isToolsOpen]);

  useEffect(() => {
    if (!isCollectionSection) return;
    if (searchParams.get("tools") !== "1") return;

    setIsToolsOpen(true);
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.delete("tools");
    const query = nextParams.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [isCollectionSection, pathname, router, searchParams]);

  const updateCollectionQuery = (updates) => {
    if (!isCollectionSection) return;

    const nextParams = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      const normalized = typeof value === "string" ? value.trim() : value;
      if (!normalized) {
        nextParams.delete(key);
      } else {
        nextParams.set(key, normalized);
      }
    });

    const query = nextParams.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const handleSearchSubmit = (event) => {
    event.preventDefault();
    updateCollectionQuery({ q: searchDraft });
  };

  const handleSearchClear = () => {
    setSearchDraft("");
    updateCollectionQuery({ q: "" });
  };

  const handleToolsClick = () => {
    if (!isCollectionSection) {
      router.push(`${collectionHref}?tools=1`);
      return;
    }

    setIsToolsOpen((open) => !open);
  };

  const renderCollectionTools = (variant = "desktop") => {
    const isDesktop = variant === "desktop";
    const isFilterPanelOpen = isDesktop ? desktopFiltersOpen : mobileFiltersOpen;

    return (
      <div className="space-y-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Collection Tools
        </p>

        <form onSubmit={handleSearchSubmit} className="space-y-2">
          <label htmlFor={`${variant}-collection-search`} className="text-xs font-medium text-[var(--text-primary)]">
            Search
          </label>
          <div className="flex gap-2">
            <input
              id={`${variant}-collection-search`}
              type="search"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search this collection"
              className="min-w-0 flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none ring-0 placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]"
            />
            <button
              type="submit"
              className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              Apply
            </button>
            {localToolState.q ? (
              <button
                type="button"
                onClick={handleSearchClear}
                className="rounded-lg border border-[var(--border-subtle)] px-2 py-2 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                aria-label="Clear collection search"
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>

        <div className="space-y-2">
          <label htmlFor={`${variant}-collection-view`} className="text-xs font-medium text-[var(--text-primary)]">
            View
          </label>
          <select
            id={`${variant}-collection-view`}
            value={localToolState.view}
            onChange={(event) => updateCollectionQuery({ view: event.target.value })}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
          >
            {COLLECTION_VIEW_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={() => (isDesktop ? setDesktopFiltersOpen((open) => !open) : setMobileFiltersOpen((open) => !open))}
          className="w-full rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-left text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          aria-expanded={isFilterPanelOpen}
        >
          {isFilterPanelOpen ? "Hide filters" : "Show filters"}
        </button>

        {isFilterPanelOpen ? (
          <div className="space-y-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 p-2.5">
            <label htmlFor={`${variant}-collection-sort`} className="block text-xs font-medium text-[var(--text-primary)]">
              Sort
            </label>
            <select
              id={`${variant}-collection-sort`}
              value={localToolState.sort}
              onChange={(event) => updateCollectionQuery({ sort: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {COLLECTION_SORT_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>

            <label htmlFor={`${variant}-collection-type`} className="mt-2 block text-xs font-medium text-[var(--text-primary)]">
              Type
            </label>
            <select
              id={`${variant}-collection-type`}
              value={localToolState.type}
              onChange={(event) => updateCollectionQuery({ type: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {COLLECTION_TYPE_OPTIONS.map((option) => (
                <option key={option.id || "all-types"} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>

            <label htmlFor={`${variant}-collection-condition`} className="mt-2 block text-xs font-medium text-[var(--text-primary)]">
              Condition
            </label>
            <select
              id={`${variant}-collection-condition`}
              value={localToolState.condition}
              onChange={(event) => updateCollectionQuery({ condition: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {COLLECTION_CONDITION_OPTIONS.map((option) => (
                <option key={option.id || "all-conditions"} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>

            <label htmlFor={`${variant}-collection-tcg`} className="mt-2 block text-xs font-medium text-[var(--text-primary)]">
              TCG
            </label>
            <select
              id={`${variant}-collection-tcg`}
              value={localToolState.tcg}
              onChange={(event) => updateCollectionQuery({ tcg: event.target.value })}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {COLLECTION_TCG_OPTIONS.map((option) => (
                <option key={option.id || "all-tcgs"} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="lg:grid lg:grid-cols-[15.25rem_minmax(0,1fr)] lg:items-start lg:gap-4">
        <aside className="hidden lg:block lg:border-r lg:border-[var(--border-subtle)] lg:pr-4">
          <div className="sticky top-[calc(var(--app-header-offset,4.5rem)+0.75rem)] space-y-4">
            <nav aria-label="Public profile sections" className="px-1">
              <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Sections
              </p>
              <div className="mt-2 space-y-1">
                {sectionItems.map((item) => {
                  const isActive = isSectionActive(item);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={isActive ? "page" : undefined}
                      className={[
                        "flex items-center rounded-xl border px-3 py-2.5 text-sm font-medium transition-colors",
                        isActive
                          ? "border-[var(--accent)] bg-[var(--surface-elevated)] text-[var(--accent)]"
                          : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                      ].join(" ")}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </nav>

            {isCollectionSection ? (
              <section className="border-t border-[var(--border-subtle)] px-1 pt-4">
                {renderCollectionTools("desktop")}
              </section>
            ) : null}
          </div>
        </aside>

        <div className="min-w-0 pb-[calc(6rem+env(safe-area-inset-bottom))] lg:pb-0">{children}</div>
      </div>

      <div className="lg:hidden">
        {isCollectionSection && isToolsOpen ? (
          <div
            role="region"
            aria-label="Collection tools panel"
            className="fixed inset-x-4 bottom-[calc(5.25rem+env(safe-area-inset-bottom))] z-40 max-h-[min(70vh,28rem)] overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 shadow-lg"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">Tools</p>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  Collection tools for this public profile only.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsToolsOpen(false)}
                className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]"
                aria-label="Close tools panel"
              >
                Close
              </button>
            </div>

            <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
              {renderCollectionTools("mobile")}
            </div>
          </div>
        ) : null}

        <nav
          aria-label="Public profile navigation"
          className="fixed inset-x-0 bottom-0 z-50 border-t border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 backdrop-blur"
          style={{ paddingBottom: "max(0.65rem, env(safe-area-inset-bottom))" }}
        >
          <div className="mx-auto grid max-w-xl grid-cols-5 gap-1 px-3 pt-2">
            {mobileNavItems.map((item) => {
              const isActive = isSectionActive(item);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-label={`Open ${item.label} section`}
                  aria-current={isActive ? "page" : undefined}
                  className={[
                    "flex flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 text-[11px] font-medium transition-colors",
                    isActive
                      ? "text-[var(--accent)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                  ].join(" ")}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              );
            })}

            <button
              type="button"
              onClick={handleToolsClick}
              aria-label={isCollectionSection ? "Toggle profile tools panel" : "Open collection tools"}
              aria-expanded={isCollectionSection ? isToolsOpen : undefined}
              title="Collection tools"
              className={[
                "flex flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 text-[11px] font-medium transition-colors",
                isCollectionSection && isToolsOpen
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 3v4" />
                <path d="M12 17v4" />
                <path d="M4.9 4.9l2.8 2.8" />
                <path d="M16.3 16.3l2.8 2.8" />
                <path d="M3 12h4" />
                <path d="M17 12h4" />
                <path d="M4.9 19.1l2.8-2.8" />
                <path d="M16.3 7.7l2.8-2.8" />
              </svg>
              <span>Tools</span>
            </button>
          </div>
        </nav>
      </div>
    </div>
  );
}
