"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useMediaQuery from "@/hooks/useMediaQuery";
import MarketSparkline from "./MarketSparkline";
import MarketWindowSelector from "./MarketWindowSelector";
import MiniMarketSparkline from "./MiniMarketSparkline";
import DarkSelect from "@/components/ui/DarkSelect";
import ReturnToTopButton from "@/components/ui/ReturnToTopButton";
import SetMarketTopMovers from "./SetMarketTopMovers";
import { getStandardDeltaWindowDefinitions, resolveDeltaWindowBaselineValue } from "@/lib/explore/marketDeltaWindows.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { SET_LOGO_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { getPokemonSetValueHistory } from "@/lib/pokemon/pokemonSetMarketClient";
import { clipSetMarketDetailHistory, needsLifetimeSetMarketHistory } from "@/lib/explore/setMarketDetailHistory.mjs";
import { selectSetMarketMiniTrend } from "@/lib/explore/setMarketMiniTrend.mjs";
import styles from "./explore.module.css";

// ---------------------------------------------------------------------------
// Set Market — one master-detail surface.
//
// WHY THIS REPLACED THE SPARKLINE LADDER
// --------------------------------------
// The previous Set Value Rankings drew a full sparkline for every tracked set.
// At the ~30 sets the snapshot carries today that was merely heavy; at the
// 167+ the catalogue is heading for it is a page that mounts 167 interactive
// SVG charts and grows to ten thousand pixels. The scalable shape is the one
// every financial terminal uses: ONE scannable list, ONE chart, and the chart
// follows the selection.
//
// DATA
// ----
// The compact global snapshot remains authoritative for ranking, current Set
// Value and window movements. The one visible detail chart lazily loads the
// selected set's normalized daily value-history and clips it with those same
// canonical window dates. Top movers remains its own per-selection request.
// ---------------------------------------------------------------------------

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
const signedCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", signDisplay: "always", minimumFractionDigits: 2, maximumFractionDigits: 2 });

const WINDOWS = getStandardDeltaWindowDefinitions();
const DEFAULT_WINDOW = "7D";
const ALL_ERAS = "__all__";

const SORT_OPTIONS = [
  { key: "value", label: "Set Value" },
  { key: "change", label: "Change" },
  { key: "name", label: "Set Name" },
];

const windowLabel = (key) => (key === "lifetime" ? "All" : key);

function directionOf(amount) {
  if (!Number.isFinite(amount)) return "neutral";
  return amount > 0 ? "positive" : amount < 0 ? "negative" : "neutral";
}

function toneOf(direction) {
  if (direction === "positive") return POSITIVE_VALUE_COLOR;
  if (direction === "negative") return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

function SetLogo({ target, name, className = "h-8 w-8" }) {
  const [failed, setFailed] = useState(false);
  const src = optimizedImageUrl(String(target?.logoUrl || target?.symbolUrl || "").trim(), SET_LOGO_THUMBNAIL_WIDTH);
  useEffect(() => { setFailed(false); }, [src]);
  if (!src || failed) {
    return (
      <span aria-hidden="true" className={`flex ${className} flex-none items-center justify-center rounded bg-white/5 text-[9px] font-semibold text-[var(--text-secondary)]`}>
        {String(name || "?").slice(0, 2).toUpperCase()}
      </span>
    );
  }
  return <img src={src} alt="" className={`${className} flex-none object-contain`} loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}

/** Signed "▲ +$12.34 (+1.2%)" for a published window movement, or an explicit N/A. */
function ChangeText({ movement, windowKey, className = "" }) {
  const amount = movement?.amount ?? null;
  const percent = movement?.percent ?? null;
  const direction = directionOf(amount);
  if (amount === null || percent === null) {
    return <span className={`tabular-nums ${className}`} style={{ color: "var(--text-secondary)" }}>{`N/A · ${windowLabel(windowKey)}`}</span>;
  }
  const glyph = direction === "positive" ? "▲" : direction === "negative" ? "▼" : "—";
  return (
    <span className={`tabular-nums ${className}`} style={{ color: toneOf(direction) }}>
      {`${glyph} ${signedCurrency.format(amount)} (${percent >= 0 ? "+" : ""}${percent.toFixed(1)}%)`}
    </span>
  );
}

/** Compact "▼11.8%" for the list column, where the dollar move does not fit. */
function ChangePercent({ movement, windowKey }) {
  const amount = movement?.amount ?? null;
  const percent = movement?.percent ?? null;
  if (amount === null || percent === null) {
    return <span className="tabular-nums text-[var(--text-secondary)]">{`N/A · ${windowLabel(windowKey)}`}</span>;
  }
  const direction = directionOf(amount);
  const glyph = direction === "positive" ? "▲" : direction === "negative" ? "▼" : "—";
  return (
    <span className="tabular-nums" style={{ color: toneOf(direction) }}>{`${glyph}${Math.abs(percent).toFixed(1)}%`}</span>
  );
}

/**
 * Rank every priced target by canonical current Set Value — once, and
 * independently of the search/era/sort controls, so "#1" always means "first
 * in the market" rather than "first in whatever you filtered to".
 */
function buildRankedRows(targets) {
  return (Array.isArray(targets) ? targets : [])
    .map((target) => ({ target, value: Number(target?.currentSetValue) }))
    .filter(({ value }) => Number.isFinite(value) && value > 0)
    .sort((a, b) => b.value - a.value || String(a.target?.name || "").localeCompare(String(b.target?.name || "")))
    .map((row, index) => ({
      ...row,
      position: index + 1,
      setId: String(row.target?.setId || ""),
      name: String(row.target?.name || row.target?.setId || "Unknown Set"),
      era: String(row.target?.era || "Pokémon"),
    }));
}

export function resolveSetMarketRowAction({ isMasterDetail, isActive, clickCount }) {
  if (!isMasterDetail) return "navigate";
  return isActive || clickCount >= 2 ? "navigate" : "select";
}

export function shouldResetSetMarketResults({ control, sortKey }) {
  return control === "query" || control === "era" || control === "sort" || (control === "timeframe" && sortKey === "change");
}

export default function SetMarketExplorer({ targets = [], loadError = false, navigate = null }) {
  const navigationStartedRef = useRef(false);
  const sectionTopRef = useRef(null);
  const resultsTopRef = useRef(null);
  const mobileToolbarRef = useRef(null);
  const returnThresholdRef = useRef(null);
  const [showReturnToSetMarketTop, setShowReturnToSetMarketTop] = useState(false);
  const [query, setQuery] = useState("");
  const [era, setEra] = useState(ALL_ERAS);
  const [sortKey, setSortKey] = useState("value");
  // One timeframe drives the mobile scanner and both desktop master/detail
  // panes. Mobile has no internal detail screen; rows drill into set pages.
  const [listWindowKey, setListWindowKey] = useState(DEFAULT_WINDOW);
  const isMasterDetail = useMediaQuery("(min-width: 1200px)", true);
  const activeDetailWindowKey = listWindowKey;
  const [selectedSetId, setSelectedSetId] = useState(null);
  // Below desktop the browser and the analysis are two states of one screen,
  // never a squeezed split. Desktop ignores this entirely.
  const detailHistoryCache = useRef(new Map());
  const [detailHistoryState, setDetailHistoryState] = useState({ setId: null, status: "idle", history: [], days: 0, error: null });
  const [historyRetryToken, setHistoryRetryToken] = useState(0);

  const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const scrollToTarget = (target, includeToolbar = false) => {
    if (!target || typeof window === "undefined" || isMasterDetail) return;
    const headerOffset = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--app-header-offset")) || 64;
    const toolbarOffset = includeToolbar ? mobileToolbarRef.current?.getBoundingClientRect().height || 0 : 0;
    const top = target.getBoundingClientRect().top + window.scrollY - headerOffset - toolbarOffset;
    window.scrollTo({ top: Math.max(0, top), behavior: reducedMotion() ? "auto" : "smooth" });
  };
  const resetResultsIfDeep = (control) => {
    if (!shouldResetSetMarketResults({ control, sortKey }) || !resultsTopRef.current || typeof window === "undefined") return;
    const headerOffset = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--app-header-offset")) || 64;
    if (resultsTopRef.current.getBoundingClientRect().top < headerOffset) scrollToTarget(resultsTopRef.current, true);
  };

  const ranked = useMemo(() => buildRankedRows(targets), [targets]);

  const eras = useMemo(
    () => [...new Set(ranked.map((row) => row.era))].sort((a, b) => a.localeCompare(b)),
    [ranked]
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = ranked.filter((row) => {
      if (era !== ALL_ERAS && row.era !== era) return false;
      if (!needle) return true;
      return row.name.toLowerCase().includes(needle) || row.era.toLowerCase().includes(needle);
    });
    if (sortKey === "name") {
      return [...filtered].sort((a, b) => a.name.localeCompare(b.name));
    }
    if (sortKey === "change") {
      // Unranked movements sink rather than sorting as zero — "no comparable
      // snapshot" is not "flat".
      return [...filtered].sort((a, b) => {
        const left = a.target?.windows?.[listWindowKey]?.percent;
        const right = b.target?.windows?.[listWindowKey]?.percent;
        const leftValid = Number.isFinite(left);
        const rightValid = Number.isFinite(right);
        if (leftValid !== rightValid) return leftValid ? -1 : 1;
        if (!leftValid) return a.position - b.position;
        return right - left || a.position - b.position;
      });
    }
    return filtered;
  }, [ranked, query, era, sortKey, listWindowKey]);

  useEffect(() => {
    if (isMasterDetail || !returnThresholdRef.current || typeof IntersectionObserver === "undefined") {
      setShowReturnToSetMarketTop(false);
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      setShowReturnToSetMarketTop(!entry.isIntersecting && entry.boundingClientRect.top < 0);
    });
    observer.observe(returnThresholdRef.current);
    return () => observer.disconnect();
  }, [isMasterDetail, visible.length]);

  // The selection is sticky and defaults to the #1 set by canonical Set Value.
  // Deliberately NOT derived from the filtered list: typing in the search box
  // must not silently repoint the analysis pane at whatever floated to the top.
  const selected = useMemo(
    () => ranked.find((row) => row.setId === selectedSetId) || ranked[0] || null,
    [ranked, selectedSetId]
  );

  const selectSet = (setId, { openDetail = false } = {}) => {
    setSelectedSetId(setId);
    // Only the LOCAL mobile window resets with the selection. The shared
    // desktop window is a property of the workspace, not of the row you
    // clicked, so changing sets must leave it exactly where the user put it.
  };

  const hrefForSet = (row) => buildTcgSetHrefFromTarget(
    { target_type: "set", target_id: row.target?.canonicalKey || row.setId, name: row.name },
    { tab: "market", section: "set-value" }
  );
  const navigateToSet = (row) => {
    const href = hrefForSet(row);
    if (!href || navigationStartedRef.current) return;
    navigationStartedRef.current = true;
    if (navigate) navigate(href);
    else if (typeof window !== "undefined") window.location.assign(href);
  };
  const activateSetRow = (event, row, isActive) => {
    if (resolveSetMarketRowAction({ isMasterDetail, isActive, clickCount: event?.detail ?? 0 }) === "navigate") {
      navigateToSet(row);
      return;
    }
    selectSet(row.setId, { openDetail: true });
  };

  const detailMovement = selected?.target?.windows?.[activeDetailWindowKey] || null;
  useEffect(() => {
    const browserIsDesktop = typeof window === "undefined" || typeof window.matchMedia !== "function"
      ? isMasterDetail
      : window.matchMedia("(min-width: 1200px)").matches;
    if (!isMasterDetail || !browserIsDesktop) return undefined;
    const setId = selected?.setId;
    if (!setId) return undefined;

    const cached = detailHistoryCache.current.get(setId) || null;
    const needsAll = cached && needsLifetimeSetMarketHistory({
      activeWindowKey: activeDetailWindowKey,
      historyStartDate: selected.target?.historyStartDate,
      loadedHistory: cached.history,
      loadedDays: cached.days,
    });
    if (cached && !needsAll) {
      setDetailHistoryState({ setId, status: "success", history: cached.history, days: cached.days, error: null });
      return undefined;
    }

    const days = needsAll ? 1825 : 365;
    let cancelled = false;
    setDetailHistoryState({ setId, status: "loading", history: [], days, error: null });
    getPokemonSetValueHistory(setId, { days, scope: "standard" })
      .then((payload) => {
        if (cancelled) return;
        const history = Array.isArray(payload?.history) ? payload.history : [];
        detailHistoryCache.current.set(setId, { history, days });
        setDetailHistoryState({ setId, status: "success", history, days, error: null });
      })
      .catch((error) => {
        if (!cancelled) setDetailHistoryState({ setId, status: "error", history: [], days, error });
      });
    return () => { cancelled = true; };
  }, [isMasterDetail, selected?.setId, selected?.target?.historyStartDate, activeDetailWindowKey, historyRetryToken]);

  const detailTrend = selected && detailHistoryState.setId === selected.setId && detailHistoryState.status === "success"
    ? clipSetMarketDetailHistory(detailHistoryState.history, detailMovement)
    : [];
  const detailDirection = directionOf(detailMovement?.amount);
  const detailHref = selected
    ? buildTcgSetHrefFromTarget(
        { target_type: "set", target_id: selected.target?.canonicalKey || selected.setId, name: selected.name },
        { tab: "market", section: "set-value" }
      )
    : null;
  const moversHref = selected
    ? buildTcgSetHrefFromTarget(
        { target_type: "set", target_id: selected.target?.canonicalKey || selected.setId, name: selected.name },
        { tab: "cards", section: "market-movers", window: "7D" }
      )
    : null;

  if (!ranked.length) {
    return (
      <section className={`${styles.surfaceQuiet} set-glass-surface`} aria-labelledby="set-market-heading">
        <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
          <h2 id="set-market-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Set Market</h2>
        </div>
        {loadError
          ? <p role="alert" className="px-4 py-6 text-sm text-[var(--text-secondary)]">Set Market is temporarily unavailable.</p>
          : <p className="px-4 py-6 text-sm text-[var(--text-secondary)]">Sets appear once the current Market snapshot is available.</p>}
      </section>
    );
  }

  const listPane = (
    <div data-set-market-list className="flex min-w-0 flex-col">
      <div className={`${styles.setListHeader} ${styles.setListHeaderDesktop}`} aria-hidden="true">
        <span>#</span>
        <span>Set</span>
        <span>{`Set value / ${windowLabel(listWindowKey)}`}</span>
      </div>
      <div className={styles.setListShell}>
        <div className={`${styles.setListScroll} index-scrollbar`}>
          {visible.length === 0 ? (
            <p role="status" className="px-3 py-6 text-sm text-[var(--text-secondary)]">No tracked set matches those filters.</p>
          ) : (
            <ul aria-label="Tracked Pokémon sets, ranked by canonical current Set Value">
              {visible.map((row, index) => {
                const movement = row.target?.windows?.[listWindowKey] || null;
                const miniTrend = selectSetMarketMiniTrend(row.target, listWindowKey);
                const isActive = selected?.setId === row.setId;
                return (
                  <li key={row.setId} ref={index === Math.min(5, visible.length - 1) ? returnThresholdRef : undefined} data-set-market-return-threshold={index === Math.min(5, visible.length - 1) ? "true" : undefined}>
                    <button
                      type="button"
                      data-set-market-row={row.setId}
                      aria-current={isActive ? "true" : undefined}
                      onClick={(event) => activateSetRow(event, row, isActive)}
                      title={isMasterDetail && isActive ? `Open ${row.name}` : undefined}
                      className={`${styles.setListRow} ${isActive ? styles.setListRowActive : ""}`}
                    >
                      <span className="text-[12px] font-semibold tabular-nums text-[var(--text-secondary)]">{`#${row.position}`}</span>
                      <SetLogo target={row.target} name={row.name} />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium text-[var(--text-primary)]">{row.name}</span>
                        <span className="block truncate text-[10px] text-[var(--text-secondary)]">{row.era}</span>
                      </span>
                      <span className="hidden justify-self-center max-desk:block">
                        <MiniMarketSparkline points={miniTrend} color={toneOf(directionOf(movement?.amount))} />
                      </span>
                      <span className="min-w-0 text-right">
                        <span className="block text-[13px] font-semibold tabular-nums text-[var(--text-primary)]">{compactCurrency.format(row.value)}</span>
                        <span className="block text-[10px] font-medium">
                          <ChangePercent movement={movement} windowKey={listWindowKey} />
                        </span>
                      </span>
                      <span className="sr-only">{`Select ${row.name} to inspect its Set Market analysis.`}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );

  const detailPane = selected ? (
    <div data-set-market-detail className={`${styles.setMarketDetail} flex min-w-0 flex-col px-3 py-3 sm:px-4`}>
      <div className="flex items-start gap-3">
        <SetLogo target={selected.target} name={selected.name} className="h-11 w-11" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <h3 data-set-market-detail-name className="min-w-0 text-[17px] font-semibold leading-tight text-[var(--text-primary)] desk:text-[16px]">
              {detailHref
                ? <a href={detailHref} className="rounded hover:text-[var(--brand-light)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand)]">{selected.name}</a>
                : selected.name}
            </h3>
            <span className="flex-none text-[13px] font-semibold tabular-nums text-[var(--text-secondary)]">{`#${selected.position}`}</span>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-[var(--text-secondary)]">{selected.era}</p>
        </div>
      </div>

      <div className="mt-3">
        <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span data-set-market-detail-value className="text-[24px] font-semibold leading-none tabular-nums text-[var(--text-primary)]">
            {currency.format(selected.value)}
          </span>
          <ChangeText movement={detailMovement} windowKey={activeDetailWindowKey} className="text-[13px] font-semibold" />
        </p>
        <p data-set-market-detail-window={activeDetailWindowKey} className="mt-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {`Set Value · ${windowLabel(activeDetailWindowKey)}`}
          {detailMovement?.coverage === "partial" ? <span> · since first available</span> : null}
        </p>
      </div>

      <div className="mt-3 min-w-0">
        {detailHistoryState.setId !== selected.setId || detailHistoryState.status === "idle" || detailHistoryState.status === "loading" ? (
          <div
            data-set-market-detail-skeleton
            aria-hidden="true"
            className="h-44 animate-pulse rounded-lg border border-[var(--border-subtle)] bg-[rgba(148,163,184,0.08)] motion-reduce:animate-none desk:h-[15rem]"
          />
        ) : detailHistoryState.status === "error" ? (
          <div role="alert" className="flex h-44 flex-col items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-4 text-center text-xs text-[var(--text-secondary)] desk:h-[15rem]">
            <span>Set Value history is temporarily unavailable.</span>
            <button type="button" onClick={() => setHistoryRetryToken((token) => token + 1)} className="rounded-md border border-[rgba(45,212,191,0.40)] px-3 py-1.5 font-semibold text-[rgb(45,212,191)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]">Retry</button>
          </div>
        ) : (
          <MarketSparkline
            points={detailTrend}
            valueKey="setValue"
            trendDirection={detailDirection}
            baselineValue={resolveDeltaWindowBaselineValue(detailMovement, selected.value)}
            label={`${selected.name} Set Value trend`}
            emptyLabel="No daily Set Value history is available for this timeframe."
            data-set-market-detail-chart-window={activeDetailWindowKey}
            className="w-full"
            plotClassName="h-44 desk:h-[15rem]"
          />
        )}
      </div>

      <SetMarketTopMovers key={selected.setId} setId={selected.setId} setName={selected.name} viewAllHref={moversHref} />
    </div>
  ) : null;

  return (
    <section ref={sectionTopRef} data-set-market-top className={`${styles.surfaceQuiet} ${styles.marketMobileSection} set-glass-surface flex min-w-0 flex-col`} aria-labelledby="set-market-heading">
      <div ref={mobileToolbarRef} className={styles.setMarketMobileSticky}>
      <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
        <div className="flex items-center gap-2">
          <h2 id="set-market-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Set Market</h2>
          <span className="ml-auto text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">{`${ranked.length} tracked sets`}</span>
        </div>

        {/* Toolbar. Search, era and sort all read metadata the snapshot already
            publishes on each set — no filtering contract was invented for this.
            It governs the LIST, so below desktop it is hidden while the detail
            state is showing: controls for a list that is not on screen, next to
            the selected set's own timeframe row, read as two competing pickers. */}
        <div
          data-set-market-toolbar
          className="mt-3 flex flex-col gap-2.5 desk:flex-row desk:flex-wrap desk:items-center"
        >
          <label className="min-w-0 flex-1 desk:max-w-[16rem]">
            <span className="sr-only">Search sets</span>
            <input
              type="search"
              value={query}
              onChange={(event) => {
                resetResultsIfDeep("query");
                setQuery(event.target.value);
              }}
              placeholder="Search sets..."
              className={`${styles.setMarketControl} min-h-11 w-full px-2.5 py-1 text-xs desk:min-h-0 desk:py-1.5`}
            />
          </label>

          <div className="flex min-w-0 gap-2.5">
            <DarkSelect
              ariaLabel="Filter by era"
              value={era}
              onChange={(nextEra) => {
                resetResultsIfDeep("era");
                setEra(nextEra);
              }}
              options={[{ value: ALL_ERAS, label: "All Eras" }, ...eras.map((entry) => ({ value: entry, label: entry }))]}
            />

            <DarkSelect
              ariaLabel="Sort sets"
              value={sortKey}
              onChange={(nextSort) => {
                resetResultsIfDeep("sort");
                setSortKey(nextSort);
              }}
              options={SORT_OPTIONS.map((entry) => ({ value: entry.key, label: `Sort: ${entry.label}` }))}
            />
          </div>

          <div className="min-w-0 desk:ml-auto desk:w-auto">
            <MarketWindowSelector
              windows={WINDOWS}
              value={listWindowKey}
              onChange={(nextWindow) => {
                resetResultsIfDeep("timeframe");
                setListWindowKey(nextWindow);
              }}
              ariaDescription={isMasterDetail
                ? "Sets the timeframe for the whole Set Market: the list's change column, the selected set's change and its daily chart."
                : "Sets the timeframe the set list's change column reports. No data is fetched."}
            />
          </div>
        </div>
      </div>
      <div className={`${styles.setListHeader} ${styles.setListHeaderMobile}`} aria-hidden="true">
        <span>#</span>
        <span>Set</span>
        <span>{`Set value / ${windowLabel(listWindowKey)}`}</span>
      </div>
      </div>

      {/* Mobile renders only the scanner list. Desktop adds the selected detail
          pane beside it, separated by the existing hairline. */}
      <div ref={resultsTopRef} data-set-market-results-top className={styles.setMarketBody}>
        <div>{listPane}</div>
        <div className="hidden desk:block">{detailPane}</div>
      </div>
      <ReturnToTopButton
        visible={showReturnToSetMarketTop}
        onActivate={() => scrollToTarget(sectionTopRef.current)}
        ariaLabel="Return to top of Set Market"
        className="flex desk:hidden"
      />
    </section>
  );
}
