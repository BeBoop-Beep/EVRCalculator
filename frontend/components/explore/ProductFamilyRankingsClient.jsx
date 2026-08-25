"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import ExploreTableClient from "./ExploreTableClient";
import SegmentedControl from "@/components/ui/SegmentedControl";
import DarkSelect from "@/components/ui/DarkSelect";
import InfoPopover from "@/components/ui/InfoPopover";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { getTierTone } from "@/lib/explore/interpretationTone";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import styles from "./explore.module.css";

const SORT_OPTIONS = Object.freeze([
  { value: "overallRipScore", label: "Sort: Overall RIP" }, { value: "financialRipScore", label: "Sort: Financial RIP" },
  { value: "collectorAppealScore", label: "Sort: Collector Appeal" }, { value: "marketPrice", label: "Sort: Market Price" },
  { value: "expectedValue", label: "Sort: Expected Value" }, { value: "chanceToRecoverCost", label: "Sort: Chance to Recover Cost" },
]);
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const COLUMN_HELP = Object.freeze({
  overall: "Overall RIP combines Financial RIP and Collector Appeal to compare how favorable this product is to open.",
  tier: "Tier summarizes this product's Overall RIP score using the canonical S–F score bands.",
  financial: "How favorable this product's modeled financial outcome profile is relative to its current price.",
  collector: "How strong the set's collector-facing appeal is under the current Collector Appeal model.",
  marketPrice: "The current tracked market price used for this product's RIP calculations.",
  expectedValue: "Average modeled value across simulated openings.",
  recovery: "The modeled probability that an opening returns at least the product's current market price.",
  formatStrength: "How this product ranks against other products in the same sealed-product format.",
});
const number = (value) => Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : null;
const pluralFamilyLabel = (label) => ({ "Elite Trainer Box": "Elite Trainer Boxes", "Pokémon Center Elite Trainer Box": "Pokémon Center Elite Trainer Boxes", "Booster Box": "Booster Boxes", "Enhanced Booster Box": "Enhanced Booster Boxes" }[label] || `${label}s`);

export function filterAndSortProducts(products, query, sortKey) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  return (Array.isArray(products) ? products : []).filter((product) => !needle || [product?.productName, product?.setName].some((value) => String(value || "").toLocaleLowerCase().includes(needle))).slice().sort((a, b) => {
    const av = number(a?.[sortKey]); const bv = number(b?.[sortKey]);
    if (av === null) return bv === null ? Number(a.familyRank) - Number(b.familyRank) : 1;
    if (bv === null) return -1;
    return bv - av || Number(a.familyRank) - Number(b.familyRank);
  });
}
const score = (value) => number(value) === null ? "Unavailable" : `${formatPublicRipScore(value)} / 10`;
const recovery = (value) => { const parsed = number(value); return parsed === null ? "Unavailable" : `${(100 * (parsed > 1 ? parsed / 100 : parsed)).toFixed(1)}%`; };
function productHref(product) { const base = buildTcgSetHrefFromTarget({ target_type: "set", target_id: product.setId, name: product.setName }); return `${base}?sealedProduct=${encodeURIComponent(product.sealedProductId)}`; }

export function productFormatStrength(product) {
  const rank = number(product?.familyRank); const size = number(product?.familySize); const tier = String(product?.familyTier || "").toUpperCase();
  const heading = rank === 1 ? "Format leader" : tier === "S" ? "Elite in format" : tier === "A" ? "Strong in format" : tier === "B" ? "Competitive in format" : "Ranks within format";
  return { heading, detail: rank && size ? `#${rank} of ${size} ${pluralFamilyLabel(product?.productFamilyLabel || "product")}` : "Format rank unavailable" };
}
function FormatStrength({ product }) { const text = productFormatStrength(product); const tone = product?.familyTier ? getTierTone(product.familyTier) : null; return <div data-product-format-strength className="flex min-w-[10rem] items-start gap-2.5"><span aria-hidden="true" className="mt-1 h-2.5 w-2.5 flex-none rotate-45 border" style={{borderColor:tone?.accentColor || "var(--accent)"}}/><span><strong className="block text-xs text-[var(--text-primary)]">{text.heading}</strong><span className="mt-1 block text-[10.5px] text-[var(--text-secondary)]">{text.detail}</span></span></div>; }
function HeaderWithInfo({ children, text }) { return <span className="inline-flex items-center gap-1 whitespace-nowrap">{children}<InfoPopover text={text}/></span>; }
function OverallRankingLockedPanel() { return <section className={`${styles.surface} set-glass-surface`} aria-label="Overall product rankings — coming soon"><div className="flex flex-col items-center gap-2 px-4 py-16 text-center"><h2 className="text-lg font-semibold text-[var(--text-primary)]">Overall Product Rankings</h2><p className="max-w-md text-sm text-[var(--text-secondary)]">Compare sealed products across formats at a common spending level.</p><p className="mt-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Coming Soon</p></div></section>; }

export default function ProductFamilyRankingsClient({ targets, productFamilyRankings, loadError }) {
  const families = productFamilyRankings?.families || {}; const familyEntries = Object.entries(families).filter(([, block]) => Number(block?.count) > 0);
  const [view, setView] = useState("sets"); const [sortKey, setSortKey] = useState("overallRipScore"); const [query, setQuery] = useState("");
  const selected = families[view]; const products = useMemo(() => filterAndSortProducts(selected?.products, query, sortKey), [selected, query, sortKey]);
  const productsActive = view !== "sets"; const changeView = (next) => { setQuery(""); setView(next === "products" ? "overall-locked" : "sets"); };
  return <>
    <SegmentedControl className="mb-3 inline-block" ariaLabel="Ranking view" variant="primary" value={productsActive ? "products" : "sets"} onChange={changeView} options={[{value:"sets",label:"Sets"},{value:"products",label:"Products"}]}/>
    {productsActive ? <nav aria-label="Product family" className="mb-3 flex gap-2 overflow-x-auto pb-1"><button type="button" onClick={()=>{setView("overall-locked");setQuery("");}} aria-pressed={view==="overall-locked"} className={`${styles.productFamilyTab} ${view==="overall-locked"?styles.productFamilyTabActive:""}`}>Overall</button>{familyEntries.map(([family,block])=><button key={family} type="button" onClick={()=>{setView(family);setQuery("");}} aria-pressed={view===family} className={`${styles.productFamilyTab} ${view===family?styles.productFamilyTabActive:""}`}>{pluralFamilyLabel(block.label)}</button>)}</nav>:null}
    {view === "sets" ? <ExploreTableClient targets={targets} loadError={loadError}/> : view === "overall-locked" ? <OverallRankingLockedPanel/> :
      <section className={`${styles.surface} set-glass-surface`} aria-label={`${selected?.label} rankings`}>
        <div className={`${styles.divider} grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_minmax(14rem,17rem)_minmax(14rem,17rem)] md:items-center`}><div><h2 className="font-semibold text-[var(--text-primary)]">Best {pluralFamilyLabel(selected?.label)} to Rip</h2><p className="text-xs text-[var(--text-secondary)]">Compared only with {pluralFamilyLabel(selected?.label)} · {selected?.count} ranked</p></div><input type="search" value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="Search products or sets..." aria-label="Search products or sets" className={`${styles.setMarketControl} w-full px-2.5 text-xs`}/><DarkSelect ariaLabel="Sort products" value={sortKey} onChange={setSortKey} options={SORT_OPTIONS} className="w-full md:justify-self-end"/></div>
        {products.length ? <><div className="hidden overflow-x-auto md:block"><table className={styles.table}><caption className="sr-only">{selected?.label} rankings. Sorting preserves official family rank.</caption><thead className={styles.head}><tr><th>Rank</th><th>Product / Set</th><th><HeaderWithInfo text={COLUMN_HELP.overall}>Overall RIP</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.tier}>Tier</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.financial}>Financial RIP</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.collector}>Collector Appeal</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.marketPrice}>Market Price</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.expectedValue}>Expected Value</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.recovery}>Chance to Recover Cost</HeaderWithInfo></th><th><HeaderWithInfo text={COLUMN_HELP.formatStrength}>Format Strength</HeaderWithInfo></th></tr></thead><tbody>{products.map((p)=><tr key={p.sealedProductId} className={styles.row}><td className={styles.numeric}>#{p.familyRank}</td><td><Link href={productHref(p)} className={styles.rowLink}><span className="block font-semibold text-[var(--text-primary)]">{p.productName}</span><span className="text-xs text-[var(--text-secondary)]">{p.setName} · {p.productFamilyLabel}</span></Link></td><td className={styles.numeric}><RipScoreBadge score={p.overallRipScore} tier={p.familyTier}/></td><td className="text-center"><RipTierMark tier={p.familyTier}/></td><td className={styles.numeric}>{score(p.financialRipScore)}</td><td className={styles.numeric}>{score(p.collectorAppealScore)}</td><td className={styles.numeric}>{number(p.marketPrice)===null?"Unavailable":money.format(p.marketPrice)}</td><td className={styles.numeric}>{number(p.expectedValue)===null?"Unavailable":money.format(p.expectedValue)}</td><td className={styles.numeric}>{recovery(p.chanceToRecoverCost)}</td><td><FormatStrength product={p}/></td></tr>)}</tbody></table></div>
        <div className="space-y-2 p-3 md:hidden">{products.map((p)=><Link key={p.sealedProductId} href={productHref(p)} className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto_auto] items-center gap-2.5`}><b className="text-right">#{p.familyRank}</b><div className="min-w-0"><p className="truncate font-semibold">{p.productName}</p><p className="truncate text-xs text-[var(--text-secondary)]">{p.setName}</p></div><RipScoreBadge score={p.overallRipScore} tier={p.familyTier} compact/><RipTierMark tier={p.familyTier}/></Link>)}</div></> : <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">No products match your search.</p>}
      </section>}
  </>;
}
