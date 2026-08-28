"use client";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { SET_PACK_COLUMNS, sortSetPackMetrics, formatSetMetric, mergeSetEconomics } from "./setPackMetricsSelector.mjs";
import styles from "./explore.module.css";

function FamilyEconomics({ rows }) {
  if (!rows?.length) return null;
  return <details className="mt-3"><summary className="cursor-pointer text-xs text-[rgb(var(--ex-teal))]">View Product-Family Economics</summary><div className="mt-2 grid gap-2">{rows.map(row => <div key={row.family} className="rounded-lg border border-[var(--ex-line)] p-2 text-xs"><b className="capitalize">{String(row.family).replaceAll("_", " ")}</b><p className="mt-1 text-[var(--text-secondary)]">{row.productSkuCount} products · Cost {formatSetMetric("packPrice", row.averageCostPerPack) || "—"} · Break-even {formatSetMetric("modelBreakEven", row.averageModelBreakEvenPerPack) || "—"} · Typical {formatSetMetric("typicalOpening", row.typicalOpeningPerPack) || "—"}</p><p className="text-[var(--text-secondary)]">Return {formatSetMetric("modeledReturn", row.modeledReturnOnSpend) || "—"} · Entertainment {formatSetMetric("entertainmentCost", row.averageEntertainmentCostPerPack) || "—"} · Retention {formatSetMetric("typicalRetention", row.typicalRetention) || "—"} · Recover {formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"}</p></div>)}</div></details>;
}

function Identity({ row }) {
  return <Link href={buildTcgSetHrefFromTarget(row.raw)} className="flex items-center gap-3">{row.logo ? <Image src={row.logo} width={64} height={36} alt="" className="h-9 w-14 object-contain" /> : null}<span>{row.setName}<small className="block text-[var(--text-secondary)]">Set RIP #{row.canonicalRank || "—"}</small></span></Link>;
}

export default function SetPackMetrics({ sets, targets, eraFilter }) {
  const [sort, setSort] = useState({ key: "modeledReturn", direction: "desc" });
  const filtered = mergeSetEconomics(sets, targets).filter(row => !eraFilter || String(row.eraName).toLowerCase() === String(eraFilter).toLowerCase());
  const rows = useMemo(() => sortSetPackMetrics(filtered, sort.key, sort.direction), [filtered, sort]);
  const change = key => setSort(current => ({ key, direction: current.key === key && current.direction === "desc" ? "asc" : "desc" }));
  return <section data-set-pack-metrics><header className="mb-3"><h2 className="text-lg font-semibold">Pack Economics by Set</h2><p className="text-xs text-[var(--text-secondary)]">All eligible modeled sealed products, normalized per pack. Sorting never changes the official Set RIP rank.</p></header>
    <div className={`${styles.surface} hidden overflow-x-auto desk:block`}><table className={styles.table}><thead className={styles.head}><tr><th>Set</th>{SET_PACK_COLUMNS.map(([key, label]) => <th key={key}><button onClick={() => change(key)}>{label} {sort.key === key ? (sort.direction === "asc" ? "↑" : "↓") : null}</button></th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.setId}><th className="min-w-64 text-left"><Identity row={row}/><FamilyEconomics rows={row.familyEconomics}/></th>{SET_PACK_COLUMNS.map(([key]) => <td key={key} className="text-right tabular-nums">{formatSetMetric(key, row[key]) || "—"}</td>)}</tr>)}</tbody></table></div>
    <ul className="space-y-2.5 desk:hidden">{rows.map(row => <li key={row.setId} className={`${styles.surface} rounded-xl p-3.5`}><Identity row={row}/><dl className="mt-3 grid grid-cols-2 gap-2">{["modeledReturn", "typicalOpening", "entertainmentCost", "typicalRetention"].map(key => <div key={key}><dt className="text-[.65rem] uppercase text-[var(--text-secondary)]">{SET_PACK_COLUMNS.find(column => column[0] === key)[1]}</dt><dd>{formatSetMetric(key, row[key]) || "—"}</dd></div>)}</dl><p className="mt-2 border-t border-[var(--ex-line)] pt-2 text-xs text-[var(--text-secondary)]">Pack {formatSetMetric("packPrice", row.packPrice) || "—"} · Break-even {formatSetMetric("modelBreakEven", row.modelBreakEven) || "—"} · Recover {formatSetMetric("chanceToRecoverCost", row.chanceToRecoverCost) || "—"}</p><FamilyEconomics rows={row.familyEconomics}/></li>)}</ul>
  </section>;
}
