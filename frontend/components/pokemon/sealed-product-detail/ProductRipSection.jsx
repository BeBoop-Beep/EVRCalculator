import Link from "next/link";
import InfoPopover from "@/components/ui/InfoPopover";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import { getRipTierPresentation } from "@/components/explore/ripTierPresentation.mjs";
import { finite, formatStrength, pluralFamilyLabel } from "./productDetailModel.mjs";

const money = (value) => finite(value) === null ? "Unavailable" : finite(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
const percent = (value) => finite(value) === null ? "Unavailable" : `${(finite(value) * 100).toFixed(1).replace(/\.0$/, "")}%`;

export function ProductRipLock() {
  return (
    <section data-product-rip-lock aria-labelledby="product-rip-lock-title" className="set-glass-surface relative min-h-48 overflow-hidden rounded-2xl border border-amber-300/20">
      <div aria-hidden="true" className="absolute inset-0 grid grid-cols-3 gap-3 p-5 opacity-20 blur-sm"><span className="rounded-xl bg-white/10" /><span className="rounded-xl bg-white/10" /><span className="rounded-xl bg-white/10" /></div>
      <div className="relative z-10 flex min-h-48 flex-col items-center justify-center bg-[rgba(2,6,23,.68)] px-5 py-7 text-center">
        <p className="text-xs font-bold uppercase tracking-[.14em] text-amber-300">🔒 Index Plus</p>
        <h2 id="product-rip-lock-title" className="mt-2 text-2xl font-semibold">Unlock Product RIP</h2>
        <p className="mt-2 max-w-xl text-sm text-[var(--text-secondary)]">See how this product ranks within its format and what its modeled opening outcomes look like.</p>
        <Link href="/pricing" className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-amber-300/40 bg-amber-300/10 px-4 text-sm font-semibold text-amber-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300">Explore Index Plus</Link>
      </div>
    </section>
  );
}

function Score({ label, value, info, primary = false }) {
  return <div className={`rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.4)] p-4 ${primary ? "sm:p-5" : ""}`}><dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.09em] text-[var(--text-secondary)]"><span>{label}</span>{info ? <InfoPopover text={info} /> : null}</dt><dd className={`mt-2 font-semibold tabular-nums ${primary ? "text-4xl" : "text-2xl"}`}>{finite(value) === null ? "Unavailable" : <>{formatPublicRipScore(value)} <span className="text-xs text-[var(--text-secondary)]">/10</span></>}</dd></div>;
}

export function ProductRipSection({ detail }) {
  const { rip, product } = detail;
  if (!rip.available) return <section data-product-rip-unavailable className="set-glass-surface rounded-2xl border p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">Product RIP</p><h2 className="mt-1 text-2xl font-semibold">Opening intelligence is not currently available for this product.</h2><p className="mt-2 text-sm text-[var(--text-secondary)]">This product does not have a current published, format-comparable opening result. Market and catalog information remain available.</p></section>;
  const tier = getRipTierPresentation(rip.publicTier, { strength: "hero" });
  return (
    <section data-product-rip-section aria-labelledby="product-rip-title" className="set-glass-surface rounded-2xl border p-4 sm:p-5">
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">Product RIP · Index Plus</p>
      <h2 id="product-rip-title" className="mt-1 text-2xl font-semibold">How favorable is opening this exact product?</h2>
      <p className="mt-1.5 max-w-3xl text-sm text-[var(--text-secondary)]">Product RIP measures this product and ranks it only against comparable products of the same format.</p>
      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,.75fr)]">
        <Score primary label="Overall RIP" value={rip.overallRipLeaderScore} />
        <div style={tier.style} className="rounded-xl border border-[var(--tier-border)] bg-[var(--tier-surface)] p-4"><p className="text-xs font-semibold uppercase tracking-[.09em] text-[var(--text-secondary)]">RIP Tier</p><p className="mt-2 text-3xl font-bold text-[var(--tier-color)]">{tier.tier || "Unavailable"}</p><p className="mt-2 text-sm font-semibold">{formatStrength(rip)}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">Format Rank · #{rip.familyRank} of {rip.familySize} {pluralFamilyLabel(product.productFamilyLabel)}</p></div>
      </div>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        <Score label="Financial RIP" value={rip.financialRipLeaderScore} />
        <Score label="Collector Appeal" value={rip.collectorAppealScore} info="Collector Appeal reflects the collector-facing appeal of the product's parent set. It is not recalculated simply because this product contains more packs." />
      </dl>
    </section>
  );
}

export const APPROVED_PRIMARY_OUTCOMES = [
  ["Expected Value", "expectedValue", "Average modeled gross market value across simulated openings.", money],
  ["Typical Opening", "medianValue", "The median modeled result — half of simulated openings finished above it and half below it.", money],
  ["Chance to Recover Cost", "chanceToRecoverCost", "Modeled probability that the opening's gross market value reaches or exceeds the product's current market price.", percent],
  ["Entertainment Cost", "entertainmentCost", "Purchase price minus modeled gross market value.", money],
  ["Realistic Upside", "p95Value", "The 95th-percentile opening value — roughly 5% of modeled openings reached this value or higher.", money],
  ["Jackpot Upside", "p99Value", "The 99th-percentile opening value — roughly 1% of modeled openings reached this value or higher.", money],
];

export function ProductOpeningProfile({ rip }) {
  const value = (key) => key === "entertainmentCost" ? rip.entertainmentCost?.entertainmentCost : rip[key];
  const composition = rip.composition || {};
  return (
    <section data-opening-outcome-profile aria-labelledby="opening-profile-title" className="set-glass-surface rounded-2xl border p-4 sm:p-5">
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">Index Plus</p><h2 id="opening-profile-title" className="mt-1 text-2xl font-semibold">Opening Outcome Profile</h2><p className="mt-1.5 text-sm text-[var(--text-secondary)]">What does opening this product actually look like?</p>
      <dl data-primary-outcome-metrics className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{APPROVED_PRIMARY_OUTCOMES.map(([label, key, info, formatter]) => <div data-primary-outcome={key} key={key} className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)] p-4"><dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.07em] text-[var(--text-secondary)]">{label}<InfoPopover text={info} /></dt><dd className="mt-2 text-xl font-semibold tabular-nums">{formatter(value(key))}</dd></div>)}</dl>
      <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-white/[.02] p-4"><h3 className="text-sm font-semibold">Product Composition</h3><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-[var(--text-secondary)]">Packs</dt><dd className="font-semibold">{finite(composition.packCount) ?? "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Random Packs</dt><dd className="font-semibold">{finite(composition.randomPackCount) ?? "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Modeled Guaranteed Components</dt><dd className="font-semibold">{finite(composition.guaranteedComponentCount) ?? "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Guaranteed Component Value</dt><dd className="font-semibold">{money(composition.guaranteedComponentMarketValue)}</dd></div></dl><p className="mt-3 text-xs text-[var(--text-secondary)]">Accessories are not assigned modeled market value under the current opening model.</p></div>
      <details className="mt-3 rounded-xl border border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]"><summary className="cursor-pointer font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">Additional outcome details</summary><dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><div><dt>P05 Opening</dt><dd className="font-semibold text-[var(--text-primary)]">{money(rip.p05Value)}</dd></div><div><dt>Expected Loss When Losing</dt><dd className="font-semibold text-[var(--text-primary)]">{money(rip.expectedLossWhenLosing)}</dd></div><div><dt>Median Loss When Losing</dt><dd className="font-semibold text-[var(--text-primary)]">{money(rip.medianLossWhenLosing)}</dd></div><div><dt>Modeled Return Ratio</dt><dd className="font-semibold text-[var(--text-primary)]">{finite(rip.totalValueToCostRatio) === null ? "Unavailable" : `${(rip.totalValueToCostRatio * 100).toFixed(1)}%`}</dd></div><div><dt>Entertainment Cost Per Pack</dt><dd className="font-semibold text-[var(--text-primary)]">{money(rip.entertainmentCost?.entertainmentCostPerPackEquivalent)}</dd></div></dl><p className="mt-4">Entertainment Cost uses gross modeled market value. Marketplace fees, shipping, liquidation friction, bid/ask spread, and grading are not deducted or assumed. It is the price of the modeled opening experience, not a loss prediction.</p></details>
    </section>
  );
}
