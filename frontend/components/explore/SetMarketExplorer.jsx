"use client";

import { useEffect, useMemo, useState } from "react";
import useMediaQuery from "@/hooks/useMediaQuery";
import MarketSparkline from "./MarketSparkline";
import MarketWindowSelector from "./MarketWindowSelector";
import SetMarketTopMovers from "./SetMarketTopMovers";
import { getStandardDeltaWindowDefinitions, resolveDeltaWindowBaselineValue } from "@/lib/explore/marketDeltaWindows.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { SET_LOGO_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
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
// Everything below reads the SAME published global Set Value snapshot the
// ladder read — `currentSetValue`, `windows[key]` and `trend`, all authored by
// the backend. Nothing here computes a set value, a movement or a rank, and
// selecting a set costs no set-value request. The only network call on this
// surface belongs to SetMarketTopMovers, which is lazy and per-selection.
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

const windowLabel = (key) => (key === "lifetime" ? "LT" : key);

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

/** The trend points the selected window actually covers, per the backend's own dates. */
function clipTrend(target, movement) {
  return (Array.isArray(target?.trend) ? target.trend : [])
    .map(([date, setValue]) => ({ date, setValue }))
    .filter((point) => !movement?.startDate || (point.date >= movement.startDate && point.date <= movement.endDate));
}

export default function SetMarketExplorer({ targets = [], loadError = false }) {
  const [query, setQuery] = useState("");
  const [era, setEra] = useState(ALL_ERAS);
  const [sortKey, setSortKey] = useState("value");
  // TIMEFRAME, AND WHY THERE ARE TWO STATES FOR ONE CONCEPT
  // -------------------------------------------------------
  // At desktop the list and the analysis are one workspace on one screen, so
  // they read ONE window: the toolbar's. Two selectors for the same concept,
  // visible at the same time, is an ambiguity rather than a feature — so the
  // detail pane's selector is not rendered at all up here, and every
  // timeframe-dependent figure on both sides derives from `listWindowKey`.
  //
  // Below `desk` the two panes are separate SCREENS (browse, then detail), so
  // a local control per screen is the right model: the list keeps the window
  // you were scanning at, and inspecting one set at 30D does not silently
  // rewrite it. `detailWindowKey` exists only for that composition.
  //
  // The breakpoint is deliberately the same 1200px at which the master-detail
  // split itself collapses — one idea, one boundary.
  const [listWindowKey, setListWindowKey] = useState(DEFAULT_WINDOW);
  const [detailWindowKey, setDetailWindowKey] = useState(DEFAULT_WINDOW);
  const isMasterDetail = useMediaQuery("(min-width: 1200px)", true);
  // The one window the detail pane actually reads.
  const activeDetailWindowKey = isMasterDetail ? listWindowKey : detailWindowKey;
  const [selectedSetId, setSelectedSetId] = useState(null);
  // Below desktop the browser and the analysis are two states of one screen,
  // never a squeezed split. Desktop ignores this entirely.
  const [mobileView, setMobileView] = useState("browse");

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
    if (!isMasterDetail) setDetailWindowKey(DEFAULT_WINDOW);
    if (openDetail) setMobileView("detail");
  };

  const detailMovement = selected?.target?.windows?.[activeDetailWindowKey] || null;
  const detailTrend = selected ? clipTrend(selected.target, detailMovement) : [];
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
      <div className={styles.setListHeader} aria-hidden="true">
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
              {visible.map((row) => {
                const movement = row.target?.windows?.[listWindowKey] || null;
                const isActive = selected?.setId === row.setId;
                return (
                  <li key={row.setId}>
                    <button
                      type="button"
                      data-set-market-row={row.setId}
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => selectSet(row.setId, { openDetail: true })}
                      className={`${styles.setListRow} ${isActive ? styles.setListRowActive : ""}`}
                    >
                      <span className="text-[12px] font-semibold tabular-nums text-[var(--text-secondary)]">{`#${row.position}`}</span>
                      <SetLogo target={row.target} name={row.name} />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium text-[var(--text-primary)]">{row.name}</span>
                        <span className="block truncate text-[10px] text-[var(--text-secondary)]">{row.era}</span>
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
      <button
        type="button"
        data-set-market-back
        onClick={() => setMobileView("browse")}
        className="mb-3 inline-flex min-h-11 items-center gap-1.5 self-start rounded-md text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:hidden"
      >
        <span aria-hidden="true">←</span> All sets
      </button>

      <div className="flex items-start gap-3">
        <SetLogo target={selected.target} name={selected.name} className="h-11 w-11" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <h3 data-set-market-detail-name className="min-w-0 text-[17px] font-semibold leading-tight text-[var(--text-primary)] desk:text-[16px]">
              {detailHref
                ? <a href={detailHref} className="rounded hover:text-[rgb(45,212,191)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">{selected.name}</a>
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

      {/* Not rendered at all in the master-detail composition — the toolbar's
          selector is the one control up there. Hiding a second copy with CSS
          would leave two radiogroups in the accessibility tree announcing the
          same setting. */}
      {isMasterDetail ? null : (
        <div className="mt-3">
          <MarketWindowSelector
            windows={WINDOWS}
            value={detailWindowKey}
            onChange={setDetailWindowKey}
            fullWidth
            ariaDescription="Clips the selected set's chart and its change value to this timeframe. No data is fetched."
          />
        </div>
      )}

      <div className="mt-3 min-w-0">
        <MarketSparkline
          points={detailTrend}
          valueKey="setValue"
          trendDirection={detailDirection}
          baselineValue={resolveDeltaWindowBaselineValue(detailMovement, selected.value)}
          label={`${selected.name} Set Value trend`}
          data-set-market-detail-chart-window={activeDetailWindowKey}
          className="w-full"
          plotClassName="h-44 desk:h-[15rem]"
        />
      </div>

      <SetMarketTopMovers key={selected.setId} setId={selected.setId} setName={selected.name} viewAllHref={moversHref} />
    </div>
  ) : null;

  return (
    <section className={`${styles.surfaceQuiet} set-glass-surface flex min-w-0 flex-col`} aria-labelledby="set-market-heading">
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
          className={`mt-3 flex-col gap-2.5 desk:flex desk:flex-row desk:flex-wrap desk:items-center ${mobileView === "detail" ? "hidden" : "flex"}`}
        >
          <label className="min-w-0 flex-1 desk:max-w-[16rem]">
            <span className="sr-only">Search sets</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search sets..."
              className={`${styles.setMarketControl} min-h-11 w-full px-2.5 py-1 text-xs desk:min-h-0 desk:py-1.5`}
            />
          </label>

          <div className="flex min-w-0 gap-2.5">
            <label className="min-w-0 flex-1">
              <span className="sr-only">Filter by era</span>
              <select
                value={era}
                onChange={(event) => setEra(event.target.value)}
                className={`${styles.setMarketControl} min-h-11 w-full px-2 py-1 text-xs desk:min-h-0 desk:py-1.5`}
              >
                <option value={ALL_ERAS}>All Eras</option>
                {eras.map((entry) => <option key={entry} value={entry}>{entry}</option>)}
              </select>
            </label>

            <label className="min-w-0 flex-1">
              <span className="sr-only">Sort sets</span>
              <select
                value={sortKey}
                onChange={(event) => setSortKey(event.target.value)}
                className={`${styles.setMarketControl} min-h-11 w-full px-2 py-1 text-xs desk:min-h-0 desk:py-1.5`}
              >
                {SORT_OPTIONS.map((entry) => <option key={entry.key} value={entry.key}>{`Sort: ${entry.label}`}</option>)}
              </select>
            </label>
          </div>

          <div className="min-w-0 desk:ml-auto desk:w-auto">
            <MarketWindowSelector
              windows={WINDOWS}
              value={listWindowKey}
              onChange={setListWindowKey}
              ariaDescription={isMasterDetail
                ? "Sets the timeframe for the whole Set Market: the list's change column, the selected set's change and its chart. No data is fetched."
                : "Sets the timeframe the set list's change column reports. No data is fetched."}
            />
          </div>
        </div>
      </div>

      {/* ONE body. Desktop is a two-pane grid divided by a hairline; below
          desktop the same two panes are the browse and detail STATES of one
          screen, so neither is ever squeezed into half a phone. */}
      <div className={styles.setMarketBody}>
        <div className={mobileView === "detail" ? "hidden desk:block" : "block"}>{listPane}</div>
        <div className={mobileView === "detail" ? "block" : "hidden desk:block"}>{detailPane}</div>
      </div>
    </section>
  );
}
