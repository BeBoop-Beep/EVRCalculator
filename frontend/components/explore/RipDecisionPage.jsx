"use client";

import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import { getRipPageIconPresentation } from "./ripPageIconPresentation.mjs";
import RipDistributionChart from "./RipDistributionChart";
import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import InfoPopover from "@/components/ui/InfoPopover";
import RankBadge from "@/components/ui/RankBadge";
import { topPercentToTier } from "@/constants/rankConfig";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import styles from "./RipDecisionPage.module.css";

// A reader who opens a metric bubble wants the methodology, not a content hub,
// so this deep-links straight to the article rather than to /Articles.
const METHODOLOGY_ARTICLE_HREF = "/Articles/how-rip-score-works";

function Help({ text, href = METHODOLOGY_ARTICLE_HREF, label = "How the RIP Score works" }) {
  return <InfoPopover text={text} learnMoreHref={href} learnMoreLabel={label} />;
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

function metricTier(metric) {
  if (metric?.tier) return String(metric.tier).toUpperCase();
  if (metric?.rank === null || metric?.cohortSize === null || metric.cohortSize <= 0) return null;
  return topPercentToTier((metric.rank / metric.cohortSize) * 100);
}

function scorePercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  return Math.min(100, Math.max(0, Number(value)));
}

function IconCue({ name, role = "neutral", tier = null, contained = false, className = "h-4 w-4" }) {
  const presentation = getRipPageIconPresentation(role, tier);
  return <span className={`${contained ? `inline-flex h-10 w-10 items-center justify-center rounded-lg border ${presentation.containerClassName}` : "inline-flex items-center justify-center"} ${presentation.iconClassName}`} style={presentation.style}><SetPageIcon name={name} className={className} /></span>;
}

// One canonical public metric in the unified Verdict -> Why It Ranks card.
// Scores and ranks come directly from buildRipDecisionModel; the bar is a
// visual rendering of the same published relative score, not a new scale.
function EvidenceMetric({ metric }) {
  const tier = metricTier(metric);
  const presentation = getRipPageIconPresentation(metric.role, tier);
  const percent = scorePercent(metric.score);
  return (
    <div data-rip-evidence={metric.key} className={`${styles.scoreCard} ${metric.key === "rip" ? styles.scoreCardOverall : ""}`} style={metric.key === "rip" ? { "--score-accent": presentation.style.color } : undefined}>
      <dt className="flex min-w-0 items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-[0.07em] text-[var(--text-primary)]"><IconCue name={metric.icon} role={metric.role} tier={tier} className="h-3.5 w-3.5" /><span>{metric.label}</span><Help text={metric.help} href={metric.methodologyHref} label={`How ${metric.label} works`} /></span>
        <RankBadge rank={tier} format="tier" size="compact" subtle />
      </dt>
      <dd className="mt-5 flex items-baseline gap-1"><span className={`${metric.key === "rip" ? "text-[2rem]" : "text-3xl"} font-semibold leading-none tabular-nums text-[var(--text-primary)]`}>{score(metric.score)}</span>{metric.score === null ? null : <span className="text-xs font-medium text-[var(--text-secondary)]">/100</span>}</dd>
      <dd className="mt-3 text-xs tabular-nums text-[var(--text-secondary)]">{metric.rankLabel ? `${metric.rankLabel} ` : ""}{rank(metric.rank, metric.cohortSize)}</dd>
      <dd className="mt-auto flex items-center gap-2 pt-4">
        <span className={`${styles.driverTrack} h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--border-subtle)]`} role="progressbar" aria-label={`${metric.label} score`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={percent === null ? "Score unavailable" : `${score(metric.score)} out of 100`}>
          {percent === null ? null : <span className="block h-full rounded-full" style={{ width: `${percent}%`, backgroundColor: presentation.style.color }} />}
        </span>
        <span className="w-8 text-right text-[11px] font-medium tabular-nums text-[var(--text-secondary)]">{percent === null ? "—" : `${Math.round(percent)}%`}</span>
      </dd>
    </div>
  );
}

// Mobile keeps the same metric model and canonical tier presentation as the
// desktop cards, but compresses the three outputs into one comparison deck.
function CompactEvidenceMetric({ metric }) {
  const tier = metricTier(metric);
  const presentation = getRipPageIconPresentation(metric.role, tier);
  const percent = scorePercent(metric.score);
  return (
    <div data-rip-compact-evidence={metric.key} className={`${styles.compactMetric} ${metric.key === "rip" ? styles.compactMetricOverall : ""}`} style={{ "--score-accent": presentation.style.color }}>
      <dt className={styles.compactLabel}><IconCue name={metric.icon} role={metric.role} tier={tier} className="h-3.5 w-3.5" /><span>{metric.label}</span><Help text={metric.help} href={metric.methodologyHref} label={`How ${metric.label} works`} /></dt>
      <dd className={styles.compactScore}><span>{score(metric.score)}</span>{metric.score === null ? null : <small>/100</small>}</dd>
      <dd className={styles.compactTier}><RankBadge rank={tier} format="tier" size="compact" subtle /></dd>
      <dd className={styles.compactRank}>{rank(metric.rank, metric.cohortSize).replace(" of ", " / ")}</dd>
      <dd className={styles.compactProgress}><span className={styles.compactTrack} role="progressbar" aria-label={`${metric.label} score`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={percent === null ? "Score unavailable" : `${score(metric.score)} out of 100`}>{percent === null ? null : <span style={{ width: `${percent}%`, backgroundColor: presentation.style.color }} />}</span></dd>
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
  const headline = model.overall.rank === null ? "Modern Set RIP Ranking Unavailable" : "Modern Set to Rip Right Now";
  const evidenceMetrics = [
    { key: "rip", label: "Overall RIP", help: "The overall relative ranking score for opening this set, combining opening economics and collector appeal on a 0–100 scale.", rankLabel: "Overall Rank", icon: "gauge", role: "overall", tier: model.overall.tier, score: model.overall.publicScore, rank: model.overall.rank, cohortSize: model.overall.cohortSize },
    { key: "financial", label: "Financial RIP", help: "Measures opening economics across normal outcomes, downside protection, upside potential, and efficiency.", methodologyHref: "/Articles/how-financial-rip-works", icon: "shield", role: "financial", tier: null, score: model.financial.publicScore, rank: model.financial.rank, cohortSize: model.financial.cohortSize },
    { key: "collector", label: "Collector Appeal", help: "Reflects how desirable the set is to collectors and how often the modeled pack can deliver a desirable Pokémon.", methodologyHref: "/Articles/how-collector-appeal-works", icon: "star", role: "collector", tier: null, score: model.collector.publicScore, rank: model.collector.rank, cohortSize: model.collector.cohortSize },
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
        <div className={`${styles.decisionIntro} flex items-start gap-3.5`}><span className="inline-flex h-10 w-10 flex-none"><IconCue name="gauge" role="verdict" contained className="h-5 w-5" /></span><div className="min-w-0"><p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-bold uppercase tracking-[0.16em]"><span style={{ color: verdictPresentation.style.color }}>Verdict</span>{model.qualitativeLabel ? <><span aria-hidden="true" className="text-[var(--border-subtle)]">/</span><span data-rip-qualitative-label style={{ color: model.qualitativeLabel.color || undefined }}>{model.qualitativeLabel.label}</span></> : null}</p><div className="mt-2 flex flex-wrap items-center gap-2.5 md:gap-3">{model.overall.rank === null ? null : <span data-rip-verdict-rank className={styles.verdictRank} style={{ borderColor: model.qualitativeLabel?.color || undefined }}>#{Math.round(model.overall.rank)}</span>}<h1 className={`${styles.headline} max-w-4xl text-2xl font-semibold leading-tight tracking-tight text-[var(--text-primary)] md:text-3xl`}>{headline}</h1></div><p className="mt-2 max-w-4xl text-sm leading-snug text-[var(--text-secondary)] md:text-base">{model.verdict}</p></div></div>
        <div data-rip-section="why-it-ranks" className="mt-4 border-t border-[var(--border-subtle)] pt-4">
          <h2 className="flex items-center gap-2.5 text-xl font-semibold text-[var(--text-primary)]"><IconCue name="analysis" />Why It Ranks <Help text="This set’s overall opening verdict, based on Overall RIP, Financial RIP, and Collector Appeal relative to other ranked sets." /></h2>
          <dl data-rip-desktop-score-cards className={`${styles.whyGrid} mt-3 hidden gap-3 md:grid md:grid-cols-3`}>
            {evidenceMetrics.map((metric) => <EvidenceMetric key={metric.key} metric={metric} />)}
          </dl>
          <dl data-rip-mobile-score-deck className={`${styles.compactDeck} mt-2.5 grid grid-cols-3 md:hidden`}>
            {evidenceMetrics.map((metric) => <CompactEvidenceMetric key={metric.key} metric={metric} />)}
          </dl>
          <p className={`${styles.takeaway} mt-3 flex items-start gap-2 rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,0.36)] px-3.5 py-3 text-xs leading-snug text-[var(--text-secondary)]`}><IconCue name="bulb" role="takeaway" className="mt-0.5 h-4 w-4" /><span><span className="font-semibold text-[var(--text-primary)]">The takeaway:</span> {model.takeaway}</span></p>
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
        <a href="/Articles/how-financial-rip-works" className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 text-sm font-semibold text-[var(--accent)] transition-colors hover:border-[var(--accent)] hover:bg-[rgba(255,255,255,0.03)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">View Financial RIP methodology <span aria-hidden="true">→</span></a>
      </article>

      <div className={`${styles.lowerGrid} grid gap-5 lg:grid-cols-2 lg:items-start`}>
        <article data-rip-section="chase-cards" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="cards" />What Can I Actually Pull?</h2>{chaseCards.length ? <ul className={`${styles.chaseList} mt-1`}>{chaseCards.slice(0, 3).map((card, index) => <ChaseCard key={card?.id || card?.canonicalCardId || `${card?.name}:${index}`} card={card} />)}</ul> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Chase-card data is unavailable for this set.</p>}<a href={cardsHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>{Number.isFinite(Number(cardCount)) && Number(cardCount) > 0 ? `View all ${Number(cardCount).toLocaleString("en-US")} cards →` : "View all cards →"}</a></article>
        <article data-rip-section="opening-odds" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="target" role="odds" />Your Opening Odds</h2>{model.openingOdds.length ? <dl className="mt-2">{model.openingOdds.map((row) => <div key={row.label} className={`${styles.oddsRow} flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] py-3 first:border-t-0`}><dt className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><IconCue name="target" role="odds" />{row.label}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">1 in {Number(row.denominator).toLocaleString("en-US", { maximumFractionDigits: 1 })} packs</dd></div>)}</dl> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Consumer-summary odds are unavailable for this set.</p>}<a href={pullRatesHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>View full pull rates →</a></article>
      </div>
    </section>
  );
}
