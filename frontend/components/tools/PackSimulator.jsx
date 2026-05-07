"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import InterpretationInsight from "@/components/explore/InterpretationInsight";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import ToolHistoricalComparisonChart from "@/components/tools/ToolHistoricalComparisonChart";
import InfoPopover from "@/components/ui/InfoPopover";
import InterpretationBadge from "@/components/ui/InterpretationBadge";
import RankBadge from "@/components/ui/RankBadge";
import { getCalloutAccentStyle, getInterpretationTone } from "@/lib/explore/interpretationTone";
import { runPackSimulation } from "@/lib/tools/packSimulatorClient";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : currencyFormatter.format(parsed);
}

function formatPercent(value, probability = false) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  const normalized = probability && parsed <= 1 ? parsed * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function formatScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : parsed.toFixed(1);
}

function formatRatio(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : `${parsed.toFixed(2)}x`;
}

function formatSignedCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  if (Math.abs(parsed) < 0.005) {
    return currencyFormatter.format(0);
  }
  return `${parsed < 0 ? "-" : "+"}${currencyFormatter.format(Math.abs(parsed))}`;
}

function formatDelta(value, percent = false) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  if (Math.abs(parsed) < 0.0001) {
    return "No change";
  }
  const sign = parsed > 0 ? "+" : "-";
  const abs = Math.abs(parsed);
  return percent ? `${sign}${abs.toFixed(1)} pts` : `${sign}${abs.toFixed(2)}`;
}

function formatProbabilityDeltaPoints(customValue, marketValue) {
  const custom = toNumber(customValue);
  const market = toNumber(marketValue);
  if (custom === null || market === null) {
    return "-";
  }
  const customPct = custom <= 1 ? custom * 100 : custom;
  const marketPct = market <= 1 ? market * 100 : market;
  return formatDelta(customPct - marketPct, true);
}

function formatDisplayRarity(hit) {
  const raw =
    hit?.display_rarity ||
    hit?.rarity_type ||
    hit?.rarity ||
    hit?.rarity_bucket ||
    null;
  if (!raw) {
    return null;
  }

  const normalized = String(raw).replace(/_/g, " ").trim();
  if (!normalized) {
    return null;
  }

  const lower = normalized.toLowerCase();
  if (lower === "hits") {
    return null;
  }

  const alias = {
    sir: "Special Illustration Rare",
    ir: "Illustration Rare",
    ur: "Ultra Rare",
    dr: "Double Rare",
    hr: "Hyper Rare",
  };

  if (alias[lower]) {
    return alias[lower];
  }

  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function ViewModeToggle({ viewMode, onChange }) {
  return (
    <div className="inline-grid w-full max-w-xs grid-cols-2 items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/92 p-1 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03),0_10px_24px_rgba(15,23,42,0.14)] sm:inline-flex sm:w-auto sm:max-w-none">
      <button
        type="button"
        onClick={() => onChange("simple")}
        aria-pressed={viewMode === "simple"}
        className={`min-w-0 rounded-full px-3 py-2 text-[10px] font-semibold leading-none transition-colors sm:min-w-[4.5rem] sm:px-3 sm:py-1.5 ${
          viewMode === "simple"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Simple
      </button>
      <button
        type="button"
        onClick={() => onChange("expert")}
        aria-pressed={viewMode === "expert"}
        className={`min-w-0 rounded-full px-3 py-2 text-[10px] font-semibold leading-none transition-colors sm:min-w-[4.5rem] sm:px-3 sm:py-1.5 ${
          viewMode === "expert"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Expert
      </button>
    </div>
  );
}

function ScoreModeToggle({ scoreMode, onChange }) {
  return (
    <div className="inline-grid w-full max-w-[12rem] grid-cols-2 items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/92 p-1 sm:inline-flex sm:w-auto sm:max-w-none">
      <button
        type="button"
        onClick={() => onChange("relative")}
        aria-pressed={scoreMode === "relative"}
        className={`min-w-0 rounded-full px-2.5 py-1.5 text-[9px] font-semibold leading-none transition-colors sm:min-w-[4rem] ${
          scoreMode === "relative"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Relative
      </button>
      <button
        type="button"
        onClick={() => onChange("absolute")}
        aria-pressed={scoreMode === "absolute"}
        className={`min-w-0 rounded-full px-2.5 py-1.5 text-[9px] font-semibold leading-none transition-colors sm:min-w-[4rem] ${
          scoreMode === "absolute"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Absolute
      </button>
    </div>
  );
}

function ScoreMeter({ score }) {
  const parsed = Number(score);
  const width = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : 0;
  return (
    <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="relative h-full overflow-hidden rounded-full"
        style={{
          width: `${width}%`,
          background:
            "linear-gradient(90deg, rgba(20,184,166,0.66) 0%, rgba(45,212,191,0.82) 50%, rgba(94,234,212,0.54) 85%, rgba(94,234,212,0.74) 100%)",
        }}
      />
    </div>
  );
}

function SectionCard({ title, subtitle = null, titleInfoText = null, children }) {
  return (
    <article className="w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
          {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
        </div>
        {subtitle ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className="mt-4">{children}</div>
    </article>
  );
}

function ComparisonMetricCard({ label, marketValue, yourValue, differenceValue, isGood = null, note = null }) {
  const diffColor =
    isGood === true
      ? "text-emerald-400"
      : isGood === false
        ? "text-rose-400"
        : "text-[var(--text-primary)]";
  return (
    <article className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(14,20,34,0.88),rgba(8,12,22,0.92))] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02)]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</p>
      <div className="mt-3 grid grid-cols-2 gap-x-3">
        <div>
          <p className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">At Market</p>
          <p className="mt-1 text-base font-semibold text-[var(--text-primary)]">{marketValue}</p>
        </div>
        <div>
          <p className="text-[9px] font-medium uppercase tracking-[0.07em] text-[rgba(20,184,166,0.85)]">At Your Price</p>
          <p className="mt-1 text-base font-semibold text-[var(--text-primary)]">{yourValue}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-[var(--border-subtle)]/40 pt-2.5">
        <p className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">Difference</p>
        <p className={`text-xs font-semibold ${diffColor}`}>{differenceValue}</p>
      </div>
      {note ? <p className="mt-1.5 text-[10px] text-[var(--text-secondary)]">{note}</p> : null}
    </article>
  );
}

function SingleValueMetricCard({ label, value, note = null }) {
  return (
    <article className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(14,20,34,0.88),rgba(8,12,22,0.92))] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02)]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
      {note ? <p className="mt-1.5 text-[10px] text-[var(--text-secondary)]">{note}</p> : null}
    </article>
  );
}

function ComparisonStatTile({ label, value }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-2 text-base font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function ScoreComparisonBlock({ marketScore, marketTier, customScore, customTier, deltaValue = null, priceIndependent = false }) {
  const delta = toNumber(deltaValue) ?? ((toNumber(customScore) || 0) - (toNumber(marketScore) || 0));
  const noChange = priceIndependent || Math.abs(delta) < 0.05;
  const isImprovement = !noChange && delta > 0;
  const diffColor = noChange
    ? "text-[var(--text-secondary)]"
    : isImprovement
      ? "text-emerald-400"
      : "text-rose-400";
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3">
      <div className="grid grid-cols-2 gap-x-4">
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">At Market</p>
          <p className="mt-1 text-xl font-bold leading-none text-[var(--text-primary)]">{formatScore(marketScore)}</p>
          <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Tier {marketTier || "-"}</p>
        </div>
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-[0.07em] text-[rgba(20,184,166,0.9)]">At Your Price</p>
          <p className="mt-1 text-xl font-bold leading-none text-[var(--text-primary)]">{formatScore(customScore)}</p>
          <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Tier {customTier || "-"}</p>
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-[var(--border-subtle)]/40 pt-2">
        <p className="text-[9px] font-medium uppercase tracking-[0.07em] text-[var(--text-secondary)]/70">Difference</p>
        <p className={`text-xs font-semibold ${diffColor}`}>
          {noChange ? "No change" : formatDelta(delta)}
        </p>
      </div>
    </div>
  );
}

function PillarMetricRows({ rows }) {
  if (!rows || rows.length === 0) {
    return null;
  }
  return (
    <div>
      <div className="grid grid-cols-[minmax(0,1fr)_5rem_5rem] items-center gap-x-2 pb-1.5 text-[9px] font-semibold uppercase tracking-[0.06em]">
        <span />
        <span className="text-right text-[var(--text-secondary)]/60">Market</span>
        <span className="text-right text-[rgba(20,184,166,0.75)]">Your Price</span>
      </div>
      {rows.map((row) => (
        <div
          key={row.label}
          className="grid min-h-[2.15rem] grid-cols-[minmax(0,1fr)_5rem_5rem] items-center gap-x-2 border-t border-[var(--border-subtle)]/40 py-2 text-xs last:pb-0"
        >
          <span className="text-[var(--text-secondary)]">{row.label}</span>
          <span className="text-right text-[var(--text-secondary)]">{typeof row.market === "string" ? row.market : String(row.market)}</span>
          <span className="text-right font-medium text-[var(--text-primary)]">{typeof row.custom === "string" ? row.custom : String(row.custom)}</span>
        </div>
      ))}
    </div>
  );
}

function RegradePillarCard({
  title,
  marketScore,
  customScore,
  marketTier,
  customTier,
  customRank,
  sectionMeta,
  rows,
  scoreDelta = null,
  priceIndependent = false,
  note = null,
}) {
  const customRankText = toNumber(customRank);
  return (
    <article className="grid h-full grid-rows-[auto_auto_minmax(6.75rem,auto)_auto_minmax(9rem,1fr)] rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div className="mb-3 min-h-[3.25rem] content-start flex min-w-0 flex-wrap items-center gap-2.5">
        <h3 className="text-sm font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">{title}</h3>
        <p className="text-2xl font-bold leading-none text-[var(--text-primary)]">{formatScore(customScore)}</p>
        <RankBadge
          rank={customTier}
          label={`${title} Rank`}
          title={customRankText === null ? `${title} rank unavailable` : `${title} Rank #${Math.round(customRankText)}`}
          size="supporting"
          subtle
        />
      </div>

      <ScoreMeter score={customScore} />

      <div className="mt-3 min-h-[6.75rem]">
        <InterpretationInsight
          sectionMeta={sectionMeta}
          fallbackSummary={null}
          rankTier={customTier || marketTier}
          compact
          showEvidence={false}
        />
      </div>

      <div className="mt-3 self-start">
        <ScoreComparisonBlock
          marketScore={marketScore}
          marketTier={marketTier}
          customScore={customScore}
          customTier={customTier}
          deltaValue={scoreDelta}
          priceIndependent={priceIndependent}
        />
      </div>

      <div className="mt-4 min-h-[9rem]">
        <PillarMetricRows rows={rows} />
        <div className="mt-3 min-h-[1rem]">
          {note ? <p className="text-xs text-[var(--text-secondary)]">{note}</p> : null}
        </div>
      </div>
    </article>
  );
}

function TopCardsContent({ topHits, meanValue, sectionMeta }) {
  const hits = Array.isArray(topHits) ? topHits.slice(0, 10) : [];
  const totalEV = toNumber(meanValue);
  const visibleTopEV = hits.reduce((sum, hit) => sum + (toNumber(hit?.ev_contribution) || 0), 0);
  const totalValue = totalEV !== null ? totalEV : visibleTopEV;

  if (hits.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No top card rows are available for this run.</p>;
  }

  const evidence = Array.isArray(sectionMeta?.evidence) ? sectionMeta.evidence : [];
  const leadingCard = evidence.find((item) => String(item?.label || "").toLowerCase().includes("leading card"));
  const leadingGroup = evidence.find((item) => String(item?.label || "").toLowerCase().includes("leading value"));

  return (
    <div className="space-y-2">
      {(leadingCard?.value || leadingGroup?.value) ? (
        <div className="mb-2 flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2">
          {leadingCard?.value ? (
            <span className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]">
              <span className="shrink-0">Leading card</span>
              <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(leadingCard.value)}</span>
            </span>
          ) : null}
          {leadingGroup?.value ? (
            <span className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]">
              <span className="shrink-0">Leading value group</span>
              <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(leadingGroup.value)}</span>
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mb-3 flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Simulated Average Pack Value</span>
        <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(totalValue)}</span>
      </div>

      {hits.map((hit, index) => {
        const imageSrc = hit?.image_url || hit?.image_small_url || hit?.image_large_url || null;
        const evContribution = toNumber(hit?.ev_contribution);
        const evShare = evContribution !== null && totalEV !== null && totalEV > 0 ? `${((evContribution / totalEV) * 100).toFixed(1)}%` : "-";
        const displayRarity = formatDisplayRarity(hit);
        const cardVariantId = hit?.card_variant_id;
        const isClickable = Boolean(cardVariantId);
        const content = (
          <div
            key={`repriced-hit:${hit?.card_name || "unknown"}:${index}`}
            className={`rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3 ${
              isClickable
                ? "cursor-pointer transition-transform group-hover:-translate-y-px group-hover:border-brand/50 group-hover:bg-[var(--surface-page)]/75 group-hover:shadow-[0_0_0_1px_rgba(20,184,166,0.18)]"
                : ""
            }`}
          >
            <div className="flex min-w-0 flex-col gap-3 sm:grid sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <div className="flex min-w-0 items-center gap-3">
                <div className="h-[4.5rem] w-[3.125rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]">
                  {imageSrc ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={imageSrc}
                      alt={hit?.card_name ? `${hit.card_name} card image` : "Card image"}
                      loading="lazy"
                      decoding="async"
                      className="h-full w-full rounded-[5px] object-contain"
                    />
                  ) : null}
                </div>
                <div className="min-w-0 max-w-full">
                  <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{hit?.card_name || "Unknown Card"}</p>
                  {displayRarity ? <p className="text-xs text-[var(--text-secondary)]">{displayRarity}</p> : null}
                  <p className="text-xs text-[var(--text-secondary)]">{evShare} of pack value</p>
                </div>
              </div>
              <div className="mt-3 grid min-w-0 grid-cols-2 gap-3 text-left sm:mt-0 sm:min-w-[13rem] sm:text-right">
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Near Mint Price</p>
                  <p className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{formatCurrency(hit?.current_near_mint_price)}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Value Contribution</p>
                  <p className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{formatCurrency(evContribution)}</p>
                </div>
              </div>
            </div>
          </div>
        );

        if (!isClickable) {
          return content;
        }

        return (
          <Link
            key={`repriced-hit-link:${hit?.card_name || "unknown"}:${index}`}
            href={`/cards/${encodeURIComponent(String(cardVariantId))}`}
            className="group block rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
            title="Open card detail"
            aria-label={`Open ${hit?.card_name || "card"} detail page`}
            prefetch={false}
          >
            {content}
          </Link>
        );
      })}
    </div>
  );
}

function CenteredSuffixInline({ as: Component = "button", children, suffix = null, className = "", contentClassName = "", suffixWrapperClassName = "", ...props }) {
  return (
    <Component
      {...props}
      className={[
        "relative inline-grid min-w-0 grid-cols-[1fr_auto_1fr] items-center text-center",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span aria-hidden="true" className="pointer-events-none invisible col-start-1 inline-flex min-w-[1rem] items-center justify-center">
        {suffix}
      </span>
      <span className={["col-start-2 min-w-0 truncate text-center", contentClassName].filter(Boolean).join(" ")}>
        {children}
      </span>
      {suffix ? (
        <span aria-hidden="true" className={["pointer-events-none col-start-3 inline-flex min-w-[1rem] items-center justify-center", suffixWrapperClassName].filter(Boolean).join(" ")}>
          {suffix}
        </span>
      ) : (
        <span aria-hidden="true" className="pointer-events-none invisible col-start-3 inline-flex min-w-[1rem] items-center justify-center" />
      )}
    </Component>
  );
}

function buildMarkerRows(result) {
  if (!result) {
    return [];
  }
  return [
    {
      key: "market-pack-cost",
      label: "Market Pack Cost",
      value: result?.charts?.baseline_reference_lines?.pack_cost,
    },
    {
      key: "custom-pack-cost",
      label: "Your Pack Cost",
      value: result?.charts?.custom_reference_lines?.pack_cost,
    },
    {
      key: "mean-value",
      label: "Mean Value",
      value: result?.charts?.baseline_reference_lines?.mean_value,
    },
    {
      key: "median-value",
      label: "Median Value",
      value: result?.charts?.baseline_reference_lines?.median_value,
    },
    {
      key: "big-hit-custom",
      label: "Big Hit (5x your cost)",
      value: result?.charts?.custom_reference_lines?.big_hit_threshold,
    },
  ];
}

function scoreForMode(entity, scoreMode, key) {
  if (!entity) {
    return null;
  }
  if (scoreMode === "relative") {
    const relativeKey = `relative_${key}`;
    if (entity[relativeKey] !== undefined && entity[relativeKey] !== null) {
      return entity[relativeKey];
    }
  }
  return entity[key];
}

export default function PackSimulator({ targets = [], defaultTargetId = "" }) {
  const [targetId, setTargetId] = useState(defaultTargetId || "");
  const [customPackCost, setCustomPackCost] = useState("5.50");
  const [viewMode, setViewMode] = useState("simple");
  const [scoreMode, setScoreMode] = useState("relative");
  const [graphMode, setGraphMode] = useState("outcome-distribution");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [heroSetPickerOpen, setHeroSetPickerOpen] = useState(false);
  const heroSetPickerRef = useRef(null);
  const hasMountedRef = useRef(false);
  const requestSequenceRef = useRef(0);
  const activeAbortControllerRef = useRef(null);

  const selectedTarget = useMemo(
    () => targets.find((entry) => String(entry?.target_id) === String(targetId)) || null,
    [targets, targetId]
  );
  const heroLogoUrl =
    selectedTarget?.logo_image_url || selectedTarget?.hero_image_url || selectedTarget?.symbol_image_url || null;

  const hasRelativeScores = useMemo(() => {
    if (!result) {
      return false;
    }
    const baselineHas = Object.keys(result?.baseline || {}).some((key) => key.startsWith("relative_"));
    const customHas = Object.keys(result?.custom || {}).some((key) => key.startsWith("relative_"));
    return baselineHas && customHas;
  }, [result]);

  const customPackScoreMeta = result?.custom?.interpretation_meta?.packScore || null;
  const recommendationSummary = customPackScoreMeta?.summary || result?.custom?.interpretation || null;
  const recommendationLabel = customPackScoreMeta?.label || "Repriced Summary";
  const recommendationTone = getInterpretationTone({
    label: recommendationLabel,
    rankTier: result?.custom?.pack_tier,
    severity: customPackScoreMeta?.severity,
  });

  const chartMarkers = useMemo(() => buildMarkerRows(result), [result]);
  const summaryMetrics = result?.comparison?.summary_metrics || {};
  const pillarMetrics = result?.comparison?.pillar_metrics || {};

  const displayedBaselinePackScore = scoreForMode(result?.baseline, scoreMode, "pack_score");
  const displayedCustomPackScore = scoreForMode(result?.custom, scoreMode, "pack_score");
  const displayedPackScoreDelta =
    toNumber(displayedCustomPackScore) !== null && toNumber(displayedBaselinePackScore) !== null
      ? (toNumber(displayedCustomPackScore) || 0) - (toNumber(displayedBaselinePackScore) || 0)
      : null;

  const displayedBaselineProfit = scoreForMode(result?.baseline, scoreMode, "profit_score");
  const displayedCustomProfit = scoreForMode(result?.custom, scoreMode, "profit_score");
  const displayedBaselineSafety = scoreForMode(result?.baseline, scoreMode, "safety_score");
  const displayedCustomSafety = scoreForMode(result?.custom, scoreMode, "safety_score");
  const displayedBaselineStability = scoreForMode(result?.baseline, scoreMode, "stability_score");
  const displayedCustomStability = scoreForMode(result?.custom, scoreMode, "stability_score");

  useEffect(() => {
    if (!heroSetPickerOpen || typeof document === "undefined") {
      return undefined;
    }

    const handleOutsideClick = (event) => {
      if (!event.target.closest?.("[data-hero-picker]")) {
        setHeroSetPickerOpen(false);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setHeroSetPickerOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("touchstart", handleOutsideClick, { passive: true });
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("touchstart", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [heroSetPickerOpen]);

  async function executeGrade({ nextTargetId = targetId, clearResultOnStart = false } = {}) {
    setError("");

    const parsedCost = Number(customPackCost);
    if (!nextTargetId) {
      setError("Select a set first.");
      return;
    }
    if (!Number.isFinite(parsedCost) || parsedCost <= 0 || parsedCost >= 1000) {
      setError("Enter a custom pack cost greater than 0 and less than 1000.");
      return;
    }

    const previousController = activeAbortControllerRef.current;
    if (previousController) {
      previousController.abort();
    }

    const controller = new AbortController();
    activeAbortControllerRef.current = controller;
    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;

    if (clearResultOnStart) {
      setResult(null);
    }
    setLoading(true);

    try {
      const payload = await runPackSimulation(
        {
          target_type: "set",
          target_id: nextTargetId,
          custom_pack_cost: parsedCost,
          mode: "fast",
        },
        { signal: controller.signal }
      );

      if (sequence !== requestSequenceRef.current) {
        return;
      }

      setResult(payload);
    } catch (requestError) {
      if (requestError?.name === "AbortError") {
        return;
      }
      if (sequence !== requestSequenceRef.current) {
        return;
      }
      setError(requestError?.message || "Failed to run pack repricing.");
    } finally {
      if (sequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    await executeGrade();
  }

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }

    if (!targetId) {
      return;
    }

    void executeGrade({ nextTargetId: targetId, clearResultOnStart: true });
  }, [targetId]);

  useEffect(() => {
    return () => {
      if (activeAbortControllerRef.current) {
        activeAbortControllerRef.current.abort();
      }
    };
  }, []);

  return (
    <main className="w-full max-w-full pb-8 pt-0 lg:py-8">
      <div className="dashboard-container mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-6">
        <section className="page-hero-panel relative overflow-hidden rounded-xl px-4 py-6 md:rounded-2xl md:px-6 md:py-8">
          {heroLogoUrl ? (
            <div className="pointer-events-none absolute left-1/2 top-[8.75rem] z-0 w-full max-w-[46.2rem] -translate-x-1/2 select-none sm:top-[9.75rem] sm:max-w-[49.5rem] lg:top-[10.25rem] lg:max-w-[52.8rem]">
              <img
                src={heroLogoUrl}
                alt=""
                aria-hidden="true"
                className="h-auto w-full object-contain opacity-[0.1] [filter:drop-shadow(0_0_20px_rgba(148,163,184,0.16))]"
                loading="lazy"
                decoding="async"
              />
            </div>
          ) : null}
          <div className="relative z-10 mx-auto mt-2 flex w-full max-w-[46rem] flex-col items-center text-center">
            <div ref={heroSetPickerRef} data-hero-picker className="relative w-full">
              <CenteredSuffixInline
                as="button"
                type="button"
                onClick={() => setHeroSetPickerOpen((open) => !open)}
                disabled={loading || targets.length === 0}
                aria-expanded={heroSetPickerOpen}
                aria-haspopup="listbox"
                aria-controls="repricer-set-picker-list"
                className="block w-full rounded-lg px-10 py-1 text-3xl font-semibold text-[var(--text-primary)] transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] sm:px-12 sm:text-4xl disabled:cursor-not-allowed disabled:opacity-90"
                contentClassName="mx-auto max-w-full whitespace-normal break-words text-center leading-tight text-balance"
                suffixWrapperClassName="right-3 sm:right-4"
                suffix={
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    className={`h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform ${heroSetPickerOpen ? "rotate-180" : ""}`}
                    fill="currentColor"
                  >
                    <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                  </svg>
                }
                title={targets.length > 0 ? "Switch set" : "No sets available"}
              >
                <span>{selectedTarget?.name || "Select a set"}</span>
              </CenteredSuffixInline>

              {heroSetPickerOpen ? (
                <div
                  id="repricer-set-picker-list"
                  role="listbox"
                  aria-label="Available sets"
                  className="index-scrollbar absolute left-1/2 top-full z-30 mt-2 max-h-72 w-[min(36rem,92vw)] -translate-x-1/2 overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1.5 text-left shadow-[0_12px_30px_rgba(0,0,0,0.42)]"
                >
                  {targets.map((target) => {
                    const isSelected = String(target.target_id) === String(targetId || "");
                    return (
                      <button
                        key={`repricer-set-option:${target.target_type}:${target.target_id}`}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        onClick={() => {
                          setTargetId(String(target.target_id || ""));
                          setHeroSetPickerOpen(false);
                        }}
                        className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                          isSelected
                            ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                            : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                        }`}
                      >
                        <span className="truncate">{target.name}</span>
                        {isSelected ? <span className="ml-2 text-xs font-medium text-[var(--accent)]">Current</span> : null}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <p className="mt-4 text-sm text-[var(--text-secondary)]">Enter your pack price and regrade the set instantly.</p>

            <form onSubmit={onSubmit} className="mt-4 w-full max-w-2xl">
              <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/75 p-3 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),0_14px_30px_rgba(2,6,23,0.22)]">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Analyze at your pack price</div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2.5 transition-[border-color,box-shadow] focus-within:border-[var(--accent)] focus-within:ring-2 focus-within:ring-[rgba(250,204,21,0.25)]">
                    <span className="text-sm font-semibold text-[var(--text-secondary)]">$</span>
                    <input
                      type="number"
                      min="0.01"
                      max="999.99"
                      step="0.01"
                      value={customPackCost}
                      onChange={(event) => setCustomPackCost(event.target.value)}
                      className="no-number-spinner h-8 w-full border-none bg-transparent px-0 text-sm text-[var(--text-primary)] outline-none focus:ring-0"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(20,184,166,0.22)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loading ? "Grading..." : "Grade"}
                  </button>
                </div>
                <p className="mt-2 text-xs text-[var(--text-secondary)]">Use the price you found in-store, online, or at a card show.</p>
              </div>
            </form>

            {error ? (
              <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</p>
            ) : null}

            {result ? (
              <>
                <div className="mt-6 flex w-full flex-wrap items-center justify-center gap-2">
                  <ViewModeToggle viewMode={viewMode} onChange={setViewMode} />
                  {viewMode === "expert" && hasRelativeScores ? (
                    <ScoreModeToggle scoreMode={scoreMode} onChange={setScoreMode} />
                  ) : null}
                </div>

                <div className="mt-4 flex w-full justify-center">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Rip Score (Your Price)</p>
                </div>
                <div className="mt-2 flex w-full justify-center">
                  <div className="relative inline-block leading-none">
                    <span className="text-[clamp(3.25rem,10vw,5rem)] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                      {formatScore(displayedCustomPackScore)}
                    </span>
                    <span className="pointer-events-none absolute bottom-2 left-full ml-2 text-sm font-medium text-[var(--text-secondary)] sm:bottom-3">/100</span>
                  </div>
                </div>
                <div className="mt-3 w-full max-w-lg">
                  <ScoreMeter score={displayedCustomPackScore} />
                </div>
                <div className="mt-4 flex w-full flex-wrap items-center justify-center gap-2">
                  <RankBadge rank={result?.custom?.pack_tier} label="Your Tier" size="hero" />
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs text-[var(--text-secondary)]">
                    Market RIP: {formatScore(displayedBaselinePackScore)}
                  </span>
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-semibold text-[var(--text-primary)]">
                    Your RIP: {formatScore(displayedCustomPackScore)}
                  </span>
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-semibold text-[var(--text-primary)]">
                    Score {formatDelta(displayedPackScoreDelta)}
                  </span>
                  <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-semibold text-[var(--text-primary)]">
                    Tier {result?.baseline?.pack_tier || "-"} to {result?.custom?.pack_tier || "-"}
                  </span>
                </div>

                <div className="mx-auto mt-5 w-full max-w-2xl">
                  <div
                    className="border-l-2 px-4 py-3 text-left sm:px-5"
                    style={getCalloutAccentStyle({ label: recommendationLabel, rankTier: result?.custom?.pack_tier })}
                  >
                    <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                      <span className="h-1.5 w-1.5 rounded-full" aria-hidden="true" style={{ backgroundColor: recommendationTone.dotColor }} />
                      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Recommendation</p>
                      <InterpretationBadge label={recommendationLabel} rankTier={result?.custom?.pack_tier} className="px-2.5 py-0.5 text-[10px] tracking-[0.08em]" />
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{recommendationSummary || "No interpretation summary is available yet."}</p>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </section>

        {result ? (
          <>
            <section>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <ComparisonMetricCard
                  label="Pack Cost"
                  marketValue={formatCurrency(summaryMetrics?.pack_cost?.market_value ?? result?.baseline?.pack_cost)}
                  yourValue={formatCurrency(summaryMetrics?.pack_cost?.custom_value ?? result?.custom?.pack_cost)}
                  differenceValue={
                    summaryMetrics?.pack_cost?.difference_label ||
                    formatSignedCurrency((toNumber(result?.custom?.pack_cost) || 0) - (toNumber(result?.baseline?.pack_cost) || 0))
                  }
                  isGood={
                    typeof summaryMetrics?.pack_cost?.is_improvement === "boolean"
                      ? summaryMetrics.pack_cost.is_improvement
                      : (toNumber(result?.custom?.pack_cost) || 0) < (toNumber(result?.baseline?.pack_cost) || 0)
                  }
                />
                <ComparisonMetricCard
                  label="Chance to Beat Cost"
                  marketValue={formatPercent(summaryMetrics?.chance_to_beat_cost?.market_value ?? result?.baseline?.prob_profit, true)}
                  yourValue={formatPercent(summaryMetrics?.chance_to_beat_cost?.custom_value ?? result?.custom?.prob_profit, true)}
                  differenceValue={
                    summaryMetrics?.chance_to_beat_cost?.difference_label ||
                    formatProbabilityDeltaPoints(result?.custom?.prob_profit, result?.baseline?.prob_profit)
                  }
                  isGood={
                    typeof summaryMetrics?.chance_to_beat_cost?.is_improvement === "boolean"
                      ? summaryMetrics.chance_to_beat_cost.is_improvement
                      : (toNumber(result?.custom?.prob_profit) || 0) > (toNumber(result?.baseline?.prob_profit) || 0)
                  }
                />
                <ComparisonMetricCard
                  label="Avg Loss When Losing"
                  marketValue={formatCurrency(summaryMetrics?.average_loss_when_losing?.market_value ?? result?.baseline?.expected_loss_when_losing)}
                  yourValue={formatCurrency(summaryMetrics?.average_loss_when_losing?.custom_value ?? result?.custom?.expected_loss_when_losing)}
                  differenceValue={
                    summaryMetrics?.average_loss_when_losing?.difference_label ||
                    formatSignedCurrency((toNumber(result?.custom?.expected_loss_when_losing) || 0) - (toNumber(result?.baseline?.expected_loss_when_losing) || 0))
                  }
                  isGood={
                    typeof summaryMetrics?.average_loss_when_losing?.is_improvement === "boolean"
                      ? summaryMetrics.average_loss_when_losing.is_improvement
                      : (toNumber(result?.custom?.expected_loss_when_losing) || 0) < (toNumber(result?.baseline?.expected_loss_when_losing) || 0)
                  }
                />
                <ComparisonMetricCard
                  label="ROI / Return"
                  marketValue={formatPercent(summaryMetrics?.roi_return?.market_value ?? result?.baseline?.roi_percent)}
                  yourValue={formatPercent(summaryMetrics?.roi_return?.custom_value ?? result?.custom?.roi_percent)}
                  differenceValue={
                    summaryMetrics?.roi_return?.difference_label ||
                    formatDelta((toNumber(result?.custom?.roi_percent) || 0) - (toNumber(result?.baseline?.roi_percent) || 0), true)
                  }
                  isGood={
                    typeof summaryMetrics?.roi_return?.is_improvement === "boolean"
                      ? summaryMetrics.roi_return.is_improvement
                      : (toNumber(result?.custom?.roi_percent) || 0) > (toNumber(result?.baseline?.roi_percent) || 0)
                  }
                />
                <SingleValueMetricCard
                  label="Average Pack Value"
                  value={formatCurrency(summaryMetrics?.average_pack_value?.value ?? result?.custom?.mean_value)}
                  note={summaryMetrics?.average_pack_value?.note || "Same simulation value regardless of pack price."}
                />
              </div>
            </section>

            <section>
              <div className="grid gap-3 md:grid-cols-3">
                  <RegradePillarCard
                    title="Profit"
                    marketScore={displayedBaselineProfit}
                    customScore={displayedCustomProfit}
                    marketTier={result?.baseline?.profit_tier}
                    customTier={result?.custom?.profit_tier}
                    customRank={result?.custom?.profit_rank}
                    sectionMeta={result?.custom?.interpretation_meta?.profit}
                    scoreDelta={result?.comparison?.score_deltas?.profit}
                    rows={[
                      {
                        label: "Chance to Beat Cost",
                        market: formatPercent(
                          pillarMetrics?.profit?.chance_to_beat_cost?.market_value ?? result?.baseline?.prob_profit,
                          true
                        ),
                        custom: formatPercent(
                          pillarMetrics?.profit?.chance_to_beat_cost?.custom_value ?? result?.custom?.prob_profit,
                          true
                        ),
                      },
                      {
                        label: "P95 / Cost",
                        market: formatRatio(
                          pillarMetrics?.profit?.p95_to_cost?.market_value ??
                            (toNumber(result?.charts?.percentiles?.p95) || 0) / (toNumber(result?.baseline?.pack_cost) || 1)
                        ),
                        custom: formatRatio(
                          pillarMetrics?.profit?.p95_to_cost?.custom_value ??
                            (toNumber(result?.charts?.percentiles?.p95) || 0) / (toNumber(result?.custom?.pack_cost) || 1)
                        ),
                      },
                      {
                        label: "ROI",
                        market: formatPercent(pillarMetrics?.profit?.roi_return?.market_value ?? result?.baseline?.roi_percent),
                        custom: formatPercent(pillarMetrics?.profit?.roi_return?.custom_value ?? result?.custom?.roi_percent),
                      },
                    ]}
                  />
                  <RegradePillarCard
                    title="Safety"
                    marketScore={displayedBaselineSafety}
                    customScore={displayedCustomSafety}
                    marketTier={result?.baseline?.safety_tier}
                    customTier={result?.custom?.safety_tier}
                    customRank={result?.custom?.safety_rank}
                    sectionMeta={result?.custom?.interpretation_meta?.safety}
                    scoreDelta={result?.comparison?.score_deltas?.safety}
                    rows={[
                      {
                        label: "Average Loss (when losing)",
                        market: formatCurrency(
                          pillarMetrics?.safety?.average_loss_when_losing?.market_value ?? result?.baseline?.expected_loss_when_losing
                        ),
                        custom: formatCurrency(
                          pillarMetrics?.safety?.average_loss_when_losing?.custom_value ?? result?.custom?.expected_loss_when_losing
                        ),
                      },
                      {
                        label: "Typical Loss (when losing)",
                        market: formatCurrency(
                          pillarMetrics?.safety?.typical_loss_when_losing?.market_value ?? result?.baseline?.median_loss_when_losing
                        ),
                        custom: formatCurrency(
                          pillarMetrics?.safety?.typical_loss_when_losing?.custom_value ?? result?.custom?.median_loss_when_losing
                        ),
                      },
                      {
                        label: "Bad Pack Floor",
                        market: formatCurrency(result?.charts?.percentiles?.p5),
                        custom: formatCurrency(result?.charts?.percentiles?.p5),
                      },
                    ]}
                  />
                  <RegradePillarCard
                    title="Stability"
                    marketScore={displayedBaselineStability}
                    customScore={displayedCustomStability}
                    marketTier={result?.baseline?.stability_tier}
                    customTier={result?.custom?.stability_tier}
                    customRank={result?.custom?.stability_rank}
                    sectionMeta={result?.custom?.interpretation_meta?.stability}
                    scoreDelta={result?.comparison?.score_deltas?.stability}
                    rows={[
                      {
                        label: "Stability Score",
                        market: formatScore(
                          pillarMetrics?.stability?.stability_score?.market_value ?? displayedBaselineStability
                        ),
                        custom: formatScore(
                          pillarMetrics?.stability?.stability_score?.custom_value ?? displayedCustomStability
                        ),
                      },
                    ]}
                    priceIndependent={true}
                    note="Value spread does not change with pack price."
                  />
                </div>
            </section>

            <section>
              <SectionCard
                title={graphMode === "outcome-distribution" ? "What Usually Happens" : "Is This Set Getting Better?"}
                subtitle={
                  graphMode === "outcome-distribution"
                    ? "The same RIP distribution model, re-annotated for your entered pack cost."
                    : "Historical Pack Value vs Cost"
                }
                titleInfoText={
                  graphMode === "outcome-distribution"
                    ? "Histogram bars and chance-to-reach curve use the latest simulation distribution."
                    : "Your price is primary. Market pricing remains as context."
                }
              >
                <div className="mb-4">
                  <div className="grid w-full grid-cols-2 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                    <button
                      type="button"
                      onClick={() => setGraphMode("outcome-distribution")}
                      aria-pressed={graphMode === "outcome-distribution"}
                      className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                        graphMode === "outcome-distribution"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      <span className="block truncate">What Usually Happens</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setGraphMode("historical-trend")}
                      aria-pressed={graphMode === "historical-trend"}
                      className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                        graphMode === "historical-trend"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      <span className="block truncate">Is This Set Getting Better?</span>
                    </button>
                  </div>
                </div>

                <InterpretationInsight
                  sectionMeta={
                    graphMode === "historical-trend"
                      ? result?.custom?.interpretation_meta?.historicalTrend
                      : result?.custom?.interpretation_meta?.outcomeDistribution
                  }
                  fallbackSummary={null}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />

                {graphMode === "outcome-distribution" ? (
                  <>
                    <RipDistributionChart
                      bins={result?.charts?.distribution_bins || []}
                      thresholdBins={result?.charts?.threshold_bins || []}
                      markers={chartMarkers}
                      markerStyleMap={{
                        "market-pack-cost": {
                          stroke: "rgba(148,163,184,0.62)",
                          strokeWidth: 1,
                          strokeDasharray: "2 6",
                        },
                        "custom-pack-cost": {
                          stroke: "rgba(250,204,21,0.98)",
                          strokeWidth: 2.8,
                          strokeDasharray: "7 3",
                        },
                      }}
                    />
                    <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                      <ComparisonStatTile label="Market Cost" value={formatCurrency(result?.baseline?.pack_cost)} />
                      <ComparisonStatTile label="Your Cost" value={formatCurrency(result?.custom?.pack_cost)} />
                      <ComparisonStatTile label="Mean" value={formatCurrency(result?.custom?.mean_value)} />
                      <ComparisonStatTile label="Median" value={formatCurrency(result?.custom?.median_value)} />
                      <ComparisonStatTile label="Big Hit at Your Price" value={formatCurrency(result?.charts?.custom_reference_lines?.big_hit_threshold)} />
                    </div>
                  </>
                ) : (
                  <>
                    <ToolHistoricalComparisonChart historyTrend={result?.context?.history_trend || []} />
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <ComparisonStatTile
                        label="Mean / Your Cost"
                        value={formatRatio((result?.context?.history_trend || []).slice(-1)[0]?.mean_to_custom_cost_ratio)}
                      />
                      <ComparisonStatTile
                        label="Median / Your Cost"
                        value={formatRatio((result?.context?.history_trend || []).slice(-1)[0]?.median_to_custom_cost_ratio)}
                      />
                      <ComparisonStatTile
                        label="P95 / Your Cost"
                        value={formatRatio((result?.context?.history_trend || []).slice(-1)[0]?.p95_to_custom_cost_ratio)}
                      />
                      <ComparisonStatTile label="Break-even" value="1.00x" />
                    </div>
                  </>
                )}
              </SectionCard>
            </section>

            <section>
              <SectionCard title="Top 10 Cards Carrying the Set" subtitle={null}>
                <InterpretationInsight
                  sectionMeta={result?.custom?.interpretation_meta?.topEVDrivers}
                  fallbackSummary={null}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />
                <TopCardsContent
                  topHits={result?.context?.top_hits || []}
                  meanValue={result?.custom?.mean_value}
                  sectionMeta={result?.custom?.interpretation_meta?.topEVDrivers}
                />
                <p className="mt-3 text-xs text-[var(--text-secondary)]">Value drivers do not change with pack price.</p>
              </SectionCard>
            </section>

            {viewMode === "expert" ? (
              <section>
                <details className="group rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-left transition-colors hover:text-white">
                    <div>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">Expert Comparison Details</p>
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">Deep before/after metrics for market vs your price.</p>
                    </div>
                    <span className="text-xs text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180">▾</span>
                  </summary>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b border-[var(--border-subtle)] text-left text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                          <th className="py-2 pr-4">Metric</th>
                          <th className="py-2 pr-4">Market</th>
                          <th className="py-2 pr-4">Your Price</th>
                          <th className="py-2">Delta</th>
                        </tr>
                      </thead>
                      <tbody className="text-[var(--text-primary)]">
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">RIP Score</td><td className="py-2 pr-4">{formatScore(displayedBaselinePackScore)}</td><td className="py-2 pr-4">{formatScore(displayedCustomPackScore)}</td><td className="py-2">{formatDelta(displayedPackScoreDelta)}</td></tr>
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">Tier</td><td className="py-2 pr-4">{result?.baseline?.pack_tier || "-"}</td><td className="py-2 pr-4">{result?.custom?.pack_tier || "-"}</td><td className="py-2">{`${result?.baseline?.pack_tier || "-"} to ${result?.custom?.pack_tier || "-"}`}</td></tr>
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">Probability of Profit</td><td className="py-2 pr-4">{formatPercent(result?.baseline?.prob_profit, true)}</td><td className="py-2 pr-4">{formatPercent(result?.custom?.prob_profit, true)}</td><td className="py-2">{summaryMetrics?.chance_to_beat_cost?.difference_label || formatProbabilityDeltaPoints(result?.custom?.prob_profit, result?.baseline?.prob_profit)}</td></tr>
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">ROI Percent</td><td className="py-2 pr-4">{formatPercent(result?.baseline?.roi_percent)}</td><td className="py-2 pr-4">{formatPercent(result?.custom?.roi_percent)}</td><td className="py-2">{summaryMetrics?.roi_return?.difference_label || formatDelta((toNumber(result?.custom?.roi_percent) || 0) - (toNumber(result?.baseline?.roi_percent) || 0), true)}</td></tr>
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">P95 / Cost</td><td className="py-2 pr-4">{formatRatio(pillarMetrics?.profit?.p95_to_cost?.market_value ?? ((toNumber(result?.charts?.percentiles?.p95) || 0) / (toNumber(result?.baseline?.pack_cost) || 1)))}</td><td className="py-2 pr-4">{formatRatio(pillarMetrics?.profit?.p95_to_cost?.custom_value ?? ((toNumber(result?.charts?.percentiles?.p95) || 0) / (toNumber(result?.custom?.pack_cost) || 1)))}</td><td className="py-2">{pillarMetrics?.profit?.p95_to_cost?.difference_label || "-"}</td></tr>
                        <tr className="border-b border-[var(--border-subtle)]/70"><td className="py-2 pr-4">Big Hit Threshold</td><td className="py-2 pr-4">{formatCurrency((toNumber(result?.baseline?.pack_cost) || 0) * 5)}</td><td className="py-2 pr-4">{formatCurrency(result?.charts?.custom_reference_lines?.big_hit_threshold)}</td><td className="py-2">{formatSignedCurrency((toNumber(result?.charts?.custom_reference_lines?.big_hit_threshold) || 0) - ((toNumber(result?.baseline?.pack_cost) || 0) * 5))}</td></tr>
                        <tr><td className="py-2 pr-4">Expected Loss (When Losing)</td><td className="py-2 pr-4">{formatCurrency(result?.baseline?.expected_loss_when_losing)}</td><td className="py-2 pr-4">{formatCurrency(result?.custom?.expected_loss_when_losing)}</td><td className="py-2">{formatSignedCurrency((toNumber(result?.baseline?.expected_loss_when_losing) || 0) - (toNumber(result?.custom?.expected_loss_when_losing) || 0))}</td></tr>
                      </tbody>
                    </table>
                  </div>
                </details>
              </section>
            ) : null}

            <section>
              <p className="text-xs text-[var(--text-secondary)]">
                Uses the latest simulation run and reprices cost-sensitive metrics against your entered pack price. Your analysis does not change public rankings.
              </p>
              {(result?.meta?.approximation_notes || []).length > 0 ? (
                <div className="mt-2">
                  <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">Approximation Notes</p>
                  <ul className="mt-1 space-y-1 text-xs text-[var(--text-secondary)]">
                    {(result?.meta?.approximation_notes || []).map((note, index) => (
                      <li key={`approx:${index}`}>- {note}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
