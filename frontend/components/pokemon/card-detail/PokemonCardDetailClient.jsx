"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { useAuth } from "@/components/AuthContext";
import InfoPopover from "@/components/ui/InfoPopover";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getRipTierPresentation } from "@/components/explore/ripTierPresentation.mjs";
import {
  FEATURE_CARD_CHASE_EFFICIENCY,
  hasIndexFeatureAccess,
  hasIndexPlusAccess,
} from "@/lib/access/indexPlanAccess.mjs";
import {
  optimizedImageUrl,
  SET_LOGO_WIDTH,
} from "@/lib/images/remoteImageDelivery.mjs";
import {
  buildPokemonCardDetailHref,
  getPokemonCardChaseEfficiency,
  getPokemonCardDetail,
} from "@/lib/pokemon/pokemonCardDetailClient";
import { compactSealedProductLabel } from "@/components/pokemon/set-page/Overview/sealedMarketTrendSelector.mjs";
import AssetMarketPanel from "./AssetMarketPanel";
import {
  buildSealedProductHref,
  expectedProductsCopy,
  orderCardProducts,
  productDisplayPrice,
} from "./productPresentation.mjs";
import {
  cumulativePullProbability,
  buildCardParentSetHref,
  milestoneXPosition,
  packsAtPlotX,
  probabilityMilestones,
  scorePercent,
  validPullProbability,
} from "./cardDetailModel.mjs";
import { getObjectContainPaintedRect } from "./cardDetailImageGeometry.mjs";
import {
  PROBABILITY_ANALYTICS_COLOR,
  PROBABILITY_ANALYTICS_SOFT_BORDER,
  PROBABILITY_ANALYTICS_TEXT_COLOR,
} from "./cardDetailVisualTokens.mjs";

const finite = (value) =>
  value !== null && value !== undefined && Number.isFinite(Number(value))
    ? Number(value)
    : null;
const money = (value) =>
  finite(value) === null
    ? "Unavailable"
    : finite(value).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
      });
const number = (value, digits = 0) =>
  finite(value) === null
    ? "Unavailable"
    : finite(value).toLocaleString("en-US", { maximumFractionDigits: digits });
const percent = (value, digits = 1) =>
  finite(value) === null
    ? "Unavailable"
    : `${(finite(value) * 100).toFixed(digits).replace(/\.0+$/, "")}%`;
const dateLabel = (value) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(`${String(value).slice(0, 10)}T00:00:00Z`))
    : "Unavailable";

function Metric({ label, info = null, children }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.35)] p-3.5">
      <dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
        <span>{label}</span>
        {info ? <InfoPopover text={info} /> : null}
      </dt>
      <dd className="mt-1.5 text-lg font-semibold tabular-nums sm:text-xl">
        {children}
      </dd>
    </div>
  );
}

function AnalyticalMetric({ label, info = null, children, className = "" }) {
  return (
    <div className={`min-w-0 px-4 py-3 ${className}`}>
      <dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
        <span>{label}</span>
        {info ? <InfoPopover text={info} /> : null}
      </dt>
      <dd className="mt-1.5 text-lg font-semibold tabular-nums sm:text-xl">
        {children}
      </dd>
    </div>
  );
}

const PULL_STATUS_LABELS = Object.freeze({
  legacy_run_variant_detail_unavailable:
    "Exact variant detail unavailable for this legacy run",
  not_pullable_by_current_model: "Not pullable by the current pack model",
  pull_model_configuration_missing: "Pull-model configuration missing",
  insufficient_observed_pulls: "Insufficient observed simulation pulls",
});

const PULL_STATUS_EXPLANATIONS = Object.freeze({
  not_pullable_by_current_model:
    "Pull analytics are not available because this printing is not currently part of the modeled pack configuration.",
  pull_model_configuration_missing:
    "The set model does not currently contain enough configuration to publish pull odds for this printing.",
  legacy_run_variant_detail_unavailable:
    "Exact printing-level pull intelligence will be available after this set is recalculated with the current simulation model.",
  insufficient_observed_pulls:
    "This printing is part of the model, but the current simulation did not observe enough pulls to publish a reliable exact rate.",
});

const pullStatusLabel = (status) =>
  PULL_STATUS_LABELS[status] || "Pull intelligence unavailable";
const pullStatusExplanation = (status) =>
  PULL_STATUS_EXPLANATIONS[status] ||
  "Pull analytics are unavailable for this printing in the current model.";

function VariantSelector({ detail, onSelect, pending }) {
  if (detail.availableVariants.length < 2) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-[var(--text-secondary)]">
        Printing
      </p>
      <div
        role="radiogroup"
        aria-label="Card printing"
        className="mt-2 flex flex-wrap gap-2"
      >
        {detail.availableVariants.map((variant) => {
          const selected = detail.selectedVariantId === variant.cardVariantId;
          return (
            <button
              key={variant.cardVariantId}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={pending}
              onClick={() => onSelect(variant.cardVariantId)}
              className={`min-h-11 rounded-lg border px-3 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-wait disabled:opacity-55 ${selected ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] text-[var(--accent)]" : "border-[var(--border-subtle)] bg-white/5 text-[var(--text-secondary)] hover:border-[color-mix(in_srgb,var(--accent)_35%,transparent)]"}`}
            >
              {variant.label}
              {!variant.modeled
                ? ` · ${pullStatusLabel(variant.pullModelStatus)}`
                : ""}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PlusLock({ title }) {
  const id = title.replace(/\s/g, "-").toLowerCase();
  return (
    <section
      data-plus-lock
      aria-labelledby={id}
      className="set-glass-surface relative min-h-36 overflow-hidden rounded-2xl border"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 grid grid-cols-3 gap-3 p-5 opacity-20 blur-sm"
      >
        <span className="h-16 rounded-xl bg-white/10" />
        <span className="h-16 rounded-xl bg-white/10" />
        <span className="h-16 rounded-xl bg-white/10" />
      </div>
      <div className="relative z-10 flex min-h-36 flex-col items-center justify-center bg-[rgba(2,6,23,.62)] px-5 py-6 text-center">
        <p className="text-xs font-bold uppercase tracking-[.14em] text-amber-300">
          🔒 Index Plus
        </p>
        <h2 id={id} className="mt-2 text-xl font-semibold">
          Unlock {title}
        </h2>
        <Link
          href="/pricing"
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-amber-300/40 bg-amber-300/10 px-4 text-sm font-semibold text-amber-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
        >
          Explore Index Plus
        </Link>
      </div>
    </section>
  );
}

function ProbabilityJourney({ chase, milestoneDollars = null }) {
  const probability = validPullProbability(chase.modeledProbability);
  const milestones = probabilityMilestones(probability, chase);
  const usable =
    probability !== null &&
    milestones.every(({ packs }) => Number.isSafeInteger(packs) && packs > 0);
  const maxPacks = usable ? milestones.at(-1).packs : 0;
  const [hoveredPacks, setHoveredPacks] = useState(null);
  const [tooltipPoint, setTooltipPoint] = useState(null);
  const x = (packs) => milestoneXPosition(packs, maxPacks);
  const y = (value) => 196 - value * 166;
  const curve = usable
    ? Array.from({ length: 65 }, (_, index) => {
        const packs = (maxPacks * index) / 64;
        return [packs, cumulativePullProbability(probability, packs)];
      })
    : [];
  const path = curve
    .map(
      ([packs, value], index) =>
        `${index ? "L" : "M"}${x(packs).toFixed(2)},${y(value).toFixed(2)}`,
    )
    .join(" ");
  const hoveredProbability =
    hoveredPacks === null
      ? null
      : cumulativePullProbability(probability, hoveredPacks);
  const move = (event) => {
    const svg = event.currentTarget.ownerSVGElement;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    const plotX = Math.max(54, Math.min(680, local.x));
    const packs = packsAtPlotX(plotX, maxPacks);
    setHoveredPacks(packs);
    setTooltipPoint({
      x: plotX,
      y: y(cumulativePullProbability(probability, packs)),
    });
  };
  return (
    <section
      aria-labelledby="probability-title"
      className="border-t border-[var(--border-subtle)] pt-5"
    >
      <h3
        id="probability-title"
        className="flex items-center gap-1.5 text-lg font-semibold"
      >
        Probability Journey
        <InfoPopover text="Shows approximately how many eligible packs correspond to each cumulative probability of pulling at least one copy of this exact printing. These probability thresholds are not guarantees." />
      </h3>
      <p className="mt-1.5 max-w-4xl text-sm leading-relaxed text-[var(--text-secondary)]">
        Your cumulative chance of pulling this exact printing at least once as
        you open more eligible packs. “1 in N” is a long-run rate, not a
        guarantee that the card appears within N packs.
      </p>
      {usable ? (
        <>
          <div
            data-probability-journey-chart
            className="relative mt-4 overflow-hidden border-y border-[var(--border-subtle)] bg-white/[.015] py-3"
          >
            <svg
              role="img"
              aria-label="Cumulative pull probability by packs opened"
              aria-describedby="probability-chart-desc"
              viewBox="0 0 710 235"
              className="h-[230px] w-full sm:h-[300px]"
            >
              <desc id="probability-chart-desc">
                Pack counts are positioned proportionally, with milestones at
                50, 75, 90 and 95 percent.
              </desc>
              <defs>
                <linearGradient
                  id="probability-area"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0"
                    stopColor={PROBABILITY_ANALYTICS_COLOR}
                    stopOpacity=".24"
                  />
                  <stop
                    offset="1"
                    stopColor={PROBABILITY_ANALYTICS_COLOR}
                    stopOpacity="0"
                  />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75, 1].map((guide) => (
                <g key={guide}>
                  <line
                    x1="54"
                    x2="680"
                    y1={y(guide)}
                    y2={y(guide)}
                    stroke="rgba(148,163,184,.16)"
                    strokeDasharray="3 6"
                  />
                  <text
                    x="45"
                    y={y(guide) + 4}
                    textAnchor="end"
                    fill="rgba(232,238,247,.58)"
                    fontSize="11"
                  >
                    {guide * 100}%
                  </text>
                </g>
              ))}
              <path
                d={`${path} L680,196 L54,196 Z`}
                fill="url(#probability-area)"
              />
              <path
                data-probability-curve
                d={path}
                fill="none"
                stroke={PROBABILITY_ANALYTICS_COLOR}
                strokeWidth="3"
                vectorEffect="non-scaling-stroke"
              />
              {milestones.map(({ label, packs, target }) => (
                <g data-probability-marker={label} key={label}>
                  <line
                    x1={x(packs)}
                    x2={x(packs)}
                    y1={y(target)}
                    y2="196"
                    stroke={PROBABILITY_ANALYTICS_SOFT_BORDER}
                    strokeDasharray="2 5"
                  />
                  <circle
                    cx={x(packs)}
                    cy={y(target)}
                    r="5"
                    fill={PROBABILITY_ANALYTICS_COLOR}
                    stroke="rgba(4,15,26,.9)"
                    strokeWidth="3"
                  />
                  <text
                    x={x(packs)}
                    y={Math.max(16, y(target) - 11)}
                    textAnchor="middle"
                    fill={PROBABILITY_ANALYTICS_TEXT_COLOR}
                    fontSize="11"
                    fontWeight="700"
                  >
                    {label}
                  </text>
                </g>
              ))}
              {hoveredPacks !== null ? (
                <g pointerEvents="none">
                  <line
                    x1={x(hoveredPacks)}
                    x2={x(hoveredPacks)}
                    y1="30"
                    y2="196"
                    stroke="rgba(226,232,240,.35)"
                    strokeDasharray="3 4"
                  />
                  <circle
                    cx={x(hoveredPacks)}
                    cy={y(hoveredProbability)}
                    r="4"
                    fill="white"
                  />
                </g>
              ) : null}
              <line
                x1="54"
                x2="680"
                y1="196"
                y2="196"
                stroke="rgba(148,163,184,.3)"
              />
              <text
                x="367"
                y="225"
                textAnchor="middle"
                fill="rgba(232,238,247,.62)"
                fontSize="11"
              >
                Packs Opened
              </text>
              <rect
                aria-label="Inspect cumulative probability"
                x="54"
                y="30"
                width="626"
                height="166"
                fill="transparent"
                className="cursor-crosshair"
                onPointerMove={move}
                onPointerLeave={() => {
                  setHoveredPacks(null);
                  setTooltipPoint(null);
                }}
              />
            </svg>
            {hoveredPacks !== null ? (
              <div
                role="status"
                className="pointer-events-none absolute z-10 max-w-[14rem] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,8,23,.92)] px-3 py-2 text-xs shadow-lg"
                style={{
                  left: `${Math.min(82, Math.max(5, (tooltipPoint?.x || 54) / 7.1))}%`,
                  top: `${Math.min(72, Math.max(5, ((tooltipPoint?.y || 30) / 235) * 100))}%`,
                  transform:
                    (tooltipPoint?.x || 0) > 520
                      ? "translateX(-100%)"
                      : "translateX(10px)",
                }}
              >
                <strong className="block text-[var(--text-primary)]">
                  {number(hoveredPacks)} packs opened
                </strong>
                <span className="text-[var(--text-secondary)]">
                  {percent(hoveredProbability)} chance of ≥1 copy
                </span>
              </div>
            ) : null}
          </div>
          <div className="mt-4">
            <h4 className="text-xs font-semibold uppercase tracking-[.1em] text-[var(--text-secondary)]">
              Probability Milestones
            </h4>
            <dl
              data-probability-milestone-rail
              className="mt-2 grid grid-cols-2 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-white/[.025] sm:grid-cols-4"
            >
              {milestones.map(({ label, packs }) => (
                <div
                  key={label}
                  className="border-b border-r border-[var(--border-subtle)] px-3 py-3 even:border-r-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
                >
                  <dt className="text-[11px] font-semibold uppercase tracking-[.06em] text-[var(--text-secondary)]">
                    {label} chance to pull
                  </dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
                    {number(packs)} packs
                    {finite(milestoneDollars?.[label]) !== null ? (
                      <span className="mt-1 block text-sm font-semibold text-[var(--text-primary)]">
                        ≈ {money(milestoneDollars[label])}
                      </span>
                    ) : null}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 text-sm text-[var(--text-secondary)]">
          Probability Journey is unavailable because this printing does not have
          a valid pull model.
        </div>
      )}
    </section>
  );
}

function ProductEconomics({
  chase,
  pullAnalyticsAvailable = false,
  showHeading = true,
}) {
  const products = useMemo(
    () => orderCardProducts(chase.products),
    [chase.products],
  );
  const [selectedId, setSelectedId] = useState(
    products[0]?.sealedProductId || null,
  );
  useEffect(
    () => setSelectedId(products[0]?.sealedProductId || null),
    [chase.cardVariantId, products],
  );
  const selected =
    products.find((product) => product.sealedProductId === selectedId) ||
    products[0];
  const selectedName =
    selected?.productName ||
    selected?.productFamilyLabel ||
    compactSealedProductLabel(selected);
  const selectedHref = buildSealedProductHref(selected);
  const expectedCopy = expectedProductsCopy(selected);
  if (!selected)
    return (
      <div>
        {showHeading ? (
          <h3 className="text-lg font-semibold">Choose How You Open It</h3>
        ) : null}
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Product economics are unavailable for this printing in the current
          simulation run.
        </p>
      </div>
    );
  return (
    <section
      aria-labelledby={showHeading ? "opening-title" : "opening-products-title"}
    >
      {showHeading ? (
        <h3 id="opening-title" className="text-lg font-semibold">
          Choose How You Open It
        </h3>
      ) : null}
      {!pullAnalyticsAvailable ? (
        <p
          data-product-pull-status
          className="mt-2 max-w-4xl text-sm text-[var(--text-secondary)]"
        >
          Card-level pull economics cannot be calculated for this printing until
          pull intelligence is available. Product market information remains
          available.
        </p>
      ) : null}
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(15rem,19rem)_minmax(0,1fr)]">
        <div>
          <label htmlFor="product-select" className="sr-only">
            Sealed product
          </label>
          <select
            id="product-select"
            value={selected.sealedProductId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="min-h-11 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] md:hidden"
          >
            {products.map((product) => (
              <option
                key={product.sealedProductId}
                value={product.sealedProductId}
              >
                {product.productName ||
                  product.productFamilyLabel ||
                  "Product identity unavailable"}{" "}
                ·{" "}
                {product.available
                  ? `${number(product.packCount)} packs`
                  : `${productDisplayPrice(product) === null ? "Price unavailable" : money(productDisplayPrice(product))} · Not supported`}
              </option>
            ))}
          </select>
          <div
            role="radiogroup"
            aria-label="Sealed product"
            className="hidden max-h-[22rem] space-y-1 overflow-y-auto pr-1 md:block"
          >
            {products.map((product) => {
              const active =
                selected.sealedProductId === product.sealedProductId;
              return (
                <button
                  key={product.sealedProductId}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setSelectedId(product.sealedProductId)}
                  className={`w-full rounded-lg border px-3 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${active ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_13%,rgba(2,8,23,.58))]" : "border-transparent bg-white/[.025] hover:border-[var(--border-subtle)] hover:bg-white/[.05]"}`}
                >
                  <span className="flex items-center gap-2.5">
                    {product.imageUrl ? (
                      <Image
                        src={product.imageUrl}
                        alt=""
                        width={44}
                        height={44}
                        className="h-11 w-11 flex-none rounded-md object-contain"
                      />
                    ) : null}
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">
                        {product.productName ||
                          product.productFamilyLabel ||
                          "Product identity unavailable"}
                      </span>
                      <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
                        {productDisplayPrice(product) === null
                          ? "Price unavailable"
                          : money(productDisplayPrice(product))}
                      </span>
                      <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
                        {product.available
                          ? `${number(product.packCount)} packs · ${percent(product.targetProbabilityPerProduct)} chance`
                          : `${finite(product.packCount) === null ? "" : `${number(product.packCount)} packs · `}Not supported`}
                      </span>
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.32)] p-4">
          <p className="text-xs font-bold uppercase tracking-[.12em] text-[var(--accent)]">
            Selected format
          </p>
          <h4 className="mt-1 text-xl font-semibold">{selectedName}</h4>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--text-secondary)]">
            {selected.imageUrl ? (
              <Image
                src={selected.imageUrl}
                alt=""
                width={64}
                height={64}
                className="h-16 w-16 rounded-lg object-contain"
              />
            ) : null}
            {selectedHref ? (
              <Link
                href={selectedHref}
                className="font-semibold text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              >
                View Product →
              </Link>
            ) : null}
          </div>
          {!selected.available ? (
            <>
              <dl className="mt-4 grid overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-white/[.025] sm:grid-cols-2">
                <AnalyticalMetric label="Product Price">
                  {productDisplayPrice(selected) === null
                    ? "Price unavailable"
                    : money(productDisplayPrice(selected))}
                </AnalyticalMetric>
              </dl>
              <p className="mt-4 rounded-lg border border-dashed border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
                Card-level opening intelligence is not currently supported for
                this product.
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {number(selected.packCount)} packs ·{" "}
                {percent(selected.targetProbabilityPerProduct)} chance of
                pulling this card
              </p>
              <dl
                data-product-analytics-matrix
                className="mt-4 grid overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-white/[.025] sm:grid-cols-2"
              >
                <AnalyticalMetric
                  className="border-b border-[var(--border-subtle)] sm:border-r"
                  label="Product Price"
                  info={`Market price used by the current product model${selected.priceAsOf ? ` as of ${selected.priceAsOf}` : ""}${selected.priceSource ? ` from ${selected.priceSource}` : ""}.`}
                >
                  {money(selected.productPrice)}
                </AnalyticalMetric>
                <AnalyticalMetric
                  className="border-b border-[var(--border-subtle)]"
                  label={expectedCopy.label}
                  info={expectedCopy.tooltip}
                >
                  {number(selected.expectedProductsToHit, 2)}
                </AnalyticalMetric>
                <AnalyticalMetric
                  className="border-b border-[var(--border-subtle)] sm:border-b-0 sm:border-r"
                  label="Gross Chase Spend"
                  info={`Estimated total spend at the long-run expected number of ${selectedName} products required per copy of this card, before crediting incidental pull value.`}
                >
                  {money(selected.grossSpend)}
                </AnalyticalMetric>
                <AnalyticalMetric
                  label="Recovery-adjusted Cost"
                  info="Gross Chase Spend minus modeled incidental pull recovery, including duplicate targets, at the run's gross Near Mint market-value basis. Fees, shipping, condition discounts, liquidity, and sell-through are not modeled."
                >
                  {money(selected.ripAcquisitionCost)}
                </AnalyticalMetric>
              </dl>
              <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">
                Recovery credits modeled incidental pulls at gross Near Mint
                market value. Fees, shipping, condition discounts, liquidity,
                and sell-through are not modeled.
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function PullProfile({ chase }) {
  const expectedChance = cumulativePullProbability(
    chase.modeledProbability,
    chase.expectedPacksToHit,
  );
  return (
    <section aria-labelledby="pull-profile-title">
      <h3 id="pull-profile-title" className="text-lg font-semibold">
        Pull Profile
      </h3>
      <dl data-pull-profile className="mt-2 grid sm:grid-cols-2">
        <div className="border-b border-[var(--border-subtle)] py-2 sm:border-b-0 sm:border-r sm:pr-6">
          <dt className="text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
            Pull Odds
          </dt>
          <dd className="mt-1 text-lg font-semibold tabular-nums">
            1 in {number(chase.impliedOddsOneInN, 2)} packs
          </dd>
        </div>
        <div className="py-2 sm:pl-6">
          <dt className="text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">
            Expected Packs
          </dt>
          <dd className="mt-1 text-lg font-semibold tabular-nums">
            {number(chase.expectedPacksToHit, 2)}
            {expectedChance !== null ? (
              <span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">
                ≈{percent(expectedChance, 0)} chance by then
              </span>
            ) : null}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function OpeningProductsSection({ detail }) {
  const chase = detail.chase || {};
  const pullAnalyticsAvailable = chase.available === true;
  return (
    <section
      aria-labelledby="opening-products-title"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
    >
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
        Index Plus
      </p>
      <h2 id="opening-products-title" className="mt-1 text-2xl font-semibold">
        Choose How You Open It
      </h2>
      <div className="mt-4">
        <ProductEconomics
          chase={chase}
          pullAnalyticsAvailable={pullAnalyticsAvailable}
          showHeading={false}
        />
      </div>
    </section>
  );
}

function PremiumLock() {
  const premiumTier = getRipTierPresentation("S", { strength: "hero" });
  return (
    <section
      data-chase-efficiency-lock
      className="set-glass-surface relative min-h-44 overflow-hidden rounded-2xl border border-[var(--tier-border)]"
      style={premiumTier.style}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 grid grid-cols-4 gap-2 p-5 opacity-20 blur-sm"
      >
        {[1, 2, 3, 4].map((key) => (
          <span
            key={key}
            className="h-16 rounded-xl bg-[var(--tier-surface)]"
          />
        ))}
      </div>
      <div className="relative z-10 flex min-h-44 flex-col items-center justify-center bg-[rgba(2,6,23,.72)] px-5 py-6 text-center">
        <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--tier-color)]">
          Index Premium
        </p>
        <h2 className="mt-2 text-xl font-semibold">Unlock Chase Efficiency</h2>
        <p className="mt-1 max-w-lg px-4 text-xs text-[var(--text-secondary)]">
          See how economically favorable this exact printing is to chase, its
          global context, and canonical milestone costs.
        </p>
        <Link
          href="/pricing"
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-[var(--tier-border)] bg-[var(--tier-surface)] px-4 text-sm font-semibold text-[var(--tier-color)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tier-color)]"
        >
          Explore Index Premium
        </Link>
      </div>
    </section>
  );
}

const rarityRankLabel = (rarity) =>
  rarity === "Special Illustration Rare"
    ? "Special Illustration Rares"
    : rarity === "Illustration Rare"
      ? "Illustration Rares"
      : `${rarity || "Rarity"} printings`;

function ChaseEfficiencySection({ state, detail }) {
  if (state.status === "loading")
    return (
      <section className="set-glass-surface rounded-2xl border border-[rgba(45,212,191,.2)] p-6 text-sm text-[var(--text-secondary)]">
        Loading Chase Efficiency…
      </section>
    );
  if (state.status !== "ready" || !state.payload?.row) {
    const probability = validPullProbability(detail.chase?.modeledProbability);
    const fallbackChase =
      probability === null
        ? null
        : {
            ...detail.chase,
            modeledProbability: probability,
            impliedOddsOneInN: 1 / probability,
            expectedPacksToHit: 1 / probability,
          };
    return (
      <section
        data-chase-efficiency-section
        className="set-glass-surface rounded-2xl border p-5"
        style={{ borderColor: PROBABILITY_ANALYTICS_SOFT_BORDER }}
      >
        <p
          className="text-xs font-bold uppercase tracking-[.14em]"
          style={{ color: PROBABILITY_ANALYTICS_COLOR }}
        >
          Chase Efficiency Â· Index Premium
        </p>
        <h2 className="mt-1 text-2xl font-semibold">Chase Efficiency</h2>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Chase Efficiency ranking is unavailable for this printing.
        </p>
        <div className="mt-5 space-y-5">
          {fallbackChase ? (
            <>
              <PullProfile chase={fallbackChase} />
              <ProbabilityJourney chase={fallbackChase} />
            </>
          ) : (
            <section data-pull-analytics-status>
              <h3 className="text-sm font-semibold">Pull Analytics</h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {pullStatusExplanation(detail.chase?.reason)}
              </p>
            </section>
          )}
        </div>
      </section>
    );
  }
  const row = state.payload.row,
    milestones = row.milestones || {};
  const detailProbability = validPullProbability(
    detail.chase?.modeledProbability,
  );
  const rowProbability = validPullProbability(row.exactPullProbability);
  const tolerance = Math.max(1e-12, Math.abs(rowProbability) * 1e-6);
  if (
    detailProbability !== null &&
    Math.abs(rowProbability - detailProbability) > tolerance
  ) {
    throw new Error(
      "Card Detail and Chase Efficiency exact-printing probabilities disagree.",
    );
  }
  const premiumChase = {
    ...detail.chase,
    modeledProbability: rowProbability,
    impliedOddsOneInN: 1 / rowProbability,
    expectedPacksToHit: 1 / rowProbability,
  };
  const dollars = {};
  for (const threshold of [50, 75, 90, 95]) {
    premiumChase[`packsFor${threshold}PercentChance`] =
      milestones[String(threshold)]?.packsNeeded;
    dollars[`${threshold}%`] = milestones[String(threshold)]?.spend;
  }
  const rank = row.ranks?.overall || {},
    chosen = row.chosenProduct || {};
  const chaseTier = getRipTierPresentation(row.tier, { strength: "hero" });
  return (
    <section
      data-chase-efficiency-section
      aria-labelledby="chase-efficiency-title"
      className="set-glass-surface overflow-hidden rounded-2xl border border-[var(--tier-border)]"
      style={chaseTier.style}
    >
      <header
        className="border-b p-5 sm:p-6"
        style={{
          borderColor: "var(--tier-border)",
          background:
            "linear-gradient(135deg, var(--tier-surface), rgba(2,8,23,.28))",
        }}
      >
        <p
          className="text-xs font-bold uppercase tracking-[.18em]"
          style={{ color: "var(--tier-color)" }}
        >
          Chase Efficiency · Index Premium
        </p>
        <h2
          id="chase-efficiency-title"
          className="mt-2 text-2xl font-semibold sm:text-3xl"
        >
          #{number(rank.rank)} of {number(rank.cohortSize)} eligible printings
        </h2>
        <p
          className="mt-1 text-sm font-semibold"
          style={{ color: "var(--tier-color)" }}
        >
          Top {number(row.topPercent, 1)}%
        </p>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          <strong className="text-[var(--text-primary)]">
            Chase Efficiency
          </strong>{" "}
          measures how economically favorable hunting this exact printing is
          relative to buying it and relative to other cards.
        </p>
      </header>
      <div className="space-y-5 p-4 sm:p-6">
        <PullProfile chase={premiumChase} />
        <section>
          <h3 className="text-lg font-semibold">Rank Context</h3>
          <dl
            data-rank-context-rail
            className="mt-2 grid grid-cols-2 border-y border-[var(--border-subtle)] lg:grid-cols-4"
          >
            {[
              ["Overall", row.ranks?.overall],
              ["Era", row.ranks?.era],
              ["Set", row.ranks?.set],
              [rarityRankLabel(row.rarity), row.ranks?.rarity],
            ].map(([label, value]) => (
              <AnalyticalMetric
                key={label}
                label={label}
                className="border-b border-r border-[var(--border-subtle)] even:border-r-0 lg:border-b-0 lg:border-r lg:last:border-r-0"
              >
                #{number(value?.rank)}{" "}
                <span className="text-sm font-normal text-[var(--text-secondary)]">
                  / {number(value?.cohortSize)}
                </span>
              </AnalyticalMetric>
            ))}
          </dl>
        </section>
        <section>
          <h3 className="text-lg font-semibold">Economics</h3>
          <dl
            data-chase-economics-matrix
            className="mt-2 grid overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-white/[.02] sm:grid-cols-2 lg:grid-cols-4"
          >
            <AnalyticalMetric
              className="border-b border-r border-[var(--border-subtle)]"
              label="Card Market Price"
            >
              {money(row.currentNearMintMarketPrice)}
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-b border-[var(--border-subtle)] lg:border-r"
              label="Best Verified Opening Route"
            >
              {chosen.name || "Unavailable"}
              <span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">
                {number(chosen.randomPackCount)} random packs ·{" "}
                {money(chosen.price)}
              </span>
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-b border-r border-[var(--border-subtle)]"
              label="Effective Pack Cost"
            >
              {money(row.bestVerifiedPackEquivalentCost)}
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-b border-[var(--border-subtle)]"
              label="Loose Pack Price"
            >
              {money(row.looseBoosterPackPrice)}
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-b border-r border-[var(--border-subtle)] lg:border-b-0"
              label="Chance at Buy Price"
            >
              {percent(row.chanceAtBuyPrice)}
              <span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">
                within {number(row.packsAtBuyPrice)} pack-equivalents
              </span>
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-b border-[var(--border-subtle)] lg:border-b-0 lg:border-r"
              label="50% Cost Multiple"
            >
              {finite(row.costMultiple50) === null
                ? "Unavailable"
                : `${number(row.costMultiple50, 1)}× the single`}
            </AnalyticalMetric>
            <AnalyticalMetric
              className="border-r border-[var(--border-subtle)]"
              label="Chase Efficiency"
            >
              {number(row.chaseEfficiency, 6)}
            </AnalyticalMetric>
          </dl>
        </section>
        <ProbabilityJourney chase={premiumChase} milestoneDollars={dollars} />
      </div>
    </section>
  );
}

function treatmentMethodology(rarity, metric) {
  const lead =
    "How much extra value does the market give a card just because of its treatment, once we remove the effects of Pokémon popularity and rarity/pull odds?";
  if (!metric?.available)
    return `${lead} Treatment Prestige V2 is currently unavailable for this printing because approved scarcity-adjusted evidence has not been published.`;
  const premium = finite(metric.adjustedMarketPremiumPct);
  const score = finite(metric.score10);
  const evidence =
    metric.cardCount && metric.setCount
      ? ` Based on ${metric.cardCount} cards across ${metric.setCount} sets.`
      : "";
  return `${lead} Treatment Prestige V2 estimates the market premium associated with this treatment after controlling for Pokémon identity/popularity, pull scarcity, and set effects. The 0–10 score is derived from how consistently this treatment's adjusted premium exceeds other validated treatments across repeated statistical samples. Scores are measured from market data, not assigned by hand. Current treatment: ${rarity || metric.treatmentKey || "Unavailable"}. Adjusted treatment premium: ${premium === null ? "Unavailable" : `${premium >= 0 ? "+" : ""}${premium.toFixed(1)}%`}. Treatment score: ${score === null ? "Unavailable" : `${score.toFixed(1)} / 10`}. Study: Card Treatment Prestige V2.${evidence}`;
}

function CollectorIntelligence({ intelligence, rarity }) {
  const Meter = ({ label, metric, info, primary = false }) => {
    const score = scorePercent(metric?.score);
    const available = metric?.available && score !== null;
    const tier = getRipTierPresentation(metric?.tier, {
      strength: primary ? "supporting" : "factor",
    });
    return (
      <div
        style={tier.style}
        className={`rounded-xl border p-3.5 ${tier.tier ? "border-[var(--tier-border)] bg-[var(--tier-surface)]" : primary ? "border-[rgba(45,212,191,.25)] bg-[rgba(2,8,23,.46)]" : "border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)]"}`}
      >
        <dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[.1em] text-[var(--text-secondary)]">
          <span>{label}</span>
          <InfoPopover text={info} />
        </dt>
        <dd className="mt-2 flex items-center justify-between gap-3">
          <span
            className={`${primary ? "text-2xl" : "text-xl"} font-semibold tabular-nums`}
          >
            {available ? `${(score / 10).toFixed(1)} / 10` : "Unavailable"}
          </span>
          {available && tier.tier ? (
            <span
              className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg border border-[var(--tier-border)] px-2 text-sm font-bold text-[var(--tier-color)]"
              aria-label={tier.label}
            >
              {tier.tier}
            </span>
          ) : null}
        </dd>
        {available ? (
          <div
            aria-hidden="true"
            className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[.07]"
          >
            <span
              className="block h-full rounded-full bg-[var(--tier-track-fill,var(--accent))]"
              style={{ width: `${score}%` }}
            />
          </div>
        ) : (
          <div
            aria-hidden="true"
            className="mt-3 h-1.5 rounded-full bg-white/[.04]"
          />
        )}
      </div>
    );
  };
  return (
    <section
      aria-labelledby="collector-title"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
    >
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
        Index Plus
      </p>
      <h2 id="collector-title" className="mt-1 text-2xl font-semibold">
        Collector Intelligence
      </h2>
      <p className="mt-1.5 max-w-3xl text-sm text-[var(--text-secondary)]">
        Card Appeal combines Pokémon demand and this card’s collectible
        treatment. It is not a price prediction.
      </p>
      <dl className="mt-4 space-y-2">
        <Meter
          label="Card Appeal"
          metric={intelligence?.cardAppeal}
          info="inDex's composite collector-interest score for this card. It combines Pokémon Demand and Card Treatment using the published card-appeal weights, renormalized across available factors. It is not a price prediction."
          primary
        />
        <div className="grid gap-2 sm:grid-cols-3">
          <Meter
            label="Pokémon Demand"
            metric={intelligence?.pokemonDemand}
            info="The weighted desirability score of the Pokémon subjects linked to this card, using the published Pokémon desirability composite records and their card-link contribution weights."
          />
          <Meter
            label="Card Treatment"
            metric={intelligence?.treatmentPrestige}
            info={treatmentMethodology(rarity, intelligence?.treatmentPrestige)}
          />
          <Meter
            label="Scarcity"
            metric={intelligence?.scarcity}
            info="Scarcity scoring is not currently published for this card or printing."
          />
        </div>
      </dl>
    </section>
  );
}

function CardArtwork({ detail, imageRef, onLoad }) {
  const source = detail.card.imageLargeUrl || detail.card.imageSmallUrl;
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [source]);
  if (!source || failed)
    return (
      <div
        data-card-artwork-fallback
        className="flex aspect-[734/1024] w-full max-w-[300px] items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-white/[.035] px-6 text-center text-sm text-[var(--text-secondary)]"
      >
        Card artwork unavailable
      </div>
    );
  return (
    <Image
      ref={imageRef}
      src={source}
      alt={`${detail.card.name} card artwork`}
      width={734}
      height={1024}
      priority
      onLoad={onLoad}
      onError={() => setFailed(true)}
      className="h-auto w-full max-w-[430px] object-contain drop-shadow-[0_24px_40px_rgba(0,0,0,.48)] md:h-full md:w-auto md:max-w-full"
    />
  );
}

export default function PokemonCardDetailClient({ initialDetail }) {
  const [detail, setDetail] = useState(initialDetail);
  const [error, setError] = useState(null);
  const [pending, startTransition] = useTransition();
  const artworkAreaRef = useRef(null);
  const artworkImageRef = useRef(null);
  const [artworkAlignment, setArtworkAlignment] = useState(null);
  const { user } = useAuth();
  const router = useRouter();
  const entitled = hasIndexPlusAccess(user?.index_plan);
  const premiumEntitled = hasIndexFeatureAccess(
    user?.index_plan,
    FEATURE_CARD_CHASE_EFFICIENCY,
  );
  const [chaseEfficiencyState, setChaseEfficiencyState] = useState({
    status: "idle",
    payload: null,
  });
  useEffect(() => {
    if (!premiumEntitled) {
      setChaseEfficiencyState({ status: "locked", payload: null });
      return undefined;
    }
    const controller = new AbortController();
    setChaseEfficiencyState({ status: "loading", payload: null });
    getPokemonCardChaseEfficiency(
      detail.set.id,
      detail.card.id,
      detail.selectedVariantId,
      { signal: controller.signal },
    )
      .then((payload) => setChaseEfficiencyState({ status: "ready", payload }))
      .catch((caught) => {
        if (caught.name !== "AbortError")
          setChaseEfficiencyState({
            status: "error",
            error: caught.message,
            payload: null,
          });
      });
    return () => controller.abort();
  }, [
    premiumEntitled,
    detail.set.id,
    detail.card.id,
    detail.selectedVariantId,
  ]);
  const setHref = buildCardParentSetHref(detail.set);
  const cardImageSource =
    detail.card.imageLargeUrl || detail.card.imageSmallUrl;
  const syncArtworkAlignment = useCallback(() => {
    const image = artworkImageRef.current;
    const area = artworkAreaRef.current;
    if (
      !image ||
      !area ||
      !image.complete ||
      image.naturalWidth <= 0 ||
      image.naturalHeight <= 0
    )
      return;
    const painted = getObjectContainPaintedRect({
      imageRect: image.getBoundingClientRect(),
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
    });
    if (!painted) return;
    const areaBounds = area.getBoundingClientRect();
    setArtworkAlignment({
      width: painted.width,
      left: painted.left - areaBounds.left,
    });
  }, []);
  useLayoutEffect(() => {
    setArtworkAlignment(null);
    const image = artworkImageRef.current;
    const area = artworkAreaRef.current;
    if (!image || !area) return undefined;
    syncArtworkAlignment();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(syncArtworkAlignment);
    observer.observe(image);
    observer.observe(area);
    window.addEventListener("resize", syncArtworkAlignment);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", syncArtworkAlignment);
    };
  }, [
    cardImageSource,
    detail.card.id,
    detail.selectedVariantId,
    syncArtworkAlignment,
  ]);
  const artwork = optimizedImageUrl(
    detail.set.heroImageUrl ||
      detail.set.logoImageUrl ||
      detail.set.symbolImageUrl,
    SET_LOGO_WIDTH,
  );
  const selectVariant = (variantId) =>
    startTransition(async () => {
      try {
        setError(null);
        const next = await getPokemonCardDetail(
          detail.set.id,
          detail.card.id,
          variantId,
        );
        setDetail(next);
        router.replace(
          buildPokemonCardDetailHref({
            setSlug: detail.set.slug,
            canonicalCardId: detail.card.id,
            cardVariantId: variantId,
          }),
          { scroll: false },
        );
      } catch (caught) {
        setError(caught.message);
      }
    });
  return (
    <main className="card-detail-environment index-environment set-detail-glass-scope relative isolate min-h-screen px-4 pb-10 pt-5 text-[var(--text-primary)] sm:px-6 lg:px-8">
      <PageArtworkAtmosphere
        src={artwork}
        dataAttribute="data-card-set-ambient-artwork"
        visibilityClassName="hidden sm:block"
      />
      <nav
        data-card-back-navigation
        className="relative mx-auto mb-4 max-w-[1600px]"
      >
        <Link
          href={setHref}
          className="inline-flex min-h-10 items-center rounded-lg pr-3 text-sm font-semibold text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          ← Back to {detail.set.name}
        </Link>
      </nav>
      <div className="relative mx-auto max-w-[1400px] space-y-4">
        <section
          data-card-detail-hero
          className="grid gap-4 md:grid-cols-[minmax(260px,36%)_minmax(0,1fr)] md:items-stretch lg:gap-7"
        >
          <div className="order-1 flex min-w-0 justify-center md:h-full md:min-h-0">
            <div
              data-card-visual-frame
              className="grid h-full min-h-0 w-full gap-4 md:grid-rows-[auto_minmax(0,1fr)]"
            >
              <header
                data-card-identity
                className="min-w-0 max-w-full justify-self-start text-left"
                style={
                  artworkAlignment
                    ? {
                        width: `${artworkAlignment.width}px`,
                        marginLeft: `${artworkAlignment.left}px`,
                      }
                    : undefined
                }
              >
                <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
                  {detail.set.name}
                </p>
                <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">
                  {detail.card.name}
                </h1>
                <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
                  {[
                    detail.card.rarity,
                    detail.card.printedNumber || detail.card.cardNumber,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  Market Price As Of {dateLabel(detail.market.marketDate)}
                </p>
                {error ? (
                  <p role="alert" className="mt-2 text-sm text-red-300">
                    {error}
                  </p>
                ) : null}
              </header>
              <div
                ref={artworkAreaRef}
                className="card-detail-artwork flex min-h-[280px] items-center justify-center md:min-h-0 md:items-end"
              >
                <CardArtwork
                  detail={detail}
                  imageRef={artworkImageRef}
                  onLoad={syncArtworkAlignment}
                />
              </div>
            </div>
          </div>
          <div className="order-2 min-w-0 md:h-full">
            <div data-card-market-panel className="h-full">
              <AssetMarketPanel market={detail.market} />
            </div>
          </div>
        </section>
        <VariantSelector
          detail={detail}
          onSelect={selectVariant}
          pending={pending}
        />
        {premiumEntitled ? (
          <ChaseEfficiencySection
            state={chaseEfficiencyState}
            detail={detail}
          />
        ) : (
          <PremiumLock />
        )}
        {entitled ? (
          <OpeningProductsSection detail={detail} />
        ) : (
          <PlusLock title="Choose How You Open It" />
        )}
        {entitled ? (
          <CollectorIntelligence
            intelligence={detail.intelligence}
            rarity={detail.card.rarity}
          />
        ) : (
          <PlusLock title="Collector Intelligence" />
        )}
        <details className="set-glass-surface rounded-2xl border p-4 text-sm text-[var(--text-secondary)]">
          <summary className="cursor-pointer font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">
            Methodology & Provenance
          </summary>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            <li>
              Market points are real variant- and condition-scoped observations.
            </li>
            <li>
              Pull rates and product composition are modeled, not guaranteed.
            </li>
            <li>
              Opening outcomes are independent under the model assumptions.
            </li>
            <li>
              Market prices are derived from tracked market observations;
              recovery model: {detail.chase?.recoveryModel || "Unavailable"}.
            </li>
          </ul>
        </details>
        <Link
          href={setHref}
          className="group flex min-h-12 items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-white/[.035] px-4 text-sm font-semibold transition hover:border-[color-mix(in_srgb,var(--accent)_40%,transparent)] hover:bg-white/[.055] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          <span>Explore more cards from {detail.set.name}</span>
          <span
            aria-hidden="true"
            className="text-[var(--accent)] transition-transform group-hover:translate-x-1"
          >
            →
          </span>
        </Link>
      </div>
    </main>
  );
}
