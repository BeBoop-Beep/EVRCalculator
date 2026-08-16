"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import MarketWindowSelector from "./MarketWindowSelector";
import MarketSparkline from "./MarketSparkline";
import { getStandardDeltaWindowDefinitions, resolveDeltaWindowBaselineValue } from "@/lib/explore/marketDeltaWindows.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { SET_LOGO_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import styles from "./explore.module.css";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signedCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", signDisplay: "always", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const WINDOWS = getStandardDeltaWindowDefinitions();
const MOBILE_PREVIEW_LIMIT = 5;

function SetLogo({ target, name }) {
  const [failed, setFailed] = useState(false);
  const src = optimizedImageUrl(String(target?.logoUrl || target?.symbolUrl || "").trim(), SET_LOGO_THUMBNAIL_WIDTH);
  if (!src || failed) return <span className="flex h-9 w-9 items-center justify-center rounded bg-white/5 text-[9px] font-semibold text-[var(--text-secondary)]">{name.slice(0, 2).toUpperCase()}</span>;
  return <img src={src} alt="" className="h-9 w-9 object-contain" loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}

function Sparkline({ points, direction, baselineValue }) {
  // w-full and nothing else — the Top Chase Cards sparkline wrapper minus its
  // desktop width cap, because the rankings trend column is deliberately the
  // wider one. No fixed or viewport-relative maximum belongs here: the chart
  // fills whatever its grid cell gives it, on both compositions.
  return <MarketSparkline points={points} valueKey="setValue" trendDirection={direction} baselineValue={baselineValue} label="Set Value trend" className="w-full" plotClassName="h-11 desk:h-[4.25rem]" />;
}

function buildRows(targets, selectedWindowKey) {
  return (Array.isArray(targets) ? targets : []).map((target) => {
    const movement = target?.windows?.[selectedWindowKey] || null;
    const trend = (Array.isArray(target?.trend) ? target.trend : []).map(([date, setValue]) => ({ date, setValue })).filter((point) => !movement?.startDate || (point.date >= movement.startDate && point.date <= movement.endDate));
    return { target, movement, trend, value: Number(target?.currentSetValue) };
  }).filter(({ value }) => Number.isFinite(value) && value > 0).sort((a, b) => b.value - a.value || String(a.target?.name || "").localeCompare(String(b.target?.name || ""))).map((row, index) => ({ ...row, position: index + 1 }));
}

export default function ExploreTopRankings({ targets = [], loadError = false }) {
  const [selectedWindowKey, setSelectedWindowKey] = useState("30D");
  const [showAllMobileRows, setShowAllMobileRows] = useState(false);
  const rows = useMemo(() => buildRows(targets, selectedWindowKey), [targets, selectedWindowKey]);
  const hiddenCount = Math.max(0, rows.length - MOBILE_PREVIEW_LIMIT);
  return <section className={`${styles.surfaceQuiet} set-glass-surface flex min-w-0 flex-col`} aria-labelledby="explore-top-rankings-heading">
    <div className={`${styles.divider} px-3 py-3 sm:px-4`}>
      <div className="flex items-center gap-2"><h2 id="explore-top-rankings-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">Set Value Rankings</h2><span className="ml-auto text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">Set Value</span></div>
      <div className="mt-3"><MarketWindowSelector windows={WINDOWS} value={selectedWindowKey} onChange={setSelectedWindowKey} fullWidth ariaDescription="Controls every sparkline and both movement values without fetching data." /></div>
    </div>
    {rows.length ? <div className={rows.length > 9 ? styles.scrollShell : undefined}>
      <div className={styles.rankingHeader} aria-hidden="true"><span>Rank</span><span>Set</span><span>Trend</span><span>Set value / change</span></div>
      <ol className={`${styles.ladderScroll} index-scrollbar`} aria-label="Sets ordered by canonical current Set Value, highest first">{rows.map(({ target, movement, trend, value, position }, index) => {
        const name = String(target?.name || target?.setId || "Unknown Set");
        const amount = movement?.amount ?? null, percent = movement?.percent ?? null;
        const direction = amount > 0 ? "positive" : amount < 0 ? "negative" : "neutral";
        const color = direction === "positive" ? POSITIVE_VALUE_COLOR : direction === "negative" ? NEGATIVE_VALUE_COLOR : "var(--text-secondary)";
        const routeTarget = { target_type: "set", target_id: target.canonicalKey || target.setId, name };
        const href = buildTcgSetHrefFromTarget(routeTarget, { tab: "market", section: "set-value" });
        // Computed once, rendered per composition — the same rule TopMarketCardRow
        // applies to its price cell. Duplicating the wrapper is presentation;
        // duplicating the computation would be a data risk.
        const valueCell = <span className="block min-w-0 text-right">
          <span className="block text-sm font-semibold tabular-nums text-[var(--text-primary)]">{currency.format(value)}</span>
          <span className="block truncate text-[10px] font-medium tabular-nums" style={{ color }}>{amount === null || percent === null ? `N/A · ${selectedWindowKey === "lifetime" ? "LT" : selectedWindowKey}` : `${amount > 0 ? "▲" : amount < 0 ? "▼" : "—"} ${signedCurrency.format(amount)} (${percent >= 0 ? "+" : ""}${percent.toFixed(1)}%)`}</span>
          {movement?.coverage === "partial" ? <span className="block text-[9px] text-[var(--text-secondary)]">Since first available</span> : null}
        </span>;
        return <li key={target.setId} className={!showAllMobileRows && index >= MOBILE_PREVIEW_LIMIT ? "hidden desk:list-item" : undefined}><div className={styles.ladderRow} style={{ "--ex-rank-strength": position <= 3 ? 0.7 : 0.22 }}>
          {/* The information region IS the link and the chart is its sibling —
              TopMarketCardRow's composition. Below desktop the link is the whole
              compact line (rank | logo | identity | value + change) and the
              sparkline spans the row beneath it. At desktop the link narrows to
              rank + set, the trend takes column three and the value moves into
              its own column-four link. A focusable, arrow-key-driven chart is
              never nested in an anchor, so nothing needs event suppression. */}
          <Link data-ranking-nav href={href} className={styles.ladderNav} aria-label={`${name} — open Set Market`}>
            <span className="text-[13px] font-semibold tabular-nums text-[var(--text-secondary)]">#{position}</span>
            <SetLogo target={target} name={name} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-[var(--text-primary)]">{name}</span>
              <span className="block truncate text-[10px] text-[var(--text-secondary)]">{target?.era || "Pokémon"}</span>
            </span>
            <span data-ranking-value="compact" className="min-w-0 desk:hidden">{valueCell}</span>
          </Link>
          <div data-ranking-chart className="min-w-0"><Sparkline points={trend} direction={direction} baselineValue={resolveDeltaWindowBaselineValue(movement, value)} /></div>
          <Link data-ranking-value-nav href={href} className={styles.ladderValueNav} aria-label={`${name} Set Value — open Set Market`}>
            <span data-ranking-value="table">{valueCell}</span>
          </Link>
        </div></li>;
      })}{hiddenCount ? <li className="px-3 py-2 desk:hidden"><button type="button" className="min-h-11 text-xs font-medium text-[var(--text-primary)]" onClick={() => setShowAllMobileRows((open) => !open)}>{showAllMobileRows ? "Show less" : `Show ${hiddenCount} more`}</button></li> : null}</ol>
    </div> : loadError ? <p role="alert" className="px-4 py-6 text-sm text-[var(--text-secondary)]">Set Value rankings are temporarily unavailable.</p> : <p className="px-4 py-6 text-sm text-[var(--text-secondary)]">Rankings appear once the current Market snapshot is available.</p>}
  </section>;
}
