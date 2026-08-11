"use client";

import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function money(value) { return value === null ? "—" : currency.format(value); }
function score(value) { return value === null ? "—" : Number(value).toFixed(1).replace(/\.0$/, ""); }
function rank(value, cohort) { return value === null ? "—" : `#${Math.round(value)}${cohort === null ? "" : ` of ${Math.round(cohort)}`}`; }
function probability(value) {
  if (value === null) return "—";
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1).replace(/\.0$/, "")}%`;
}

function ChaseCard({ card }) {
  const name = card?.name || "Card name unavailable";
  const image = card?.imageUrl || card?.image_url || card?.images?.small || null;
  const price = card?.marketPrice ?? card?.market_price ?? card?.currentPrice ?? card?.current_price ?? card?.price ?? null;
  const odds = card?.specificCardOddsDenominator ?? card?.specific_card_odds_denominator ?? card?.pullOddsDenominator ?? card?.pull_odds_denominator ?? null;
  const validOdds = Number.isFinite(Number(odds)) && Number(odds) > 0;
  return (
    <li className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
      <div className="flex h-16 w-14 items-center justify-center overflow-hidden rounded-lg bg-[var(--surface-page)]/55">
        {image ? <img src={image} alt={`${name} card`} className="h-full w-full object-contain" loading="lazy" /> : null}
      </div>
      <div className="min-w-0"><p className="truncate font-semibold text-[var(--text-primary)]">{name}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{card?.rarity || "Rarity unavailable"}</p></div>
      <div className="text-right"><p className="font-semibold tabular-nums text-[var(--text-primary)]">{money(price === null ? null : Number(price))}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{validOdds ? `1 in ${Math.round(Number(odds)).toLocaleString("en-US")} packs` : "Odds unavailable"}</p></div>
    </li>
  );
}

export default function RipDecisionPage({ canonical, summary, chaseCards = [], cardCount = null, pullRateAssumptions, cardsHref, pullRatesHref }) {
  const model = buildRipDecisionModel({ canonical, summary, pullRateAssumptions });
  const headline = model.overall.rank === null ? "Modern Set RIP Ranking Unavailable" : `#${Math.round(model.overall.rank)} Modern Set to Rip Right Now`;
  const metrics = [
    ["Pack Price", money(model.packCost), "per pack", "tag"],
    ["Expected Value", money(model.expectedValue), "long-run avg.", "trend"],
    ["Typical Opening", money(model.typicalOpening), "middle opening", "package"],
    ["Recover Your Cost", probability(model.recoverCostProbability), "beat pack cost", "target"],
  ];
  return (
    <section id="set-detail-overview" data-rip-decision-page className="scroll-mt-24 space-y-3 md:scroll-mt-28 md:space-y-3.5">
      <article data-rip-section="decision" className="set-glass-surface rounded-2xl border p-4 md:p-5">
        <div className="flex items-start gap-3.5"><span className="inline-flex h-10 w-10 flex-none items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_35%,transparent)] bg-[color:color-mix(in_srgb,var(--accent)_10%,transparent)] text-[var(--accent)]"><SetPageIcon name="trophy" className="h-5 w-5" /></span><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">Verdict</p><h1 className="mt-1 max-w-4xl text-3xl font-semibold leading-tight tracking-tight text-[var(--text-primary)] md:text-[2.25rem]">{headline}</h1><p className="mt-1.5 max-w-4xl text-sm leading-snug text-[var(--text-secondary)] md:text-base">{model.verdict}</p></div></div>
        <dl className="mt-4 grid grid-cols-2 border-t border-[var(--border-subtle)] pt-2 md:grid-cols-4">
          {metrics.map(([label, value, helper, icon], index) => <div key={label} className={`grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-x-2 px-2 py-2 first:pl-0 md:px-4 md:first:pl-0 ${index % 2 ? "border-l border-[var(--border-subtle)]" : ""} ${index > 1 ? "border-t border-[var(--border-subtle)] md:border-t-0" : ""} ${index === 2 ? "md:border-l" : ""}`}><span className="row-span-3 mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_9%,transparent)] text-[var(--accent)]"><SetPageIcon name={icon} /></span><dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</dt><dd className="mt-0.5 text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)] md:text-2xl">{value}</dd><dd className="text-[11px] leading-tight text-[var(--text-secondary)]">{helper}</dd></div>)}
        </dl>
      </article>

      <article data-rip-section="why-it-ranks" className="set-glass-surface rounded-2xl border p-4 md:p-5">
        <h2 className="flex items-center gap-2.5 text-xl font-semibold text-[var(--text-primary)]"><span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_10%,transparent)] text-[var(--accent)]"><SetPageIcon name="star" /></span>Why It Ranks {model.overall.rank === null ? "" : `#${Math.round(model.overall.rank)}`}</h2>
        <dl className="mt-3 grid md:grid-cols-3">
          {[["Financial Quality", model.financial.absoluteScore, model.financial, "shield"], ["Collector Appeal", model.collector.absoluteScore, model.collector, "star"]].map(([label, value, block, icon], index) => <div key={label} className={`grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2.5 py-2 md:px-5 md:first:pl-0 ${index ? "border-t border-[var(--border-subtle)] md:border-l md:border-t-0" : ""}`}><span className="row-span-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_8%,transparent)] text-[var(--accent)]"><SetPageIcon name={icon} /></span><dt className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</dt><dd className="text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{score(value)}</dd><dd className="text-xs text-[var(--text-secondary)]">Rank {rank(block.rank, block.cohortSize)}</dd></div>)}
          <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2.5 border-t border-[var(--border-subtle)] py-2 md:border-l md:border-t-0 md:px-5"><span className="row-span-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_8%,transparent)] text-[var(--accent)]"><SetPageIcon name="trophy" /></span><dt className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Overall RIP</dt><dd className="text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)]">{rank(model.overall.rank, model.overall.cohortSize)}</dd><dd className="text-xs text-[var(--text-secondary)]">Relative RIP Index: {score(model.overall.relativeScore)}</dd></div>
        </dl>
        <p className="mt-2 flex items-start gap-2 border-t border-[var(--border-subtle)] pt-2.5 text-xs leading-snug text-[var(--text-secondary)]"><SetPageIcon name="bulb" className="mt-0.5 h-4 w-4 flex-none text-[var(--accent)]" /><span><span className="font-semibold text-[var(--text-primary)]">The takeaway:</span> {model.takeaway}</span></p>
      </article>

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <article data-rip-section="chase-cards" className="set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4"><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_9%,transparent)] text-[var(--accent)]"><SetPageIcon name="diamond" /></span>What Can I Actually Pull?</h2>{chaseCards.length ? <ul className="mt-1">{chaseCards.slice(0, 3).map((card, index) => <ChaseCard key={card?.id || card?.canonicalCardId || `${card?.name}:${index}`} card={card} />)}</ul> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Chase-card data is unavailable for this set.</p>}<a href={cardsHref} className="mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">{Number.isFinite(Number(cardCount)) && Number(cardCount) > 0 ? `View all ${Number(cardCount).toLocaleString("en-US")} cards →` : "View all cards →"}</a></article>
        <article data-rip-section="opening-odds" className="set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4"><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--accent)_9%,transparent)] text-[var(--accent)]"><SetPageIcon name="target" /></span>Your Opening Odds</h2>{model.openingOdds.length ? <dl className="mt-2">{model.openingOdds.map((row) => <div key={row.label} className="flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] py-3 first:border-t-0"><dt className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><SetPageIcon name="target" className="h-4 w-4 text-[var(--accent)]" />{row.label}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">1 in {Math.round(row.denominator).toLocaleString("en-US")} packs</dd></div>)}</dl> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Consumer-summary odds are unavailable for this set.</p>}<a href={pullRatesHref} className="mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View full pull rates →</a></article>
      </div>
    </section>
  );
}
