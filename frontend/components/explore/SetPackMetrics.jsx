"use client";

import Image from "next/image";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { displaySetPackFamily, orderSetPackFamilies } from "./setPackFamilyPresentation.mjs";
import { SET_PACK_COLUMNS, sortSetPackMetrics, formatSetMetric, mergeSetEconomics } from "./setPackMetricsSelector.mjs";
import styles from "./explore.module.css";

const TOTAL_COLUMN_COUNT = SET_PACK_COLUMNS.length + 1;
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

export default function SetPackMetrics({ sets, targets, eraFilter }) {
  const [sort, setSort] = useState({ key: "modeledReturn", direction: "desc" });
  const [query, setQuery] = useState("");
  const [expandedSetId, setExpandedSetId] = useState(null);
  const merged = mergeSetEconomics(sets, targets);
  const filtered = merged.filter((row) => {
    if (eraFilter && String(row.eraName).toLowerCase() !== String(eraFilter).toLowerCase()) return false;
    const needle = query.trim().toLowerCase();
    return !needle || `${row.setName || ""} ${row.eraName || ""}`.toLowerCase().includes(needle);
  });
  const rows = useMemo(() => sortSetPackMetrics(filtered, sort.key, sort.direction), [filtered, sort]);
  const change = (key) => setSort((current) => ({ key, direction: current.key === key && current.direction === "desc" ? "asc" : "desc" }));
  const toggle = (setId) => setExpandedSetId((current) => current === setId ? null : setId);
  return <section data-set-pack-metrics>
    <div className="mb-3 grid items-end gap-3 md:grid-cols-[1fr_minmax(14rem,22rem)_auto]" data-pack-economics-toolbar><div><h2 className="text-lg font-semibold">Pack Economics by Set</h2><p className="text-xs text-[var(--text-secondary)]">Canonical V3 Set aggregates with published product-family detail.</p></div><TableSearchInput value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sets..." ariaLabel="Search Pack Economics sets" /><span className="whitespace-nowrap text-right text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]"><span className="tabular-nums text-[var(--text-primary)]">{rows.length}</span> shown</span></div>
    <div className={`${styles.surface} hidden overflow-x-auto desk:block`}><table className={styles.table}><caption className="sr-only">Pack Economics by Set. Parent metrics are canonical V3 Set aggregates.</caption><thead className={styles.head}><tr><th className="min-w-52">Set</th>{SET_PACK_COLUMNS.map(([key, label]) => <th key={key} className={styles.numeric} aria-sort={sort.key === key ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}><button type="button" className={styles.sortButton} onClick={() => change(key)}>{label}</button></th>)}</tr></thead><tbody>{rows.map((row) => { const expanded = expandedSetId === row.setId; return <Fragment key={row.setId}><tr className={styles.row} data-set-pack-parent-row={row.setId}><td><div className="flex items-center gap-2"><button type="button" onClick={() => toggle(row.setId)} aria-expanded={expanded} aria-controls={`family-economics-${row.setId}`} aria-label={`${expanded ? "Hide" : "View"} Product-Family Economics for ${row.setName}`} className="relative z-[2] flex h-7 w-7 flex-none items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-white/5 hover:text-[var(--text-primary)]"><span aria-hidden="true" className={`transition-transform ${expanded ? "rotate-90" : ""}`}>›</span></button><Identity row={row} /></div></td>{SET_PACK_COLUMNS.map(([key]) => <td key={key} className={`${styles.numeric} tabular-nums`}>{formatSetMetric(key, row[key]) || "—"}</td>)}</tr>{expanded ? <tr className="family-detail-row" data-family-detail-row={row.setId}><td colSpan={TOTAL_COLUMN_COUNT} className="border-b border-[var(--ex-line-strong)] bg-[rgba(2,8,23,0.34)] px-4 py-3"><FamilyMatrix rows={row.familyEconomics} setId={row.setId} /></td></tr> : null}</Fragment>; })}</tbody></table></div>
    <ul className="space-y-2.5 desk:hidden">{rows.map((row) => { const expanded = expandedSetId === row.setId; return <li key={row.setId} className={`${styles.surface} rounded-xl p-3.5`} data-set-pack-mobile-row={row.setId}><div className="flex items-center justify-between gap-2"><Identity row={row} /><button type="button" onClick={() => toggle(row.setId)} aria-expanded={expanded} aria-controls={`family-economics-${row.setId}`} className="min-h-11 px-2 text-xs text-[rgb(var(--ex-teal))]">{expanded ? "Hide families" : "View families"}</button></div><dl className="mt-3 grid grid-cols-2 gap-2">{["modeledReturn", "typicalOpening", "entertainmentCost", "typicalRetention"].map((key) => <div key={key}><dt className="text-[.65rem] uppercase text-[var(--text-secondary)]">{SET_PACK_COLUMNS.find((column) => column[0] === key)[1]}</dt><dd>{formatSetMetric(key, row[key]) || "—"}</dd></div>)}</dl><p className="mt-2 border-t border-[var(--ex-line)] pt-2 text-xs text-[var(--text-secondary)]">Pack {formatSetMetric("packPrice", row.packPrice) || "—"} · Break-even {formatSetMetric("modelBreakEven", row.modelBreakEven) || "—"} · Recover {formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"}</p>{expanded ? <div className="mt-2 border-t border-[var(--border-subtle)] pt-1"><FamilyMatrix rows={row.familyEconomics} setId={row.setId} /></div> : null}</li>; })}</ul>
  </section>;
}
