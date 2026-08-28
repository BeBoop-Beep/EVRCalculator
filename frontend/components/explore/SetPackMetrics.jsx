"use client";

import Image from "next/image";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import AnalyticsTableShell from "./AnalyticsTableShell";
import { PremiumMetricLock } from "./RankedProductTablePrimitives.jsx";
import { displaySetPackFamily, orderSetPackFamilies } from "./setPackFamilyPresentation.mjs";
import { SET_PACK_COLUMNS, sortSetPackMetrics, formatSetMetric, mergeSetEconomics } from "./setPackMetricsSelector.mjs";
import styles from "./explore.module.css";

const TOTAL_COLUMN_COUNT = SET_PACK_COLUMNS.length + 1;
const PUBLIC_COLUMN_KEYS = new Set(["products", "packPrice"]);
const displayFamily = displaySetPackFamily;

function Identity({ row }) {
  return <Link href={buildTcgSetHrefFromTarget(row.raw)} className="flex min-w-0 items-center gap-2.5">{row.logo ? <Image src={row.logo} width={56} height={32} alt="" className="h-8 w-12 flex-none object-contain" /> : <span className="h-8 w-12 flex-none" />}<span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{row.setName}<small className="block text-[10px] font-normal text-[var(--text-secondary)]">Set RIP #{row.canonicalRank || "—"}</small></span></Link>;
}

function FamilyMatrix({ rows, setId }) {
  const families = orderSetPackFamilies(rows);
  return <div id={`family-economics-${setId}`} data-family-economics-detail>
    <table className="hidden w-full table-fixed text-xs desk:table" data-family-economics-matrix><thead><tr className="border-b border-[var(--border-subtle)] text-[9px] uppercase tracking-wide text-[var(--text-secondary)]"><th className="py-2 text-left">Product Family</th><th>Products</th><th>Avg Cost / Pack</th><th>Break-Even / Pack</th><th>Typical / Pack</th><th>Modeled Return</th><th>Ent. Cost / Pack</th><th>Typical Retention</th><th>Chance to Recover</th></tr></thead><tbody>{families.map((row) => <tr key={row.family} data-family-economics-row={row.family} className="border-b border-[rgba(255,255,255,0.035)] last:border-0"><th className="py-2 text-left font-medium">{displayFamily(row.family)}</th><td className="text-center tabular-nums">{row.productSkuCount ?? "—"}</td><td className="text-center tabular-nums">{formatSetMetric("packPrice", row.averageCostPerPack) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("modelBreakEven", row.averageModelBreakEvenPerPack) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("typicalOpening", row.typicalOpeningPerPack) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("modeledReturn", row.modeledReturnOnSpend) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("entertainmentCost", row.averageEntertainmentCostPerPack) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("typicalRetention", row.typicalRetention) || "—"}</td><td className="text-center tabular-nums">{formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"}</td></tr>)}</tbody></table>
    <ul className="space-y-1.5 desk:hidden">{families.map((row) => <li key={row.family} data-family-economics-mobile-row={row.family} className="border-b border-[var(--border-subtle)] px-1 py-2 last:border-0"><div className="flex justify-between gap-3"><strong className="text-xs">{displayFamily(row.family)}</strong><strong className="text-xs tabular-nums">{formatSetMetric("modeledReturn", row.modeledReturnOnSpend) || "—"}</strong></div><p className="mt-1 text-[10px] text-[var(--text-secondary)]">{formatSetMetric("packPrice", row.averageCostPerPack) || "—"} cost · {formatSetMetric("modelBreakEven", row.averageModelBreakEvenPerPack) || "—"} EV · {formatSetMetric("typicalOpening", row.typicalOpeningPerPack) || "—"} typical</p><p className="text-[10px] text-[var(--text-secondary)]">{formatSetMetric("entertainmentCost", row.averageEntertainmentCostPerPack) || "—"} entertainment · {formatSetMetric("typicalRetention", row.typicalRetention) || "—"} typical retention · {formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"} recover</p></li>)}</ul>
  </div>;
}

export default function SetPackMetrics({ sets, targets, eraFilter, marketDate = null, canViewRankingsIntelligence = false, onUnlockProductRip = null }) {
  const [sort, setSort] = useState(() => ({ key: canViewRankingsIntelligence ? "modeledReturn" : "packPrice", direction: "desc" }));
  const [query, setQuery] = useState("");
  const [expandedSetId, setExpandedSetId] = useState(null);
  const merged = mergeSetEconomics(sets, targets);
  const filtered = merged.filter((row) => {
    if (eraFilter && String(row.eraName).toLowerCase() !== String(eraFilter).toLowerCase()) return false;
    const needle = query.trim().toLowerCase();
    return !needle || `${row.setName || ""} ${row.eraName || ""}`.toLowerCase().includes(needle);
  });
  const effectiveSort = canViewRankingsIntelligence || PUBLIC_COLUMN_KEYS.has(sort.key) ? sort : { key: "packPrice", direction: "desc" };
  const rows = useMemo(() => sortSetPackMetrics(filtered, effectiveSort.key, effectiveSort.direction), [effectiveSort.direction, effectiveSort.key, filtered]);
  const change = (key) => {
    if (!canViewRankingsIntelligence && !PUBLIC_COLUMN_KEYS.has(key)) {
      onUnlockProductRip?.();
      return;
    }
    setSort((current) => ({ key, direction: current.key === key && current.direction === "desc" ? "asc" : "desc" }));
  };
  const toggle = (setId) => canViewRankingsIntelligence ? setExpandedSetId((current) => current === setId ? null : setId) : onUnlockProductRip?.();
  return <AnalyticsTableShell title="Pack Economics by Set" info="Each Set aggregates all eligible modeled sealed products as per-pack equivalents. Product families are balanced within the Set; expanding a row shows the published family-level breakdown for Index Plus members." query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search sets..." searchLabel="Search Pack Economics sets" shown={rows.length} marketDate={marketDate}>
    <section data-set-pack-metrics data-pack-economics-entitled={canViewRankingsIntelligence ? "true" : "false"}>
    <div className="hidden overflow-x-auto desk:block"><table className={styles.table}><caption className="sr-only">Pack Economics by Set. Parent metrics are canonical V3 Set aggregates.</caption><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr><th className="min-w-52">Set</th>{SET_PACK_COLUMNS.map(([key, label]) => <th key={key} className={styles.numeric} aria-sort={effectiveSort.key === key ? (effectiveSort.direction === "asc" ? "ascending" : "descending") : undefined}><button type="button" className={styles.sortButton} onClick={() => change(key)}>{label}</button></th>)}</tr></thead><tbody>{rows.map((row) => { const expanded = canViewRankingsIntelligence && expandedSetId === row.setId; return <Fragment key={row.setId}><tr className={styles.row} data-set-pack-parent-row={row.setId}><td><div className="flex items-center gap-2"><button type="button" onClick={() => toggle(row.setId)} aria-expanded={expanded} aria-controls={canViewRankingsIntelligence ? `family-economics-${row.setId}` : undefined} aria-label={canViewRankingsIntelligence ? `${expanded ? "Hide" : "View"} Product-Family Economics for ${row.setName}` : `Unlock Product-Family Economics for ${row.setName}`} className="relative z-[2] flex h-7 w-7 flex-none items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-white/5 hover:text-[var(--text-primary)]">{canViewRankingsIntelligence ? <span aria-hidden="true" className={`transition-transform ${expanded ? "rotate-90" : ""}`}>›</span> : <PremiumMetricLock />}</button><Identity row={row} /></div></td>{SET_PACK_COLUMNS.map(([key]) => <td key={key} className={`${styles.numeric} tabular-nums`}>{canViewRankingsIntelligence || PUBLIC_COLUMN_KEYS.has(key) ? (formatSetMetric(key, row[key]) || "—") : <PremiumMetricLock />}</td>)}</tr>{expanded ? <tr className="family-detail-row" data-family-detail-row={row.setId}><td colSpan={TOTAL_COLUMN_COUNT} className="border-b border-[var(--ex-line-strong)] bg-[rgba(2,8,23,0.34)] px-4 py-3"><FamilyMatrix rows={row.familyEconomics} setId={row.setId} /></td></tr> : null}</Fragment>; })}</tbody></table></div>
    <ul className="space-y-2.5 p-3 desk:hidden">{rows.map((row) => { const expanded = canViewRankingsIntelligence && expandedSetId === row.setId; return <li key={row.setId} className={`${styles.surfaceQuiet} rounded-xl p-3.5`} data-set-pack-mobile-row={row.setId}><div className="flex items-center justify-between gap-2"><Identity row={row} /><button type="button" onClick={() => toggle(row.setId)} aria-expanded={expanded} aria-controls={canViewRankingsIntelligence ? `family-economics-${row.setId}` : undefined} className="min-h-11 px-2 text-xs text-[rgb(var(--ex-teal))]">{canViewRankingsIntelligence ? (expanded ? "Hide families" : "View families") : "Index Plus"}</button></div>{canViewRankingsIntelligence ? <><dl className="mt-3 grid grid-cols-2 gap-2">{["modeledReturn", "typicalOpening", "entertainmentCost", "typicalRetention"].map((key) => <div key={key}><dt className="text-[.65rem] uppercase text-[var(--text-secondary)]">{SET_PACK_COLUMNS.find((column) => column[0] === key)[1]}</dt><dd>{formatSetMetric(key, row[key]) || "—"}</dd></div>)}</dl><p className="mt-2 border-t border-[var(--ex-line)] pt-2 text-xs text-[var(--text-secondary)]">Products {formatSetMetric("products", row.products) || "—"} · Pack {formatSetMetric("packPrice", row.packPrice) || "—"} · Break-even {formatSetMetric("modelBreakEven", row.modelBreakEven) || "—"} · Recover {formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"}</p>{expanded ? <div className="mt-2 border-t border-[var(--border-subtle)] pt-1"><FamilyMatrix rows={row.familyEconomics} setId={row.setId} /></div> : null}</> : <div className="mt-3 border-t border-[var(--ex-line)] pt-2"><p className="text-xs tabular-nums text-[var(--text-primary)]">{formatSetMetric("products", row.products) || "—"} products · {formatSetMetric("packPrice", row.packPrice) || "—"} avg cost / pack</p><button type="button" onClick={() => onUnlockProductRip?.()} className="mt-2 text-left text-xs text-[rgb(var(--ex-teal))]">Index Plus required for detailed Pack Economics</button></div>}</li>; })}</ul>
    </section>
  </AnalyticsTableShell>;
}
