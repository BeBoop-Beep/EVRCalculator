"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import ExploreTableClient from "./ExploreTableClient";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";

const METRICS = Object.freeze({
  overallRipScore: ["Overall RIP", false], financialRipScore: ["Financial RIP", false],
  collectorAppealScore: ["Collector Appeal", false], marketPrice: ["Market Price", true],
  expectedValue: ["Model Break-Even", true], medianValue: ["Typical Opening", true],
  chanceToRecoverCost: ["Chance to Recover Cost", false],
});
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const number = (value) => Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : null;
const display = (product, metric) => {
  const value = number(product?.[metric]);
  if (value === null) return "Unavailable";
  if (METRICS[metric][1]) return money.format(value);
  if (metric === "chanceToRecoverCost") return `${(100 * (value > 1 ? value / 100 : value)).toFixed(1)}%`;
  return `${formatPublicRipScore(value)} / 10`;
};
function productHref(product) {
  const base = buildTcgSetHrefFromTarget({ target_type: "set", target_id: product.setId, name: product.setName });
  return `${base}?sealedProduct=${encodeURIComponent(product.sealedProductId)}`;
}

/**
 * Locked placeholder for the future cross-format budget-normalized ranking
 * capability. Intentionally renders NO ranking data of any kind — no sample
 * ranks, no budget selector, no product-tier or pricing copy, no internal
 * methodology detail. Just enough to signal something is coming.
 */
function OverallRankingLockedPanel() {
  return (
    <section
      className={`${styles.surface} set-glass-surface`}
      aria-label="Overall product rankings — coming soon"
    >
      <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Overall Product Rankings</h2>
        <p className="max-w-md text-sm text-[var(--text-secondary)]">
          Compare sealed products across formats at a common spending level.
        </p>
        <p className="mt-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Coming Soon
        </p>
      </div>
    </section>
  );
}

export default function ProductFamilyRankingsClient({ targets, productFamilyRankings, loadError }) {
  const families = productFamilyRankings?.families || {};
  const familyEntries = Object.entries(families).filter(([, block]) => Number(block?.count) > 0);
  const [view, setView] = useState("sets");
  const [metric, setMetric] = useState("overallRipScore");
  const selected = families[view];
  const products = useMemo(() => [...(selected?.products || [])].sort((a, b) => {
    const av = number(a?.[metric]); const bv = number(b?.[metric]);
    if (av === null) return bv === null ? a.familyRank - b.familyRank : 1;
    if (bv === null) return -1;
    return bv - av || a.familyRank - b.familyRank;
  }), [selected, metric]);

  const productsActive = view !== "sets" && view !== "overall-locked";
  const openProducts = () => setView(familyEntries[0]?.[0] || "sets");
  const rankingView = productsActive ? "products" : view;
  const changeRankingView = (nextView) => nextView === "products" ? openProducts() : setView(nextView);
  return <>
    <SegmentedControl className="mb-3 inline-block" ariaLabel="Ranking view" variant="primary" value={rankingView} onChange={changeRankingView} options={[
      { value: "sets", label: "Sets" },
      { value: "products", label: "Individual Products", disabled: !familyEntries.length },
      { value: "overall-locked", label: "Overall" },
    ]} />
    {/*
      Locked preview of the future budget-normalized cross-format ranking
          capability. Deliberately shows no data of any kind — see
          OverallRankingLockedPanel below.
      <button type="button" onClick={() => setView("overall-locked")} aria-pressed={view === "overall-locked"} className={`whitespace-nowrap rounded-md px-4 py-2 text-xs font-semibold transition-colors ${view === "overall-locked" ? "bg-[var(--accent)] text-black" : "text-[var(--text-secondary)]"}`}>Overall</button>
    */}
    {productsActive ? <nav aria-label="Product family" className="mb-3 flex gap-2 overflow-x-auto pb-1">{familyEntries.map(([family, block]) => <button key={family} type="button" onClick={() => setView(family)} aria-pressed={view === family} className={`whitespace-nowrap rounded-full border px-3 py-2 text-xs font-semibold ${view === family ? "border-[var(--accent)] text-[var(--text-primary)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>{block.label}s</button>)}</nav> : null}
    {view === "sets" ? <ExploreTableClient targets={targets} loadError={loadError} /> :
     view === "overall-locked" ? <OverallRankingLockedPanel /> :
      <section className={`${styles.surface} set-glass-surface`} aria-label={`${selected?.label} rankings`}>
        <div className={`${styles.divider} flex flex-wrap items-center gap-3 px-4 py-3`}><div><h2 className="font-semibold text-[var(--text-primary)]">Best {selected?.label}s to Rip</h2><p className="text-xs text-[var(--text-secondary)]">Compared only with {selected?.label}s · {selected?.count} ranked</p></div><label className="ml-auto text-xs text-[var(--text-secondary)]">Metric <select value={metric} onChange={(event) => setMetric(event.target.value)} className="ml-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-2 py-2 text-[var(--text-primary)]">{Object.entries(METRICS).map(([key, [label]]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
        <div className="hidden overflow-x-auto md:block"><table className={styles.table}><caption className="sr-only">{selected?.label} rankings. Alternate sorting preserves official family rank.</caption><thead className={styles.head}><tr><th>Rank</th><th>Product / Set</th><th>Overall RIP</th><th>Financial RIP</th><th>Collector Appeal</th><th>Market Price</th><th>Model Break-Even</th><th>Typical Opening</th><th>Chance to Recover Cost</th></tr></thead><tbody>{products.map((product) => <tr key={product.sealedProductId} className={styles.row}><td>#{product.familyRank}</td><td><Link href={productHref(product)} className={styles.rowLink}><span className="block font-semibold text-[var(--text-primary)]">{product.productName}</span><span className="text-xs text-[var(--text-secondary)]">{product.setName} · {product.productFamilyLabel}</span></Link></td>{["overallRipScore", "financialRipScore", "collectorAppealScore", "marketPrice", "expectedValue", "medianValue", "chanceToRecoverCost"].map((key) => <td key={key} className={styles.numeric}>{display(product, key)}</td>)}</tr>)}</tbody></table></div>
        <div className="space-y-2 p-3 md:hidden">{products.map((product) => <Link key={product.sealedProductId} href={productHref(product)} className={styles.mobileRow}><div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2"><b className="text-right">#{product.familyRank}</b><div className="min-w-0"><p className="truncate font-semibold">{product.productName}</p><p className="truncate text-xs text-[var(--text-secondary)]">{product.setName} · {product.productFamilyLabel}</p></div><div className="text-right"><b className="block">{display(product, metric)}</b><span className="text-[10px] text-[var(--text-secondary)]">{METRICS[metric][0]}</span></div></div></Link>)}</div>
      </section>}
  </>;
}
