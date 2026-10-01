"use client";

import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes.mjs";
import AnalyticsTableShell from "./AnalyticsTableShell";
import BestOpenDetailsPopover from "./BestOpenDetailsPopover";
import SetIdentity from "./SetIdentity";
import { ECONOMIC_KEYS, SET_PACK_COLUMNS, filterPackEconomicsSets, formatPackEconomicsValue, sortPackEconomicsSets } from "./setPackMetricsSelector.mjs";
import styles from "./explore.module.css";

const DEFINITIONS = {
  productFamilyCount: "Distinct modeled sealed-product families in this Set.",
  productCount: "Exact modeled sealed products represented by the contract.",
  averagePackCostPerPack: "Average modeled purchase cost per pack.",
  expectedValuePerPack: "Average modeled card value per pack.",
  modeledReturnOnSpend: "Modeled card value divided by purchase cost.",
  chanceToRecoverCost: "Modeled chance that an opening recovers its purchase cost.",
  entertainmentCostPerPack: "Average pack cost not recovered by modeled card value.",
  bestOpenPrice: "The highest modeled purchase price where opening this product still meets its Best-Open comparison threshold.",
};

function setHref(row) {
  return buildTcgSetHrefFromTarget({ target_type: "set", target_id: row.setId, setId: row.setId, canonical_key: row.canonicalKey, name: row.setName });
}
const setTarget = (row) => ({ target_id: row.setId, set_id: row.setId, name: row.setName, canonical_key: row.canonicalKey, era: row.era?.eraName, logo_image_url: row.logoImageUrl, symbol_image_url: row.symbolImageUrl });

function Numeric({ children, className = "" }) {
  return <td className={`${styles.numeric} tabular-nums ${className}`}>{children ?? "—"}</td>;
}

const LockedMetric = () => <span className="text-xs font-medium text-[var(--text-secondary)]" aria-label="Requires Index Plus">Locked</span>;

function SetRow({ row, expanded, toggle, entitled }) {
  return <tr className={`${styles.row} bg-white/[.018]`} data-set-pack-parent-row={row.setId}>
    <td><div className="flex min-w-0 items-center gap-2"><button type="button" onClick={toggle} aria-expanded={expanded} aria-controls={`pack-products-${row.setId}`} aria-label={`${expanded ? "Hide" : "View"} exact Products for ${row.setName}`} className="flex h-8 w-8 flex-none items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-white/5"><span aria-hidden="true" className={`text-lg transition-transform ${expanded ? "rotate-90" : ""}`}>›</span></button><Link href={setHref(row)} className="min-w-0 hover:underline"><SetIdentity target={setTarget(row)} variant="compact" /></Link></div></td>
    <Numeric>{formatPackEconomicsValue("productFamilyCount", row.productFamilyCount)}</Numeric>
    <Numeric>{formatPackEconomicsValue("productCount", row.productCount)}</Numeric>
    {ECONOMIC_KEYS.map((key) => <Numeric key={key}>{entitled || key === "averagePackCostPerPack" ? formatPackEconomicsValue(key, row[key]) : <LockedMetric />}</Numeric>)}
    <Numeric>{entitled ? <><span className="text-[var(--text-secondary)]">—</span><span className="sr-only">No Set-level Best-Open aggregate</span></> : <LockedMetric />}</Numeric>
  </tr>;
}

function ProductRow({ product, first, setId }) {
  return <tr id={first ? `pack-products-${setId}` : undefined} className="border-b border-white/[.025] bg-[rgba(2,8,23,.18)] text-[var(--text-secondary)]" data-pack-product-row={product.sealedProductId}>
    <th scope="row" className="px-2 py-2 text-left text-xs font-normal"><Link href={buildSealedProductHref(product) || "#"} className="ml-10 inline-flex hover:underline">{product.productName || "Exact Product"}</Link><span className="sr-only">Exact Product</span>{product.packCount ? <span className="ml-10 block text-[10px]">{product.packCount} packs · {product.familyKey || "Product"}</span> : null}</th>
    <Numeric><span className="text-[var(--text-secondary)]">—</span></Numeric><Numeric>1</Numeric>
    {ECONOMIC_KEYS.map((key) => <Numeric key={key}>{formatPackEconomicsValue(key, product[key]) || <span className="text-[var(--text-secondary)]">—</span>}</Numeric>)}
    <Numeric><BestOpenDetailsPopover row={product} /></Numeric>
  </tr>;
}

function MetricList({ source, includeBestOpen = false, entitled = true }) {
  return <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">{ECONOMIC_KEYS.map((key) => <div key={key}><dt className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">{SET_PACK_COLUMNS.find(([column]) => column === key)?.[1]}</dt><dd className="tabular-nums">{entitled || key === "averagePackCostPerPack" ? formatPackEconomicsValue(key, source?.[key]) || "—" : <LockedMetric />}</dd></div>)}{includeBestOpen ? <div><dt className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">Best-Open Price</dt><dd className="font-semibold tabular-nums">{entitled ? <BestOpenDetailsPopover row={source} /> : <LockedMetric />}</dd></div> : null}</dl>;
}

function MobileSet({ row, expanded, toggle, entitled }) {
  return <li className={`${styles.surfaceQuiet} rounded-xl p-3.5`} data-set-pack-mobile-row={row.setId}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><Link href={setHref(row)} className="hover:underline"><SetIdentity target={setTarget(row)} variant="mobileRanking" /></Link><p className="mt-1 text-xs text-[var(--text-secondary)]">{row.productFamilyCount} families · {row.productCount} products</p></div>{entitled ? <button type="button" onClick={toggle} aria-expanded={expanded} aria-controls={`mobile-pack-products-${row.setId}`} aria-label={`${expanded ? "Hide" : "View"} exact Products for ${row.setName}`} className="min-h-11 shrink-0 text-xs font-semibold text-[var(--text-primary)]">{expanded ? "Hide products" : "View products"}</button> : null}</div><MetricList source={row} entitled={entitled} />{expanded ? <ul id={`mobile-pack-products-${row.setId}`} className="mt-3 space-y-2 border-t border-[var(--border-subtle)] pt-3">{(row.products || []).map((product) => <li key={product.sealedProductId} className="rounded-lg bg-white/[.025] p-3" data-pack-product-mobile={product.sealedProductId}><Link href={buildSealedProductHref(product) || "#"} className="text-sm font-semibold hover:underline">{product.productName || "Exact Product"}</Link><p className="mt-1 text-[10px] text-[var(--text-secondary)]">{product.packCount ? `${product.packCount} packs · ` : ""}{product.familyKey || "Product"}</p><MetricList source={product} includeBestOpen bestOpen={formatPackEconomicsValue("bestOpenPrice", product.bestOpenPrice)} /></li>)}</ul> : null}</li>;
}

export default function SetPackMetrics({ contract, eraFilter, entitled = true }) {
  const [sort, setSort] = useState({ key: entitled ? "modeledReturnOnSpend" : "setName", direction: entitled ? "desc" : "asc" });
  const [query, setQuery] = useState("");
  const [expandedSetId, setExpandedSetId] = useState(null);
  const filtered = useMemo(() => filterPackEconomicsSets(contract?.sets, query, eraFilter), [contract, eraFilter, query]);
  const rows = useMemo(() => sortPackEconomicsSets(filtered, sort.key, sort.direction), [filtered, sort]);
  useEffect(() => { if (expandedSetId && !rows.some((row) => row.setId === expandedSetId)) setExpandedSetId(null); }, [expandedSetId, rows]);
  const changeSort = (key) => { if (key === "bestOpenPrice") return; setSort((current) => ({ key, direction: current.key === key && current.direction === "desc" ? "asc" : "desc" })); };
  const freshness = contract?.bestOpenSourceMarketDate ? `Best-Open as of ${contract.bestOpenSourceMarketDate}${contract.bestOpenFreshnessStatus === "older" ? " · independently dated" : ""}` : null;
  return <AnalyticsTableShell title="Pack Economics by Set" info="Set identity, modeled counts, and average pack cost are public. Component economics and Best-Open require Index Plus." query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search Sets…" searchLabel="Search Sets" context={freshness} shown={rows.length} marketDate={contract?.openingEconomicsMarketDate || null}>
    <section data-set-pack-metrics data-pack-economics-entitled={entitled ? "true" : "false"}>
      <div className="hidden overflow-x-auto desk:block"><table className={`${styles.table} min-w-[68rem] table-fixed`}><caption className="sr-only">Pack Economics hierarchy. Each expanded Set contains aligned exact Product rows.</caption><colgroup><col className={styles.colPackEconomicsIdentity} /><col span="2" className={styles.colPackEconomicsCount} /><col span="5" className={styles.colPackEconomicsMetric} /><col className={styles.colPackEconomicsBestOpen} /></colgroup><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr><th><button type="button" className={styles.sortButton} onClick={() => changeSort("setName")}>Set / Product</button></th>{SET_PACK_COLUMNS.map(([key, label]) => <th key={key} className={styles.numeric} aria-sort={sort.key === key ? sort.direction === "asc" ? "ascending" : "descending" : undefined}><span className="inline-flex items-center justify-end gap-1"><button type="button" disabled={key === "bestOpenPrice" || (!entitled && !["productFamilyCount", "productCount", "averagePackCostPerPack"].includes(key))} className={styles.sortButton} onClick={() => changeSort(key)}>{label}</button><InfoPopover text={DEFINITIONS[key]} /></span></th>)}</tr></thead><tbody>{rows.map((row) => { const expanded = entitled && expandedSetId === row.setId; return <Fragment key={row.setId}><SetRow row={row} expanded={expanded} entitled={entitled} toggle={() => entitled && setExpandedSetId((current) => current === row.setId ? null : row.setId)} />{expanded ? (row.products || []).map((product, productIndex) => <ProductRow key={product.sealedProductId} product={product} setId={row.setId} first={productIndex === 0} />) : null}</Fragment>; })}</tbody></table></div>
      <ul className="space-y-2.5 p-3 desk:hidden">{rows.map((row) => <MobileSet key={row.setId} row={row} expanded={entitled && expandedSetId === row.setId} toggle={() => entitled && setExpandedSetId((current) => current === row.setId ? null : row.setId)} entitled={entitled} />)}</ul>
    </section>
  </AnalyticsTableShell>;
}
