"use client";

import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import { getRipPageIconPresentation } from "./ripPageIconPresentation.mjs";
import styles from "./RipDecisionPage.module.css";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function money(value) { return value === null ? "—" : currency.format(value); }
function score(value) { return value === null ? "—" : Number(value).toFixed(1).replace(/\.0$/, ""); }
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

// One comparative driver of the Overall RIP. The eyebrow ("Helps" / "Hurts" /
// "Stronger driver") is decided in ripDrivers.mjs, never by position, and the
// bar visualises the SAME cohort standing the "#3 of 22" beside it states.
function DriverCell({ driver, index }) {
  const presentation = getRipPageIconPresentation(driver.role);
  return (
    <div data-rip-driver={driver.key} className={`${styles.whyMetric} py-2 md:px-5 md:first:pl-0 ${index ? "border-t border-[var(--border-subtle)] md:border-l md:border-t-0" : ""}`}>
      <dt className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]"><IconCue name={driver.icon} role={driver.role} className="h-3.5 w-3.5" />{driver.standingLabel}</dt>
      <dd className="mt-0.5 flex items-baseline gap-2"><span className="text-sm font-semibold text-[var(--text-primary)]">{driver.label}</span><span className="text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">{score(driver.score)}</span><span className="text-xs tabular-nums text-[var(--text-secondary)]">{rank(driver.rank, driver.cohortSize)}</span></dd>
      <dd className={`${styles.driverTrack} mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--border-subtle)]`}>{driver.barPercent === null ? null : <span className="block h-full rounded-full" style={{ width: `${driver.barPercent}%`, backgroundColor: presentation.style.color }} />}</dd>
    </div>
  );
}

function ChaseCard({ card }) {
  const name = card?.name || "Card name unavailable";
  const image = card?.imageUrl || card?.image_url || card?.images?.small || null;
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

export default function RipDecisionPage({ canonical, summary, chaseCards = [], cardCount = null, pullRateAssumptions, cardsHref, pullRatesHref }) {
  const model = buildRipDecisionModel({ canonical, summary, pullRateAssumptions });
  const verdictPresentation = getRipPageIconPresentation("verdict");
  const headline = model.overall.rank === null ? "Modern Set RIP Ranking Unavailable" : `#${Math.round(model.overall.rank)} Modern Set to Rip Right Now`;
  const metrics = [
    ["Pack Price", money(model.packCost), "per pack", "tag"],
    ["Expected Value", money(model.expectedValue), "long-run avg.", "trend"],
    ["Typical Opening", money(model.typicalOpening), "middle opening", "package"],
    ["Recover Your Cost", probability(model.recoverCostProbability), "beat pack cost", "target"],
  ];
  return (
    <section id="set-detail-overview" data-rip-decision-page className={`${styles.page} scroll-mt-24 space-y-3 md:scroll-mt-28 md:space-y-3.5`}>
      <article data-rip-section="decision" className={`${styles.decision} set-glass-surface rounded-2xl border p-4 md:p-5`}>
        <div className={`${styles.decisionIntro} flex items-start gap-3.5`}><span className="inline-flex h-10 w-10 flex-none"><IconCue name="gauge" role="verdict" contained className="h-5 w-5" /></span><div className="min-w-0"><p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-bold uppercase tracking-[0.16em]"><span style={{ color: verdictPresentation.style.color }}>Verdict</span>{model.qualitativeLabel ? <><span aria-hidden="true" className="text-[var(--border-subtle)]">/</span><span data-rip-qualitative-label style={{ color: model.qualitativeLabel.color || undefined }}>{model.qualitativeLabel.label}</span></> : null}</p><h1 className={`${styles.headline} mt-1 max-w-4xl text-3xl font-semibold leading-tight tracking-tight text-[var(--text-primary)] md:text-[2.25rem]`}>{headline}</h1><p className="mt-1.5 max-w-4xl text-sm leading-snug text-[var(--text-secondary)] md:text-base">{model.verdict}</p></div></div>
        <dl className={`${styles.metrics} mt-4 grid grid-cols-2 border-t border-[var(--border-subtle)] pt-2 md:grid-cols-4`}>
          {metrics.map(([label, value, helper, icon], index) => <div key={label} className={`${styles.metric} grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-x-2 px-2 py-2 first:pl-0 md:px-4 md:first:pl-0 ${index % 2 ? "border-l border-[var(--border-subtle)]" : ""} ${index > 1 ? "border-t border-[var(--border-subtle)] md:border-t-0" : ""} ${index === 2 ? "md:border-l" : ""}`}><span className="row-span-3 mt-1 inline-flex h-6 w-6 items-center justify-center"><IconCue name={icon} /></span><dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</dt><dd className="mt-0.5 text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)] md:text-2xl">{value}</dd><dd className="text-[11px] leading-tight text-[var(--text-secondary)]">{helper}</dd></div>)}
        </dl>
      </article>

      <article data-rip-section="why-it-ranks" className={`${styles.why} set-glass-surface rounded-2xl border p-4 md:p-5`}>
        <h2 className="flex items-center gap-2.5 text-xl font-semibold text-[var(--text-primary)]"><IconCue name="analysis" />Why It Ranks {model.overall.rank === null ? "" : `#${Math.round(model.overall.rank)}`}</h2>
        <dl className={`${styles.whyGrid} mt-3 grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)]`}>
          {model.drivers.drivers.map((driver, index) => <DriverCell key={driver.key} driver={driver} index={index} />)}
          <div data-rip-driver="result" className={`${styles.whyMetric} ${styles.whyResult} border-t border-[var(--border-subtle)] py-2 md:border-l md:border-t-0 md:px-5`}><dt className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]"><IconCue name="trophy" role="overall" tier={model.overall.tier} className="h-3.5 w-3.5" />Result</dt><dd className="mt-0.5 text-2xl font-semibold leading-tight tabular-nums text-[var(--text-primary)] md:text-3xl">{rank(model.overall.rank, model.overall.cohortSize)} <span className="text-sm font-semibold text-[var(--text-secondary)]">Overall RIP</span></dd><dd className="mt-0.5 text-xs text-[var(--text-secondary)]">Relative RIP Index {score(model.overall.relativeScore)}</dd></div>
        </dl>
        <p className={`${styles.takeaway} mt-2 flex items-start gap-2 border-t border-[var(--border-subtle)] pt-2.5 text-xs leading-snug text-[var(--text-secondary)]`}><IconCue name="bulb" role="takeaway" className="mt-0.5 h-4 w-4" /><span><span className="font-semibold text-[var(--text-primary)]">The takeaway:</span> {model.takeaway}</span></p>
      </article>

      <div className={`${styles.lowerGrid} grid gap-5 lg:grid-cols-2 lg:items-start`}>
        <article data-rip-section="chase-cards" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="cards" />What Can I Actually Pull?</h2>{chaseCards.length ? <ul className={`${styles.chaseList} mt-1`}>{chaseCards.slice(0, 3).map((card, index) => <ChaseCard key={card?.id || card?.canonicalCardId || `${card?.name}:${index}`} card={card} />)}</ul> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Chase-card data is unavailable for this set.</p>}<a href={cardsHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>{Number.isFinite(Number(cardCount)) && Number(cardCount) > 0 ? `View all ${Number(cardCount).toLocaleString("en-US")} cards →` : "View all cards →"}</a></article>
        <article data-rip-section="opening-odds" className={`${styles.lowerPanel} set-glass-surface flex min-h-0 flex-col rounded-2xl border p-4`}><h2 className="flex items-center gap-2.5 text-lg font-semibold text-[var(--text-primary)]"><IconCue name="target" role="odds" />Your Opening Odds</h2>{model.openingOdds.length ? <dl className="mt-2">{model.openingOdds.map((row) => <div key={row.label} className={`${styles.oddsRow} flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] py-3 first:border-t-0`}><dt className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><IconCue name="target" role="odds" />{row.label}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">1 in {Number(row.denominator).toLocaleString("en-US", { maximumFractionDigits: 1 })} packs</dd></div>)}</dl> : <p className="mt-3 text-sm text-[var(--text-secondary)]">Consumer-summary odds are unavailable for this set.</p>}<a href={pullRatesHref} className={`${styles.cta} mt-auto inline-flex min-h-9 items-end justify-center pt-2 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]`}>View full pull rates →</a></article>
      </div>
    </section>
  );
}
