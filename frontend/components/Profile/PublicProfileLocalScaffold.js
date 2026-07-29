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

// Correction 1: the Set Overview contract puts desktop at 1200px, but Tailwind's
// `xl` is 1280px. Moving the whole scaffold would retune My Collection and the
// public profile layouts, and leaving it alone would produce a mixed band from
// 1200-1279px where the set page's inner content is desktop while this shell is
// still mobile. So both recipes are written out in full and selected by prop.
//   `xl`   - 1280px, the historical behaviour. Default for every consumer.
//   `desk` - 1200px, opted into by RipStatisticsPageClient in setDetailMode.
// Nothing here concatenates a variant prefix; Tailwind only emits classes it can
// find as literal strings, so every string below is statically discoverable.
const SCAFFOLD_BREAKPOINTS = {
  xl: {
    rootGrid: "xl:grid xl:grid-cols-[260px_minmax(0,1fr)] xl:items-start",
    rootFlat: "relative xl:block",
    asideBase: "hidden xl:block",
    asideAbsolute: "xl:absolute xl:inset-y-0 xl:left-0 xl:w-[260px] xl:min-w-[260px] xl:pl-6 xl:pr-4",
    asideStatic: "xl:self-stretch xl:w-[260px] xl:min-w-[260px] xl:pl-6 xl:pr-4",
    desktopHeader: "mb-6 hidden xl:block",
    toolsTrigger: "hidden lg:flex xl:hidden items-center mb-3",
    bottomNavHidden: "xl:hidden",
    toolsPanelHidden: "xl:hidden",
    // Padding is longhand (px/py, not p-*) so it reliably beats the base
    // sm:px-6. overflow-x-clip, not -hidden: `hidden` computes overflow-y:auto,
    // which makes this a scroll container and breaks position:sticky for the
    // set-level tabs inside it.
    contentFramed:
      "min-w-0 overflow-x-clip px-4 pt-3 tab:px-6 xl:overflow-x-visible xl:rounded-3xl xl:border xl:border-[var(--border-subtle)] xl:bg-[var(--surface-page)]/70 xl:px-4 xl:py-4 2xl:px-5 2xl:py-5",
    contentFlat: "min-w-0 overflow-x-clip px-4 pt-3 tab:px-6 xl:overflow-x-visible xl:px-0 xl:pt-0",
    // `max-*` variants are emitted before `sm:`/`lg:` in the stylesheet, so a
    // `max-desk:space-y-0` here would lose to `sm:space-y-6` from 640px up.
    // Each recipe therefore states its own spacing at its own boundary.
    rootSpacing: "space-y-5 sm:space-y-6",
  },
  desk: {
    rootGrid: "desk:grid desk:grid-cols-[260px_minmax(0,1fr)] desk:items-start",
    rootFlat: "relative desk:block",
    asideBase: "hidden desk:block",
    asideAbsolute: "desk:absolute desk:inset-y-0 desk:left-0 desk:w-[260px] desk:min-w-[260px] desk:pl-6 desk:pr-4",
    asideStatic: "desk:self-stretch desk:w-[260px] desk:min-w-[260px] desk:pl-6 desk:pr-4",
    desktopHeader: "mb-6 hidden desk:block",
    toolsTrigger: "hidden lg:flex desk:hidden items-center mb-3",
    bottomNavHidden: "desk:hidden",
    toolsPanelHidden: "desk:hidden",
    contentFramed:
      "min-w-0 overflow-x-clip px-4 pt-3 tab:px-6 desk:overflow-x-visible desk:rounded-3xl desk:border desk:border-[var(--border-subtle)] desk:bg-[var(--surface-page)]/70 desk:px-4 desk:py-4 2xl:px-5 2xl:py-5",
    contentFlat: "min-w-0 overflow-x-clip px-4 pt-3 tab:px-6 desk:overflow-x-visible desk:px-0 desk:pt-0",
    // No stacked gap below desktop — the set page owns its own section rhythm.
    rootSpacing: "space-y-0 desk:space-y-6",
  },
};

export default function PublicProfileLocalScaffold({
  profileBaseHref,
  desktopHeader = null,
  children,
  mode = "public",
  sectionItems: sectionItemsOverride = null,
  mobileNavItems: mobileNavItemsOverride = null,
  desktopSidebarContent = null,
  mobileToolsPanelContent = null,
  mobileToolsTitle = "Collection tools",
  mobileToolsDescription = null,
  mobileToolsPanelAriaLabel = "Tools panel",
  mobileToolsTriggerLabel = "Open tools",
  mobileToolsTriggerTitle = "Open tools",
  hideBottomNav = false,
  desktopContentOffsetClassName = "xl:flex xl:justify-center xl:transform xl:-translate-x-[130px]",
  wrapDesktopContentInFrame = true,
  centerContentIgnoringSidebar = false,
  useFloatingToolsOnTablet = false,
  desktopSidebarClassName = "",
  floatingToolsContainerClassName = null,
  forceCompactToolsBelow2xl = false,
  contentShellClassName = "lg:w-full lg:max-w-7xl lg:px-6",
  mobileBottomNavContent = null,
  mobileBottomNavVariant = "card",
  hideDesktopSidebar = false,
  desktopBreakpoint = "xl",
}) {
  const breakpoint = SCAFFOLD_BREAKPOINTS[desktopBreakpoint] || SCAFFOLD_BREAKPOINTS.xl;
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mobileToolsPanelId = "public-profile-mobile-tools-panel";
  const [isToolsOpen, setIsToolsOpen] = useState(false);
  const [desktopFiltersOpen, setDesktopFiltersOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const sectionItems = sectionItemsOverride || [
    { label: "Collection", href: `${profileBaseHref}/collection`, exact: true },
    { label: "Performance", href: `${profileBaseHref}/performance` },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  const collectionHref = `${profileBaseHref}/collection`;

  const mobileNavItems = mobileNavItemsOverride || [
    {
      label: "Collection",
      href: `${profileBaseHref}/collection`,
      exact: true,
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="4.25" y="4" width="10.5" height="14" rx="2" />
          <rect x="9.25" y="6" width="10.5" height="14" rx="2" />
        </svg>
      ),
    },
    {
      label: "Performance",
      href: `${profileBaseHref}/performance`,
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 18.25h15" />
          <path d="M7.5 16v-2.8" />
          <path d="M11.5 16v-5.1" />
          <path d="M15.5 16v-7.3" />
          <path d="M6.9 10.6 10.8 8l3.2 1.9 3.4-3.9" />
          <path d="M15.7 6h2.8v2.8" />
        </svg>
      ),
    },
    {
      label: "Wishlist",
      href: `${profileBaseHref}/wishlist`,
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 19.3s-6-3.6-7.9-6.9a4.7 4.7 0 0 1 7.9-4.8 4.7 4.7 0 0 1 7.9 4.8c-1.9 3.3-7.9 6.9-7.9 6.9Z" />
        </svg>
      ),
    },
    {
      label: "Activity",
      href: `${profileBaseHref}/activity`,
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3.75 12h3.5l2.1-4.1 4.2 8.2 2.2-4.1h4.5" />
          <circle cx="13.55" cy="16.1" r="0.85" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
  ];

  const isSectionActive = (item) =>
    item.exact
      ? pathname === item.href
      : pathname === item.href || pathname?.startsWith(`${item.href}/`);

  // Resolve first, then decide. A render function that returns null (the set
  // page does exactly this) used to still get an empty page-sticky-bar wrapper
  // with mb-2 px-3 py-2, which is the blank band under the global header.
  const resolvedBottomNavContent = mobileBottomNavContent
    ? (typeof mobileBottomNavContent === "function" ? mobileBottomNavContent() : mobileBottomNavContent)
    : null;
  const hasResolvedBottomNavContent =
    resolvedBottomNavContent !== null &&
    resolvedBottomNavContent !== undefined &&
    resolvedBottomNavContent !== false;
  const shouldRenderBottomNav =
    !hideBottomNav && (hasResolvedBottomNavContent || (!mobileBottomNavContent && mobileNavItems.length > 0));

  const isCollectionSection = pathname === collectionHref || pathname?.startsWith(`${collectionHref}/`);
  const hasCustomSidebar = desktopSidebarContent !== null;
  const hasCustomToolsPanel = mobileToolsPanelContent !== null;
  const isToolsFeatureEnabled = isCollectionSection || hasCustomToolsPanel;
  const desktopSidebarVisibilityClass = forceCompactToolsBelow2xl
    ? "xl:!hidden 2xl:!block"
    : desktopSidebarClassName;
  const mobileToolsPanelVisibilityClass = forceCompactToolsBelow2xl ? "2xl:hidden" : breakpoint.toolsPanelHidden;
  const floatingToolsContainerClass = floatingToolsContainerClassName
    || (forceCompactToolsBelow2xl
      ? "2xl:hidden"
      : (useFloatingToolsOnTablet ? breakpoint.bottomNavHidden : "lg:hidden"));
  const mobileBottomNavClassName = mobileBottomNavVariant === "flat"
    ? `${breakpoint.bottomNavHidden} page-sticky-bar z-30 mb-2 w-full max-w-full overflow-x-auto bg-[var(--surface-page)]/92 px-3 py-2 backdrop-blur sm:px-6 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`
    : `${breakpoint.bottomNavHidden} page-sticky-bar z-30 mx-3 mb-2 overflow-x-auto max-w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/92 px-2 py-2 backdrop-blur sm:mx-6 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`;

  // One mount, two presentations. Responsive presentation now comes from this
  // one wrapper's classes instead of from two hidden copies of the tree.
  const contentWrapperClassName = wrapDesktopContentInFrame
    ? breakpoint.contentFramed
    : breakpoint.contentFlat;

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
    if (!isCollectionSection && !hasCustomToolsPanel && isToolsOpen) {
      setIsToolsOpen(false);
    }
  }, [hasCustomToolsPanel, isCollectionSection, isToolsOpen]);

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

  const handleOpenCollectionTools = () => {
    // The button only renders when a panel exists (isToolsFeatureEnabled), so
    // there is nothing left to fall through to. The old else-branch pushed the
    // user to `${collectionHref}?tools=1`, which on the set page navigated them
    // off the page they were reading.
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
            Search this collection
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
          className="w-full rounded-lg border border-brand bg-brand px-3 py-2 text-left text-xs font-medium text-white transition-colors hover:border-brand-dark hover:bg-brand-dark"
          aria-expanded={isFilterPanelOpen}
        >
          {isFilterPanelOpen ? "Hide filters for this collection" : "Filter this collection"}
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
    <div className={breakpoint.rootSpacing}>
      <div className={hideDesktopSidebar || centerContentIgnoringSidebar ? breakpoint.rootFlat : breakpoint.rootGrid}>
        {!hideDesktopSidebar ? <aside
          className={centerContentIgnoringSidebar
            ? `${breakpoint.asideBase} ${breakpoint.asideAbsolute} ${desktopSidebarVisibilityClass}`
            : `${breakpoint.asideBase} ${breakpoint.asideStatic} ${desktopSidebarVisibilityClass}`}
        >
          {hasCustomSidebar ? (
            <div className="sticky top-[calc(var(--app-header-offset,4rem)+2rem)]">{desktopSidebarContent}</div>
          ) : (
            <div className="sticky top-[calc(var(--app-header-offset,4rem)+2rem)] space-y-4">
              <nav aria-label={mode === "owner" ? "Owner collection sections" : "Public profile sections"} className="px-1">
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
                <section className="px-1 pt-2">
                  {renderCollectionTools("desktop")}
                </section>
              ) : null}
            </div>
          )}
        </aside> : null}

        <div className={`min-w-0 pb-4 lg:pb-0 ${desktopContentOffsetClassName}`}>
          <div className={contentShellClassName}>
            {isToolsFeatureEnabled && !useFloatingToolsOnTablet ? (
              <div className={breakpoint.toolsTrigger}>
                <button
                  type="button"
                  onClick={() => setIsToolsOpen((open) => !open)}
                  aria-expanded={isToolsOpen}
                  aria-controls={mobileToolsPanelId}
                  className="inline-flex items-center gap-2.5 rounded-xl border border-brand bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:border-brand-dark hover:bg-brand-dark"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 7h16" />
                    <path d="M7 12h10" />
                    <path d="M10 17h4" />
                  </svg>
                  {mobileToolsTriggerLabel}
                </button>
              </div>
            ) : null}
            {shouldRenderBottomNav ? (
              <nav
                aria-label={mode === "owner" ? "Owner collection section navigation" : "Profile section navigation"}
                className={mobileBottomNavClassName}
              >
                {hasResolvedBottomNavContent ? (
                  resolvedBottomNavContent
                ) : (
                  <div className="flex min-w-max gap-2 pr-1">
                    {mobileNavItems.map((item) => {
                      const isActive = isSectionActive(item);

                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-label={`Open ${item.label} section`}
                          aria-current={isActive ? "page" : undefined}
                          className={[
                            "inline-flex flex-none min-w-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors duration-150 ease-out",
                            isActive
                              ? "border-[var(--accent)] bg-[color:color-mix(in_srgb,var(--accent)_12%,transparent)] text-[var(--accent)]"
                              : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                          ].join(" ")}
                        >
                          <span className="max-[380px]:hidden">{item.icon}</span>
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </nav>
            ) : null}
            {/* The header sits inside the wrapper so the framed consumers
                (/u/[username]) keep it within the bordered desktop frame, where
                it has always been. It carries its own desktop-only visibility
                now that the wrapper itself is no longer desktop-only. */}
            <div className={contentWrapperClassName}>
              {desktopHeader ? <div className={breakpoint.desktopHeader}>{desktopHeader}</div> : null}
              {children}
            </div>
          </div>
        </div>
      </div>

      {isToolsFeatureEnabled && isToolsOpen ? (
        <div
          id={mobileToolsPanelId}
          role="region"
          aria-label={mobileToolsPanelAriaLabel}
          className={`${mobileToolsPanelVisibilityClass} fixed inset-x-4 bottom-[calc(5.25rem+env(safe-area-inset-bottom))] lg:bottom-4 z-40 max-h-[min(70vh,28rem)] overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 shadow-lg`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{mobileToolsTitle}</p>
              {mobileToolsDescription ? (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{mobileToolsDescription}</p>
              ) : isCollectionSection ? (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {mode === "owner"
                    ? "Search and filter your collection with owner tools."
                    : "Search and filter this collection for this public profile only."}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => setIsToolsOpen(false)}
              className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)]"
              aria-label="Close tools panel"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
            {hasCustomToolsPanel
              ? typeof mobileToolsPanelContent === "function"
                ? mobileToolsPanelContent({ closeToolsPanel: () => setIsToolsOpen(false) })
                : mobileToolsPanelContent
              : renderCollectionTools("mobile")}
          </div>
        </div>
      ) : null}

      {/* The floating trigger only makes sense where a tools panel exists. On the
          set page there is none, so it used to render an inert green circle that
          navigated the user away and sat in the focus order for nothing. */}
      {isToolsFeatureEnabled ? (
      <div className={floatingToolsContainerClass}>
        <button
          type="button"
          onClick={handleOpenCollectionTools}
          aria-label={mobileToolsTriggerLabel}
          title={mobileToolsTriggerTitle}
          aria-controls={mobileToolsPanelId}
          aria-expanded={isToolsFeatureEnabled && isToolsOpen}
          className="fixed right-4 z-40 inline-flex h-14 min-h-[56px] w-14 min-w-[56px] items-center justify-center rounded-full border border-brand bg-brand text-white shadow-[0_14px_28px_rgba(0,0,0,0.42)] backdrop-blur transition hover:border-brand-dark hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          style={{ bottom: "calc(6rem + env(safe-area-inset-bottom))" }}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M4 7h16" />
            <path d="M7 12h10" />
            <path d="M10 17h4" />
          </svg>
        </button>

      </div>
      ) : null}
    </div>
  );
}
