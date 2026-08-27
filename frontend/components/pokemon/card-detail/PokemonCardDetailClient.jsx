"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import { useAuth } from "@/components/AuthContext";
import InfoPopover from "@/components/ui/InfoPopover";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { getRipTierPresentation } from "@/components/explore/ripTierPresentation.mjs";
import { hasIndexPlusAccess } from "@/lib/access/indexPlanAccess.mjs";
import {
  optimizedImageUrl,
  SET_LOGO_WIDTH,
} from "@/lib/images/remoteImageDelivery.mjs";
import { getPokemonCardDetail } from "@/lib/pokemon/pokemonCardDetailClient";
import { compactSealedProductLabel } from "@/components/pokemon/set-page/Overview/sealedMarketTrendSelector.mjs";
import AssetMarketPanel from "./AssetMarketPanel";
import {
  cumulativePullProbability,
  milestoneXPosition,
  packsAtPlotX,
  probabilityMilestones,
  scorePercent,
  validPullProbability,
} from "./cardDetailModel.mjs";

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
              {!variant.modeled ? " · Not modeled" : ""}
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
      aria-labelledby={id}
      className="set-glass-surface relative overflow-hidden rounded-2xl border p-5"
    >
      <div
        aria-hidden="true"
        className="grid grid-cols-3 gap-3 opacity-20 blur-sm"
      >
        <span className="h-16 rounded-xl bg-white/10" />
        <span className="h-16 rounded-xl bg-white/10" />
        <span className="h-16 rounded-xl bg-white/10" />
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-[rgba(2,6,23,.62)] text-center">
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

function ProbabilityJourney({ chase }) {
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
      className="rounded-2xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.42)] p-4"
    >
      <h3 id="probability-title" className="text-lg font-semibold">
        Probability Journey
      </h3>
      <p className="mt-1.5 max-w-4xl text-sm leading-relaxed text-[var(--text-secondary)]">
        Your cumulative chance of pulling this exact printing at least once as
        you open more eligible packs. Pull odds are modeled probabilities, not
        guarantees; “1 in N” describes a long-run rate, not a promise within N
        packs.
      </p>
      {usable ? (
        <>
          <div
            data-probability-journey-chart
            className="relative mt-4 overflow-hidden rounded-xl border border-[rgba(45,212,191,.14)] bg-[rgba(2,8,23,.46)] px-2 py-3 sm:px-4"
          >
            <svg
              role="img"
              aria-labelledby="probability-chart-title probability-chart-desc"
              viewBox="0 0 710 235"
              className="h-[190px] w-full sm:h-[220px]"
            >
              <title id="probability-chart-title">
                Cumulative pull probability by packs opened
              </title>
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
                    stopColor="rgb(45,212,191)"
                    stopOpacity=".24"
                  />
                  <stop
                    offset="1"
                    stopColor="rgb(45,212,191)"
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
                stroke="rgb(45,212,191)"
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
                    stroke="rgba(45,212,191,.16)"
                    strokeDasharray="2 5"
                  />
                  <circle
                    cx={x(packs)}
                    cy={y(target)}
                    r="5"
                    fill="rgb(45,212,191)"
                    stroke="rgba(4,15,26,.9)"
                    strokeWidth="3"
                  />
                  <text
                    x={x(packs)}
                    y={Math.max(16, y(target) - 11)}
                    textAnchor="middle"
                    fill="rgb(153,246,228)"
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
          <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {milestones.map(({ label, packs }) => (
              <Metric key={label} label={`${label} Chance`}>
                {number(packs)} packs
              </Metric>
            ))}
          </dl>
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

function ProductEconomics({ chase }) {
  const products = useMemo(
    () => (Array.isArray(chase.products) ? chase.products : []),
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
  if (!selected)
    return (
      <div>
        <h3 className="text-lg font-semibold">Choose How You Open It</h3>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Product economics are unavailable for this printing in the current
          simulation run.
        </p>
      </div>
    );
  return (
    <section aria-labelledby="opening-title">
      <h3 id="opening-title" className="text-lg font-semibold">
        Choose How You Open It
      </h3>
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(13rem,17rem)_minmax(0,1fr)]">
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
                {compactSealedProductLabel(product)} ·{" "}
                {product.available
                  ? `${number(product.packCount)} packs`
                  : "Not supported"}
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
                  <span className="block text-sm font-semibold">
                    {compactSealedProductLabel(product)}
                  </span>
                  <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
                    {product.available
                      ? `${number(product.packCount)} packs · ${percent(product.targetProbabilityPerProduct)} chance`
                      : "Not supported"}
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
          <h4 className="mt-1 text-xl font-semibold">
            {compactSealedProductLabel(selected)}
          </h4>
          {!selected.available ? (
            <p className="mt-4 rounded-lg border border-dashed border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
              Card-level opening intelligence is not currently supported for
              this product.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {number(selected.packCount)} packs ·{" "}
                {percent(selected.targetProbabilityPerProduct)} chance of
                pulling this card
              </p>
              <dl className="mt-4 grid gap-2 sm:grid-cols-2">
                <Metric
                  label="Product Price"
                  info={`Market price used by the current product model${selected.priceAsOf ? ` as of ${selected.priceAsOf}` : ""}${selected.priceSource ? ` from ${selected.priceSource}` : ""}.`}
                >
                  {money(selected.productPrice)}
                </Metric>
                <Metric
                  label="Expected Products"
                  info="The long-run average number of fully opened products needed per successful product under the modeled product pull probability."
                >
                  {number(selected.expectedProductsToHit, 2)}
                </Metric>
                <Metric
                  label="Gross Chase Spend"
                  info="Product market price multiplied by the model's expected number of fully opened products needed to reach the first successful product."
                >
                  {money(selected.grossSpend)}
                </Metric>
                <Metric
                  label="Recovery-adjusted Cost"
                  info="Gross Chase Spend minus modeled incidental pull recovery, including duplicate targets, at the run's gross Near Mint market-value basis."
                >
                  {money(selected.ripAcquisitionCost)}
                </Metric>
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

function CardIntelligence({ detail }) {
  const chase = detail.chase || {};
  if (!chase.available)
    return (
      <section
        aria-labelledby="card-intelligence-title"
        className="set-glass-surface rounded-2xl border p-4 sm:p-5"
      >
        <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
          Index Plus
        </p>
        <h2
          id="card-intelligence-title"
          className="mt-1 text-2xl font-semibold"
        >
          Card Intelligence
        </h2>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Pull intelligence is not modeled for this printing. Its available
          market data remains usable above.
        </p>
      </section>
    );
  const expectedChance = cumulativePullProbability(
    chase.modeledProbability,
    chase.expectedPacksToHit,
  );
  return (
    <section
      aria-labelledby="card-intelligence-title"
      className="set-glass-surface rounded-2xl border p-4 sm:p-5"
    >
      <p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">
        Index Plus
      </p>
      <h2 id="card-intelligence-title" className="mt-1 text-2xl font-semibold">
        Card Intelligence
      </h2>
      <div className="mt-4 space-y-4">
        <dl className="grid gap-2 sm:grid-cols-3">
          <Metric
            label="Pull Odds"
            info="Long-run modeled probability of pulling this exact card printing from one eligible pack."
          >
            1 in {number(chase.impliedOddsOneInN, 2)} packs
          </Metric>
          <Metric
            label="Expected Packs"
            info="The long-run average number of eligible packs per copy. This is not the number of packs required to guarantee a pull."
          >
            {number(chase.expectedPacksToHit, 2)}
            {expectedChance !== null ? (
              <span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">
                ≈{percent(expectedChance, 0)} chance by then
              </span>
            ) : null}
          </Metric>
          {finite(chase.expectedSpend) !== null ? (
            <Metric label="Expected Spend">{money(chase.expectedSpend)}</Metric>
          ) : null}
        </dl>
        <ProbabilityJourney chase={chase} />
        <ProductEconomics chase={chase} />
      </div>
    </section>
  );
}

function CollectorIntelligence({ intelligence }) {
  const Meter = ({ label, metric, primary = false }) => {
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
        <dt className="text-xs font-semibold uppercase tracking-[.1em] text-[var(--text-secondary)]">
          {label}
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
        <Meter label="Card Appeal" metric={intelligence?.cardAppeal} primary />
        <div className="grid gap-2 sm:grid-cols-3">
          <Meter label="Pokémon Demand" metric={intelligence?.pokemonDemand} />
          <Meter label="Card Treatment" metric={intelligence?.treatment} />
          <Meter label="Scarcity" metric={intelligence?.scarcity} />
        </div>
      </dl>
    </section>
  );
}

function CardArtwork({ detail }) {
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
      src={source}
      alt={`${detail.card.name} card artwork`}
      width={734}
      height={1024}
      priority
      onError={() => setFailed(true)}
      className="h-auto max-h-[46vh] w-auto max-w-full object-contain drop-shadow-[0_24px_40px_rgba(0,0,0,.48)]"
    />
  );
}

export default function PokemonCardDetailClient({ initialDetail }) {
  const [detail, setDetail] = useState(initialDetail);
  const [error, setError] = useState(null);
  const [pending, startTransition] = useTransition();
  const { user } = useAuth();
  const router = useRouter();
  const entitled = hasIndexPlusAccess(user?.index_plan);
  const setHref = `/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}?tab=cards`;
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
          `/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}/Cards/${encodeURIComponent(detail.card.id)}?variant=${encodeURIComponent(variantId)}`,
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
      <div className="relative mx-auto max-w-[1400px] space-y-4">
        <div>
          <Link
            href={setHref}
            className="inline-flex min-h-10 items-center rounded-lg pr-3 text-sm font-semibold text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            ← Back to {detail.set.name}
          </Link>
        </div>
        <section
          data-card-detail-hero
          className="grid gap-4 md:grid-cols-[minmax(210px,31%)_minmax(0,1fr)] md:items-stretch lg:gap-7"
        >
          <div className="order-2 space-y-4 md:order-1">
            <div className="card-detail-artwork flex min-h-[280px] justify-center">
              <CardArtwork detail={detail} />
            </div>
            <section
              aria-labelledby="details-title"
              className="set-glass-surface rounded-xl border px-4 py-3"
            >
              <h2 id="details-title" className="text-sm font-semibold">
                Card Details
              </h2>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div>
                  <dt className="text-xs text-[var(--text-secondary)]">Set</dt>
                  <dd className="font-medium">{detail.set.name}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[var(--text-secondary)]">
                    Card Number
                  </dt>
                  <dd className="font-medium">
                    {detail.card.printedNumber ||
                      detail.card.cardNumber ||
                      "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-[var(--text-secondary)]">
                    Rarity
                  </dt>
                  <dd className="font-medium">
                    {detail.card.rarity || "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-[var(--text-secondary)]">
                    Market Price As Of
                  </dt>
                  <dd className="font-medium">
                    {dateLabel(detail.market.marketDate)}
                  </dd>
                </div>
              </dl>
              <div className="mt-4">
                <VariantSelector
                  detail={detail}
                  onSelect={selectVariant}
                  pending={pending}
                />
              </div>
              {error ? (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  {error}
                </p>
              ) : null}
            </section>
          </div>
          <div className="order-1 min-w-0 space-y-3 md:order-2">
            <header>
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
            </header>
            <AssetMarketPanel market={detail.market} />
          </div>
        </section>
        {entitled ? (
          <>
            <CardIntelligence detail={detail} />
            <CollectorIntelligence intelligence={detail.intelligence} />
          </>
        ) : (
          <>
            <PlusLock title="Card Intelligence" />
            <PlusLock title="Collector Intelligence" />
          </>
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
              Market source: {detail.market.source || "Unavailable"}; recovery
              model: {detail.chase?.recoveryModel || "Unavailable"}.
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
