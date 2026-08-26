"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";
import {
  resolveCanonicalFinancialRip,
  selectFinancialRipV3Breakdown,
} from "./financialRipV3Selector.mjs";
import { selectCollectorAppealBreakdown } from "./collectorAppealBreakdownSelector.mjs";
import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import CollectorAppealBreakdown from "./CollectorAppealBreakdown.jsx";
import RipDistributionChart from "./RipDistributionChart";
import SimulationFullReport, { SimulationDiagnostics } from "./SimulationFullReport.jsx";
import EvRepresentativenessSection from "./simulation-evidence/EvRepresentativenessSection.jsx";
import InfoPopover, { PublicRipTierInfo } from "@/components/ui/InfoPopover";
import RankBadge from "@/components/ui/RankBadge";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import { getRipPageIconPresentation } from "./ripPageIconPresentation.mjs";
import {
  selectCollectorDiagnostic,
  selectCollectorDriverSubjects,
  selectCollectorRankDrivers,
  selectFinancialRankDrivers,
} from "./ripStorySelectors.mjs";
import { CollectorDriverSubjects } from "./RipStoryEvidence.jsx";
import { getRipTierPresentation } from "./ripTierPresentation.mjs";
import styles from "./RipDecisionPage.module.css";
import { ANALYTICAL_ACTION_CLASS } from "@/components/ui/analyticalInteraction.mjs";
import ProductOpeningValue, {
  ENTERTAINMENT_COST_PER_PACK_HELP,
  ENTERTAINMENT_COST_HELP,
} from "./ProductOpeningValue.jsx";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";
import { PremiumMetricLock, RankedProductHeader, RankedProductIdentity } from "./RankedProductTablePrimitives.jsx";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import rankingStyles from "./explore.module.css";
import { buildFamilyRankLookup, groupProductsByFamily } from "./setProductComparison.mjs";
import {
  selectLoosePackMarketPrice,
  selectRipDecisionContract,
} from "./ripDecisionContract.mjs";
import { familyLabel } from "./SetRipFamilyBreakdown.jsx";

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
  return value === null || value === undefined ? "—" : (Number(value) / 10).toFixed(1);
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
/** Percentage of price, derived losslessly from two already-published numbers. */
function pctOfPrice(part, whole_) {
  if (part === null || part === undefined || whole_ === null || whole_ === undefined) return null;
  const price = Number(whole_);
  if (!price) return null;
  return Math.round((Number(part) / price) * 100);
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
                /10
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
          /10
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
function ChaseReality({ chase, available, contractPresent, loosePackPrice, compact = false, canViewAdvanced = false }) {
  if (!chase) {
    return (
      <article
        data-rip-section="chase-reality"
        data-chase-state="unavailable"
        className={compact ? undefined : `${styles.panel} set-glass-surface`}
      >
        {compact ? null : <p className={styles.eyebrow}>The Chase</p>}
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
      className={compact ? undefined : `${styles.panel} set-glass-surface`}
    >
      {compact ? null : (
        <>
          <p className={styles.eyebrow}>The Chase</p>
          <h2 className={styles.sectionTitle}>Your Biggest Chase</h2>
          <p className={styles.sectionLede}>
            The highest-value card this set&apos;s modeled packs can actually
            produce, with its exact modeled odds.
          </p>
        </>
      )}
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
        {canViewAdvanced ? <dl className={styles.chaseThresholds}>
          <div>
            <dt>50/50 Chance to Pull One</dt>
            <dd>{whole(chase.packsFor50PercentChance)} packs</dd>
            <p>
              {grossSpend(chase.packsFor50PercentChance) === null
                ? null
                : `≈ ${grossSpend(chase.packsFor50PercentChance)} at today's pack price`}
            </p>
            <small>Opening this many modeled packs gives you roughly a 50% chance of seeing at least one copy. It is not guaranteed.</small>
          </div>
          <div>
            <dt>90% Chance to Pull One</dt>
            <dd>{whole(chase.packsFor90PercentChance)} packs</dd>
            <p>
              {grossSpend(chase.packsFor90PercentChance) === null
                ? null
                : `≈ ${grossSpend(chase.packsFor90PercentChance)} at today's pack price`}
            </p>
            <small>Opening this many modeled packs gives you roughly a 90% chance of seeing at least one copy.</small>
          </div>
        </dl> : (
          <div className={styles.premiumTeaser} data-index-plus-teaser="chase-acquisition">
            <strong>Index Plus acquisition research</strong>
            <p>See the modeled pack counts for approximately a 50% or 90% chance of pulling this card.</p>
          </div>
        )}
      </div>
      <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
        These are modeled independent-pack chances, not a guaranteed acquisition cost. You could pull{" "}
        {chase.name || "this card"} on your first pack, or not within the packs shown.
      </p>
    </article>
  );
}

// The market-value-ranked "other high-value cards" grid (distinct from the
// canonical Top Chase) was removed from the Set Overview composition — it
// duplicated Top Chase, Most Desirable Pokémon, Pull Rates and What Drives
// Expected Value without adding unique decision value. No component used it
// outside this page, so it was deleted rather than merely unmounted.

const EV_DONUT_COLORS = ["#2dd4bf", "#a78bfa", "#facc15", "#38bdf8", "#f97373", "#94a3b8"];

/**
 * WHAT DRIVES EXPECTED VALUE? — EV CONTRIBUTION BY RARITY.
 *
 * Reuses the SAME `rankings` data SimulationDriverCards already reads
 * (`rarity_bucket` + `total_sampled_value`, both produced by the Monte Carlo
 * sampler, not a static market-value sum). This is deliberately not a new
 * calculation: the old "Cards Driving Pack Value" section computed this
 * exact contribution-by-rarity breakdown already, buried in a disclosure —
 * it is promoted here rather than recreated.
 */
function EvContributionSection({ rankings = [], bare = false }) {
  const rows = useMemo(() => {
    return (Array.isArray(rankings) ? rankings : [])
      .map((row) => ({
        label: row?.rarity_bucket || row?.rarityBucket,
        value: (() => {
          const parsed = Number(row?.total_sampled_value ?? row?.totalSampledValue);
          return Number.isFinite(parsed) ? parsed : null;
        })(),
      }))
      .filter((row) => row.label && row.value !== null && row.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [rankings]);
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  const Wrapper = bare ? "div" : "article";

  return (
    <Wrapper data-rip-section="ev-contribution" className={bare ? undefined : `${styles.panel} set-glass-surface`}>
      {bare ? null : (
        <>
          <p className={styles.eyebrow}>What drives Expected Value?</p>
          <h2 className={styles.sectionTitle}>Where the Value Comes From</h2>
        </>
      )}
      {rows.length === 0 || total <= 0 ? (
        <p className={styles.unavailableNote}>
          Expected Value contribution by rarity is not available for this set&apos;s current simulation.
        </p>
      ) : (
        <>
          <p className={styles.sectionLede}>
            Share of modeled Expected Value contributed by each rarity — not how often each rarity is
            pulled, but how much of the dollar total it accounts for.
          </p>
          <div className={styles.evLayout}>
            <div className={styles.evDonutWrap}>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={rows} dataKey="value" nameKey="label" innerRadius={62} outerRadius={92} paddingAngle={2} stroke="none">
                    {rows.map((row, index) => (
                      <Cell key={row.label} fill={EV_DONUT_COLORS[index % EV_DONUT_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className={styles.evDonutCenter}>
                <span>{money(total)}</span>
                <small>Expected Value</small>
              </div>
            </div>
            <div className={styles.evTable}>
              <div className={styles.evTableHead}>
                <span>Rarity</span>
                <span>EV Contribution</span>
                <span>Share</span>
              </div>
              <ul>
                {rows.map((row, index) => (
                  <li key={row.label}>
                    <span className={styles.evSwatch} style={{ background: EV_DONUT_COLORS[index % EV_DONUT_COLORS.length] }} aria-hidden="true" />
                    <span className={styles.evRarityLabel}>{String(row.label).replaceAll("_", " ")}</span>
                    <span className={styles.evCell}>{money(row.value)}</span>
                    <span className={styles.evCell}>{Math.round((row.value / total) * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </>
      )}
    </Wrapper>
  );
}

/**
 * DEEP DIVE ROW — a single collapsible advanced-content module.
 *
 * Every item Sections 1-6 demoted (Set RIP family breakdown, the break-even
 * chart, market-value chase context, EV drivers) lives here behind its own
 * disclosure, so the page reads as one methodology section rather than six.
 */
function DeepDiveRow({ id, title, subtitle, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = `${id}-panel`;
  return (
    <div data-deep-dive-row={id} className={styles.deepDiveRow}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className={styles.disclosureButton}
      >
        <span>
          <span className="block">{title}</span>
          {subtitle ? (
            <span className="mt-0.5 block text-xs font-normal normal-case tracking-normal text-[var(--text-secondary)]">
              {subtitle}
            </span>
          ) : null}
        </span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div id={panelId} className="mt-3">
          {children}
        </div>
      ) : null}
    </div>
  );
}

/**
 * TWO DISTINCT RANKS, NEVER MIXED.
 *
 * FAMILY RANK — "#3 of 22 ETBs". Sourced from the canonical
 * `productFamilyRankings` block the backend already publishes
 * (`build_product_family_rankings`, keyed by `sealedProductId`): every
 * currently eligible modeled product in the SAME canonical family, across
 * every ranked set. This is the rank that matters — it answers "is this
 * product actually strong relative to the market", and it is never computed
 * here, only looked up.
 *
 * The backend's comparison-scope contract (`crossFormatComparable: false`) is
 * still load-bearing: nothing here ever compares across families.
 */
function productComparisonMetrics(product) {
  const perPack = product.entertainmentCost?.available ? product.entertainmentCost.perPack : null;
  const pricePerPack = product.marketPrice !== null && product.packCount ? product.marketPrice / product.packCount : null;
  return { perPack, pricePerPack, valueBackPct: pctOfPrice(product.typicalOpening, product.marketPrice) };
}

function ProductIdentity({ product, familyRankInfo, setName, isBest }) {
  const identity = { ...product, productFamily: product.family, productImageUrl: familyRankInfo?.productImageUrl, setCanonicalKey: familyRankInfo?.setCanonicalKey };
  return <RankedProductIdentity product={identity} secondary={`${setName || "This set"} · ${familyRankInfo?.productFamilyLabel || familyLabel(product.family)}`}>{isBest ? <small className={styles.comparisonBestTag}>Featured</small> : null}</RankedProductIdentity>;
}

function LockedValue({ canView, children }) {
  return canView ? children : <PremiumMetricLock />;
}

function ComparisonMobileRow({ product, familyRankInfo, setName, canView, isBest = false }) {
  const { perPack, pricePerPack, valueBackPct } = productComparisonMetrics(product);
  const rows = [
    ["Product Rank", familyRankInfo ? `#${familyRankInfo.familyRank} / ${familyRankInfo.familySize}` : "—"],
    ["Typical Back", valueBackPct === null ? money(product.typicalOpening) : `${valueBackPct}% · ${money(product.typicalOpening)} typical`],
    ["Entertainment Cost", perPack === null ? "—" : money(perPack)],
    ["Recover Cost", product.chanceToRecoverCost === null ? "—" : probability(product.chanceToRecoverCost)],
  ];
  return (
    <article className={`${rankingStyles.surfaceQuiet} min-w-0 w-full overflow-hidden p-3`} data-product-key={product.key} data-best-in-family={isBest ? "true" : undefined}>
      <ProductIdentity product={product} familyRankInfo={familyRankInfo} setName={setName} isBest={isBest} />
      <div className="mt-3 flex items-center justify-between border-y border-[var(--border-subtle)] py-2">
        <LockedValue canView={canView}><RipScoreBadge score={familyRankInfo?.overallRipLeaderScore} tier={familyRankInfo?.publicTier} compact /></LockedValue>
        <LockedValue canView={canView}><RipTierMark tier={familyRankInfo?.publicTier} /></LockedValue>
      </div>
      <dl className="mt-2 grid gap-2 text-xs">
        <div className="flex items-center justify-between gap-4"><dt className="text-[var(--text-secondary)]">Market Price</dt><dd className="font-semibold tabular-nums">{money(product.marketPrice)}</dd></div>
        <div className="flex items-center justify-between gap-4"><dt className="text-[var(--text-secondary)]">$ / Pack</dt><dd className="font-semibold tabular-nums">{pricePerPack === null ? "—" : money(pricePerPack)}</dd></div>
        {rows.map(([label, value]) => <div key={label} className="flex items-center justify-between gap-4"><dt className="text-[var(--text-secondary)]">{label}</dt><dd className="font-semibold tabular-nums"><LockedValue canView={canView}>{value}</LockedValue></dd></div>)}
      </dl>
    </article>
  );
}

function ComparisonTableRow({ product, familyRankInfo, setName, canView, isBest = false }) {
  const { perPack, pricePerPack, valueBackPct } = productComparisonMetrics(product);
  return (
    <tr className={rankingStyles.row} data-product-key={product.key} data-sealed-product-id={product.sealedProductId} data-best-in-family={isBest ? "true" : undefined}>
      <td className={`${rankingStyles.numeric} whitespace-nowrap`}><LockedValue canView={canView}>{familyRankInfo ? `#${familyRankInfo.familyRank} / ${familyRankInfo.familySize}` : "—"}</LockedValue></td>
      <td className={rankingStyles.productIdentityCell}><ProductIdentity product={product} familyRankInfo={familyRankInfo} setName={setName} isBest={isBest} /></td>
      <td className="text-center"><LockedValue canView={canView}><RipScoreBadge score={familyRankInfo?.overallRipLeaderScore} tier={familyRankInfo?.publicTier} compact /></LockedValue></td>
      <td className="text-center"><LockedValue canView={canView}><RipTierMark tier={familyRankInfo?.publicTier} /></LockedValue></td>
      <td className={rankingStyles.numeric}>{money(product.marketPrice)}</td>
      <td className={rankingStyles.numeric}>{pricePerPack === null ? "—" : money(pricePerPack)}</td>
      <td className={rankingStyles.numeric}><LockedValue canView={canView}><span>{valueBackPct === null ? money(product.typicalOpening) : `${valueBackPct}%`}<small className="block text-[10px] font-normal text-[var(--text-secondary)]">{valueBackPct === null ? "typical" : `${money(product.typicalOpening)} typical`}</small></span></LockedValue></td>
      <td className={rankingStyles.numeric}><LockedValue canView={canView}>{perPack === null ? "—" : money(perPack)}</LockedValue></td>
      <td className={rankingStyles.numeric}><LockedValue canView={canView}>{product.chanceToRecoverCost === null ? "—" : probability(product.chanceToRecoverCost)}</LockedValue></td>
    </tr>
  );
}

export default function RipDecisionPage({
  canonical,
  summary,
  ripDecision = null,
  setRip = null,
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
  initialProductId = null,
  familyFilter = null,
  productFamilyRankings = null,
  evRepresentativeness = null,
  openingOutcomeProfile = null,
  calculationRunId = null,
}) {
  const { canViewRankingsIntelligence: canViewProductRipIntelligence } = useRankingsAccess();
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

  // SECTION 1/2 — grouped, within-family-only comparison. Cross-format
  // comparison is deliberately never computed: decision.crossFormatComparable
  // is published false, and product order here must never imply otherwise.
  //
  // `familyRankLookup` is the ONLY source of the primary Product Rank shown in
  // the hero and the comparison table — a lookup into the canonical global
  // per-family cohort the backend already publishes, never a local sort of
  // this set's own products. Local set-only sorting still exists (Set SKU
  // Rank), but it is explicitly the SECONDARY rank and is hidden entirely
  // when there is only one comparable SKU in this set.
  const familyRankLookup = useMemo(() => buildFamilyRankLookup(productFamilyRankings), [productFamilyRankings]);
  const familyGroups = useMemo(
    () => groupProductsByFamily(decision.products, familyRankLookup),
    [decision.products, familyRankLookup]
  );
  const heroPick = useMemo(() => {
    // The hero recommends the product with the BEST (lowest-numbered) global
    // family rank among products this set actually publishes — never a
    // locally-recomputed score comparison, and never a claim that spans
    // families (a #3 ETB is never preferred over a #1 Booster Box here; each
    // family's own #1 is a candidate, and ties fall back to Overall RIP).
    let best = null;
    let bestInfo = null;
    for (const group of familyGroups) {
      for (const product of group.products) {
        const info = familyRankLookup.get(product.sealedProductId);
        if (!info) continue;
        if (
          !best ||
          info.familyRank < bestInfo.familyRank ||
          (info.familyRank === bestInfo.familyRank &&
            (product.overallRipScore ?? -Infinity) > (best.overallRipScore ?? -Infinity))
        ) {
          best = product;
          bestInfo = info;
        }
      }
    }
    if (!best) {
      // No product in this set carries a published global family rank yet —
      // fall back to the first published product so the hero still shows
      // real economics, just without a rank claim.
      const firstGroup = familyGroups[0];
      best = firstGroup?.products?.[0] || null;
      bestInfo = null;
    }
    return best ? { product: best, familyRankInfo: bestInfo } : null;
  }, [familyGroups, familyRankLookup]);

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
  const heroProduct = heroPick?.product || null;
  const heroPerPack = heroProduct?.entertainmentCost?.available ? heroProduct.entertainmentCost.perPack : null;
  const heroPricePerPack =
    heroProduct?.marketPrice !== null && heroProduct?.marketPrice !== undefined && heroProduct?.packCount
      ? heroProduct.marketPrice / heroProduct.packCount
      : null;
  const heroValueBackPct = heroProduct ? pctOfPrice(heroProduct.typicalOpening, heroProduct.marketPrice) : null;
  const heroFamilyName = heroProduct ? familyLabel(heroProduct.family) : null;
  const chartMarkersForAccess = canViewProductRipIntelligence ? chartMarkers : [
    ...(Array.isArray(chartMarkers) ? chartMarkers.filter((marker) => ["pack-cost", "median", "mean"].includes(marker?.key)) : []),
    ...[["p25", "P25"], ["p75", "P75"], ["bad-floor", "Bad Floor"], ["big-hit", "Big Hit Threshold"], ["big-hit-upside", "Strong Upside"], ["god-pull-upside", "Jackpot Upside"], ["max", "Best Pull"]].map(([key, label]) => ({ key, label, value: null, locked: true })),
  ];

  return (
    <section
      id="set-detail-overview"
      data-rip-decision-page
      className={`${styles.page} scroll-mt-24 md:scroll-mt-28`}
    >
      <article data-rip-section="opening-snapshot" className={`${styles.panel} set-glass-surface`}>
        <p className={styles.eyebrow}>1. Opening snapshot</p>
        <h1 className={styles.sectionTitle}>Opening Snapshot</h1>
        <p className={styles.sectionLede}>The headline view of what opening {setName || "this set"} is like at today&apos;s pack price.</p>
        <div className={styles.compactScores}>
          <ScoreSurface metric={metrics.overall} onActivate={() => setOverallOpen((value) => !value)} expanded={overallOpen} controls="overall-rip-explanation" />
          <ScoreSurface metric={metrics.financial} onActivate={() => scrollToSection("set-detail-financial-rip")} />
          <ScoreSurface metric={metrics.collector} onActivate={() => scrollToSection("set-detail-collector-appeal")} />
        </div>
        {overallOpen ? <div id="overall-rip-explanation" className={styles.overallDisclosure}>Overall RIP combines Financial RIP opening economics with Collector Appeal.</div> : null}
        <p className={styles.compactScoreTakeaway}>{model.takeaway}</p>
      </article>

      <div data-rip-section="compare-products" className={`${styles.sectionIntro} scroll-mt-24 md:scroll-mt-28`}>
        <p className={styles.eyebrow}>2. Compare ways to open {setName || "this set"}</p>
        <h2 className={styles.sectionTitle}>Compare Ways to Open</h2>
      </div>

      {/* ============================================================
          1. BEST WAY TO OPEN [SET] — the decision, first.
          ============================================================ */}
      {canViewProductRipIntelligence ? <article data-rip-subsection="best-way-to-open" className={`${styles.panel} set-glass-surface ${styles.heroPanel}`}>
        <p className={styles.eyebrow}>Best way to open {setName || "this set"}</p>
        {!heroProduct ? (
          <p className={styles.unavailableNote}>
            {decision.contractPresent === false
              ? "Product opening economics are not published in this set's current snapshot."
              : decision.available === false
                ? "No current calculation run is available for this set."
                : "No currently modeled sealed products are available for this set."}
          </p>
        ) : (
          <div className={styles.heroLayout}>
            <div className={styles.heroIdentity}>
              {productImage ? (
                <div className={styles.heroProductArt}>
                  <Image
                    src={productImage.src || productImage}
                    alt={`${heroProduct.label} artwork`}
                    fill
                    sizes="(max-width: 767px) 96px, 148px"
                    className="object-contain"
                  />
                </div>
              ) : null}
              <div className="min-w-0">
                <h1 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
                  Best in {heroFamilyName}
                </h1>
                <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{heroProduct.label}</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {heroPick.familyRankInfo
                    ? `Ranked against every currently eligible modeled ${heroFamilyName} across modeled sets.`
                    : `This set's ${heroFamilyName} at today's prices; a global ${heroFamilyName} rank is not yet published for it.`}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className={styles.heroBadge}>
                    {heroPick.familyRankInfo ? (
                      <>
                        #{heroPick.familyRankInfo.familyRank} of {heroPick.familyRankInfo.familySize} eligible {heroFamilyName}
                        {heroPick.familyRankInfo.familySize === 1 ? "" : "s"}
                      </>
                    ) : (
                      "Family rank unavailable"
                    )}
                    <InfoPopover text={`Ranked against all currently eligible modeled ${heroFamilyName}s in the canonical product-family cohort, across every modeled set — not just this one.`} />
                  </span>
                  {heroProduct.overallRipScore === null ? null : (
                    <span className={styles.heroBadge}>
                      {score(heroProduct.overallRipScore)} RIP Score
                    </span>
                  )}
                </div>
              </div>
            </div>
            <dl className={styles.heroMetrics}>
              <div>
                <dt>
                  Market Price
                  <InfoPopover text="Current tracked market price used by the model for this product." />
                </dt>
                <dd>{money(heroProduct.marketPrice)}</dd>
                <p>{heroProduct.priceAsOf ? `As of ${heroProduct.priceAsOf}` : "What it costs today"}</p>
              </div>
              {heroPricePerPack === null ? null : (
                <div>
                  <dt>
                    Price / Pack
                    <InfoPopover text="The product's current market price divided by the modeled number of packs it contains." />
                  </dt>
                  <dd>{money(heroPricePerPack)}</dd>
                  <p>{heroProduct.packCount} packs</p>
                </div>
              )}
              <div>
                <dt>
                  Typical Value Back
                  <InfoPopover text="The median modeled opening value. Half of simulated outcomes finished above this amount and half below it. The percentage compares this median modeled card value with today's product cost." />
                </dt>
                <dd>{money(heroProduct.typicalOpening)}</dd>
                <p>{heroValueBackPct === null ? "Median simulated opening" : `${heroValueBackPct}% of price`}</p>
              </div>
              <div>
                <dt>
                  Entertainment Cost / Pack
                  <InfoPopover text={ENTERTAINMENT_COST_PER_PACK_HELP} />
                </dt>
                <dd>{heroPerPack === null ? "Not modeled yet" : money(heroPerPack)}</dd>
                <p>What you pay for the experience</p>
              </div>
              <div>
                <dt>
                  Chance to Recover Cost
                  <InfoPopover text="The modeled percentage of openings whose card value meets or exceeds the purchase price. Uses gross market value, before selling fees, shipping or spreads." />
                </dt>
                <dd>{heroProduct.chanceToRecoverCost === null ? "—" : probability(heroProduct.chanceToRecoverCost)}</dd>
                <p>Beat your purchase price</p>
              </div>
            </dl>
            {heroProduct.sealedProductId ? <Link
              href={`/sealed-products/${encodeURIComponent(heroProduct.sealedProductId)}`}
              className={`${styles.heroCta} ${ANALYTICAL_ACTION_CLASS}`}
            >
              View Product <span aria-hidden="true">→</span>
            </Link> : null}
          </div>
        )}
        <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
          Products are compared only within their own format — a Booster Box against other Booster Boxes,
          never against a Bundle or ETB. Cross-format comparison is not yet validated by the model.
        </p>
      </article> : null}

      {/* ============================================================
          2. COMPARE WAYS TO OPEN [SET]
          ============================================================ */}
      {familyGroups.length === 0 ? null : (
        <article data-rip-subsection="product-comparison" className={`${styles.panel} set-glass-surface`}>
          <h2 className={styles.sectionTitle}>Product Comparison</h2>
          <p className={styles.sectionLede}>
            Compare each way to open this set. Product Rank and RIP Score compare each product only
            with products of the same type; opening economics below describe the specific product at
            its current market price.
          </p>
          {!canViewProductRipIntelligence ? <div className={styles.premiumTeaser} data-index-plus-teaser="best-way-to-open">
            <strong>Find the Best Way to Open {setName || "This Set"}</strong>
            <p>Index Plus compares every modeled product against equivalent products across eligible sets at today&apos;s market price.</p>
            <a href="/checkout">Unlock with Index Plus</a>
          </div> : null}
          {/* ONE shared header for the entire table. Family groups below are a
              thin divider row, never a second full header — repeating column
              labels per product was the exact complaint this rebuild fixes. */}
          <div className="mt-3 hidden overflow-x-auto rounded-xl border border-[var(--border-subtle)] lg:block">
            <table className={`${rankingStyles.table} min-w-[960px]`} data-set-product-comparison-table>
              <colgroup><col className="w-[7rem]" /><col className="w-[16rem]" /><col className="w-[5rem]" /><col className="w-[4rem]" /><col span="2" className="w-[6.25rem]" /><col className="w-[8rem]" /><col className="w-[8rem]" /><col className="w-[6.25rem]" /></colgroup>
              <caption className="sr-only">Sealed-product opening economics for {setName || "this set"}</caption>
              <thead className={rankingStyles.head}><tr>
                <th scope="col" className="whitespace-normal"><RankedProductHeader text="Ranked against eligible modeled products of the same product family.">Product Rank</RankedProductHeader></th>
                <th scope="col">Product</th>
                <th scope="col"><RankedProductHeader text="How close this product's Overall RIP performance is to the strongest eligible product of the same type.">RIP Score</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader info={<PublicRipTierInfo />}>Tier</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader text="The current tracked market price used for this product's RIP calculations.">Market Price</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader text="Current product market price divided by its included pack count.">$ / Pack</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader text="The modeled typical opening value, shown with the share of current product price typically returned.">Typical Back</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader text={ENTERTAINMENT_COST_HELP}>Entertainment Cost</RankedProductHeader></th>
                <th scope="col"><RankedProductHeader text="The modeled probability that an opening returns at least the product's current market price.">Recover Cost</RankedProductHeader></th>
              </tr></thead>
              <tbody>{familyGroups.flatMap((group) =>
                  group.products.map((product) => {
                    const familyRankInfo = familyRankLookup.get(product.sealedProductId) || null;
                    return <ComparisonTableRow key={product.key} product={product} familyRankInfo={familyRankInfo} setName={setName} canView={canViewProductRipIntelligence} isBest={heroProduct?.key === product.key} />;
                  })
                )}</tbody>
            </table>
          </div>
          <div className="mt-3 grid gap-2 lg:hidden" data-set-product-comparison-mobile>
            {familyGroups.flatMap((group) =>
                group.products.map((product) => {
                  const familyRankInfo = familyRankLookup.get(product.sealedProductId) || null;
                  return (
                    <ComparisonMobileRow
                      key={product.key}
                      product={product}
                      familyRankInfo={familyRankInfo}
                      setName={setName}
                      canView={canViewProductRipIntelligence}
                      isBest={heroProduct?.key === product.key}
                    />
                  );
                })
              )}
          </div>
        </article>
      )}

      {/* ============================================================
          3. WHAT ARE YOU CHASING? — Top Chase and Most Desirable
          Pokémon merged into one story: both answer "what am I
          actually opening this set for?"
          ============================================================ */}
      <article data-rip-section="chase-summary" className={`${styles.panel} set-glass-surface`}>
        <p className={`${styles.eyebrow} ${styles.collectorEyebrow}`}>3. What are you chasing?</p>
        <h2 className={styles.sectionTitle}>What Are You Chasing?</h2>
        <p className={styles.sectionLede}>
          Top cards and Pokémon driving value and collector demand.
        </p>
        <ChaseReality
          chase={decision.topChase}
          available={decision.available}
          contractPresent={decision.contractPresent}
          loosePackPrice={loosePackPrice}
          compact
          canViewAdvanced={canViewProductRipIntelligence}
        />
        <div className={styles.chaseDivider}>
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
            Most Desirable Pokémon
          </p>
        </div>
        <CollectorDriverSubjects subjects={collectorSubjects} />
        <a href={pullRatesHref} className={styles.pullRatesCta}>
          View all modeled pull rates <span aria-hidden="true">→</span>
        </a>
      </article>

      {/* ============================================================
          6. SIMULATION EVIDENCE
          ============================================================ */}
      <article
        id="set-detail-outcome-distribution"
        data-rip-section="simulation-evidence"
        className={`${styles.panel} set-glass-surface scroll-mt-24 md:scroll-mt-28`}
      >
        <p className={styles.eyebrow}>5. Simulation evidence</p>
        <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
          What One Million Simulated Openings Look Like
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The evidence behind Financial RIP, with today&apos;s pack price plotted on the same value axis.
        </p>
        <div className="mt-3">
          {distributionBins.length || thresholdBins.length ? (
            <RipDistributionChart
              bins={distributionBins}
              thresholdBins={thresholdBins}
              markers={chartMarkersForAccess}
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
        <SimulationFullReport
          canonical={canonical}
          summary={summary}
          percentiles={percentiles}
          evRepresentativeness={evRepresentativeness}
          openingOutcomeProfile={openingOutcomeProfile}
          calculationRunId={calculationRunId}
          canViewAdvanced={canViewProductRipIntelligence}
        />
      </article>

      {/* ============================================================
          FOR THOSE WHO WANT TO GO DEEPER — EV contribution, break-even,
          Set RIP construction and the Financial/Collector breakdowns are
          all advanced analytical evidence, not first-glance answers, so
          every one of them is a collapsed disclosure here rather than
          its own primary-flow section.
          ============================================================ */}
      <article data-rip-section="deep-dive" className={`${styles.panel} set-glass-surface`}>
        <p className={styles.eyebrow}>For those who want to go deeper</p>
        <h2 className={styles.sectionTitle}>For Those Who Want to Go Deeper</h2>
        <p className={styles.sectionLede}>
          Explore the pricing, value structure and model details behind the headline results.
        </p>

        {!canViewProductRipIntelligence ? <div className={styles.premiumTeaser} data-index-plus-teaser="advanced-research">
          <strong>Advanced research with Index Plus</strong>
          <p>Unlock EV composition, opening break-even analytics, downside and tail diagnostics, plus Financial RIP and Collector Appeal factor breakdowns.</p>
          <a href="/checkout">Unlock with Index Plus</a>
        </div> : null}

        {canViewProductRipIntelligence ? <>
        <DeepDiveRow
          id="deep-dive-ev-realization"
          title="When Does EV Start Looking Real?"
          subtitle="EV realization and convergence for real-sized opening runs"
        >
          <EvRepresentativenessSection summary={summary} percentiles={percentiles} evRepresentativeness={evRepresentativeness} calculationRunId={calculationRunId} headingId="deep-dive-ev-realization-heading" />
        </DeepDiveRow>

        <DeepDiveRow
          id="deep-dive-downside-upside"
          title="Downside & Upside"
          subtitle="Compact outcome, tail and distribution diagnostics"
        >
          <SimulationDiagnostics canonical={canonical} summary={summary} percentiles={percentiles} />
        </DeepDiveRow>

        <DeepDiveRow
          id="deep-dive-ev-contribution"
          title="What Drives Expected Value?"
          subtitle="Expected Value contribution by rarity"
        >
          <EvContributionSection rankings={rankings} bare />
        </DeepDiveRow>

        <DeepDiveRow
          id="deep-dive-break-even"
          title="Today's Price vs. Modeled Break-Even"
          subtitle="Each product against its own model break-even"
        >
          <ProductOpeningValue decision={decision} setName={setName} initialProductId={initialProductId} familyFilter={familyFilter} />
        </DeepDiveRow>

        <div
          id="set-detail-financial-rip"
          tabIndex={-1}
          data-rip-section="financial-explanation"
          className="scroll-mt-24 md:scroll-mt-28"
        >
          <DeepDiveRow
            id="deep-dive-financial-rip"
            title={`Financial RIP Breakdown — why Financial RIP is ${score(model.financial.publicScore)}`}
            defaultOpen={financialDeepDiveOpen}
          >
            <SectionMeta metric={model.financial} />
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Six dimensions explain this set&apos;s modeled opening economics.
            </p>
            <FinancialDriverSummary drivers={financialDrivers} />
            <div className="mt-3">
              <FinancialRipV3Breakdown canonical={canonical} requestTimeout={false} />
            </div>
          </DeepDiveRow>
        </div>

        <div
          id="set-detail-collector-appeal"
          tabIndex={-1}
          data-rip-section="collector-explanation"
          className="scroll-mt-24 md:scroll-mt-28"
        >
          <DeepDiveRow
            id="deep-dive-collector-appeal"
            title={`Collector Appeal Breakdown — why Collector Appeal is ${score(model.collector.publicScore)}`}
            defaultOpen={collectorDeepDiveOpen}
          >
            <SectionMeta metric={model.collector} />
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Two parallel factors describe the roster and how often a desirable card can appear.
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
                    <strong className="text-[var(--text-primary)]">Dual-Path Depth</strong>{" "}
                    — Not part of the current Collector Appeal score. {collectorDiagnostic.note}
                  </div>
                ) : null}
              </div>
            ) : null}
          </DeepDiveRow>
        </div>
        </> : null}
      </article>
    </section>
  );
}
