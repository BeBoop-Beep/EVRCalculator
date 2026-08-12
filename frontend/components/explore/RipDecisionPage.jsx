"use client";

import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import { getRipPageIconPresentation } from "./ripPageIconPresentation.mjs";
import RipDistributionChart from "./RipDistributionChart";
import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import InfoPopover from "@/components/ui/InfoPopover";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import styles from "./RipDecisionPage.module.css";

// A reader who opens a metric bubble wants the methodology, not a content hub,
// so this deep-links straight to the article rather than to /Articles.
const METHODOLOGY_ARTICLE_HREF = "/Articles/how-rip-score-works";

function Help({ text }) {
  return <InfoPopover text={text} learnMoreHref={METHODOLOGY_ARTICLE_HREF} learnMoreLabel="How the RIP Score works" />;
}

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function money(value) { return value === null ? "—" : currency.format(value); }
// One decimal, always. The canonical public scores are formatted identically on
// every surface, so the same set cannot read 88 here and 88.4 in the summary.
function score(value) { return value === null || value === undefined ? "—" : Number(value).toFixed(1); }
function rank(value, cohort) { return value === null ? "—" : `#${Math.round(value)}${cohort === null ? "" : ` of ${Math.round(cohort)}`}`; }
function probability(value) {
  if (value === null) return "—";
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1).replace(/\.0$/, "")}%`;
}

function IconCue({ name, role = "neutral", tier = null, contained = false, className = "h-4 w-4" }) {
  const presentation = getRipPageIconPresentation(role, tier);
  return <span className={`${contained ? `inline-flex h-10 w-10 items-center justify-center rounded-lg border ${presentation.containerClassName}` : "inline-flex items-center justify-center"} ${presentation.iconClassName}`} style={presentation.style}><SetPageIcon name={name} className={className} /></span>;
}

// One canonical public metric in the unified Verdict -> Why It Ranks card.
// Scores and ranks come directly from buildRipDecisionModel; the bar is a
// visual rendering of the same published relative score, not a new scale.
function EvidenceMetric({ metric, index }) {
  const presentation = getRipPageIconPresentation(metric.role, metric.tier);
  return (
    <div data-rip-evidence={metric.key} className={`${styles.whyMetric} py-3 md:px-5 md:first:pl-0 ${index ? "border-t border-[var(--border-subtle)] md:border-l md:border-t-0" : ""}`}>
      <dt className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]"><IconCue name={metric.icon} role={metric.role} tier={metric.tier} className="h-3.5 w-3.5" />{metric.label}<Help text={metric.help} /></dt>
      <dd className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1"><span className="text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">{score(metric.score)}</span>{metric.score === null ? null : <span className="text-xs font-medium text-[var(--text-secondary)]">/100</span>}<span className="text-xs tabular-nums text-[var(--text-secondary)]">{metric.rankLabel ? `${metric.rankLabel} ` : ""}{rank(metric.rank, metric.cohortSize)}</span>{metric.tier ? <span className="text-xs font-semibold" style={{ color: presentation.style.color }}>{metric.tier} Tier</span> : null}</dd>
      <dd className={`${styles.driverTrack} mt-2 h-1 w-full overflow-hidden rounded-full bg-[var(--border-subtle)]`}>{metric.score === null ? null : <span className="block h-full rounded-full" style={{ width: `${metric.score}%`, backgroundColor: presentation.style.color }} />}</dd>
    </div>
  );
}

function ChaseCard({ card }) {
  const name = card?.name || "Card name unavailable";
  const image = optimizedImageUrl(card?.imageUrl || card?.image_url || card?.images?.small || null, CARD_THUMBNAIL_WIDTH);
  const price = card?.marketPrice ?? card?.market_price ?? card?.currentPrice ?? card?.current_price ?? card?.price ?? null;
  const odds = card?.specificCardOddsDenominator ?? card?.specific_card_odds_denominator ?? card?.pullOddsDenominator ?? card?.pull_odds_denominator ?? null;
  const validOdds = Number.isFinite(Number(odds)) && Number(odds) > 0;
  return (
    <li className={`${styles.chaseRow} grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0`}>
      <div className={`${styles.chaseImage} flex h-16 w-14 items-center justify-center overflow-hidden rounded-lg bg-[var(--surface-page)]/55`}>
        {image ? <img src={image} alt={`${name} card`} className="h-full w-full object-contain" loading="lazy" /> : null}
      </div>
      <div className="min-w-0"><p className="truncate font-semibold text-[var(--text-primary)]">{name}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{card?.rarity || "Rarity unavailable"}</p></div>
      <div className={`${styles.chasePrice} text-right`}><p className="font-semibold tabular-nums text-[var(--text-primary)]">{money(price === null ? null : Number(price))}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{validOdds ? `1 in ${Math.round(Number(odds)).toLocaleString("en-US")} packs` : "Odds unavailable"}</p></div>
    </li>
  );
}

export default function RipDecisionPage({ canonical, summary, chaseCards = [], cardCount = null, pullRateAssumptions, cardsHref, pullRatesHref, distributionBins = [], thresholdBins = [], chartMarkers = [], p50 = null, p95 = null, p99 = null, simulationPending = false, methodologyHref = METHODOLOGY_ARTICLE_HREF }) {
  const model = buildRipDecisionModel({ canonical, summary, pullRateAssumptions });
  const verdictPresentation = getRipPageIconPresentation("verdict");
  const headline = model.overall.rank === null ? "Modern Set RIP Ranking Unavailable" : `#${Math.round(model.overall.rank)} Modern Set to Rip Right Now`;
  const evidenceMetrics = [
    { key: "rip", label: "Overall RIP", help: "The overall relative ranking score for opening this set, combining opening economics and collector appeal on a 0–100 scale.", rankLabel: "Overall Rank", icon: "gauge", role: "overall", tier: model.overall.tier, score: model.overall.publicScore, rank: model.overall.rank, cohortSize: model.overall.cohortSize },
    { key: "financial", label: "Financial RIP", help: "Measures opening economics across normal outcomes, downside protection, upside potential, and efficiency.", icon: "shield", role: "financial", tier: null, score: model.financial.publicScore, rank: model.financial.rank, cohortSize: model.financial.cohortSize },
    { key: "collector", label: "Collector Appeal", help: "Reflects how desirable the set is to collectors, including the strength of its card pool beyond pure opening economics.", icon: "star", role: "collector", tier: null, score: model.collector.publicScore, rank: model.collector.rank, cohortSize: model.collector.cohortSize },
  ];
  const openingMetrics = [
    ["Expected Value", money(model.expectedValue), "long-run mean", "The long-run average return per pack. It is useful for averages, but an average pack is not the same as a typical pack."],
    ["Typical Opening", money(p50 ?? model.typicalOpening), "P50 / median", "The median simulated result: half of openings landed above this level and half below it."],
    ["Strong Upside", money(p95), "P95 threshold", "A meaningfully good outcome at the upper end of non-jackpot results."],
    ["Jackpot Upside", money(p99), "top-1% threshold", "Rare, exceptional high-end outcomes—not what normally happens."],
  ];
  return (
    <section id="set-detail-overview" data-rip-decision-page className={`${styles.page} scroll-mt-24 space-y-3 md:scroll-mt-28 md:space-y-3.5`}>
      <article data-rip-section="decision" className={`${styles.decision} set-glass-surface rounded-2xl border p-4 md:p-5`}>
        <div className={`${styles.decisionIntro} flex items-start gap-3.5`}><span className="inline-flex h-10 w-10 flex-none"><IconCue name="gauge" role="verdict" contained className="h-5 w-5" /></span><div className="min-w-0"><p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-bold uppercase tracking-[0.16em]"><span style={{ color: verdictPresentation.style.color }}>Verdict</span>{model.qualitativeLabel ? <><span aria-hidden="true" className="text-[var(--border-subtle)]">/</span><span data-rip-qualitative-label style={{ color: model.qualitativeLabel.color || undefined }}>{model.qualitativeLabel.label}</span></> : null}</p><h1 className={`${styles.headline} mt-1 max-w-4xl text-3xl font-semibold leading-tight tracking-tight text-[var(--text-primary)] md:text-[2.25rem]`}>{headline}</h1><p className="mt-1.5 max-w-4xl text-sm leading-snug text-[var(--text-secondary)] md:text-base">{model.verdict}</p></div></div>
        <div data-rip-section="why-it-ranks" className="mt-4 border-t border-[var(--border-subtle)] pt-4">
          <h2 className="flex items-center gap-2.5 text-xl font-semibold text-[var(--text-primary)]"><IconCue name="analysis" />Why It Ranks <Help text="This set’s overall opening verdict, based on Overall RIP, Financial RIP, and Collector Appeal relative to other ranked sets." /></h2>
          <dl className={`${styles.whyGrid} mt-2 grid md:grid-cols-3`}>
            {evidenceMetrics.map((metric, index) => <EvidenceMetric key={metric.key} metric={metric} index={index} />)}
          </dl>
          <p className={`${styles.takeaway} mt-2 flex items-start gap-2 border-t border-[var(--border-subtle)] pt-2.5 text-xs leading-snug text-[var(--text-secondary)]`}><IconCue name="bulb" role="takeaway" className="mt-0.5 h-4 w-4" /><span><span className="font-semibold text-[var(--text-primary)]">The takeaway:</span> {model.takeaway}</span></p>
        </div>
      </article>

      <article id="set-detail-outcome-distribution" data-rip-section="simulation-evidence" className="set-glass-surface min-w-0 scroll-mt-24 rounded-2xl border p-4 md:scroll-mt-28 md:p-5">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-[var(--text-primary)]">What Do the Simulated Openings Actually Look Like? <Help text="This modeled pack-return distribution shows typical outcomes, better-than-normal results, and how often value reaches key thresholds." /></h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">The modeled return distribution, with today&apos;s pack price plotted on the same value axis.</p>
        <dl className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--border-subtle)] lg:grid-cols-4">
          {openingMetrics.map(([label, value, helper, help]) => <div key={label} className="min-w-0 bg-[var(--surface-panel)] p-3"><dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}<Help text={help} /></dt><dd className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd><dd className="text-[11px] text-[var(--text-secondary)]">{helper}</dd></div>)}
        </dl>
        <div className="mt-4 min-w-0">
          {distributionBins.length || thresholdBins.length ? <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} showTitle={false} flush /> : <p className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-8 text-center text-sm text-[var(--text-secondary)]">{simulationPending ? "Loading simulated opening evidenceâ€¦" : "Outcome distribution data is not available for this set yet."}</p>}
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)] pt-3 text-sm"><span className="text-[var(--text-secondary)]">Current pack price: <strong className="font-semibold text-[var(--text-primary)]">{money(model.packCost)}</strong></span><span className="text-[var(--text-secondary)]">Chance of recovering pack price: <strong className="font-semibold text-[var(--text-primary)]">{probability(model.recoverCostProbability)}</strong></span></div>
      </article>

      <article id="set-detail-financial-rip" data-rip-section="financial-evidence" className="set-glass-surface min-w-0 scroll-mt-24 rounded-2xl border p-4 md:scroll-mt-28 md:p-5">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-[var(--text-primary)]">Why Financial RIP Scores This Way <Help text="These factors explain the kinds of opening economics that make a set stronger or weaker as an opening option." /></h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">These factors highlight the main opening-economics signals used to evaluate Financial RIP.</p>
        <div className="mt-4"><FinancialRipV3Breakdown canonical={canonical} requestTimeout={false} /></div>
        <a href={methodologyHref} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 text-sm font-semibold text-[var(--accent)] transition-colors hover:border-[var(--accent)] hover:bg-[rgba(255,255,255,0.03)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View methodology <span aria-hidden="true">→</span></a>
      </article>

      <div className={`${styles.lowerGrid} grid gap-5 lg:grid-cols-2 lg:items-start`}>
        <article data-rip-section="chase-cards" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="cards" />What Can I Actually Pull?</h2>{chaseCards.length ? <ul className={`${styles.chaseList} mt-1`}>{chaseCards.slice(0, 3).map((card, index) => <ChaseCard key={card?.id || card?.canonicalCardId || `${card?.name}:${index}`} card={card} />)}</ul> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Chase-card data is unavailable for this set.</p>}<a href={cardsHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>{Number.isFinite(Number(cardCount)) && Number(cardCount) > 0 ? `View all ${Number(cardCount).toLocaleString("en-US")} cards →` : "View all cards →"}</a></article>
        <article data-rip-section="opening-odds" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="target" role="odds" />Your Opening Odds</h2>{model.openingOdds.length ? <dl className="mt-2">{model.openingOdds.map((row) => <div key={row.label} className={`${styles.oddsRow} flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] py-3 first:border-t-0`}><dt className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><IconCue name="target" role="odds" />{row.label}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">1 in {Number(row.denominator).toLocaleString("en-US", { maximumFractionDigits: 1 })} packs</dd></div>)}</dl> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Consumer-summary odds are unavailable for this set.</p>}<a href={pullRatesHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>View full pull rates →</a></article>
      </div>
    </section>
  );
}
