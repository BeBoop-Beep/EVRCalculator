"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import { buildRipDecisionModel, selectMarketChaseCards } from "./ripDecisionModel.mjs";
import {
  resolveCanonicalFinancialRip,
  selectFinancialRipV3Breakdown,
} from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import CollectorAppealBreakdown from "./CollectorAppealBreakdown.jsx";
import RipDistributionChart from "./RipDistributionChart";
import SimulationFullReport from "./SimulationFullReport.jsx";
import InfoPopover from "@/components/ui/InfoPopover";
import RankBadge from "@/components/ui/RankBadge";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import { getRipPageIconPresentation } from "./ripPageIconPresentation.mjs";
import {
  selectCollectorDiagnostic,
  selectCollectorDriverSubjects,
  selectCollectorRankDrivers,
  selectFinancialRankDrivers,
} from "./ripStorySelectors.mjs";
import {
  CollectorDriverSubjects,
  SimulationDriverCards,
} from "./RipStoryEvidence.jsx";
import { getRipTierPresentation } from "./ripTierPresentation.mjs";
import styles from "./RipDecisionPage.module.css";
import ProductOpeningValue from "./ProductOpeningValue.jsx";
import {
  selectLoosePackMarketPrice,
  selectRipDecisionContract,
} from "./ripDecisionContract.mjs";

const METHODOLOGY_ARTICLE_HREF = "/Articles/how-rip-score-works";
const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});
function Help({
  text,
  href = METHODOLOGY_ARTICLE_HREF,
  label = "How the RIP Score works",
}) {
  return (
    <InfoPopover text={text} learnMoreHref={href} learnMoreLabel={label} />
  );
}
function money(value) {
  return value === null || value === undefined
    ? "—"
    : currency.format(Number(value));
}
function score(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(1);
}
function rank(value, cohort) {
  return value === null || value === undefined
    ? "Rank unavailable"
    : `#${Math.round(value)}${cohort === null || cohort === undefined ? "" : ` of ${Math.round(cohort)}`}`;
}
function whole(value) {
  return value === null || value === undefined
    ? "Unavailable"
    : Math.round(Number(value)).toLocaleString("en-US");
}
function probability(value) {
  if (value === null || value === undefined) return "—";
  const normalized = Number(value) <= 1 ? Number(value) * 100 : Number(value);
  return `${normalized.toFixed(1).replace(/\.0$/, "")}%`;
}

function IconCue({ name, role = "neutral", className = "h-4 w-4" }) {
  const presentation = getRipPageIconPresentation(role);
  return (
    <span
      className={`inline-flex items-center justify-center ${presentation.iconClassName}`}
      style={presentation.style}
    >
      <SetPageIcon name={name} className={className} />
    </span>
  );
}

function ScoreSurface({
  metric,
  prominent = false,
  onActivate,
  expanded,
  controls,
  productContext = null,
}) {
  const tier = getRipTierPresentation(metric.tier, {
    strength: prominent ? "hero" : "supporting",
  });
  return (
    <div
      data-rip-score={metric.key}
      data-score-tier={tier.tier || "unavailable"}
      className={`${styles.scoreSurface} ${prominent ? styles.scoreSurfaceOverall : ""}`}
      style={tier.style}
    >
      <div className={styles.scoreContent}>
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.08em] text-[var(--text-primary)]">
          <IconCue name={metric.icon} />
          {metric.label}
          <Help
            text={metric.help}
            href={metric.href}
            label={`How ${metric.label} works`}
          />
        </div>
        <div className={styles.scoreFacts}>
          <p
            className={`${prominent ? "text-4xl" : "text-3xl"} font-semibold leading-none tabular-nums text-[var(--text-primary)]`}
          >
            {score(metric.score)}
            {metric.score === null ? null : (
              <span className="ml-1 text-xs text-[var(--text-secondary)]">
                /100
              </span>
            )}
          </p>
          <p className="text-xs tabular-nums text-[var(--text-secondary)]">
            {rank(metric.rank, metric.cohortSize)}
          </p>
          {metric.tier ? (
            <RankBadge rank={metric.tier} format="tier" size="compact" subtle />
          ) : null}
        </div>
        <button
          type="button"
          onClick={onActivate}
          aria-expanded={expanded}
          aria-controls={controls}
          className={styles.scoreCta}
        >
          {metric.cta}
          <span aria-hidden="true">→</span>
        </button>
      </div>
      {prominent && productContext?.productImage ? (
        <div className={styles.productArt}>
          <Image
            src={productContext.productImage.src || productContext.productImage}
            alt={`${productContext.productLabel || "Booster Pack"} being scored`}
            fill
            sizes="(max-width: 767px) 68px, 116px"
            className="object-contain"
          />
        </div>
      ) : null}
    </div>
  );
}

function SectionMeta({ metric }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      <strong className="text-lg tabular-nums text-[var(--text-primary)]">
        {score(metric.publicScore)}{" "}
        <small className="text-xs font-medium text-[var(--text-secondary)]">
          /100
        </small>
      </strong>
      <span className="text-xs tabular-nums text-[var(--text-secondary)]">
        {rank(metric.rank, metric.cohortSize)}
      </span>
      {metric.tier ? (
        <RankBadge rank={metric.tier} format="tier" size="compact" subtle />
      ) : null}
    </div>
  );
}

function scrollToSection(id) {
  const target = document.getElementById(id);
  if (!target) return;
  const reduced = window.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  )?.matches;
  target.scrollIntoView({
    behavior: reduced ? "auto" : "smooth",
    block: "start",
  });
  target.focus({ preventScroll: true });
}

function FinancialDriverSummary({ drivers }) {
  if (!drivers.available) return null;
  const Row = ({ item }) => (
    <li className="flex items-center justify-between gap-3">
      <span className="truncate">{item.title}</span>
      <span className="flex flex-none items-center gap-2">
        <strong className="tabular-nums text-[var(--text-primary)]">
          #{Math.round(item.rank)}
        </strong>
        {item.tier ? (
          <RankBadge rank={item.tier} format="tier" size="compact" subtle />
        ) : null}
      </span>
    </li>
  );
  return (
    <aside className={styles.rankDrivers}>
      <p className="text-xs font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
        Why it ranks this way
      </p>
      <div className={styles.driverStrip}>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            ↑ Strengths
          </h3>
          <ul className="mt-1.5 space-y-1 text-sm text-[var(--text-secondary)]">
            {drivers.strengths.map((item) => (
              <Row key={item.key} item={item} />
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            ↓ Main drag
          </h3>
          <ul className="mt-1.5 space-y-1 text-sm text-[var(--text-secondary)]">
            {drivers.drags.map((item) => (
              <Row key={item.key} item={item} />
            ))}
          </ul>
        </div>
      </div>
    </aside>
  );
}

// The old "What You Pay vs What You Get Back" loose-stat grid lived here. It is
// replaced by the selected-product panel in ProductOpeningValue, which shows the
// same arithmetic bound to ONE product the reader picked, against that product's
// own break-even, instead of mixing pack-level stats with no product context.

/**
 * THE CHASE — driven ONLY by `ripDecision.topChase`.
 *
 * Every number here is read verbatim from the canonical contract, which selects
 * the priciest card the run can actually produce and publishes its exact modeled
 * odds. Nothing is reconstructed from `top_hits`, EV drivers, Collector Appeal
 * subjects or rarity order: EV contribution is rate x price, so ordering by it
 * answers a different question and would name a different card.
 *
 * `loosePackPrice` is presentation only. It converts published pack COUNTS into
 * gross spend, and is omitted entirely when no single-pack product is modeled
 * rather than being guessed from another format's price.
 */
function ChaseReality({ chase, available, contractPresent, loosePackPrice }) {
  if (!chase) {
    // Restrained on purpose: an absent chase is a footnote, not a headline. The
    // two causes are genuinely different and the copy says which one applies.
    return (
      <article
        data-rip-section="chase-reality"
        data-chase-state="unavailable"
        className={`${styles.panel} set-glass-surface`}
      >
        <p className={styles.eyebrow}>The Chase</p>
        <p className={styles.unavailableNote}>
          {contractPresent === false
            ? "Modeled chase odds are not published in this set's current snapshot."
            : available === false
              ? "No current calculation run is available for this set, so modeled chase odds are not shown."
              : "Exact modeled chase odds are unavailable for this run."}
        </p>
      </article>
    );
  }

  const odds =
    chase.impliedOddsOneInN !== null
      ? `1 in ${whole(chase.impliedOddsOneInN)}`
      : probability(chase.modeledProbability);

  const grossSpend = (packs) =>
    packs === null || loosePackPrice === null || loosePackPrice === undefined
      ? null
      : money(packs * loosePackPrice);

  return (
    <article
      data-rip-section="chase-reality"
      data-chase-state="available"
      className={`${styles.panel} set-glass-surface`}
    >
      <p className={styles.eyebrow}>The Chase</p>
      <h2 className={styles.sectionTitle}>Your Biggest Chase</h2>
      <p className={styles.sectionLede}>
        The highest-value card this set&apos;s modeled packs can actually
        produce, with its exact modeled odds.
      </p>
      <div className={styles.chaseLayout}>
        {chase.imageUrl ? (
          <div className={styles.chaseImage}>
            <Image
              src={chase.imageUrl}
              alt={chase.name || "Top chase card"}
              fill
              sizes="(max-width: 767px) 76px, 130px"
              className="object-contain"
            />
          </div>
        ) : null}
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Top Chase
          </p>
          <h3 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
            {chase.name || "Top chase card"}
          </h3>
          {chase.rarity ? (
            <p className="mt-0.5 text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {chase.rarity}
            </p>
          ) : null}
          <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
            {money(chase.currentMarketPrice)}
          </p>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            Modeled pack odds:{" "}
            <strong className="text-[var(--text-primary)]">{odds}</strong>
          </p>
        </div>
        <dl className={styles.chaseThresholds}>
          <div>
            <dt>50% modeled chance</dt>
            <dd>{whole(chase.packsFor50PercentChance)} packs</dd>
            <p>
              {grossSpend(chase.packsFor50PercentChance) === null
                ? null
                : `≈ ${grossSpend(chase.packsFor50PercentChance)} gross pack spend at today's pack price`}
            </p>
          </div>
          <div>
            <dt>90% modeled chance</dt>
            <dd>{whole(chase.packsFor90PercentChance)} packs</dd>
            <p>
              {grossSpend(chase.packsFor90PercentChance) === null
                ? null
                : `≈ ${grossSpend(chase.packsFor90PercentChance)} gross pack spend at today's pack price`}
            </p>
          </div>
        </dl>
      </div>
      <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
        Modeled probabilities describe chances, not guaranteed outcomes. Gross
        pack spend is the cost of opening that many packs at today&apos;s pack
        price — not a cost to acquire the card, since every pack opened also
        produces other cards.
      </p>
    </article>
  );
}

function MaterialCards({ cards, pullRatesHref }) {
  if (!cards.length) return null;
  return (
    <article
      data-rip-section="material-cards"
      className={`${styles.panel} set-glass-surface`}
    >
      <p className={styles.eyebrow}>Set value concentration</p>
      <h2 className={styles.sectionTitle}>Other Major Value Chases</h2>
      <p className={styles.sectionLede}>
        Additional high-value cards for market context. Unlike the Top Chase
        above — which is the canonical modeled chase with exact odds — these are
        ranked by current market value only, and carry no modeled pull odds and
        no desirability score.
      </p>
      <div className={styles.materialCards}>
        {cards.map((card, index) => {
          const name = card.name || card.cardName || card.card_name;
          const value =
            card.marketPrice ??
            card.market_price ??
            card.currentPrice ??
            card.current_price;
          const imageUrl =
            card.imageSmallUrl ||
            card.image_small_url ||
            card.imageUrl ||
            card.image_url ||
            card.imageLargeUrl ||
            card.image_large_url;
          return (
            <div key={card.id || card.cardId || `${name}:${index}`}>
              <span>#{index + 1}</span>
              {imageUrl ? (
                <div className={styles.materialImage}>
                  <Image
                    src={imageUrl}
                    alt=""
                    fill
                    sizes="44px"
                    className="object-contain"
                  />
                </div>
              ) : (
                <div />
              )}
              <div>
                <strong>{name}</strong>
                <small>
                  {card.rarity ||
                    card.rarityName ||
                    card.rarity_name ||
                    "Published chase card"}
                </small>
              </div>
              <b>{money(value)}</b>
            </div>
          );
        })}
      </div>
      <a href={pullRatesHref} className={styles.pullRatesCta}>
        View modeled pull rates <span aria-hidden="true">→</span>
      </a>
    </article>
  );
}

export default function RipDecisionPage({
  canonical,
  summary,
  ripDecision = null,
  setName = null,
  chaseCards = [],
  percentiles = [],
  pullRateAssumptions,
  pullRatesHref,
  productType = "booster_pack",
  productLabel = "Booster Pack",
  productImage = null,
  distributionBins = [],
  thresholdBins = [],
  chartMarkers = [],
  p50 = null,
  p95 = null,
  p99 = null,
  simulationPending = false,
  simulationDrivers = [],
  rankings = [],
  packPaths = {},
  normalStateRows = [],
}) {
  const [overallOpen, setOverallOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [financialDeepDiveOpen, setFinancialDeepDiveOpen] = useState(false);
  const [collectorDeepDiveOpen, setCollectorDeepDiveOpen] = useState(false);
  // ONE normalization of the canonical decision contract for the whole page, so
  // no section re-reads raw snapshot keys or invents its own fallbacks.
  const decision = useMemo(() => selectRipDecisionContract(ripDecision), [ripDecision]);
  const loosePackPrice = useMemo(
    () => selectLoosePackMarketPrice(decision.products),
    [decision.products]
  );
  // Secondary market context only, with the canonical Top Chase removed: it is
  // already shown above with exact modeled odds, so repeating it as the #1
  // "other" chase would be duplication that adds no information.
  const marketChaseCards = useMemo(
    () => selectMarketChaseCards(chaseCards, { excludeCard: decision.topChase }),
    [chaseCards, decision.topChase]
  );
  const model = buildRipDecisionModel({
    canonical,
    summary,
    pullRateAssumptions,
  });
  const financial = useMemo(
    () =>
      selectFinancialRipV3Breakdown(resolveCanonicalFinancialRip(canonical)),
    [canonical],
  );
  const financialDrivers = useMemo(
    () => selectFinancialRankDrivers(financial.rows),
    [financial.rows],
  );
  const collectorBreakdown = useMemo(
    () => selectCollectorAppealBreakdown(canonical),
    [canonical],
  );
  const collectorDrivers = useMemo(
    () => selectCollectorRankDrivers(collectorBreakdown.rows),
    [collectorBreakdown.rows],
  );
  const collectorSubjects = useMemo(
    () => selectCollectorDriverSubjects(canonical),
    [canonical],
  );
  const collectorDiagnostic = useMemo(
    () => selectCollectorDiagnostic(canonical),
    [canonical],
  );
  const verdictPresentation = getRipPageIconPresentation("verdict");
  const metrics = {
    overall: {
      key: "overall",
      label: "Overall RIP",
      role: "overall",
      icon: "gauge",
      score: model.overall.publicScore,
      rank: model.overall.rank,
      cohortSize: model.overall.cohortSize,
      tier: model.overall.tier,
      cta: overallOpen ? "Hide explanation" : "How Overall RIP works",
      help: "The current canonical overall score for opening this set relative to ranked sets.",
    },
    financial: {
      key: "financial",
      label: "Financial RIP",
      role: "financial",
      icon: "shield",
      score: model.financial.publicScore,
      rank: model.financial.rank,
      cohortSize: model.financial.cohortSize,
      cta: "Explore Financial RIP",
      href: "/Articles/how-financial-rip-works",
      help: "Opening economics across typical outcomes, losses, upside, and efficiency.",
    },
    collector: {
      key: "collector",
      label: "Collector Appeal",
      role: "collector",
      icon: "star",
      score: model.collector.publicScore,
      rank: model.collector.rank,
      cohortSize: model.collector.cohortSize,
      cta: "Explore Collector Appeal",
      href: "/Articles/how-collector-appeal-works",
      help: "Roster desirability and the frequency of desirable modeled outcomes.",
    },
  };
  const openingMetrics = [
    ["Expected Value", money(model.expectedValue), "Long-run mean"],
    ["Typical Opening", money(p50 ?? model.typicalOpening), "P50 / median"],
    [
      "Chance to Beat Cost",
      probability(model.recoverCostProbability),
      "Financial break-even",
    ],
    ["Strong Upside", money(p95), "P95 threshold"],
    ["Jackpot Upside", money(p99), "P99 / top 1% threshold"],
  ];
  return (
    <section
      id="set-detail-overview"
      data-rip-decision-page
      className={`${styles.page} scroll-mt-24 md:scroll-mt-28`}
    >
      {/* A. COMPACT VERDICT — one line of position, one line of context. The
          canonical rank is the existing booster-pack RIP rank, so it is named
          as such: there is no validated multi-product Set RIP Consensus, and
          calling it one here would invent a metric. */}
      <article
        data-rip-section="decision"
        className={`${styles.panel} ${styles.compactVerdict} set-glass-surface`}
      >
        <div className={styles.compactVerdictHead}>
          {model.overall.rank !== null ? (
            <span className={styles.verdictRank}>
              #{Math.round(model.overall.rank)}
            </span>
          ) : null}
          <div className="min-w-0">
            <p
              className="text-[10px] font-bold uppercase tracking-[0.16em]"
              style={{ color: verdictPresentation.style.color }}
            >
              Verdict
            </p>
            <h1 className={styles.compactVerdictTitle}>
              {model.overall.rank === null
                ? "Booster Pack RIP Rank Unavailable"
                : "Booster Pack RIP Rank"}
            </h1>
          </div>
        </div>
        <p className={styles.compactVerdictLine}>{model.verdict}</p>
      </article>

      {/* B. PRODUCT OPENING VALUE + C. SELECTED PRODUCT ECONOMICS. */}
      <ProductOpeningValue decision={decision} setName={setName} />

      {/* D. CHASE REALITY — canonical contract only. */}
      <ChaseReality
        chase={decision.topChase}
        available={decision.available}
        contractPresent={decision.contractPresent}
        loosePackPrice={loosePackPrice}
      />

      {/* E. OTHER MAJOR VALUE CHASES — market context, explicitly secondary. */}
      <MaterialCards
        cards={marketChaseCards}
        pullRatesHref={pullRatesHref}
      />
      {/* F. SIMULATION EVIDENCE — the evidence behind the decision above. */}
      <article
        id="set-detail-outcome-distribution"
        data-rip-section="simulation-evidence"
        className={`${styles.panel} set-glass-surface scroll-mt-24 md:scroll-mt-28`}
      >
        <p className={styles.eyebrow}>Simulation evidence</p>
        <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
          What One Million Simulated Openings Look Like
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The evidence behind Financial RIP, with today&apos;s pack price
          plotted on the same value axis.
        </p>
        <div className={styles.simulationLayout}>
          <dl className={styles.metricPanel}>
            {openingMetrics.map(([label, value, helper]) => (
              <div key={label}>
                <dt className="text-xs font-semibold text-[var(--text-secondary)]">
                  {label}
                </dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
                  {value}
                </dd>
                <dd className="text-[11px] text-[var(--text-secondary)]">
                  {helper}
                </dd>
              </div>
            ))}
          </dl>
          <div className="min-w-0">
            {distributionBins.length || thresholdBins.length ? (
              <RipDistributionChart
                bins={distributionBins}
                thresholdBins={thresholdBins}
                markers={chartMarkers}
                showTitle={false}
                flush
              />
            ) : (
              <p className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-12 text-center text-sm text-[var(--text-secondary)]">
                {simulationPending
                  ? "Loading simulated opening evidence…"
                  : "Outcome distribution data is not available for this set yet."}
              </p>
            )}
          </div>
        </div>
        <SimulationFullReport
          canonical={canonical}
          summary={summary}
          percentiles={percentiles}
        />
      </article>
      <article
        data-rip-section="simulation-drivers"
        className={`${styles.panel} set-glass-surface`}
      >
        <p className={styles.eyebrow}>What creates the distribution</p>
        <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
          Cards Driving Pack Value
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          These cards contribute most to modeled Expected Value; they do not
          directly add Financial RIP points.
        </p>
        <SimulationDriverCards
          drivers={simulationDrivers}
          rankings={rankings}
          packPaths={packPaths}
          normalStateRows={normalStateRows}
        />
      </article>
      {/* G. WHY IT RANKS — compact. The full score anatomy that used to sit in
          the first viewport is gone; the three canonical scores and one
          interpretation sentence carry it, and the detail lives in Deep Dive. */}
      <article
        data-rip-section="why-it-ranks"
        className={`${styles.panel} set-glass-surface`}
      >
        <p className={styles.eyebrow}>Score</p>
        <h2 className={styles.sectionTitle}>Why It Ranks</h2>
        {/* The existing ScoreSurface primitive, three-up. Same component the
            old hero used — but without the full-width anatomy, connector and
            product art, so it reads as a summary rather than a diagram. */}
        <div className={styles.compactScores}>
          <ScoreSurface
            metric={metrics.overall}
            onActivate={() => setOverallOpen((value) => !value)}
            expanded={overallOpen}
            controls="overall-rip-explanation"
          />
          <ScoreSurface
            metric={metrics.financial}
            onActivate={() => {
              setFinancialDeepDiveOpen(true);
              scrollToSection("set-detail-financial-rip");
            }}
          />
          <ScoreSurface
            metric={metrics.collector}
            onActivate={() => {
              setCollectorDeepDiveOpen(true);
              scrollToSection("set-detail-collector-appeal");
            }}
          />
        </div>
        {overallOpen ? (
          <div id="overall-rip-explanation" className={styles.overallDisclosure}>
            Overall RIP combines the set&apos;s opening economics, represented by
            Financial RIP, with its collector-oriented desirability and desirable
            pull opportunities, represented by Collector Appeal.
          </div>
        ) : null}
        {/* The same deterministic HELPS/HURTS decision that drives the labels
            above, so this sentence can never contradict them. */}
        <p className={styles.compactScoreTakeaway}>{model.takeaway}</p>
      </article>

      {/* H. DEEP DIVE — the existing detailed breakdowns, unchanged in logic,
          reused as-is, but collapsed so they no longer dominate the page. */}
      <article
        id="set-detail-financial-rip"
        tabIndex={-1}
        data-rip-section="financial-explanation"
        className={`${styles.panel} set-glass-surface scroll-mt-24 md:scroll-mt-28`}
      >
        <p className={styles.eyebrow}>Deep dive</p>
        <button
          type="button"
          aria-expanded={financialDeepDiveOpen}
          aria-controls="financial-rip-deep-dive"
          onClick={() => setFinancialDeepDiveOpen((value) => !value)}
          className={styles.disclosureButton}
        >
          <span>
            Financial RIP Breakdown — why Financial RIP is{" "}
            {score(model.financial.publicScore)}
          </span>
          <span aria-hidden="true">{financialDeepDiveOpen ? "−" : "+"}</span>
        </button>
        {financialDeepDiveOpen ? (
          <div id="financial-rip-deep-dive" className="mt-3">
            <SectionMeta metric={model.financial} />
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Six dimensions explain this set&apos;s modeled opening economics.
            </p>
            <FinancialDriverSummary drivers={financialDrivers} />
            <div className="mt-3">
              <FinancialRipV3Breakdown
                canonical={canonical}
                requestTimeout={false}
              />
            </div>
          </div>
        ) : null}
      </article>
      <article
        id="set-detail-collector-appeal"
        tabIndex={-1}
        data-rip-section="collector-explanation"
        className={`${styles.panel} set-glass-surface scroll-mt-24 md:scroll-mt-28`}
      >
        <p className={styles.eyebrow}>Deep dive</p>
        <button
          type="button"
          aria-expanded={collectorDeepDiveOpen}
          aria-controls="collector-appeal-deep-dive"
          onClick={() => setCollectorDeepDiveOpen((value) => !value)}
          className={styles.disclosureButton}
        >
          <span>
            Collector Appeal Breakdown — why Collector Appeal is{" "}
            {score(model.collector.publicScore)}
          </span>
          <span aria-hidden="true">{collectorDeepDiveOpen ? "−" : "+"}</span>
        </button>
        {collectorDeepDiveOpen ? (
        <div id="collector-appeal-deep-dive" className="mt-3">
        <p className={styles.eyebrow}>Collector Appeal</p>
        <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
          Why Collector Appeal Is {score(model.collector.publicScore)}
        </h2>
        <SectionMeta metric={model.collector} />
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Two parallel factors describe the roster and how often a desirable
          card can appear.
        </p>
        <FinancialDriverSummary drivers={collectorDrivers} />
        <div className="mt-3">
          <CollectorAppealBreakdown canonical={canonical} />
        </div>
        {collectorDiagnostic.available ? (
          <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
            <button
              type="button"
              aria-expanded={diagnosticsOpen}
              aria-controls="collector-diagnostics"
              onClick={() => setDiagnosticsOpen((value) => !value)}
              className={styles.disclosureButton}
            >
              <span>Additional collector diagnostics</span>
              <span aria-hidden="true">{diagnosticsOpen ? "−" : "+"}</span>
            </button>
            {diagnosticsOpen ? (
              <div
                id="collector-diagnostics"
                className="mt-3 rounded-xl border border-[var(--border-subtle)] p-3 text-sm text-[var(--text-secondary)]"
              >
                <strong className="text-[var(--text-primary)]">
                  Dual-Path Depth
                </strong>{" "}
                — Not part of the current Collector Appeal score.{" "}
                {collectorDiagnostic.note}
              </div>
            ) : null}
          </div>
        ) : null}
        </div>
        ) : null}
      </article>
      <article
        data-rip-section="collector-drivers"
        className={`${styles.panel} set-glass-surface`}
      >
        <p className={`${styles.eyebrow} ${styles.collectorEyebrow}`}>
          Collector evidence
        </p>
        <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
          What Are You Chasing?
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The desirable Pokémon and representative pull paths currently supplied
          by the canonical model.
        </p>
        <CollectorDriverSubjects subjects={collectorSubjects} />
        <a href={pullRatesHref} className={styles.pullRatesCta}>
          View all modeled pull rates <span aria-hidden="true">→</span>
        </a>
      </article>
    </section>
  );
}
