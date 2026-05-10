"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import InterpretationInsight from "@/components/explore/InterpretationInsight";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import InfoPopover from "@/components/ui/InfoPopover";
import InterpretationBadge from "@/components/ui/InterpretationBadge";
import RankBadge from "@/components/ui/RankBadge";
import { RANK_CONFIG } from "@/constants/rankConfig";
import { getFriendlyMetricLabel, getScoreTootip, getFormattedTooltip, getMetricTooltip } from "@/constants/interpretabilityConfig";
import { getCalloutAccentStyle, getDangerValueStyle, getInterpretationTone } from "@/lib/explore/interpretationTone";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const REQUIRED_PACK_PATHS = ["normal", "demi_god_pack", "god_pack"];
const ANALYSIS_SECTION_ID = "explore-outcomes";
const GRAPH_SECTION_KEYS = new Set(["outcome-distribution", "historical-trend", "pack-breakdown"]);
const SECTION_ID_MAP = {
  "pack-score": "explore-score",
  "outcome-distribution": "explore-outcomes",
  "historical-trend": "explore-outcomes",
  "pack-breakdown": "explore-outcomes",
  "top-ev-drivers": "explore-drivers",
  "rarity-contribution": "explore-rarity",
};
const SECTION_SCROLL_ORDER = [
  { sectionId: "explore-score", navId: "pack-score" },
  { sectionId: ANALYSIS_SECTION_ID, navId: "outcome-distribution" },
  { sectionId: "explore-drivers", navId: "top-ev-drivers" },
  { sectionId: "explore-rarity", navId: "rarity-contribution" },
];

const RIP_COPY = {
  scoreLabel: "Rip Score",
  scoreRankLabel: "Rip Rank",
  summaryQuestion: "Should You Open This Set?",
  scoreDetailsLabel: "Show details",
  advancedLabel: "Advanced Score Details",
  recommendationLabel: "Recommendation",
  simpleMetrics: {
    chanceToBeatPackCost: "Chance to Beat Pack Cost",
    averagePackValue: "Average Pack Value",
    currentPackCost: "Estimated Pack Market Price",
    averageLoss: "Average Loss",
    chanceAtBigPull: "Chance at a Big Pull",
  },
  sections: {
    packScore: "Rip Score",
    outcomeDistribution: "What Usually Happens",
    historicalTrend: "Performance vs Cost",
    packBreakdown: "Pack Breakdown",
    topEvDrivers: "Cards Carrying the Set",
    rarityContribution: "Where the Value Comes From",
  },
  chartMarkers: {
    packCost: "Pack Cost",
    typicalPack: "Typical Pack Value",
    bigHit: "Big Hit",
    bestPull: "Best Simulated Pull",
  },
  chartStats: {
    typicalPack: "Typical Pack Value",
    badPackFloor: "Bad Pack Floor Value",
    chanceToBeatPackCost: "Chance to Beat Pack Cost",
    chanceAtBigPull: "Chance at a Big Pull",
    bestPull: "Best Simulated Pull",
  },
  advancedStats: {
    bigHitUpside: "Big Hit Upside",
    expectedLossPerPack: "Average Loss per Pack",
    expectedLossWhenLosing: "Average Loss When You Miss",
    medianLossWhenLosing: "Typical Loss When You Miss",
    coefficientOfVariation: "Coefficient of Variation",
    hhiEvConcentration: "Value Concentration",
    effectiveChaseCount: "Chase Depth",
  },
};

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed > 1 ? parsed / 100 : parsed;
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : currencyFormatter.format(parsed);
}

function formatLossCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return `-${currencyFormatter.format(Math.abs(parsed))}`;
}

function formatSignedCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  if (Math.abs(parsed) < 0.005) {
    return currencyFormatter.format(0);
  }
  return `${parsed < 0 ? "-" : "+"}${currencyFormatter.format(Math.abs(parsed))}`;
}

function formatPercent(value, options = {}) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  const normalized = options.probability ? normalizeProbability(parsed) * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function formatScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : parsed.toFixed(1);
}

function formatRawScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "—" : parsed.toFixed(1);
}

function formatNumber(value, decimals = 2) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return parsed.toFixed(decimals);
}

function getSimpleAverageLossValue(summary) {
  const meanValue = toNumber(summary?.mean_value);
  const packCost = toNumber(summary?.pack_cost);

  if (meanValue !== null && packCost !== null) {
    return Math.min(meanValue - packCost, 0);
  }

  const expectedLossPerPack = toNumber(summary?.expected_loss_per_pack);
  return expectedLossPerPack === null ? null : -Math.abs(expectedLossPerPack);
}

function titleCaseStateLabel(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPackPathLabel(value) {
  switch (String(value || "").toLowerCase()) {
    case "normal":
      return "Normal";
    case "demi_god_pack":
    case "demi_god":
    case "demigod":
      return "Demi-God Pack";
    case "god_pack":
    case "god":
      return "God Pack";
    default:
      return titleCaseStateLabel(value);
  }
}

function getPercentileValue(percentiles, requestedPercentile) {
  if (!Array.isArray(percentiles)) {
    return null;
  }
  const matched = percentiles.find((entry) => {
    const percentile = toNumber(entry?.percentile);
    if (percentile === null) {
      return false;
    }
    return (
      Math.abs(percentile - requestedPercentile) < 0.001 ||
      Math.abs(percentile - requestedPercentile * 100) < 0.001
    );
  });
  return matched?.value ?? null;
}

function sortObjectEntriesDescending(input) {
  if (!input || typeof input !== "object") {
    return [];
  }
  return Object.entries(input).sort((left, right) => {
    const leftValue = toNumber(left[1]) ?? 0;
    const rightValue = toNumber(right[1]) ?? 0;
    return rightValue - leftValue;
  });
}

function normalizeBarWidth(value, maxValue) {
  const v = toNumber(value);
  const m = toNumber(maxValue);
  if (v === null || m === null || m === 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (v / m) * 100));
}

function withAlpha(color, alpha) {
  if (typeof color !== "string") {
    return null;
  }

  const rgbaMatch = color.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[^)]+)?\)$/i);
  if (!rgbaMatch) {
    return color;
  }

  return `rgba(${rgbaMatch[1]},${rgbaMatch[2]},${rgbaMatch[3]},${alpha})`;
}

function getTierEdgeColor(rankTier) {
  const config = rankTier ? RANK_CONFIG[rankTier] : null;
  if (!config?.color) {
    return null;
  }

  switch (rankTier) {
    case "S":
      return withAlpha(config.color, 0.72);
    case "A":
      return withAlpha(config.color, 0.68);
    case "B":
      return withAlpha(config.color, 0.58);
    case "C":
      return withAlpha(config.color, 0.62);
    case "D":
      return withAlpha(config.color, 0.64);
    case "F":
      return withAlpha(config.color, 0.7);
    default:
      return null;
  }
}

function ScoreMeter({ score, rankTier }) {
  const parsed = Number(score);
  const width = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : 0;
  const edgeColor = getTierEdgeColor(rankTier);
  const endColor = edgeColor || "rgba(94,234,212,0.98)";
  const transitionColor = withAlpha(endColor, 0.54);
  const brightEndColor = withAlpha(endColor, 0.74);
  const glowColor = withAlpha(endColor, 0.42);
  return (
    <div className="relative mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="relative h-full overflow-hidden rounded-full"
        style={{
          width: `${width}%`,
          background: `linear-gradient(90deg, rgba(20,184,166,0.66) 0%, rgba(45,212,191,0.82) 50%, ${transitionColor} 85%, ${brightEndColor} 100%)`,
          boxShadow: width > 0 ? `0 0 4px 0px rgba(20,184,166,0.22), inset 0 0 2px ${withAlpha(endColor, 0.12)}` : "none",
        }}
      >
        {width > 0 ? (
          <span
            aria-hidden="true"
            className="absolute top-1/2 right-0 h-1.5 w-1.5 -translate-y-1/2 rounded-full"
            style={{
              background: brightEndColor,
              boxShadow: `0 0 3px ${glowColor}`,
              opacity: 0.9,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function HorizontalBar({ widthPercent, nonzeroMin = 2 }) {
  const width = Number.isFinite(widthPercent) ? widthPercent : 0;
  const displayWidth = width > 0 ? Math.max(width, nonzeroMin) : 0;
  return (
    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
      <div
        className="h-full rounded-full"
        style={{
          width: `${displayWidth}%`,
          background: "linear-gradient(90deg, rgba(20,184,166,0.55) 0%, rgba(94,234,212,0.85) 100%)",
        }}
      />
    </div>
  );
}

function MetricRow({ label, value, infoText }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0 last:pb-0 first:pt-0">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="text-sm text-[var(--text-secondary)]">{friendlyLabel}</span>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <span className="text-sm font-medium" style={isNegativeValue ? getDangerValueStyle() : undefined}>{value}</span>
    </div>
  );
}

function HeroMetricTile({ label, value }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  const infoText = getMetricTooltip(label);
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{friendlyLabel}</p>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <p className="mt-2 text-base font-semibold" style={isNegativeValue ? getDangerValueStyle() : { color: "var(--text-primary)" }}>
        {value}
      </p>
    </div>
  );
}

function CenteredSuffixInline({
  as: Component = "button",
  children,
  suffix = null,
  className = "",
  contentClassName = "",
  suffixWrapperClassName = "",
  ...props
}) {
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
        <span
          aria-hidden="true"
          className={[
            "pointer-events-none col-start-3 inline-flex min-w-[1rem] items-center justify-center",
            suffixWrapperClassName,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {suffix}
        </span>
      ) : (
        <span aria-hidden="true" className="pointer-events-none invisible col-start-3 inline-flex min-w-[1rem] items-center justify-center" />
      )}
    </Component>
  );
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

function CompactMetricModeToggle({ mode, onChange }) {
  return (
    <div className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/90 p-0.5 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02)]">
      <button
        type="button"
        onClick={() => onChange("overview")}
        aria-pressed={mode === "overview"}
        aria-label="Simple metrics"
        title="Simple metrics"
        className={`rounded-full px-2 py-1 text-[10px] font-semibold leading-none transition-colors ${
          mode === "overview"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Overview
      </button>
      <button
        type="button"
        onClick={() => onChange("details")}
        aria-pressed={mode === "details"}
        aria-label="Score details"
        title="Score details"
        className={`rounded-full px-2 py-1 text-[10px] font-semibold leading-none transition-colors ${
          mode === "details"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Details
      </button>
    </div>
  );
}

function MetricViewToggle({ metricView, onChange, detailsLabel = "Score Details" }) {
  return (
    <div className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/90 p-0.5 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02)]">
      <button
        type="button"
        onClick={() => onChange("overview")}
        aria-pressed={metricView === "overview"}
        className={`min-w-[4.75rem] rounded-full px-2.5 py-1 text-[10px] font-semibold leading-none transition-colors ${
          metricView === "overview"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        Overview
      </button>
      <button
        type="button"
        onClick={() => onChange("details")}
        aria-pressed={metricView === "details"}
        className={`min-w-[6rem] rounded-full px-2.5 py-1 text-[10px] font-semibold leading-none transition-colors ${
          metricView === "details"
            ? "bg-[var(--brand)] text-white"
            : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        {detailsLabel}
      </button>
    </div>
  );
}

function RecommendationBadge({ label, rankTier }) {
  if (!label) {
    return null;
  }

  return <InterpretationBadge label={label} rankTier={rankTier} className="px-2.5 py-0.5 text-[10px] tracking-[0.08em]" />;
}

function DisclosureSection({ title, description = null, children, defaultOpen = false, className = "" }) {
  return (
    <details
      open={defaultOpen}
      className={[
        "group rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-4 sm:p-5",
        className,
      ].join(" ")}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-left transition-colors hover:text-white">
        <div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
          {description ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{description}</p> : null}
        </div>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="h-5 w-5 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
          fill="currentColor"
        >
          <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
        </svg>
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

const SET_INTELLIGENCE_LENSES = [
  {
    key: "experience",
    label: "Opening Experience",
    scoreField: "relative_experience_score",
    tierField: "experience_tier",
    rankField: "experience_rank",
    format: "score",
    heading: "How this set feels to open",
    description:
      "This lens weighs typical pack value, chance to beat cost, miss protection, big-pull frequency, and consistency.",
    evidenceKeys: ["prob_profit", "mean_value", "expected_loss_when_losing"],
  },
  {
    key: "chase",
    label: "Chase Potential",
    scoreField: "relative_chase_potential_score",
    tierField: "chase_potential_tier",
    rankField: "chase_potential_rank",
    format: "score",
    heading: "How strong the chase setup is",
    description:
      "This lens weighs big-pull frequency, high-end upside, chase depth, affordability, and profit profile.",
    evidenceKeys: ["prob_big_hit", "p95_value_to_cost_ratio", "effective_chase_count"],
  },
  {
    key: "upside",
    label: "Biggest Upside",
    scoreField: "p95_value_to_cost_ratio",
    tierField: "p95_value_to_cost_tier",
    rankField: "p95_value_to_cost_rank",
    format: "multiplier",
    heading: "How high the top outcomes can run",
    description:
      "This lens uses the high-end simulated outcome compared with pack cost.",
    evidenceKeys: ["p95_value_to_cost_ratio", "big_hit_threshold", "max_value"],
  },
  {
    key: "averageReturn",
    label: "Average Return",
    scoreField: "mean_value_to_cost_ratio",
    tierField: "mean_value_to_cost_tier",
    rankField: "mean_value_to_cost_rank",
    format: "multiplier",
    heading: "Average value compared with cost",
    description:
      "This lens compares average simulated pack value against current estimated pack cost.",
    evidenceKeys: ["mean_value", "pack_cost", "expected_loss_per_pack"],
  },
];

function formatLensScore(value, format) {
  const parsed = toNumber(value);
  if (parsed === null) return "—";
  if (format === "multiplier") return `${parsed.toFixed(1)}x`;
  return parsed.toFixed(1);
}

function getLensEvidenceRow(key, summary) {
  const fmtMult = (v) => {
    const p = toNumber(v);
    return p === null ? "—" : `${p.toFixed(1)}x`;
  };
  switch (key) {
    case "prob_profit":
      return { label: "Chance to beat cost", value: formatPercent(summary.prob_profit, { probability: true }) };
    case "mean_value":
      return { label: "Average pack value", value: formatCurrency(summary.mean_value) };
    case "expected_loss_when_losing":
      return { label: "Avg loss when missing", value: formatLossCurrency(summary.expected_loss_when_losing) };
    case "prob_big_hit":
      return { label: "Chance at a big pull", value: formatPercent(summary.prob_big_hit, { probability: true }) };
    case "p95_value_to_cost_ratio":
      return { label: "Big hit upside", value: fmtMult(summary.p95_value_to_cost_ratio) };
    case "effective_chase_count":
      return { label: "Chase depth", value: formatNumber(summary.effective_chase_count, 2) };
    case "big_hit_threshold":
      return { label: "Big hit threshold", value: formatCurrency(summary.big_hit_threshold) };
    case "max_value":
      return { label: "Best simulated pull", value: formatCurrency(summary.max_value) };
    case "pack_cost":
      return { label: "Pack cost", value: formatCurrency(summary.pack_cost) };
    case "expected_loss_per_pack":
      return { label: "Avg loss per pack", value: formatLossCurrency(summary.expected_loss_per_pack) };
    default:
      return null;
  }
}

function toOptionalUpper(value) {
  if (value == null) return null;
  const s = String(value).trim().toUpperCase();
  return s || null;
}

function getLensTagline(lens, summary) {
  const tier = toOptionalUpper(summary[lens.tierField]);
  const score = toNumber(summary[lens.scoreField]);
  if (score === null) return "No data available for this lens.";
  if (lens.key === "experience") {
    if (tier === "S" || tier === "A") return "Strong pack feel compared with the field.";
    if (tier === "B") return "Above-average opening experience.";
    if (tier === "C") return "Average opening experience.";
    return "Below-average pack feel compared with the field.";
  }
  if (lens.key === "chase") {
    if (tier === "S" || tier === "A") return "Elite chase setup — top of the field.";
    if (tier === "B") return "Strong chase setup compared with peers.";
    if (tier === "C") return "Good chase setup, but not top of field.";
    return "Limited chase depth compared with the field.";
  }
  if (lens.key === "upside") {
    if (tier === "S" || tier === "A") return "High-end outcomes can run far above pack cost.";
    if (tier === "B") return "Solid upside when the pack hits.";
    if (tier === "C") return "Moderate upside compared with the field.";
    return "Limited high-end upside relative to pack cost.";
  }
  if (lens.key === "averageReturn") {
    const ratio = toNumber(summary.mean_value_to_cost_ratio);
    if (ratio !== null && ratio >= 1.0) return "Average value meets or exceeds pack cost.";
    if (tier === "B" || tier === "A" || tier === "S") return "Above-average value recovery compared with peers.";
    if (tier === "C") return "Average value trails pack cost modestly.";
    return "Average value still trails pack cost.";
  }
  return "";
}

function SetIntelligenceSection({ summary }) {
  const [selectedLensKey, setSelectedLensKey] = useState("experience");
  const selectedLens =
    SET_INTELLIGENCE_LENSES.find((l) => l.key === selectedLensKey) || SET_INTELLIGENCE_LENSES[0];
  const selectedTier = toOptionalUpper(summary[selectedLens.tierField]);
  const selectedTierConfig = selectedTier ? RANK_CONFIG[selectedTier] : null;
  const selectedDetailBorder = selectedTierConfig?.color
    ? withAlpha(selectedTierConfig.color, 0.36)
    : undefined;

  const setIntelligenceInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Set Intelligence</p>
      <p className="text-[var(--text-secondary)]">
        Quick lenses for how this set opens, chases, and returns value. Select a lens to see what is driving that view.
      </p>
    </div>
  );

  return (
    <section className="pt-4 md:pt-5">
      <article className="w-full max-w-full min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">Set Intelligence</h2>
            <InfoPopover text={setIntelligenceInfo} />
          </div>
          <p className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)] opacity-75 sm:justify-end">
            <svg
              viewBox="0 0 20 20"
              fill="none"
              aria-hidden="true"
              className="h-3.5 w-3.5 flex-none"
            >
              <path
                d="M4.75 2.75L9.8 14.2L11.95 9.95L16.2 7.8L4.75 2.75Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Select a lens to understand more.</span>
          </p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
          {SET_INTELLIGENCE_LENSES.map((lens) => {
            const score = toNumber(summary[lens.scoreField]);
            const tier = toOptionalUpper(summary[lens.tierField]);
            const rank = toNumber(summary[lens.rankField]);
            const isSelected = selectedLensKey === lens.key;
            const tierConfig = tier ? RANK_CONFIG[tier] : null;
            const tierEdgeColor = tierConfig?.color
              ? withAlpha(tierConfig.color, isSelected ? 0.52 : 0.24)
              : null;

            return (
              <button
                key={lens.key}
                type="button"
                onClick={() => setSelectedLensKey(lens.key)}
                aria-pressed={isSelected}
                className={[
                  "relative flex cursor-pointer flex-col rounded-xl border px-3.5 py-3 text-left transition-colors",
                  isSelected
                    ? "bg-[var(--surface-page)]/70 border-[var(--border-subtle)]"
                    : "bg-[var(--surface-page)]/45 border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]",
                ].join(" ")}
                style={
                  isSelected && tierEdgeColor
                    ? {
                        borderColor: tierEdgeColor,
                        boxShadow: `0 0 0 1px ${withAlpha(tierConfig.color, 0.12)}`,
                      }
                    : undefined
                }
              >
                <span className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
                  {lens.label}
                </span>
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-bold leading-none text-[var(--text-primary)]">
                    {formatLensScore(score, lens.format)}
                  </span>
                  {tier ? (
                    <RankBadge rank={tier} format="tier" size="default" subtle />
                  ) : (
                    <span className="text-xs text-[var(--text-secondary)] opacity-60">Not ranked</span>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute right-2.5 top-2 text-[var(--text-secondary)] opacity-40"
                >
                  ›
                </span>
                {rank !== null ? (
                  <span className="mt-1.5 text-[10px] text-[var(--text-secondary)] opacity-70">
                    Rank #{Math.round(rank)}
                  </span>
                ) : null}
                <span className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                  {getLensTagline(lens, summary)}
                </span>
              </button>
            );
          })}
        </div>

        <div
          className="mt-2.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-4 py-3.5"
          style={selectedDetailBorder ? { borderLeftColor: selectedDetailBorder, borderLeftWidth: "2px" } : undefined}
        >
          <div className="mb-1 flex items-start justify-between gap-3">
            <p className="text-sm font-semibold text-[var(--text-primary)]">{selectedLens.heading}</p>
            <span className="flex-none text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)] opacity-70">
              {selectedLens.label}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
            {selectedLens.description}
          </p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {selectedLens.evidenceKeys.map((key) => {
              const row = getLensEvidenceRow(key, summary);
              if (!row) return null;
              return (
                <span
                  key={key}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                >
                  <span className="flex-none">{row.label}:</span>
                  <span className="font-medium text-[var(--text-primary)]">{row.value}</span>
                </span>
              );
            })}
          </div>
        </div>
      </article>
    </section>
  );
}

function ScorePillarCard({
  title,
  score,
  rankValue,
  rankTier,
  simpleMetrics,
  advancedMetrics,
  infoText,
  rankLabel,
  sectionMeta,
  fallbackSummary,
}) {
  const [metricMode, setMetricMode] = useState("overview");
  const parsedRank = toNumber(rankValue);
  const numericRankTitle = parsedRank === null ? "Rank unavailable" : `${rankLabel} #${Math.round(parsedRank)}`;
  const metricsToDisplay = metricMode === "overview" ? simpleMetrics : advancedMetrics;

  return (
    <article className="flex flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2.5">
            <h3 className="text-base font-semibold tracking-[0.01em] text-[var(--text-secondary)]">{title}</h3>
            <p className="text-2xl font-bold leading-none text-[var(--text-primary)]">{formatScore(score)}</p>
            <RankBadge rank={rankTier} label={rankLabel} title={numericRankTitle} size="supporting" subtle />
          </div>
        </div>
        <div className="flex flex-none items-center gap-1">
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
      </div>

      <ScoreMeter score={score} rankTier={rankTier} />

      <div className="mt-4 min-h-[74px]">
        <InterpretationInsight
          sectionMeta={sectionMeta}
          fallbackSummary={fallbackSummary}
          rankTier={rankTier}
          compact
          showEvidence={false}
          className="mt-3"
        />
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
            <InfoPopover text="Switch between simple collector-facing metrics and score details." />
          </div>
          <CompactMetricModeToggle mode={metricMode} onChange={setMetricMode} />
        </div>
        <div className="min-h-[12.5rem] space-y-1">
          {metricsToDisplay.map((metric) => (
          <MetricRow
            key={metric.label}
            label={metric.label}
            value={metric.value}
            infoText={getMetricTooltip(metric.label)}
          />
          ))}
        </div>
      </div>
    </article>
  );
}

function SimplePillarSummaryCard({
  title,
  score,
  rankValue,
  rankTier,
  rankLabel,
  sectionMeta,
  fallbackSummary,
}) {
  const parsedRank = toNumber(rankValue);
  const numericRankTitle = parsedRank === null ? "Rank unavailable" : `${rankLabel} #${Math.round(parsedRank)}`;

  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2.5">
            <h4 className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</h4>
            <p className="text-xl font-semibold leading-none text-[var(--text-primary)]">{formatScore(score)}</p>
            <RankBadge rank={rankTier} label={rankLabel} title={numericRankTitle} size="supporting" subtle />
          </div>
        </div>
      </div>
      <InterpretationInsight
        sectionMeta={sectionMeta}
        fallbackSummary={fallbackSummary}
        rankTier={rankTier}
        compact
        showEvidence={false}
        className="mt-3"
      />
    </article>
  );
}

function StatTile({ label, value, valueClassName = "text-lg" }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <p className={`mt-2 font-semibold text-[var(--text-primary)] ${valueClassName}`}>{value}</p>
    </div>
  );
}

function SectionCard({ title, subtitle, titleInfoText, children }) {
  return (
    <article className="w-full max-w-full min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
      <div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
          {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
        </div>
        {subtitle ? <p className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className="mt-4 min-w-0 max-w-full">{children}</div>
    </article>
  );
}

const TOP_CARD_IMAGE_CONTAINER_CLASS = "h-[5rem] w-[3.5rem] sm:h-[6.125rem] sm:w-[4.25rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]";

function TopHitRow({ name, evContribution, evShare, nearMintPrice, imageUrl, imageSmallUrl, imageLargeUrl }) {
  const imageSrc = imageUrl || imageSmallUrl || imageLargeUrl || null;
  const [hasImageError, setHasImageError] = useState(false);

  useEffect(() => {
    setHasImageError(false);
  }, [imageSrc]);

  const shouldRenderImage = Boolean(imageSrc) && !hasImageError;

  return (
    <div className="w-full max-w-full min-w-0 box-border rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-2.5">
      <div className="flex min-w-0 flex-col gap-3 sm:grid sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <div className={TOP_CARD_IMAGE_CONTAINER_CLASS}>
            {shouldRenderImage ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imageSrc}
                alt={name ? `${name} card image` : "Card image"}
                loading="lazy"
                decoding="async"
                onError={() => setHasImageError(true)}
                className="h-full w-full rounded-[5px] object-contain"
              />
            ) : null}
          </div>
          <div className="min-w-0 max-w-full">
            <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{name || "Unknown Card"}</p>
            {evShare ? <p className="break-words text-xs text-[var(--text-secondary)]">{evShare} of pack value</p> : null}
          </div>
        </div>
        <div className="mt-3 grid min-w-0 grid-cols-2 gap-3 text-left sm:mt-0 sm:min-w-[14rem] sm:text-right">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Estimated Card Market Price</p>
            <p className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{nearMintPrice === null ? "—" : formatCurrency(nearMintPrice)}</p>
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Value Contribution</p>
            <p className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{formatCurrency(evContribution)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function getTopHitNearMintPrice(hit) {
  return toNumber(hit?.current_near_mint_price);
}

function getTopHitCardPrice(hit) {
  // TODO: If top_hits never includes a price field, wire a backend payload field (for example price_used) in a later API-safe pass.
  return (
    toNumber(hit?.current_near_mint_price) ??
    toNumber(hit?.price_used) ??
    toNumber(hit?.market_price) ??
    toNumber(hit?.card_price) ??
    toNumber(hit?.card_market_price) ??
    toNumber(hit?.price)
  );
}

function SimpleTopHitRow({ name, imageUrl, imageSmallUrl, imageLargeUrl, cardPrice }) {
  const imageSrc = imageUrl || imageSmallUrl || imageLargeUrl || null;
  const [hasImageError, setHasImageError] = useState(false);

  useEffect(() => {
    setHasImageError(false);
  }, [imageSrc]);

  const shouldRenderImage = Boolean(imageSrc) && !hasImageError;

  return (
    <div className="w-full max-w-full min-w-0 box-border rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-2.5">
      <div className="flex min-w-0 items-center gap-3">
        <div className={TOP_CARD_IMAGE_CONTAINER_CLASS}>
          {shouldRenderImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageSrc}
              alt={name ? `${name} card image` : "Card image"}
              loading="lazy"
              decoding="async"
              onError={() => setHasImageError(true)}
              className="h-full w-full rounded-[5px] object-contain"
            />
          ) : null}
        </div>

        <div className="min-w-0 max-w-full flex-1">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{name || "Unknown Card"}</p>
          <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Est. Card Market Price</p>
          <p className="mt-1 text-base font-semibold text-[var(--text-primary)]">{cardPrice === null ? "—" : formatCurrency(cardPrice)}</p>
        </div>
      </div>
    </div>
  );
}

function SimpleTopCardsContent({ topHits }) {
  const hits = Array.isArray(topHits) ? topHits.slice(0, 10) : [];

  if (hits.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No cards are available yet for this set.</p>;
  }

  return (
    <div className="w-full max-w-full min-w-0 space-y-2">
      {hits.map((hit, index) => (
        <SimpleTopHitRow
          key={`simple-hit:${hit?.card_name || "unknown"}:${index}`}
          name={hit?.card_name}
          cardPrice={getTopHitCardPrice(hit)}
          imageUrl={hit?.image_url}
          imageSmallUrl={hit?.image_small_url}
          imageLargeUrl={hit?.image_large_url}
        />
      ))}
    </div>
  );
}

function TopEVDriversContent({ topHits, meanValue }) {
  const hits = Array.isArray(topHits) ? topHits : [];
  const totalEV = toNumber(meanValue);
  const visibleTopEV = hits.reduce((sum, hit) => sum + (toNumber(hit?.ev_contribution) ?? 0), 0);
  const hasPackTotalEV = totalEV !== null;
  const totalLabel = hasPackTotalEV ? "Simulated Average Pack Value" : "Top 10 Simulated Value";
  const totalValue = hasPackTotalEV ? totalEV : visibleTopEV;

  if (hits.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No card contribution rows are available.</p>;
  }

  return (
    <div className="w-full max-w-full min-w-0 space-y-2">
      <div className="mb-3 flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{totalLabel}</span>
          <InfoPopover text={SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT} />
        </div>
        <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(totalValue)}</span>
      </div>
      <p className="text-xs text-[var(--text-secondary)]">Price-based metrics use estimated third-party market snapshots and may change over time.</p>

      {hits.map((hit) => {
        const ev = toNumber(hit?.ev_contribution);
        const evShare = ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null;
        const nearMintPrice = getTopHitNearMintPrice(hit);

        return (
          <TopHitRow
            key={`${hit?.card_name || "unknown"}:${hit?.ev_contribution ?? "na"}`}
            name={hit?.card_name}
            evContribution={hit?.ev_contribution}
            evShare={evShare}
            nearMintPrice={nearMintPrice}
            imageUrl={hit?.image_url}
            imageSmallUrl={hit?.image_small_url}
            imageLargeUrl={hit?.image_large_url}
          />
        );
      })}
    </div>
  );
}

function RarityContributionContent({ rankings, mode: controlledMode = null, showToggle = true }) {
  const [uncontrolledMode, setUncontrolledMode] = useState("ev");
  const mode = controlledMode === "ev" || controlledMode === "pull" ? controlledMode : uncontrolledMode;
  const rows = Array.isArray(rankings) ? rankings : [];

  const RarityMetricRow = ({ label, primaryValue, share, barWidth }) => (
    <div className="py-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-[var(--text-primary)]">{label}</span>
        <span className="text-right text-sm text-[var(--text-primary)]">
          <span className="font-semibold">{primaryValue}</span>
          {share ? <span className="text-[var(--text-secondary)]"> {`(${share})`}</span> : null}
        </span>
      </div>
      <HorizontalBar widthPercent={barWidth} />
    </div>
  );

  const evRows = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => (toNumber(b?.total_sampled_value) ?? 0) - (toNumber(a?.total_sampled_value) ?? 0)
    );
    const totalEV = sorted.reduce((sum, row) => sum + (toNumber(row?.total_sampled_value) ?? 0), 0);
    const maxEV = Math.max(...sorted.map((row) => toNumber(row?.total_sampled_value) ?? 0), 0);
    return { sorted, totalEV, maxEV };
  }, [rows]);

  const pullRows = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => (toNumber(b?.pulled_count) ?? 0) - (toNumber(a?.pulled_count) ?? 0)
    );
    const totalPulls = sorted.reduce((sum, row) => sum + (toNumber(row?.pulled_count) ?? 0), 0);
    const maxPulls = Math.max(...sorted.map((row) => toNumber(row?.pulled_count) ?? 0), 0);
    return { sorted, totalPulls, maxPulls };
  }, [rows]);

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No rarity ranking rows are available.</p>;
  }

  return (
    <>
      {showToggle ? (
        <div className="mb-4 inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
          <button
            type="button"
            onClick={() => setUncontrolledMode("ev")}
            aria-pressed={mode === "ev"}
            className={`rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
              mode === "ev" ? "bg-[var(--brand)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            Value Contribution
          </button>
          <button
            type="button"
            onClick={() => setUncontrolledMode("pull")}
            aria-pressed={mode === "pull"}
            className={`rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
              mode === "pull" ? "bg-[var(--brand)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            Pull Frequency
          </button>
        </div>
      ) : null}

      <div className="mb-3 flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {mode === "ev" ? "Total Simulated Value" : "Total Simulated Pulls"}
          </span>
          {mode === "ev" ? <InfoPopover text={TOTAL_SIMULATED_VALUE_INFO_TEXT} /> : null}
        </div>
        <span className="text-lg font-semibold text-[var(--text-primary)]">
          {mode === "ev" ? formatCurrency(evRows.totalEV) : pullRows.totalPulls.toLocaleString("en-US")}
        </span>
      </div>

      {mode === "ev" ? (
        <div className="space-y-1">
          {evRows.maxEV === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No value contribution data available.</p>
          ) : (
            evRows.sorted.map((ranking) => {
              const value = toNumber(ranking?.total_sampled_value) ?? 0;
              const share = evRows.totalEV > 0 ? `${((value / evRows.totalEV) * 100).toFixed(1)}%` : null;

              return (
                <RarityMetricRow
                  key={`ev:${ranking?.rarity_bucket || "unknown"}`}
                  label={titleCaseStateLabel(ranking?.rarity_bucket)}
                  primaryValue={formatCurrency(value)}
                  share={share}
                  barWidth={normalizeBarWidth(value, evRows.maxEV)}
                />
              );
            })
          )}
        </div>
      ) : (
        <div className="space-y-1">
          {pullRows.maxPulls === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No pull frequency data available.</p>
          ) : (
            pullRows.sorted.map((ranking) => {
              const count = toNumber(ranking?.pulled_count) ?? 0;
              const share = pullRows.totalPulls > 0 ? `${((count / pullRows.totalPulls) * 100).toFixed(1)}%` : null;

              return (
                <RarityMetricRow
                  key={`pull:${ranking?.rarity_bucket || "unknown"}`}
                  label={titleCaseStateLabel(ranking?.rarity_bucket)}
                  primaryValue={count.toLocaleString("en-US")}
                  share={share}
                  barWidth={normalizeBarWidth(count, pullRows.maxPulls)}
                />
              );
            })
          )}
        </div>
      )}
    </>
  );
}

function PackPathBars({ packPaths }) {
  const source = typeof packPaths === "object" && packPaths !== null ? packPaths : {};
  const normalized = {
    normal: toNumber(source.normal) ?? 0,
    demi_god_pack: toNumber(source.demi_god_pack ?? source.demi_god ?? source.demigod) ?? 0,
    god_pack: toNumber(source.god_pack ?? source.god) ?? 0,
  };

  const extras = Object.entries(source)
    .filter(([key]) => !["normal", "demi_god_pack", "demi_god", "demigod", "god_pack", "god"].includes(key))
    .map(([key, value]) => ({ key, count: toNumber(value) ?? 0 }));

  const rows = [
    ...REQUIRED_PACK_PATHS.map((key) => ({ key, count: normalized[key] ?? 0 })),
    ...extras,
  ];
  const maxCount = Math.max(...rows.map((row) => row.count), 1);

  return (
    <div className="space-y-3">
      {rows.map(({ key, count }) => (
        <div key={`path:${key}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-[var(--text-secondary)]">{formatPackPathLabel(key)}</span>
            <span className="text-sm font-medium text-[var(--text-primary)]">{count.toLocaleString("en-US")}</span>
          </div>
          <HorizontalBar widthPercent={normalizeBarWidth(count, maxCount)} />
        </div>
      ))}
    </div>
  );
}

function StateBars({ stateRows }) {
  const rows = Array.isArray(stateRows) ? stateRows : [];

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No normal-state counts are available.</p>;
  }

  const maxCount = Math.max(...rows.map(([, value]) => toNumber(value) ?? 0), 1);

  return (
    <div className="space-y-3">
      {rows.map(([name, count]) => {
        const numericCount = toNumber(count) ?? 0;
        return (
          <div key={`state:${name}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-[var(--text-secondary)]">{titleCaseStateLabel(name)}</span>
              <span className="text-sm font-medium text-[var(--text-primary)]">{numericCount.toLocaleString("en-US")}</span>
            </div>
            <HorizontalBar widthPercent={normalizeBarWidth(numericCount, maxCount)} />
          </div>
        );
      })}
    </div>
  );
}

function SectionNavigation({ items, activeSection, onSelect, mobile = false }) {
  const isItemActive = (itemId) => {
    if (itemId === "outcome-distribution") {
      return GRAPH_SECTION_KEYS.has(activeSection) || activeSection === ANALYSIS_SECTION_ID;
    }
    return activeSection === itemId;
  };

  return (
    <nav aria-label="RIP statistics section navigation" className={mobile ? "space-y-1" : "space-y-1.5"}>
      {items.map((item) => {
        const isActive = isItemActive(item.id);
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            aria-current={isActive ? "location" : undefined}
            className={[
              "group flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left transition-colors",
              isActive
                ? "border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)]"
                : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-subtle)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={[
                  "h-2 w-2 rounded-full transition-colors",
                  isActive ? "bg-[var(--brand)]" : "bg-[var(--border-subtle)] group-hover:bg-[var(--text-secondary)]",
                ].join(" ")}
              />
              <span className={mobile ? "text-sm font-medium" : "text-sm font-medium leading-tight"}>{item.label}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function buildEvidenceMap(sectionMeta) {
  const evidence = Array.isArray(sectionMeta?.evidence) ? sectionMeta.evidence : [];
  const mapping = {};
  evidence.forEach((item) => {
    if (!item?.label) {
      return;
    }
    mapping[String(item.label).toLowerCase()] = item.value;
  });
  return mapping;
}

const SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT = (
  <div className="space-y-1.5 text-left">
    <p className="font-semibold text-[var(--text-primary)]">How cards impact pack value</p>
    <p className="text-[var(--text-secondary)]">
      Simulated Average Pack Value is the average value generated per simulated pack using current card values and pull odds. Value Contribution shows how much each card adds to that average after pull odds are considered.
    </p>
  </div>
);
const TOTAL_SIMULATED_VALUE_INFO_TEXT = "The combined simulated value used to compare rarity groups.";

function collectorFriendlyText(text) {
  if (text === null || text === undefined) {
    return text;
  }

  return String(text)
    .replace(/Top EV driver data/gi, "Card contribution data")
    .replace(/Top EV drivers/gi, "Top contributing cards")
    .replace(/Top card EV share/gi, "Top Card Share")
    .replace(/Top 3 EV share/gi, "Top 3 Share")
    .replace(/Top 5 EV share/gi, "Top 5 Share")
    .replace(/EV-leading rarity share/gi, "Top Rarity Share")
    .replace(/EV-leading rarity/gi, "Top Value Rarity")
    .replace(/EV and pull aligned/gi, "Value and Pulls Align")
    .replace(/expected pack value/gi, "simulated average pack value")
    .replace(/expected value/gi, "simulated value")
    .replace(/\bEV\b/g, "value");
}

function toCollectorFriendlySectionMeta(sectionMeta) {
  if (!sectionMeta) {
    return sectionMeta;
  }

  return {
    ...sectionMeta,
    summary: collectorFriendlyText(sectionMeta.summary),
    evidence: Array.isArray(sectionMeta.evidence)
      ? sectionMeta.evidence.map((item) => ({
          ...item,
          label: collectorFriendlyText(item?.label),
          value: collectorFriendlyText(item?.value),
        }))
      : sectionMeta.evidence,
  };
}

function getPackBreakdownEvidence(sectionMeta) {
  const evidenceMap = buildEvidenceMap(sectionMeta);
  const rows = [
    ["Dominant path", evidenceMap["dominant path"]],
    ["Dominant path share", evidenceMap["dominant path share"]],
    ["Special path share", evidenceMap["special path share"]],
  ];

  return rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() && String(value) !== "N/A" && String(value) !== "—");
}

function getTopEvEvidence(sectionMeta) {
  const evidenceMap = buildEvidenceMap(sectionMeta);
  const rows = [
    ["Leading card", evidenceMap["leading card"]],
    ["Top Card Share", evidenceMap["top card ev share"]],
    ["Top 3 Share", evidenceMap["top 3 ev share"]],
    ["Leading value group", evidenceMap["leading value group"] ?? evidenceMap["leading value type"]],
  ];

  return rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() && String(value) !== "N/A" && String(value) !== "—");
}

function CompactBottomSectionNav({ activeSection, onSelect }) {
  const items = [
    {
      id: "pack-score",
      label: "Score",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 16.25a7.5 7.5 0 1 1 15 0" />
          <path d="M12 12.25l3-2.5" />
          <circle cx="12" cy="12.25" r="1" fill="currentColor" stroke="none" />
          <path d="M6.25 18.25h11.5" />
        </svg>
      ),
    },
    {
      id: "outcome-distribution",
      label: "Graph",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 18.25h15" />
          <path d="M7.5 16v-3" />
          <path d="M11.5 16v-5.5" />
          <path d="M15.5 16v-7.5" />
          <path d="M5.2 11.25 9.3 9l2.7 1.6 4.3-3.4" />
        </svg>
      ),
    },
    {
      id: "top-ev-drivers",
      label: "Cards",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 12h3.5l2.1-4.1 4.2 8.2 2.2-4.1H20" />
          <circle cx="13.55" cy="16.1" r="0.85" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
    {
      id: "rarity-contribution",
      label: "Value",
      icon: (
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 4.5 14.7 9.8l5.8.8-4.2 4.1 1 5.8L12 17.7l-5.3 2.8 1-5.8-4.2-4.1 5.8-.8Z" />
        </svg>
      ),
    },
  ];

  const isItemActive = (itemId) => {
    if (itemId === "outcome-distribution") {
      return GRAPH_SECTION_KEYS.has(activeSection) || activeSection === ANALYSIS_SECTION_ID;
    }
    return activeSection === itemId;
  };

  return (
    <div className="w-full max-w-full min-w-0 overflow-hidden">
      <div className="grid w-full max-w-full min-w-0 grid-cols-4 gap-1">
        {items.map((item) => {
          const isActive = isItemActive(item.id);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              aria-current={isActive ? "location" : undefined}
              className={[
                "inline-flex min-w-0 items-center justify-center gap-0.5 rounded-lg border px-1 py-1.5 text-[10px] font-medium leading-none transition-colors duration-150 ease-out",
                isActive
                  ? "border-[var(--accent)] bg-[color:color-mix(in_srgb,var(--accent)_12%,transparent)] text-[var(--accent)]"
                  : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              <span className={["transition-transform duration-150 ease-out max-[360px]:hidden", isActive ? "scale-105" : "scale-100"].join(" ")}>
                {item.icon}
              </span>
              <span className="min-w-0 truncate whitespace-nowrap">{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function RipStatisticsPageClient({
  targetsPayload,
  selectedTarget,
  requestedTargetType,
  requestedTargetId,
  explorePayload,
  pageError,
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const targets = targetsPayload?.targets || [];
  const summary = explorePayload?.summary || {};
  const percentiles = explorePayload?.percentiles || [];
  const distributionBins = explorePayload?.distribution_bins || [];
  const thresholdBins = explorePayload?.threshold_bins || [];
  const topHits = explorePayload?.top_hits || [];
  const historyTrend = explorePayload?.history_trend || [];
  const rankings = explorePayload?.rankings || [];
  const ripStatistics = explorePayload?.rip_statistics;
  const interpretation = explorePayload?.interpretation || {};
  const interpretationMeta = interpretation?.meta || {};
  const packScoreMeta = interpretationMeta?.packScore;
  const profitMeta = interpretationMeta?.profit;
  const safetyMeta = interpretationMeta?.safety;
  const stabilityMeta = interpretationMeta?.stability;
  const outcomeDistributionMeta = interpretationMeta?.outcomeDistribution;
  const historicalTrendMeta = interpretationMeta?.historicalTrend;
  const packBreakdownMeta = interpretationMeta?.packBreakdown;
  const topEvDriversMeta = useMemo(
    () => toCollectorFriendlySectionMeta(interpretationMeta?.topEvDrivers),
    [interpretationMeta?.topEvDrivers]
  );
  const rarityContributionMeta = useMemo(
    () => toCollectorFriendlySectionMeta(interpretationMeta?.rarityContribution),
    [interpretationMeta?.rarityContribution]
  );

  const warnings = [
    ...(targetsPayload?.meta?.warnings || []),
    ...(explorePayload?.meta?.warnings || []),
  ];

  const selectedName = selectedTarget?.name || requestedTargetId || "Selected Set";
  const percentileP5 = getPercentileValue(percentiles, 5);
  const percentileP50 = getPercentileValue(percentiles, 50);
  const percentileP95 = getPercentileValue(percentiles, 95);
  const percentileP99 = getPercentileValue(percentiles, 99);
  const meanValueToCostRatio = summary.mean_value_to_cost_ratio ?? null;
  const medianValueToCostRatio = summary.median_value_to_cost_ratio ?? null;
  const expectedLossWhenLosingFraction = summary.expected_loss_when_losing_fraction ?? null;
  const medianLossWhenLosingFraction = summary.median_loss_when_losing_fraction ?? null;
  const p05ShortfallToCost = summary.p05_shortfall_to_cost ?? null;

  const [graphMode, setGraphMode] = useState("outcome-distribution");
  const [viewMode, setViewMode] = useState("simple");
  const [heroMetricView, setHeroMetricView] = useState("overview");
  const [activeValueView, setActiveValueView] = useState("cards");
  const isExpertMode = viewMode === "expert";
  const effectiveValueView = isExpertMode ? activeValueView : "cards";
  const [activeSection, setActiveSection] = useState("pack-score");
  const [heroSetPickerOpen, setHeroSetPickerOpen] = useState(false);
  const heroSetPickerRef = useRef(null);
  const pendingNavSelectionRef = useRef(null);
  const pendingNavTimeoutRef = useRef(null);
  const pendingNavStartedAtRef = useRef(0);

  const graphSectionMeta =
    graphMode === "historical-trend"
      ? historicalTrendMeta
      : graphMode === "pack-breakdown"
      ? packBreakdownMeta
      : outcomeDistributionMeta;

  const graphSectionFallback =
    graphMode === "historical-trend"
      ? interpretation?.historicalTrend
      : graphMode === "pack-breakdown"
      ? interpretation?.packBreakdown
      : interpretation?.outcomeDistribution;

  const outcomeDistributionInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">What Usually Happens</p>
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2"><span className="flex-none">•</span><span>Bars show how often packs land in each value range.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>The line shows how often a pack reaches at least a given value.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>The markers highlight pack cost, a typical pack value, a big hit, and the best simulated pull in the run.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Extra percentile markers stay available under chart details when you want the technical view.</span></li>
      </ul>
    </div>
  );

  const rarityContributionInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Where the Value Comes From</p>
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2"><span className="flex-none">•</span><span>Shows which rarity groups contribute most to the simulated value in the run.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Higher contribution means that rarity bucket drives more of the pack&apos;s simulated average value.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Use this to see whether value is spread across many rarities or concentrated in a narrow chase tier.</span></li>
      </ul>
    </div>
  );

  const packBreakdownEvidenceRows = useMemo(
    () => getPackBreakdownEvidence(packBreakdownMeta),
    [packBreakdownMeta]
  );

  const topEvEvidenceRows = useMemo(
    () => getTopEvEvidence(topEvDriversMeta),
    [topEvDriversMeta]
  );

  const normalStateRows = useMemo(
    () => sortObjectEntriesDescending(ripStatistics?.normal_pack_states),
    [ripStatistics?.normal_pack_states]
  );

  const timingRows = Object.entries(explorePayload?.meta?.timings || {}).filter(
    ([, value]) => toNumber(value) !== null
  );

  const showDebugTimings = process.env.NODE_ENV !== "production";

  const sectionNavItems = useMemo(
    () => [
      { id: "pack-score", label: RIP_COPY.sections.packScore },
      { id: "outcome-distribution", label: RIP_COPY.sections.outcomeDistribution },
      { id: "top-ev-drivers", label: RIP_COPY.sections.topEvDrivers },
      { id: "rarity-contribution", label: RIP_COPY.sections.rarityContribution },
    ],
    []
  );
  const displayedSectionNavItems = viewMode === "simple"
    ? [{ id: "pack-score", label: RIP_COPY.sections.packScore }]
    : sectionNavItems;

  const getVisibleSectionElement = (sectionId) => {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return null;
    }

    const escapedSectionId = typeof window.CSS?.escape === "function"
      ? window.CSS.escape(sectionId)
      : sectionId;

    const matches = Array.from(document.querySelectorAll(`#${escapedSectionId}`));
    if (matches.length === 0) {
      return null;
    }

    const visibleMatch = matches.find((element) => {
      const styles = window.getComputedStyle(element);
      return styles.display !== "none" && styles.visibility !== "hidden" && element.getClientRects().length > 0;
    });

    return visibleMatch || matches[0] || null;
  };

  const getExploreStickyOffset = () => {
    if (typeof window === "undefined" || typeof document === "undefined") {
      return 0;
    }

    const rootStyles = window.getComputedStyle(document.documentElement);
    const headerOffsetRaw = rootStyles.getPropertyValue("--app-header-offset") || "64";
    const parsedHeaderOffset = Number.parseFloat(headerOffsetRaw);
    const headerOffset = Number.isFinite(parsedHeaderOffset) ? parsedHeaderOffset : 64;

    const subNav = document.querySelector('nav[aria-label="Profile section navigation"]');
    const subNavHeight = subNav instanceof HTMLElement ? subNav.offsetHeight : 0;

    return headerOffset + subNavHeight + 8;
  };

  const resolveActiveSectionFromScroll = () => {
    if (typeof window === "undefined") {
      return null;
    }

    const activationLine = getExploreStickyOffset() + 24;
    let passedSection = null;
    let upcomingSection = null;

    SECTION_SCROLL_ORDER.forEach((entry) => {
      const element = getVisibleSectionElement(entry.sectionId);
      if (!element) {
        return;
      }

      const top = element.getBoundingClientRect().top;
      if (top <= activationLine) {
        passedSection = { navId: entry.navId, top };
      } else if (!upcomingSection) {
        upcomingSection = { navId: entry.navId, top };
      }
    });

    let nextActive = passedSection?.navId || "pack-score";

    if (passedSection && upcomingSection) {
      const passedDistance = activationLine - passedSection.top;
      const upcomingDistance = upcomingSection.top - activationLine;
      if (upcomingDistance < passedDistance) {
        nextActive = upcomingSection.navId;
      }
    } else if (!passedSection && upcomingSection) {
      nextActive = upcomingSection.navId;
    }

    if (nextActive === "outcome-distribution") {
      return graphMode;
    }

    return nextActive;
  };

  const scrollToExploreSection = (sectionId) => {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return;
    }

    const targetId = SECTION_ID_MAP[sectionId] || sectionId;
    const target = getVisibleSectionElement(targetId);
    if (!target) {
      console.warn(`[Explore mobile nav] Missing section target: ${targetId}`);
      return;
    }

    const stickyOffset = getExploreStickyOffset();
    const targetTop = target.getBoundingClientRect().top + window.scrollY - stickyOffset;
    window.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
  };

  const handleSectionSelect = (sectionId) => {
    pendingNavSelectionRef.current = sectionId;
    pendingNavStartedAtRef.current = Date.now();
    if (pendingNavTimeoutRef.current !== null && typeof window !== "undefined") {
      window.clearTimeout(pendingNavTimeoutRef.current);
    }
    if (typeof window !== "undefined") {
      pendingNavTimeoutRef.current = window.setTimeout(() => {
        pendingNavSelectionRef.current = null;
        pendingNavStartedAtRef.current = 0;
        pendingNavTimeoutRef.current = null;
      }, 1200);
    }

    if (GRAPH_SECTION_KEYS.has(sectionId) && graphMode !== sectionId) {
      setGraphMode(sectionId);
    }

    if (sectionId === "top-ev-drivers") {
      setActiveValueView("cards");
    } else if (sectionId === "rarity-contribution") {
      setActiveValueView("value");
    }

    setActiveSection(sectionId);
    scrollToExploreSection(sectionId);
  };

  useEffect(() => {
    const nextActiveSection = resolveActiveSectionFromScroll();
    if (nextActiveSection) {
      setActiveSection(nextActiveSection);
    }
  }, [graphMode]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    let frameId = null;
    const updateActiveFromScroll = () => {
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(() => {
        const pendingNavSelection = pendingNavSelectionRef.current;
        if (pendingNavSelection) {
          if (pendingNavStartedAtRef.current > 0 && Date.now() - pendingNavStartedAtRef.current > 1200) {
            pendingNavSelectionRef.current = null;
            pendingNavStartedAtRef.current = 0;
            if (pendingNavTimeoutRef.current !== null) {
              window.clearTimeout(pendingNavTimeoutRef.current);
              pendingNavTimeoutRef.current = null;
            }
          }

        }

        const nextPendingNavSelection = pendingNavSelectionRef.current;
        if (nextPendingNavSelection) {
          const pendingTargetId = SECTION_ID_MAP[nextPendingNavSelection] || nextPendingNavSelection;
          const pendingTarget = getVisibleSectionElement(pendingTargetId);
          const activationLine = getExploreStickyOffset() + 24;
          if (pendingTarget) {
            const targetTop = pendingTarget.getBoundingClientRect().top;
            setActiveSection(nextPendingNavSelection);
            if (targetTop <= activationLine) {
              pendingNavSelectionRef.current = null;
              pendingNavStartedAtRef.current = 0;
              if (pendingNavTimeoutRef.current !== null) {
                window.clearTimeout(pendingNavTimeoutRef.current);
                pendingNavTimeoutRef.current = null;
              }
            }
            frameId = null;
            return;
          }
        }

        const nextActiveSection = resolveActiveSectionFromScroll();
        if (nextActiveSection) {
          setActiveSection(nextActiveSection);
        }
        frameId = null;
      });
    };

    updateActiveFromScroll();
    window.addEventListener("scroll", updateActiveFromScroll, { passive: true });
    window.addEventListener("resize", updateActiveFromScroll);

    return () => {
      window.removeEventListener("scroll", updateActiveFromScroll);
      window.removeEventListener("resize", updateActiveFromScroll);
      pendingNavSelectionRef.current = null;
      pendingNavStartedAtRef.current = 0;
      if (pendingNavTimeoutRef.current !== null) {
        window.clearTimeout(pendingNavTimeoutRef.current);
        pendingNavTimeoutRef.current = null;
      }
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [explorePayload, pageError, graphMode]);

  const chartMarkers = [
    { key: "pack-cost", label: RIP_COPY.chartMarkers.packCost, value: summary.pack_cost },
    { key: "median", label: RIP_COPY.chartMarkers.typicalPack, value: percentileP50 ?? summary.median_value },
    { key: "big-hit", label: RIP_COPY.chartMarkers.bigHit, value: summary.big_hit_threshold },
    { key: "max", label: RIP_COPY.chartMarkers.bestPull, value: summary.max_value },
  ];

  const topScoreRaw = toNumber(summary.relative_pack_score) ?? toNumber(summary.pack_score);
  const displayedTopScore = formatRawScore(topScoreRaw);

  const displayedProfitScore =
    toNumber(summary.relative_profit_score) ?? toNumber(summary.profit_score);
  const displayedSafetyScore =
    toNumber(summary.relative_safety_score) ?? toNumber(summary.safety_score);
  const displayedStabilityScore =
    toNumber(summary.relative_stability_score) ?? toNumber(summary.stability_score);
  const heroLogoUrl =
    selectedTarget?.logo_image_url || selectedTarget?.hero_image_url || selectedTarget?.symbol_image_url || null;

  const recommendationSummary = packScoreMeta?.summary || interpretation?.packScore || null;
  const recommendationBadge = packScoreMeta?.label || null;
  const recommendationTone = getInterpretationTone({ label: recommendationBadge, rankTier: summary.pack_tier });
  const simpleAverageLossValue = getSimpleAverageLossValue(summary);
  const decisionMetrics = [
    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }) },
    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value) },
    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost) },
    { label: RIP_COPY.simpleMetrics.averageLoss, value: formatSignedCurrency(simpleAverageLossValue) },
    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }) },
  ];
  const primaryDecisionMetricOrder = [
    RIP_COPY.simpleMetrics.averagePackValue,
    RIP_COPY.simpleMetrics.currentPackCost,
    RIP_COPY.simpleMetrics.averageLoss,
  ];
  const primaryDecisionMetrics = primaryDecisionMetricOrder
    .map((label) => decisionMetrics.find((metric) => metric.label === label))
    .filter(Boolean);
  const secondaryDecisionMetrics = decisionMetrics.filter(
    (metric) => !primaryDecisionMetricOrder.includes(metric.label)
  );
  const technicalScoreMetrics = [
    { label: "Average Return vs Cost", value: formatNumber(meanValueToCostRatio, 2) },
    { label: "Typical Outcome vs Cost", value: formatNumber(medianValueToCostRatio, 2) },
    { label: "Big Hit Upside", value: formatNumber(summary.p95_value_to_cost_ratio, 2) },
    { label: "Outcome Volatility", value: formatNumber(summary.coefficient_of_variation, 2) },
    { label: "Value Concentration", value: formatNumber(summary.hhi_ev_concentration, 3) },
    { label: "Chase Depth", value: formatNumber(summary.effective_chase_count, 2) },
  ];

  const handleTargetIdChange = (nextTargetId, options = {}) => {
    if (!nextTargetId) {
      return;
    }

    if (typeof options.closeToolsPanel === "function") {
      options.closeToolsPanel();
    }

    const nextParams = new URLSearchParams(searchParams?.toString() || "");
    nextParams.set("target_type", requestedTargetType || "set");
    nextParams.set("target_id", nextTargetId);
    startTransition(() => {
      router.push(`${pathname}?${nextParams.toString()}`);
    });
  };

  const handleTargetChange = (event, options = {}) => {
    const nextTargetId = String(event.target.value || "").trim();
    handleTargetIdChange(nextTargetId, options);
  };

  useEffect(() => {
    if (!heroSetPickerOpen || typeof document === "undefined") {
      return undefined;
    }

    const handleOutsideClick = (event) => {
      if (!event.target.closest?.('[data-hero-picker]')) {
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

  useEffect(() => {
    setHeroSetPickerOpen(false);
  }, [requestedTargetId]);

  const desktopSidebarContent = (
    <div className="space-y-5 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/72 p-4 backdrop-blur-sm">
      <div>
        <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Explore Controls
        </p>
        <div className="mt-3 space-y-3">
          <div>
            <label
              htmlFor="sidebar-rip-tcg"
              className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]"
            >
              TCG
            </label>
            <select
              id="sidebar-rip-tcg"
              disabled
              value="pokemon"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] opacity-80 outline-none"
            >
              <option value="pokemon">Pokemon</option>
            </select>
          </div>
          <div>
            <label
              htmlFor="sidebar-rip-target"
              className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]"
            >
              Set
            </label>
            <select
              id="sidebar-rip-target"
              value={requestedTargetId || ""}
              onChange={handleTargetChange}
              disabled={isPending || targets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {targets.map((target) => (
                <option key={`${target.target_type}:${target.target_id}`} value={target.target_id}>
                  {target.name}
                </option>
              ))}
            </select>
          </div>
          {selectedTarget?.era ? (
            <div className="flex items-center gap-2 px-1">
              <span className="text-xs font-medium text-[var(--text-secondary)]">Era</span>
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-0.5 text-xs text-[var(--text-secondary)]">
                {selectedTarget.era}
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="h-px w-full bg-[var(--border-subtle)]" />

      <div>
        <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Sections
        </p>
        <div className="mt-2">
          <SectionNavigation
            items={displayedSectionNavItems}
            activeSection={activeSection}
            onSelect={handleSectionSelect}
          />
        </div>
      </div>
    </div>
  );

  const renderMobileToolsPanelContent = ({ closeToolsPanel } = {}) => (
    <div className="space-y-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Explore Controls
        </p>
        <div className="mt-2 space-y-3">
          <div>
            <label htmlFor="mobile-rip-tcg" className="mb-1 block text-xs font-medium text-[var(--text-primary)]">
              TCG
            </label>
            <select
              id="mobile-rip-tcg"
              disabled
              value="pokemon"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] opacity-80 outline-none"
            >
              <option value="pokemon">Pokemon</option>
            </select>
          </div>
          <div>
            <label htmlFor="mobile-rip-target" className="mb-1 block text-xs font-medium text-[var(--text-primary)]">
              Set
            </label>
            <select
              id="mobile-rip-target"
              value={requestedTargetId || ""}
              onChange={(event) => handleTargetChange(event, { closeToolsPanel })}
              disabled={isPending || targets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {targets.map((target) => (
                <option key={`${target.target_type}:${target.target_id}`} value={target.target_id}>
                  {target.name}
                </option>
              ))}
            </select>
          </div>
          {selectedTarget?.era ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--text-secondary)]">Era:</span>
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                {selectedTarget.era}
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );

  return (
    <main className="w-full max-w-full pb-8 pt-0 lg:py-8">
      <PublicProfileLocalScaffold
        profileBaseHref="/Explore/rip-statistics"
        mode="public"
        sectionItems={[]}
        mobileNavItems={[]}
        desktopSidebarContent={desktopSidebarContent}
        mobileToolsPanelContent={renderMobileToolsPanelContent}
        mobileToolsTitle="Explore Filters & Navigation"
        mobileToolsDescription="Switch TCG and set filters."
        mobileToolsPanelAriaLabel="Explore filters and navigation"
        mobileToolsTriggerLabel="Filters & Tools"
        mobileToolsTriggerTitle="Open filters and navigation"
        useFloatingToolsOnTablet
        forceCompactToolsBelow2xl
        centerContentIgnoringSidebar
        desktopContentOffsetClassName="xl:flex xl:justify-center"
        wrapDesktopContentInFrame={false}
        mobileBottomNavVariant="flat"
        mobileBottomNavContent={() => (
          viewMode === "expert" ? (
            <CompactBottomSectionNav
              activeSection={activeSection}
              onSelect={handleSectionSelect}
            />
          ) : null
        )}
      >
        <div className="dashboard-container space-y-8 w-full max-w-full min-w-0 !p-0 !bg-transparent !border-0 !rounded-none xl:!p-6 xl:!bg-[rgba(255,255,255,0.02)] xl:!rounded-2xl xl:!border">
        {pageError ? (
          <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6">
            <p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p>
            <p className="mt-2 text-sm text-red-300">{pageError}</p>
          </section>
        ) : null}

        {!pageError && explorePayload ? (
          <>
            <section id="explore-score" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="page-hero-panel relative overflow-hidden scroll-mt-24 rounded-xl px-4 py-6 md:rounded-2xl md:px-6 md:py-8 md:scroll-mt-28">
              {heroLogoUrl ? (
                <div className="pointer-events-none absolute left-1/2 top-[18%] z-0 h-[100%] w-[100%] -translate-x-1/2 -translate-y-1/2 select-none sm:top-1/2 sm:h-[107%] sm:w-[107%]">
                  <img
                    src={heroLogoUrl}
                    alt=""
                    aria-hidden="true"
                    className="h-full w-full object-contain opacity-[0.1] [filter:drop-shadow(0_0_20px_rgba(148,163,184,0.16))]"
                    loading="lazy"
                    decoding="async"
                  />
                </div>
              ) : null}
              <div className="relative z-10 mx-auto mt-2 flex w-full max-w-[42rem] flex-col items-center text-center">
                <div ref={heroSetPickerRef} data-hero-picker className="relative w-full">
                  <CenteredSuffixInline
                    as="button"
                    type="button"
                    onClick={() => setHeroSetPickerOpen((open) => !open)}
                    disabled={isPending || targets.length === 0}
                    aria-expanded={heroSetPickerOpen}
                    aria-haspopup="listbox"
                    aria-controls="hero-set-picker-list"
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
                    <span>{selectedName}</span>
                  </CenteredSuffixInline>

                  {heroSetPickerOpen ? (
                    <div
                      id="hero-set-picker-list"
                      role="listbox"
                      aria-label="Available sets"
                      className="index-scrollbar absolute left-1/2 top-full z-30 mt-2 max-h-72 w-[min(36rem,92vw)] -translate-x-1/2 overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1.5 text-left shadow-[0_12px_30px_rgba(0,0,0,0.42)]"
                    >
                      {targets.map((target) => {
                        const isSelected = String(target.target_id) === String(requestedTargetId || "");
                        return (
                          <button
                            key={`hero-set-option:${target.target_type}:${target.target_id}`}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            onClick={() => {
                              handleTargetIdChange(String(target.target_id || ""));
                              setHeroSetPickerOpen(false);
                            }}
                            className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                              isSelected
                                ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                                : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                            }`}
                          >
                            <span className="truncate">{target.name}</span>
                            {isSelected ? (
                              <span className="ml-2 text-xs font-medium text-[var(--accent)]">Current</span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>

                <div className="mt-6 flex w-full flex-col items-center text-center">
                  <div className="mb-1 mt-1 flex w-full justify-center">
                    <ViewModeToggle viewMode={viewMode} onChange={setViewMode} />
                  </div>
                  <div className="mt-4 flex w-full flex-col items-center text-center">
                      <div className="mt-1 flex w-full justify-center">
                        <div className="relative inline-flex text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
                          <span>{RIP_COPY.scoreLabel}</span>
                          <span className="absolute left-full top-1/2 ml-2 inline-flex -translate-y-1/2 items-center">
                            <InfoPopover text={getFormattedTooltip("Pack Score")} />
                          </span>
                        </div>
                      </div>
                      <div className="mt-3 flex w-full justify-center">
                        <div className="relative inline-block leading-none">
                          <span className="text-[clamp(3.25rem,10vw,5rem)] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                            {displayedTopScore}
                          </span>
                          <span className="pointer-events-none absolute bottom-2 left-full ml-2 text-sm font-medium text-[var(--text-secondary)] sm:bottom-3">/100</span>
                        </div>
                      </div>
                      <div className="mt-4 w-full max-w-lg">
                        <ScoreMeter score={topScoreRaw} rankTier={summary.pack_tier} />
                      </div>
                      <div className="mt-4 flex w-full justify-center self-center">
                        <RankBadge
                          rank={summary.pack_tier}
                          label="Rank"
                          size="hero"
                          title={
                            summary.pack_rank === null || summary.pack_rank === undefined
                              ? "Rank unavailable"
                              : `Rank #${summary.pack_rank}`
                          }
                        />
                      </div>
                    </div>

                    <div className="mx-auto mt-6 w-full max-w-2xl">
                      <div
                        className="border-l-2 px-4 py-3 text-left sm:px-5"
                        style={getCalloutAccentStyle({ label: recommendationBadge, rankTier: summary.pack_tier })}
                      >
                        <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                          <span className="h-1.5 w-1.5 rounded-full" aria-hidden="true" style={{ backgroundColor: recommendationTone.dotColor }} />
                          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{RIP_COPY.recommendationLabel}</p>
                          <RecommendationBadge label={recommendationBadge} rankTier={summary.pack_tier} />
                        </div>
                        <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{recommendationSummary || "No interpretation summary is available for this set yet."}</p>
                      </div>
                    </div>

                    <div className="mx-auto mt-5 w-full max-w-2xl text-left">
                      {viewMode === "simple" ? (
                        <>
                          <div className="mb-3 flex items-center gap-2">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
                            <InfoPopover text="Core decision metrics first. Expand to view more context metrics." />
                          </div>
                          <div className="grid gap-2 sm:grid-cols-3">
                            {primaryDecisionMetrics.map((metric) => (
                              <HeroMetricTile key={metric.label} label={metric.label} value={metric.value} />
                            ))}
                          </div>
                          {secondaryDecisionMetrics.length > 0 ? (
                            <details className="group mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-3 py-2.5">
                              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-[var(--text-primary)]">
                                <span>View score breakdown</span>
                                <span className="text-xs text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180">▾</span>
                              </summary>
                              <div className="mt-3 space-y-3">
                                <div className="grid gap-3">
                                  <SimplePillarSummaryCard
                                    title="Profit"
                                    score={displayedProfitScore}
                                    rankValue={summary.profit_rank}
                                    rankTier={summary.profit_tier}
                                    rankLabel="Profit Rank"
                                    sectionMeta={profitMeta}
                                    fallbackSummary={interpretation?.profit}
                                  />
                                  <SimplePillarSummaryCard
                                    title="Safety"
                                    score={displayedSafetyScore}
                                    rankValue={summary.safety_rank}
                                    rankTier={summary.safety_tier}
                                    rankLabel="Safety Rank"
                                    sectionMeta={safetyMeta}
                                    fallbackSummary={interpretation?.safety}
                                  />
                                  <SimplePillarSummaryCard
                                    title="Stability"
                                    score={displayedStabilityScore}
                                    rankValue={summary.stability_rank}
                                    rankTier={summary.stability_tier}
                                    rankLabel="Stability Rank"
                                    sectionMeta={stabilityMeta}
                                    fallbackSummary={interpretation?.stability}
                                  />
                                </div>
                              </div>
                            </details>
                          ) : null}
                        </>
                      ) : (
                        <>
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
                              <InfoPopover text="Overview shows collector-friendly metrics. Score Details shows the technical inputs behind the score." />
                            </div>
                            <MetricViewToggle metricView={heroMetricView} onChange={setHeroMetricView} />
                          </div>
                          {(heroMetricView === "overview" ? decisionMetrics : technicalScoreMetrics).map((metric) => (
                            <MetricRow
                              key={metric.label}
                              label={metric.label}
                              value={metric.value}
                              infoText={getMetricTooltip(metric.label)}
                            />
                          ))}
                        </>
                      )}
                    </div>

                    {viewMode === "expert" ? (
                      <>
                        <div className="mx-auto mt-4 w-full max-w-2xl">
                          <button
                            type="button"
                            onClick={() => handleSectionSelect("top-ev-drivers")}
                            className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-4 py-3 text-left text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] md:flex md:items-center md:justify-between"
                          >
                            <span>Want to see what cards drive this score?</span>
                            <span className="mt-1 inline-flex font-medium text-[var(--accent)] md:mt-0">View top cards →</span>
                          </button>
                        </div>
                      </>
                    ) : null}
                </div>
              </div>
            </section>

            {viewMode === "simple" ? (
            <section id="explore-drivers" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="w-full max-w-full min-w-0 scroll-mt-24 pt-1 md:scroll-mt-28">
              <SectionCard title={RIP_COPY.sections.rarityContribution} subtitle={null} titleInfoText={rarityContributionInfo}>
                <div id="explore-rarity" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="scroll-mt-24 md:scroll-mt-28" />

                <InterpretationInsight
                  sectionMeta={topEvDriversMeta}
                  fallbackSummary={collectorFriendlyText(interpretation?.topEvDrivers)}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />

                {topEvEvidenceRows.length > 0 ? (
                  <div className="mb-3 flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2">
                    {topEvEvidenceRows.map(([label, value]) => (
                      <span
                        key={`${label}:${value}`}
                        className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        <span className="shrink-0">{label}</span>
                        <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}

                <SimpleTopCardsContent topHits={topHits} />
              </SectionCard>
            </section>
            ) : null}

            {viewMode === "expert" ? (
            <section className="pt-8">
              <div className="grid gap-4 xl:grid-cols-3">
                <ScorePillarCard
                  title="Profit"
                  score={displayedProfitScore}
                  rankValue={summary.profit_rank}
                  rankTier={summary.profit_tier}
                  rankLabel="Profit Rank"
                  sectionMeta={profitMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Profit")}
                  simpleMetrics={[
                    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }) },
                    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value) },
                    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost) },
                    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }) },
                  ]}
                  advancedMetrics={[
                    { label: "Average Return vs Cost", value: formatNumber(meanValueToCostRatio, 2) },
                    { label: "Typical Outcome vs Cost", value: formatNumber(medianValueToCostRatio, 2) },
                    { label: "Big Hit Upside", value: formatNumber(summary.p95_value_to_cost_ratio, 2) },
                    { label: "ROI", value: formatPercent(summary.roi_percent) },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={displayedSafetyScore}
                  rankValue={summary.safety_rank}
                  rankTier={summary.safety_tier}
                  rankLabel="Safety Rank"
                  sectionMeta={safetyMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Safety")}
                  simpleMetrics={[
                    { label: "Average Loss When You Miss", value: formatLossCurrency(summary.expected_loss_when_losing) },
                    { label: "Typical Pack Value", value: formatCurrency(percentileP50 ?? summary.median_value) },
                    { label: "Bad Pack Floor Value", value: formatCurrency(percentileP5 ?? summary.tail_value_p05) },
                  ]}
                  advancedMetrics={[
                    { label: "Expected Loss Per Pack", value: formatLossCurrency(summary.expected_loss_per_pack) },
                    { label: "Expected Loss When Losing", value: formatLossCurrency(summary.expected_loss_when_losing) },
                    { label: "Median Loss When Losing", value: formatLossCurrency(summary.median_loss_when_losing) },
                    { label: "Worst 5% Outcome", value: formatCurrency(percentileP5 ?? summary.tail_value_p05) },
                  ]}
                />
                <ScorePillarCard
                  title="Stability"
                  score={displayedStabilityScore}
                  rankValue={summary.stability_rank}
                  rankTier={summary.stability_tier}
                  rankLabel="Stability Rank"
                  sectionMeta={stabilityMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Stability")}
                  simpleMetrics={[
                    { label: "Cards Carrying Value", value: formatNumber(summary.effective_chase_count, 2) },
                    { label: "Top Chase Share", value: formatPercent(summary.top1_ev_share) },
                    { label: "Value Spread", value: formatNumber(summary.hhi_ev_concentration, 3) },
                  ]}
                  advancedMetrics={[
                    { label: "Outcome Volatility", value: formatNumber(summary.coefficient_of_variation, 2) },
                    { label: "EV Concentration", value: formatNumber(summary.hhi_ev_concentration, 3) },
                    { label: "Effective Chase Count", value: formatNumber(summary.effective_chase_count, 2) },
                    { label: "Top 3 Share", value: formatPercent(summary.top3_ev_share) },
                    { label: "Top 5 Share", value: formatPercent(summary.top5_ev_share) },
                  ]}
                />
              </div>
            </section>
            ) : null}

            {viewMode === "expert" ? (
              <SetIntelligenceSection summary={summary} />
            ) : null}

            {viewMode === "expert" ? (
            <section id={ANALYSIS_SECTION_ID} style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="scroll-mt-24 pt-7 md:scroll-mt-28">
              <SectionCard
                title={
                  graphMode === "historical-trend"
                    ? RIP_COPY.sections.historicalTrend
                    : graphMode === "pack-breakdown"
                    ? RIP_COPY.sections.packBreakdown
                    : RIP_COPY.sections.outcomeDistribution
                }
                subtitle={
                  graphMode === "outcome-distribution"
                    ? "See where a typical pack lands, how often packs miss, and how far the best hits can run."
                    : null
                }
                titleInfoText={graphMode === "outcome-distribution" ? outcomeDistributionInfo : null}
              >
                <div className="mb-4">
                  <div className="grid w-full grid-cols-3 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("outcome-distribution")}
                    aria-pressed={graphMode === "outcome-distribution"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "outcome-distribution"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">{RIP_COPY.sections.outcomeDistribution}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("historical-trend")}
                    aria-pressed={graphMode === "historical-trend"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "historical-trend"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">{RIP_COPY.sections.historicalTrend}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSectionSelect("pack-breakdown")}
                    aria-pressed={graphMode === "pack-breakdown"}
                    className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                      graphMode === "pack-breakdown"
                        ? "bg-[var(--brand)] text-white"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="block truncate">{RIP_COPY.sections.packBreakdown}</span>
                  </button>
                  </div>
                </div>

                <InterpretationInsight
                  sectionMeta={graphSectionMeta}
                  fallbackSummary={graphSectionFallback}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />

                {graphMode === "pack-breakdown" && packBreakdownEvidenceRows.length > 0 ? (
                  <div className="mb-4 flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2">
                    {packBreakdownEvidenceRows.map(([label, value]) => (
                      <span
                        key={`${label}:${value}`}
                        className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        <span className="shrink-0 text-[var(--text-secondary)]">{label}</span>
                        <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}

                {graphMode === "historical-trend" ? (
                  <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} />
                ) : graphMode === "pack-breakdown" ? (
                  <div className="grid gap-5 md:grid-cols-2">
                    <div>
                      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>
                      <PackPathBars packPaths={ripStatistics?.pack_paths} />
                    </div>
                    <div>
                      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Normal States</p>
                      <StateBars stateRows={normalStateRows} />
                    </div>
                  </div>
                ) : (
                  <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
                )}

                {graphMode !== "pack-breakdown" ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                    <StatTile label={RIP_COPY.chartStats.chanceToBeatPackCost} value={formatPercent(summary.prob_profit, { probability: true })} />
                    <StatTile label={RIP_COPY.chartStats.chanceAtBigPull} value={formatPercent(summary.prob_big_hit, { probability: true })} />
                    <StatTile label={RIP_COPY.chartStats.typicalPack} value={formatCurrency(percentileP50 ?? summary.median_value)} />
                    <StatTile label={RIP_COPY.chartStats.badPackFloor} value={formatCurrency(percentileP5 ?? summary.tail_value_p05)} />
                    <StatTile label={RIP_COPY.chartStats.bestPull} value={formatCurrency(summary.max_value)} />
                  </div>
                ) : null}
              </SectionCard>
            </section>
            ) : null}

            {viewMode === "expert" ? (
            <section id="explore-drivers" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="w-full max-w-full min-w-0 scroll-mt-24 pt-1 md:scroll-mt-28">
              <SectionCard title={RIP_COPY.sections.rarityContribution} subtitle={null} titleInfoText={rarityContributionInfo}>
                <div className="mb-4 overflow-x-auto">
                  <div className="inline-flex min-w-max items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5">
                    <button
                      type="button"
                      onClick={() => setActiveValueView("cards")}
                      aria-pressed={activeValueView === "cards"}
                      className={`whitespace-nowrap rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                        activeValueView === "cards"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      Cards Carrying the Set
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveValueView("value")}
                      aria-pressed={activeValueView === "value"}
                      className={`whitespace-nowrap rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                        activeValueView === "value"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      Value Contribution
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveValueView("frequency")}
                      aria-pressed={activeValueView === "frequency"}
                      className={`whitespace-nowrap rounded-md px-3 py-1.5 text-[11px] font-semibold leading-none transition-colors ${
                        activeValueView === "frequency"
                          ? "bg-[var(--brand)] text-white"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      Pull Frequency
                    </button>
                  </div>
                </div>

                <div id="explore-rarity" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="scroll-mt-24 md:scroll-mt-28" />

                {effectiveValueView === "cards" ? (
                  <>
                    <InterpretationInsight
                      sectionMeta={topEvDriversMeta}
                      fallbackSummary={collectorFriendlyText(interpretation?.topEvDrivers)}
                      compact
                      showEvidence={false}
                      className="mb-3"
                    />

                    {topEvEvidenceRows.length > 0 ? (
                      <div className="mb-3 flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2">
                        {topEvEvidenceRows.map(([label, value]) => (
                          <span
                            key={`${label}:${value}`}
                            className="inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                          >
                            <span className="shrink-0">{label}</span>
                            <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(value)}</span>
                          </span>
                        ))}
                      </div>
                    ) : null}

                    <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} />
                  </>
                ) : (
                  <>
                    <InterpretationInsight
                      sectionMeta={rarityContributionMeta}
                      fallbackSummary={collectorFriendlyText(interpretation?.rarityContribution)}
                      compact
                      showEvidence
                      maxEvidence={4}
                      className="mb-3"
                    />
                    <RarityContributionContent
                      rankings={rankings}
                      mode={effectiveValueView === "value" ? "ev" : "pull"}
                      showToggle={false}
                    />
                  </>
                )}
              </SectionCard>
            </section>
            ) : null}



            {warnings.length > 0 ? (
              <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4 sm:p-5">
                <p className="text-sm font-semibold text-[var(--text-primary)]">Warnings</p>
                <div className="mt-2 space-y-1">
                  {warnings.map((warning, index) => (
                    <p key={`${warning}:${index}`} className="text-sm text-[var(--text-secondary)]">{warning}</p>
                  ))}
                </div>
              </section>
            ) : null}

            {showDebugTimings ? (
              <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4 sm:p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Backend Timings</span>
                  {timingRows.length > 0 ? (
                    timingRows.map(([key, value]) => (
                      <span
                        key={key}
                        className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        {key.replace(/_/g, " ")}: {toNumber(value)?.toFixed(2)}ms
                      </span>
                    ))
                  ) : (
                    <span className="text-sm text-[var(--text-secondary)]">No backend timings are available.</span>
                  )}
                </div>
              </section>
            ) : null}
          </>
        ) : null}
        </div>
      </PublicProfileLocalScaffold>
    </main>
  );
}