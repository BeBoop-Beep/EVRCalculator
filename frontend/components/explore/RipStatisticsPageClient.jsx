"use client";

import { useEffect, useId, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import InterpretationInsight from "@/components/explore/InterpretationInsight";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import PullRateAssumptionsCard from "@/components/explore/PullRateAssumptionsCard";
import InfoPopover from "@/components/ui/InfoPopover";
import DeltaTrendIcon from "@/components/ui/DeltaTrendIcon";
import InterpretationBadge from "@/components/ui/InterpretationBadge";
import RankBadge from "@/components/ui/RankBadge";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { RANK_CONFIG } from "@/constants/rankConfig";
import { getFriendlyMetricLabel, getFormattedTooltip, getMetricTooltip } from "@/constants/interpretabilityConfig";
import {
  NEGATIVE_VALUE_COLOR,
  POSITIVE_VALUE_COLOR,
  getCalloutAccentStyle,
  getDangerValueStyle,
  getInterpretationTone,
} from "@/lib/explore/interpretationTone";
import { getPokemonSetCards } from "@/lib/pokemon/pokemonSetCardsClient";
import { getPokemonSetTopMarketCards, getPokemonSetValueHistory } from "@/lib/pokemon/pokemonSetMarketClient";
import {
  computeDeltaWindowsFromHistory,
  extractDeltaWindows,
  filterHistoryPointsForDeltaWindow,
  getDeltaWindowLabel,
  getPreferredDeltaWindowKey,
  getSelectedDeltaWindowFromHistory,
  getStandardDeltaWindowDefinitions,
  getVisibleHistoryWindowMetrics,
} from "@/lib/explore/marketDeltaWindows.mjs";
import { formatHistoryDate, getHistoryDateKey } from "./historyDateFormatting.mjs";
import { forwardFillDailyHistoryThroughToday, normalizeHistoryTrendPoint } from "./packValueHistoryNormalization.mjs";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const REQUIRED_PACK_PATHS = ["normal", "demi_god_pack", "god_pack"];
const ANALYSIS_SECTION_ID = "explore-outcomes";
const GRAPH_SECTION_KEYS = new Set(["outcome-distribution", "historical-trend", "simulation-drivers", "pack-breakdown", "value-contribution"]);
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
const SET_DETAIL_DEFAULT_TAB = "cards";
const SET_DETAIL_TABS = new Set(["overview", "cards", "pull-rates", "insights"]);
const SET_VALUE_HISTORY_REQUEST_DAYS = 1825;
const SET_VALUE_SCOPE_OPTIONS = [
  { key: "standard", label: "Checklist" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
];
const SET_DETAIL_TAB_ALIASES = {
  analytics: "insights",
  market: "overview",
};
const SET_DETAIL_SECTION_TARGETS = {
  "set-intelligence": { tab: "overview", targetId: "set-detail-set-intelligence" },
  "set-signals": { tab: "overview", targetId: "set-detail-set-intelligence" },
  "rip-score": { tab: "insights", targetId: "set-detail-rip-score", graphMode: "outcome-distribution" },
  "opening-outcomes": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "outcome-distribution" },
  "simulation-cards": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "simulation-drivers" },
  value: { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "value-contribution" },
  "pack-breakdown": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "pack-breakdown" },
  "performance-vs-cost": { tab: "overview", targetId: "set-detail-overview-performance", graphMode: "historical-trend" },
  "top-market-cards": { tab: "overview", targetId: "set-detail-top-market-cards" },
};

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
    averageHitValue: "Average Hit Value",
    currentPackCost: "Estimated Pack Market Price",
    averageLoss: "Average Loss",
    chanceAtBigPull: "Chance at a Big Pull",
  },
  sections: {
    packScore: "Rip Score",
    outcomeDistribution: "Opening Outcomes",
    historicalTrend: "Performance vs Cost",
    packBreakdown: "Pack Breakdown",
    topEvDrivers: "Cards Carrying the Set",
    rarityContribution: "Where the Value Comes From",
  },
  chartMarkers: {
    packCost: "Pack Cost",
    typicalPack: "Typical Pack",
    averagePack: "Average Pack",
    badFloor: "Bad Floor",
    bigHit: "Big Hit",
    bigHitUpside: "Big Hit Upside",
    godPullUpside: "God Pull Upside",
    bestPull: "Best Pull",
  },
  chartStats: {
    typicalPack: "Typical Pack Value",
    badPackFloor: "Bad Pack Floor Value",
    chanceToBeatPackCost: "Chance to Beat Pack Cost",
    chanceAtBigPull: "Chance at a Big Pull",
    bigHitUpside: "Big Hit Upside",
    godPullUpside: "God Pull Upside",
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

function normalizeSetDetailTab(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const alias = SET_DETAIL_TAB_ALIASES[normalized] || normalized;
  return SET_DETAIL_TABS.has(alias) ? alias : SET_DETAIL_DEFAULT_TAB;
}

function isValidSetDetailTab(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const alias = SET_DETAIL_TAB_ALIASES[normalized] || normalized;
  return SET_DETAIL_TABS.has(alias);
}

function getSetDetailTabParam(searchParams) {
  return normalizeSetDetailTab(searchParams?.get?.("tab"));
}

function getSetDetailSectionParam(searchParams) {
  return String(searchParams?.get?.("section") || "").trim().toLowerCase();
}

function getSetDetailFallbackTargetId(tab) {
  if (tab === "overview") return "set-detail-overview";
  if (tab === "cards") return "set-detail-cards";
  if (tab === "pull-rates") return "set-detail-pull-rates";
  return "set-detail-insights";
}

function updateSetDetailQueryParams({ pathname, searchParams, tab, section }) {
  const nextParams = new URLSearchParams(searchParams?.toString() || "");
  const nextTab = normalizeSetDetailTab(tab);
  nextParams.set("tab", nextTab);

  if (section) {
    nextParams.set("section", section);
  } else {
    nextParams.delete("section");
  }

  const query = nextParams.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function appendSetDetailIntentToHref(href, { tab, section } = {}) {
  if (!href) return href;
  const nextTab = normalizeSetDetailTab(tab);
  const [baseWithQuery, hash = ""] = String(href).split("#");
  const [base, query = ""] = baseWithQuery.split("?");
  const params = new URLSearchParams(query);
  params.set("tab", nextTab);
  if (section) {
    params.set("section", section);
  } else {
    params.delete("section");
  }
  const nextQuery = params.toString();
  return `${base}${nextQuery ? `?${nextQuery}` : ""}${hash ? `#${hash}` : ""}`;
}

const SIMPLE_PILLAR_INFO_COPY = {
  Profit:
    "Profit explains the upside side of the set. A strong profit profile does not mean every pack feels good - it means the set has enough high-end outcomes to make the upside meaningful when the right cards show up.",
  Safety:
    "Safety explains how painful the misses can feel. A set can have a strong overall score but still feel risky if the lower-end packs give back very little value.",
  Desirability:
    "Desirability is the RIP Score pillar based on the Opening Desirability model. The headline score is adjusted for set-to-set ranking, while Collector Appeal and Chase Appeal show the main drivers behind it.",
  Stability:
    "Stability explains whether value is spread across the set or concentrated in only a few cards. Better stability means the set is less dependent on one or two major hits.",
};

const DESIRABILITY_FALLBACK_COPY = "Using a fallback Opening Desirability estimate until this set has enough data.";
const DESIRABILITY_NOT_CALCULATED_COPY = "Not calculated yet.";

const METRIC_TREND_DIRECTIONS = {
  ripScore: "higher",
  packScore: "higher",
  profitScore: "higher",
  safetyScore: "higher",
  desirabilityScore: "higher",
  stabilityScore: "higher",
  packCost: "neutral",
  setValue: "higher",
  simulatedSetValue: "higher",
  averagePackValue: "higher",
  meanValue: "higher",
  averageHitValue: "higher",
  chanceToBeatPackCost: "higher",
  probProfit: "higher",
  chanceToMissPackCost: "lower",
  chanceAtBigPull: "higher",
  probBigHit: "higher",
  averageReturnVsCost: "higher",
  meanValueToCostRatio: "higher",
  typicalReturnVsCost: "higher",
  medianValueToCostRatio: "higher",
  bigHitUpside: "higher",
  p95ValueToCostRatio: "higher",
  godPullUpside: "higher",
  p99ValueToCostRatio: "higher",
  chaseDepth: "higher",
  effectiveChaseCount: "higher",
  averageLoss: "lower",
  expectedLossPerPack: "lower",
  averageLossWhenYouMiss: "lower",
  expectedLossWhenLosing: "lower",
  typicalLossWhenYouMiss: "lower",
  medianLossWhenLosing: "lower",
  p05ShortfallToCost: "lower",
  outcomeVolatility: "lower",
  coefficientOfVariation: "lower",
  evConcentration: "lower",
  hhiEvConcentration: "lower",
  top1Share: "neutral",
  top3Share: "neutral",
  top5Share: "neutral",
};

const HISTORY_METRIC_ALIASES = {
  ripScore: ["relative_pack_score", "relativePackScore", "pack_score", "packScore"],
  profitScore: ["relative_profit_score", "relativeProfitScore", "profit_score", "profitScore"],
  safetyScore: ["relative_safety_score", "relativeSafetyScore", "safety_score", "safetyScore"],
  desirabilityScore: ["relative_desirability_score", "relativeDesirabilityScore", "desirability_score", "desirabilityScore"],
  stabilityScore: ["relative_stability_score", "relativeStabilityScore", "stability_score", "stabilityScore"],
  setValue: ["simulated_set_value", "simulatedSetValue", "set_value", "setValue"],
  averageHitValue: ["average_hit_value", "averageHitValue"],
  probProfit: ["prob_profit", "probProfit", "chance_to_beat_pack_cost", "chanceToBeatPackCost"],
  probBigHit: ["prob_big_hit", "probBigHit", "chance_at_big_pull", "chanceAtBigPull"],
  p99ValueToCostRatio: ["p99_value_to_cost_ratio", "p99ValueToCostRatio", "god_pull_upside", "godPullUpside"],
  expectedLossWhenLosing: ["expected_loss_when_losing", "expectedLossWhenLosing"],
  medianLossWhenLosing: ["median_loss_when_losing", "medianLossWhenLosing"],
  tailValueP05: ["tail_value_p05", "tailValueP05", "p05_value", "p05Value", "bad_pack_floor_value", "badPackFloorValue"],
  p05ShortfallToCost: ["p05_shortfall_to_cost", "p05ShortfallToCost", "worst_5_percent_shortfall", "worst5PercentShortfall"],
  coefficientOfVariation: ["coefficient_of_variation", "coefficientOfVariation"],
  hhiEvConcentration: ["hhi_ev_concentration", "hhiEvConcentration", "ev_concentration", "evConcentration"],
  effectiveChaseCount: ["effective_chase_count", "effectiveChaseCount", "chase_depth", "chaseDepth"],
  top1Share: ["top1_ev_share", "top1EvShare", "top_chase_share", "topChaseShare"],
  top3Share: ["top3_ev_share", "top3EvShare"],
  top5Share: ["top5_ev_share", "top5EvShare"],
  maxValue: ["max_value", "maxValue", "best_pull", "bestPull"],
};

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getFirstNumericValue(source, keys = []) {
  for (const key of keys) {
    const value = toNumber(source?.[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
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

function isTruthyFlag(value) {
  return value === true || String(value).toLowerCase() === "true";
}

function getDesirabilitySummary(summary) {
  if (summary?.rip_desirability_source === "collector_appeal_fallback") {
    return "Opening Desirability needs chase data for this set, so RIP Score is temporarily using Collector Appeal.";
  }
  if (isTruthyFlag(summary?.desirability_is_fallback)) {
    return DESIRABILITY_FALLBACK_COPY;
  }
  if (toNumber(summary?.relative_desirability_score) === null && toNumber(summary?.desirability_score) === null) {
    return DESIRABILITY_NOT_CALCULATED_COPY;
  }
  return SIMPLE_PILLAR_INFO_COPY.Desirability;
}

function formatNumber(value, decimals = 2) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return parsed.toFixed(decimals);
}

function formatMultiplier(value, decimals = 1) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "—";
  }
  return `${parsed.toFixed(decimals)}x`;
}

function getMarketReadSummary({ packCost, averagePackValue, returnRatio, setValue, topShare, chaseDepth }) {
  const hasPriceValue = packCost !== null && averagePackValue !== null;
  const pricePosition = hasPriceValue
    ? packCost > averagePackValue
      ? "above"
      : packCost < averagePackValue
      ? "below"
      : "right in line with"
    : null;

  let setType = "a weak rip";
  if (returnRatio !== null && returnRatio >= 0.95) {
    setType = "a value set";
  } else if (
    (returnRatio !== null && returnRatio >= 0.65) ||
    (topShare !== null && topShare >= 35) ||
    (chaseDepth !== null && chaseDepth <= 4)
  ) {
    setType = "a chase set";
  }

  const concentration =
    topShare !== null && topShare >= 35
      ? "Value looks concentrated in the top cards"
      : chaseDepth !== null && chaseDepth >= 8
      ? "Value appears more spread across the checklist"
      : "Value concentration is still mixed from the available data";

  if (hasPriceValue) {
    return `The current pack price is ${pricePosition} modeled average pack value, so this reads like ${setType} at today's inputs. ${concentration}. The price/value relationship points to ${returnRatio !== null && returnRatio >= 1 ? "average openings that can meet or clear cost before fees" : "openings that still need strong pulls to overcome pack cost"}.`;
  }

  if (setValue !== null) {
    return `Market context is partially available for this set, with modeled set value at ${formatCurrency(setValue)}. ${concentration}, so the read is more useful for understanding where value sits than for judging pack price today.`;
  }

  return "Market context is limited for this set, so this read is based only on the modeled values currently available.";
}

function getCompactMarketRead({ packCost, averagePackValue, returnRatio, setValue, topShare, chaseDepth }) {
  const hasPriceValue = packCost !== null && averagePackValue !== null;
  if (hasPriceValue) {
    const ratioText = returnRatio === null ? "an unavailable return ratio" : `${returnRatio.toFixed(2)}x return vs cost`;
    const concentration =
      topShare !== null && topShare >= 35
        ? "value is concentrated in the top chase cards"
        : chaseDepth !== null && chaseDepth >= 8
        ? "value is spread across a deeper checklist"
        : "value concentration is mixed";
    return `Average pack value is ${formatCurrency(averagePackValue)} against a ${formatCurrency(packCost)} pack price, with ${ratioText} and ${concentration}.`;
  }

  if (setValue !== null) {
    return `Modeled set value is ${formatCurrency(setValue)}, with pack price context still limited for this set.`;
  }

  return "Market context is limited, so this view is based on currently available modeled set data.";
}

function getSimulationContextSubtitle(simulationCount) {
  const count = toNumber(simulationCount);
  if (count !== null && count > 0) {
    return `Modeled from ${count.toLocaleString("en-US")} simulated packs using current pack price, card values, pull rates, and pack path assumptions.`;
  }
  return "Modeled from simulated pack openings using current pack price, card values, pull rates, and pack path assumptions.";
}

function getCardInitials(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "?";
  }
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return `${words[0][0] || ""}${words[1][0] || ""}`.toUpperCase();
}

function getCardMarketDelta(card) {
  // TODO: sealed products, boxes, cases, and portfolio assets need this same snapshot/delta system later.
  const amount = (
    toNumber(card?.marketDelta) ??
    toNumber(card?.market_delta) ??
    toNumber(card?.priceDelta) ??
    toNumber(card?.price_delta) ??
    toNumber(card?.deltaAmount) ??
    toNumber(card?.delta_amount)
  );
  const percent = (
    toNumber(card?.marketDeltaPercent) ??
    toNumber(card?.market_delta_percent) ??
    toNumber(card?.priceDeltaPercent) ??
    toNumber(card?.price_delta_percent) ??
    toNumber(card?.deltaPercent) ??
    toNumber(card?.delta_percent) ??
    getTopCardDeltaEntries(card)[0]?.value ??
    null
  );

  if (amount === null && percent === null) {
    return null;
  }

  return { amount, percent };
}

function ChecklistCardTile({ card }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || null;
  const name = card?.name || "Unknown card";
  const number = card?.printedNumber || card?.cardNumber || null;
  const rarity = card?.rarity || null;
  const subtypeLabel = Array.isArray(card?.subtypes) && card.subtypes.length > 0 ? card.subtypes.join(" / ") : null;
  const marketPrice = getCardMarketPrice(card);
  // TODO: checklist-card deltas should use the shared market snapshot/delta system once wired into this payload.
  const marketDelta = getCardMarketDelta(card);
  const deltaTone = marketDelta?.amount ?? marketDelta?.percent ?? null;

  return (
    <article className="group overflow-hidden rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.72)] shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_22px_rgba(2,6,23,0.18)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(94,234,212,0.22)] hover:bg-[rgba(15,23,42,0.86)] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_14px_28px_rgba(2,6,23,0.26)]">
      <div className="relative aspect-[3/4] w-full border-b border-[rgba(255,255,255,0.07)] bg-[rgba(2,6,23,0.46)] p-1">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={name}
            className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.01]"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 px-3 text-center text-[var(--text-secondary)]">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-primary)]">
              {getCardInitials(name)}
            </span>
            <p className="line-clamp-2 text-xs">{name}</p>
          </div>
        )}
      </div>
      <div className="space-y-1 px-2.5 py-2.5">
        <p className="line-clamp-2 text-[13px] font-semibold leading-snug text-[var(--text-primary)]">{name}</p>
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0">
            {number ? <p className="truncate text-[11px] text-[var(--text-secondary)]">No. {number}</p> : null}
            {rarity ? <p className="truncate text-[11px] text-[var(--text-secondary)]">{rarity}</p> : null}
            {subtypeLabel ? <p className="line-clamp-1 text-[11px] text-[var(--text-secondary)]">{subtypeLabel}</p> : null}
          </div>
          {marketPrice !== null ? (
            <div className="shrink-0 text-right">
              <p className="text-xs font-semibold text-[var(--text-primary)]">{formatCurrency(marketPrice)}</p>
              {marketDelta ? (
                <div className="mt-1 inline-flex flex-col rounded-md border px-1.5 py-1 text-[10px] font-semibold leading-tight" style={getDeltaBadgeStyle(deltaTone)}>
                  {marketDelta.amount !== null ? <p>{formatSignedCurrency(marketDelta.amount)}</p> : null}
                  {marketDelta.percent !== null ? <p>{marketDelta.percent > 0 ? "+" : ""}{marketDelta.percent.toFixed(1)}%</p> : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function getChecklistCardMarketPrice(card) {
  return getCardMarketPrice(card);
}

function getCardMarketPrice(card) {
  const price = (
    toNumber(card?.marketPrice) ??
    toNumber(card?.market_price) ??
    toNumber(card?.price) ??
    toNumber(card?.estimatedMarketPrice) ??
    toNumber(card?.estimated_market_price) ??
    toNumber(card?.current_near_mint_price) ??
    toNumber(card?.currentNearMintPrice) ??
    toNumber(card?.price_used) ??
    toNumber(card?.priceUsed) ??
    toNumber(card?.card_price) ??
    toNumber(card?.cardPrice) ??
    toNumber(card?.card_market_price) ??
    toNumber(card?.cardMarketPrice) ??
    toNumber(card?.tcgplayer?.prices?.holofoil?.market) ??
    toNumber(card?.tcgplayer?.prices?.reverseHolofoil?.market) ??
    toNumber(card?.tcgplayer?.prices?.normal?.market) ??
    toNumber(card?.cardmarket?.prices?.averageSellPrice)
  );

  return price !== null && price > 0 ? price : null;
}

function normalizeTopPricedCard(card, source) {
  if (!card || typeof card !== "object") {
    return null;
  }

  const marketPrice = getCardMarketPrice(card);
  if (marketPrice === null) {
    return null;
  }

  const setNumber =
    card?.setNumber ??
    card?.set_number ??
    card?.cardNumber ??
    card?.card_number ??
    card?.printedNumber ??
    card?.printed_number ??
    card?.number ??
    null;

  return {
    id: card?.id ?? card?.cardId ?? card?.card_id ?? card?.pokemonTcgApiCardId ?? card?.pokemon_tcg_api_card_id ?? null,
    cardId: card?.cardId ?? card?.card_id ?? card?.id ?? null,
    cardVariantId: card?.cardVariantId ?? card?.card_variant_id ?? null,
    name: card?.name ?? card?.cardName ?? card?.card_name ?? "Unknown card",
    imageUrl: card?.imageUrl ?? card?.image_url ?? card?.imageSmallUrl ?? card?.image_small_url ?? card?.imageLargeUrl ?? card?.image_large_url ?? null,
    imageSmallUrl: card?.imageSmallUrl ?? card?.image_small_url ?? null,
    imageLargeUrl: card?.imageLargeUrl ?? card?.image_large_url ?? null,
    rarity: card?.rarity ?? null,
    setNumber,
    cardNumber: card?.cardNumber ?? card?.card_number ?? setNumber,
    marketPrice,
    estimatedMarketPrice: toNumber(card?.estimatedMarketPrice ?? card?.estimated_market_price),
    priceUsed: toNumber(card?.priceUsed ?? card?.price_used),
    priceHistory: Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [],
    price_history: Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [],
    historyPointCount: toNumber(card?.historyPointCount ?? card?.history_point_count),
    historyStartDate: card?.historyStartDate ?? card?.history_start_date ?? null,
    historyEndDate: card?.historyEndDate ?? card?.history_end_date ?? null,
    conditionIdUsed: card?.conditionIdUsed ?? card?.condition_id_used ?? null,
    matchingConditionObservationCount: toNumber(card?.matchingConditionObservationCount ?? card?.matching_condition_observation_count),
    historyDiagnostics:
      card?.historyDiagnostics && typeof card.historyDiagnostics === "object"
        ? card.historyDiagnostics
        : card?.history_diagnostics && typeof card.history_diagnostics === "object"
        ? card.history_diagnostics
        : null,
    deltas: card?.deltas && typeof card.deltas === "object" ? card.deltas : null,
    source,
  };
}

function getTopPricedCards({ topMarketCards, checklistCards } = {}) {
  const topMarketPricedCards = (Array.isArray(topMarketCards) ? topMarketCards : [])
    .map((card) => normalizeTopPricedCard(card, "topMarketCards"))
    .filter(Boolean)
    .sort((a, b) => b.marketPrice - a.marketPrice);

  if (topMarketPricedCards.length > 0) {
    return {
      cards: topMarketPricedCards.slice(0, 10),
      source: "topMarketCards",
      hasFullChecklistPricing: false,
    };
  }

  const checklistSource = Array.isArray(checklistCards) ? checklistCards : [];
  const checklistPricedCards = checklistSource
    .map((card) => normalizeTopPricedCard(card, "checklist"))
    .filter(Boolean)
    .sort((a, b) => b.marketPrice - a.marketPrice);
  const hasFullChecklistPricing = checklistSource.length > 0 && checklistPricedCards.length > 0;

  if (hasFullChecklistPricing) {
    return {
      cards: checklistPricedCards.slice(0, 10),
      source: "checklist",
      hasFullChecklistPricing,
    };
  }

  return {
    cards: [],
    source: "none",
    hasFullChecklistPricing: false,
  };
}

function formatShortDate(value) {
  if (!value) {
    return null;
  }
  return formatHistoryDate(value, { month: "short", day: "numeric" }) || String(value).slice(0, 10);
}

function formatCompactDay(value) {
  if (!value) {
    return "";
  }
  const dateKey = getHistoryDateKey(value);
  if (dateKey) {
    return String(Number(dateKey.slice(8, 10)));
  }
  return String(value).slice(8, 10) || String(value).slice(0, 10);
}

function formatLongDate(value) {
  if (!value) {
    return "Date unavailable";
  }
  return formatHistoryDate(value, { year: "numeric", month: "short", day: "numeric" }) || String(value);
}

function getPriceDeltaPercent(currentValue, previousValue) {
  const current = toNumber(currentValue);
  const previous = toNumber(previousValue);
  if (current === null || previous === null || previous === 0) {
    return null;
  }
  return ((current - previous) / previous) * 100;
}

function getPriceDeltaAmount(currentValue, previousValue) {
  const current = toNumber(currentValue);
  const previous = toNumber(previousValue);
  if (current === null || previous === null) {
    return null;
  }
  return current - previous;
}

function getPositiveValueStyle() {
  return {
    color: POSITIVE_VALUE_COLOR,
  };
}

function getNegativeValueStyle() {
  return getDangerValueStyle();
}

function getDeltaTextStyle(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return undefined;
  }
  return parsed < 0 ? getNegativeValueStyle() : parsed > 0 ? getPositiveValueStyle() : undefined;
}

function getDeltaBadgeStyle(value) {
  const parsed = toNumber(value);
  if (parsed === null || Math.abs(parsed) < 0.000001) {
    return {
      borderColor: "var(--border-subtle)",
      backgroundColor: "rgba(255,255,255,0.035)",
      color: "var(--text-secondary)",
      boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.025)",
    };
  }

  const color = parsed < 0 ? NEGATIVE_VALUE_COLOR : POSITIVE_VALUE_COLOR;
  return {
    borderColor: withAlpha(color, 0.26),
    backgroundColor: withAlpha(color, 0.075),
    color,
    boxShadow: `inset 0 0 0 1px ${withAlpha(color, 0.035)}`,
  };
}

function MarketWindowSelector({ windows, value, onChange, className = "" }) {
  const windowOptions = Array.isArray(windows) ? windows.filter(Boolean) : [];
  if (windowOptions.length <= 1) {
    return null;
  }

  return (
    <div className={["flex min-w-0 flex-wrap gap-1.5", className].filter(Boolean).join(" ")}>
      {windowOptions.map((entry) => {
        const isActive = entry.key === value;
        return (
          <button
            key={`market-window:${entry.key}`}
            type="button"
            onClick={() => onChange(entry.key)}
            aria-pressed={isActive}
            className={[
              "rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition-colors",
              isActive
                ? ""
                : "border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            ].join(" ")}
            style={
              isActive
                ? {
                    borderColor: withAlpha(POSITIVE_VALUE_COLOR, 0.34),
                    backgroundColor: withAlpha(POSITIVE_VALUE_COLOR, 0.1),
                    color: POSITIVE_VALUE_COLOR,
                  }
                : undefined
            }
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

function SetValueScopeSelector({ scopes, value, onChange }) {
  const scopeOptions = Array.isArray(scopes) && scopes.length > 0 ? scopes : SET_VALUE_SCOPE_OPTIONS;

  return (
    <SegmentedControl
      className="flex justify-center"
      options={scopeOptions.map((entry) => ({ value: entry.key, label: entry.label }))}
      value={value}
      onChange={onChange}
      ariaLabel="Set value scope"
    />
  );
}

function formatAxisCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) return "N/A";
  const abs = Math.abs(parsed);
  if (abs >= 1000000) return `$${(parsed / 1000000).toFixed(1)}M`;
  if (abs >= 1000) return `$${(parsed / 1000).toFixed(abs >= 10000 ? 0 : 1)}K`;
  return formatCurrency(parsed);
}

function buildCurrencyTicks(points) {
  const values = points.map((point) => toNumber(point?.setValue ?? point?.value)).filter((value) => value !== null);
  if (values.length === 0) {
    return [];
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const rawRange = maxValue - minValue;
  const padding = rawRange > 0 ? rawRange * 0.16 : Math.max(Math.abs(maxValue) * 0.08, 1);
  const lower = Math.max(0, minValue - padding);
  const upper = maxValue + padding;
  const range = upper - lower || Math.max(upper, 1);
  const stepBase = Math.pow(10, Math.floor(Math.log10(range / 3 || 1)));
  const roughStep = range / 3;
  const stepMultiplier = roughStep / stepBase <= 2 ? 2 : roughStep / stepBase <= 5 ? 5 : 10;
  const step = stepBase * stepMultiplier;
  const start = Math.floor(lower / step) * step;
  const end = Math.ceil(upper / step) * step;
  const ticks = [];

  for (let value = start; value <= end + step * 0.5; value += step) {
    const rounded = Number(value.toFixed(2));
    if (rounded >= 0 && !ticks.includes(rounded)) {
      ticks.push(rounded);
    }
  }

  if (ticks.length >= 2) {
    return ticks;
  }

  return [Math.max(0, minValue - padding), maxValue + padding].filter(
    (value, index, list) => list.findIndex((candidate) => Math.abs(candidate - value) < 0.01) === index
  );
}

function SetValueTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  const deltaAmount = toNumber(row.deltaFromPrevious);
  const deltaPercent = toNumber(row.deltaPercentFromPrevious);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 px-3 py-2 shadow-[0_16px_40px_rgba(0,0,0,0.35)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Date</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{formatLongDate(row.date)}</p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        Set Value <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(row.setValue)}</span>
      </p>
      {row.isCarriedForward ? (
        <p className="text-xs text-[var(--text-secondary)]">
          Carried forward{row.sourceDate ? <span> from {formatLongDate(row.sourceDate)}</span> : null}
        </p>
      ) : null}
      {deltaAmount !== null ? (
        <p className="text-xs text-[var(--text-secondary)]">
          Change <span className="font-semibold" style={getDeltaTextStyle(deltaAmount)}>{formatSignedCurrency(deltaAmount)}</span>
          {deltaPercent !== null ? <span style={getDeltaTextStyle(deltaAmount)}> ({deltaPercent > 0 ? "+" : ""}{deltaPercent.toFixed(1)}%)</span> : null}
        </p>
      ) : null}
    </div>
  );
}

function CompactSparkline({ points, valueKey = "value", trendDirection = "neutral", className = "" }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const chartPoints = Array.isArray(points)
    ? points.map((point, index) => ({
        index,
        date: point?.date ?? null,
        y: toNumber(point?.[valueKey] ?? point?.value),
        isCarriedForward: Boolean(point?.isCarriedForward),
        sourceDate: point?.sourceDate ?? null,
      }))
    : [];
  const numericPoints = chartPoints.filter((point) => point.y !== null);
  const strokeColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : "rgba(148,163,184,0.8)";
  const activePoint = activeIndex === null ? null : numericPoints[activeIndex] || null;
  const firstPoint = numericPoints[0] || null;
  const activeDeltaAmount = activePoint && firstPoint ? getPriceDeltaAmount(activePoint.y, firstPoint.y) : null;
  const activeDeltaPercent = activePoint && firstPoint ? getPriceDeltaPercent(activePoint.y, firstPoint.y) : null;

  const handlePointerMove = (event) => {
    if (numericPoints.length === 0) {
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (event.clientX - bounds.left) / bounds.width : 0;
    const targetIndex = Math.round(Math.max(0, Math.min(1, ratio)) * Math.max(chartPoints.length - 1, 1));
    let nearestIndex = 0;
    let nearestDistance = Infinity;
    numericPoints.forEach((point, index) => {
      const distance = Math.abs(point.index - targetIndex);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    setActiveIndex(nearestIndex);
  };

  if (numericPoints.length < 2) {
    return (
      <div className={["flex h-16 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-xs text-[var(--text-secondary)]", className].filter(Boolean).join(" ")}>
        Awaiting trend
      </div>
    );
  }

  const minY = Math.min(...numericPoints.map((point) => point.y));
  const maxY = Math.max(...numericPoints.map((point) => point.y));
  const yRange = maxY - minY || 1;
  const xRange = chartPoints.length - 1 || numericPoints.length - 1 || 1;
  const polylinePoints = numericPoints
    .map((point) => {
      const x = (point.index / xRange) * 100;
      const y = 38 - ((point.y - minY) / yRange) * 30;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const activeX = activePoint ? (activePoint.index / xRange) * 100 : null;
  const activeY = activePoint ? 38 - ((activePoint.y - minY) / yRange) * 30 : null;

  return (
    <div
      className={["group relative rounded-lg", className].filter(Boolean).join(" ")}
      onMouseMove={handlePointerMove}
      onMouseLeave={() => setActiveIndex(null)}
      onFocus={() => setActiveIndex(numericPoints.length - 1)}
      onBlur={() => setActiveIndex(null)}
      tabIndex={0}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 100 42"
        preserveAspectRatio="none"
        className="h-full w-full overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42"
      >
        <path d="M0 36H100" stroke="rgba(255,255,255,0.08)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <polyline points={polylinePoints} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {activePoint && activeX !== null && activeY !== null ? (
          <>
            <line x1={activeX} x2={activeX} y1="5" y2="38" stroke="rgba(255,255,255,0.16)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <circle cx={activeX} cy={activeY} r="3" fill={strokeColor} stroke="rgba(2,6,23,0.95)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </>
        ) : null}
      </svg>
      {activePoint ? (
        <div className="pointer-events-none absolute left-1/2 top-0 z-20 min-w-[9rem] -translate-x-1/2 -translate-y-[calc(100%+0.45rem)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{formatLongDate(activePoint.date)}</p>
          <p className="mt-1 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] tabular-nums">
            <span>{formatCurrency(activePoint.y)}</span>
            <DeltaTrendIcon value={activeDeltaAmount} size="md" />
          </p>
          {activeDeltaAmount !== null ? (
            <p className="mt-0.5 text-[11px] font-semibold tabular-nums" style={getDeltaTextStyle(activeDeltaAmount)}>
              {formatSignedCurrency(activeDeltaAmount)}
              {activeDeltaPercent !== null ? <span> ({activeDeltaPercent > 0 ? "+" : ""}{activeDeltaPercent.toFixed(1)}%)</span> : null}
            </p>
          ) : null}
          {activePoint.isCarriedForward && activePoint.sourceDate ? (
            <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Carried forward from {formatShortDate(activePoint.sourceDate)}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function normalizeSetValueHistoryPoints(points) {
  const dailyPointMap = new Map();
  (Array.isArray(points) ? points : []).forEach((point) => {
    const date = getHistoryDateKey(point?.date);
    const setValue = toNumber(point?.setValue ?? point?.value);
    if (!date) {
      return;
    }
    dailyPointMap.set(date, {
      ...point,
      date,
      setValue,
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      sourceDate: getHistoryDateKey(point?.sourceDate ?? point?.source_date),
    });
  });

  return forwardFillDailyHistoryThroughToday(
    Array.from(dailyPointMap.values()).sort((a, b) => a.date.localeCompare(b.date)),
    {
      dateField: "date",
      valueKeys: ["setValue"],
    }
  );
}

function SetValueLineChart({ points, trendDirection = "neutral" }) {
  let previousValuedPoint = null;
  const numericPoints = (Array.isArray(points) ? points : [])
    .map((point, index) => {
      const setValue = toNumber(point?.setValue ?? point?.value);
      const explicitDeltaAmount = toNumber(point?.deltaFromPrevious);
      const explicitDeltaPercent = toNumber(point?.deltaPercentFromPrevious);
      const fallbackDeltaAmount =
        setValue !== null && previousValuedPoint ? getPriceDeltaAmount(setValue, previousValuedPoint.setValue) : null;
      const fallbackDeltaPercent =
        setValue !== null && previousValuedPoint ? getPriceDeltaPercent(setValue, previousValuedPoint.setValue) : null;
      const nextPoint = {
        ...point,
        date: getHistoryDateKey(point?.date),
        setValue,
        index,
        deltaFromPrevious: explicitDeltaAmount ?? fallbackDeltaAmount,
        deltaPercentFromPrevious: explicitDeltaPercent ?? fallbackDeltaPercent,
      };

      if (setValue !== null) {
        previousValuedPoint = nextPoint;
      }

      return nextPoint;
    })
    .filter((point) => point.date);
  const valuedPoints = numericPoints.filter((point) => toNumber(point?.setValue) !== null);

  if (valuedPoints.length < 2) {
    return (
      <div className="flex min-h-[20rem] items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-sm text-[var(--text-secondary)]">
        Not enough set value history yet.
      </div>
    );
  }

  const values = valuedPoints.map((point) => point.setValue);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || Math.max(maxValue, 1) * 0.08 || 1;
  const yAxisTicks = buildCurrencyTicks(valuedPoints);
  const yMin = Math.max(0, Math.min(...yAxisTicks, minValue - range * 0.14));
  const yMax = Math.max(...yAxisTicks, maxValue + range * 0.14);
  const showEveryDayTick = numericPoints.length <= 8;
  const xAxisTicks = showEveryDayTick ? numericPoints.map((point) => point.date) : undefined;
  const trendColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : "rgba(148,163,184,0.9)";

  return (
    <div className="min-h-[21rem] w-full">
      <div className="h-[21rem] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={numericPoints} margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
            <XAxis
              dataKey="date"
              ticks={xAxisTicks}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={(value) => (showEveryDayTick ? formatCompactDay(value) : formatShortDate(value) || "")}
              minTickGap={showEveryDayTick ? 0 : 22}
              interval={showEveryDayTick ? 0 : "preserveStartEnd"}
            />
            <YAxis
              domain={[yMin, yMax]}
              ticks={yAxisTicks}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={formatAxisCurrency}
              width={58}
            />
            <RechartsTooltip content={<SetValueTooltip />} cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }} />
            <Line
              type="linear"
              dataKey="setValue"
              name="Set Value"
              stroke={trendColor}
              strokeWidth={2.5}
              dot={{ r: 2.5, fill: trendColor, strokeWidth: 0 }}
              activeDot={{ r: 4.5, stroke: "var(--surface-page)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function SetValueTrendCard({ history, historiesByScope, availableScopes, status, error }) {
  const [selectedWindowKey, setSelectedWindowKey] = useState(null);
  const [selectedScope, setSelectedScope] = useState("standard");
  const scopeOptions = useMemo(() => {
    const optionMap = new Map(SET_VALUE_SCOPE_OPTIONS.map((entry) => [entry.key, entry]));
    (Array.isArray(availableScopes) ? availableScopes : []).forEach((entry) => {
      if (entry?.key) {
        const defaultOption = SET_VALUE_SCOPE_OPTIONS.find((option) => option.key === entry.key);
        optionMap.set(entry.key, {
          key: entry.key,
          label: defaultOption?.label || entry.label || entry.key,
        });
      }
    });
    return SET_VALUE_SCOPE_OPTIONS.filter((entry) => optionMap.has(entry.key)).map((entry) => optionMap.get(entry.key));
  }, [availableScopes]);
  const selectedHistory = useMemo(() => {
    if (Array.isArray(historiesByScope?.[selectedScope])) {
      return historiesByScope[selectedScope];
    }
    return selectedScope === "standard" ? history : [];
  }, [historiesByScope, history, selectedScope]);
  const points = useMemo(() => normalizeSetValueHistoryPoints(selectedHistory), [selectedHistory]);
  const valuedPoints = useMemo(
    () => points.filter((point) => toNumber(point?.setValue) !== null),
    [points]
  );
  const {
    windows: availableDeltaWindows,
    effectiveKey: effectiveWindowKey,
    selectedWindow: selectedDeltaWindow,
  } = useMemo(
    () => getSelectedDeltaWindowFromHistory(valuedPoints, {
      selectedKey: selectedWindowKey,
      preferredKey: "30D",
      dateKey: "date",
      valueKey: "setValue",
    }),
    [selectedWindowKey, valuedPoints]
  );
  const visibleWindowMetrics = useMemo(
    () => getVisibleHistoryWindowMetrics(points, selectedDeltaWindow, {
      dateKey: "date",
      valueKey: "setValue",
    }),
    [points, selectedDeltaWindow]
  );
  const chartPoints = visibleWindowMetrics.points;
  const firstPoint = visibleWindowMetrics.firstPoint;
  const lastPoint = visibleWindowMetrics.latestPoint;
  const currentValue = visibleWindowMetrics.currentValue;
  const deltaAmount = visibleWindowMetrics.deltaAmount;
  const deltaPercent = visibleWindowMetrics.deltaPercent;
  const deltaWindowLabel = effectiveWindowKey ? getDeltaWindowLabel(effectiveWindowKey) : "Trend";
  const hasTrend = visibleWindowMetrics.valuedPoints.length >= 2;
  const trendDirection = deltaAmount === null ? "neutral" : deltaAmount < 0 ? "negative" : deltaAmount > 0 ? "positive" : "neutral";

  useEffect(() => {
    if (!effectiveWindowKey || selectedWindowKey === effectiveWindowKey) {
      return;
    }
    setSelectedWindowKey(effectiveWindowKey);
  }, [effectiveWindowKey, selectedWindowKey]);

  useEffect(() => {
    if (scopeOptions.some((entry) => entry.key === selectedScope)) {
      return;
    }
    setSelectedScope(scopeOptions[0]?.key || "standard");
  }, [scopeOptions, selectedScope]);

  return (
    <SectionCard
      title="Set Value Trend"
      titleInfoText="Daily set value history from Near Mint card market observations. Checklist sums tracked checklist cards, Hits excludes common low-rarity buckets, and Top 10 sums the highest-value tracked cards for each date."
      className="h-full"
    >
      {status === "loading" || status === "idle" ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading set value history...</p>
      ) : status === "error" ? (
        <p className="text-sm text-red-300">{error || "Unable to load set value history for this set."}</p>
      ) : !hasTrend ? (
        <div className="space-y-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Current Set Value</p>
            <p className="mt-1 text-2xl font-semibold leading-none text-[var(--text-primary)]">{currentValue === null ? "N/A" : formatCurrency(currentValue)}</p>
          </div>
          <p className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-3 py-3 text-sm text-[var(--text-secondary)]">
            Not enough set value history yet.
          </p>
          <div className="pt-1">
            <SetValueScopeSelector scopes={scopeOptions} value={selectedScope} onChange={setSelectedScope} />
          </div>
        </div>
      ) : (
        <div className="flex min-h-[26rem] flex-col space-y-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Current Set Value</p>
              <p className="mt-1 inline-flex min-w-0 items-center gap-1.5 text-2xl font-semibold leading-none text-[var(--text-primary)]">
                <span className="truncate">{currentValue === null ? "N/A" : formatCurrency(currentValue)}</span>
                <DeltaTrendIcon value={deltaAmount} size="md" />
              </p>
            </div>
            <div className="flex min-w-0 flex-wrap gap-2 sm:justify-end">
              <div className="rounded-lg border px-3 py-2 text-right" style={getDeltaBadgeStyle(deltaAmount)}>
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{deltaWindowLabel} Delta</p>
                <p className="mt-1 text-sm font-semibold">
                  {deltaAmount === null ? "N/A" : formatSignedCurrency(deltaAmount)}
                </p>
              </div>
              <div className="rounded-lg border px-3 py-2 text-right" style={getDeltaBadgeStyle(deltaPercent)}>
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  {deltaWindowLabel} %
                </p>
                <p className="mt-1 text-sm font-semibold">
                  {deltaPercent === null ? "N/A" : `${deltaPercent > 0 ? "+" : ""}${deltaPercent.toFixed(1)}%`}
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <MarketWindowSelector
              windows={availableDeltaWindows}
              value={effectiveWindowKey}
              onChange={setSelectedWindowKey}
            />
          </div>

          <SetValueLineChart points={chartPoints} trendDirection={trendDirection} />

          <div className="grid min-w-0 grid-cols-[minmax(max-content,1fr)_auto_minmax(max-content,1fr)] items-center gap-x-3 gap-y-2 pb-1 text-xs text-[var(--text-secondary)] max-[420px]:grid-cols-2">
            <span className="min-w-0 justify-self-start truncate">{formatShortDate(firstPoint?.date) || "Start"}</span>
            <div className="min-w-0 justify-self-center max-[420px]:order-3 max-[420px]:col-span-2">
              <SetValueScopeSelector scopes={scopeOptions} value={selectedScope} onChange={setSelectedScope} />
            </div>
            <span className="min-w-0 justify-self-end truncate text-right">{formatShortDate(lastPoint?.date) || "Latest"}</span>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function OverviewMetricTile({ label, value, trend = null, infoText = null }) {
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");

  return (
    <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3.5 py-3.5">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <p className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <p
        className="mt-2 inline-flex min-w-0 items-center gap-1.5 text-xl font-semibold leading-none text-[var(--text-primary)] md:text-2xl"
        style={isNegativeValue ? getDangerValueStyle() : undefined}
      >
        <span className="truncate">{value}</span>
        <TrendIndicator trend={trend} className="translate-y-px" />
      </p>
    </div>
  );
}

function OverviewReadPanel({ metrics, compactRead, detailRead }) {
  return (
    <article className="w-full max-w-full min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] sm:p-5">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Overview Context</h2>
          <InfoPopover text="Asset-style set context using existing set value, pack price, modeled average pack value, and return ratio." />
        </div>
      </div>

      {metrics.length > 0 ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <OverviewMetricTile key={`overview-context-${metric.label}`} {...metric} />
          ))}
        </div>
      ) : null}

      <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-3.5 py-3">
        <div className="flex items-start gap-2">
          <p className="flex-1 text-sm leading-relaxed text-[var(--text-primary)]">
            <span className="font-semibold">Quick Read:</span> {compactRead}
          </p>
          {detailRead ? <InfoPopover text={detailRead} /> : null}
        </div>
      </div>
    </article>
  );
}

function TopMarketCardRow({ card, index, selectedWindowKey }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl || null;
  const name = card?.name || "Unknown card";
  const rarity = card?.rarity || null;
  const price = getChecklistCardMarketPrice(card);
  const historyPoints = getTopCardPriceHistory(card);
  const topCardDeltaWindow = getTopCardDeltaWindow(card, historyPoints, selectedWindowKey);
  const sparklinePoints = filterHistoryPointsForDeltaWindow(historyPoints, topCardDeltaWindow, { dateKey: "date" });
  const valuedHistoryPoints = historyPoints.filter((point) => point.value !== null);
  const firstPrice = valuedHistoryPoints[0]?.value ?? null;
  const lastPrice = valuedHistoryPoints[valuedHistoryPoints.length - 1]?.value ?? null;
  const historyDeltaAmount = getPriceDeltaAmount(lastPrice, firstPrice);
  const displayDeltaAmount = topCardDeltaWindow?.amount ?? (selectedWindowKey ? null : historyDeltaAmount);
  const displayDelta = topCardDeltaWindow?.percent ?? (selectedWindowKey ? null : getPriceDeltaPercent(lastPrice, firstPrice));
  const sparklineTone =
    displayDeltaAmount === null
      ? displayDelta === null
        ? "neutral"
        : displayDelta < 0
        ? "negative"
        : displayDelta > 0
        ? "positive"
        : "neutral"
      : displayDeltaAmount < 0
      ? "negative"
      : displayDeltaAmount > 0
      ? "positive"
      : "neutral";

  return (
    <div className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 px-3 py-2.5 lg:grid-cols-[3.5rem_minmax(13.75rem,1fr)_minmax(11.25rem,14.5rem)_6.875rem_6rem] lg:items-center lg:gap-3.5 lg:px-4 lg:py-3">
      <span className="self-start pt-1 text-xs font-semibold text-[var(--text-secondary)] lg:self-auto lg:pt-0">#{index + 1}</span>
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-[4.875rem] w-14 flex-none items-center justify-center overflow-hidden rounded-md border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.48)] shadow-[0_10px_24px_rgba(2,6,23,0.24)]">
          {imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt={name}
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <span className="px-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
              {getCardInitials(name)}
            </span>
          )}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{name}</p>
          <p className="mt-0.5 truncate text-xs text-[var(--text-secondary)]">{rarity || "N/A"}</p>
        </div>
      </div>
      <div className="col-span-2 flex min-w-0 flex-col items-center lg:col-span-1">
        <CompactSparkline points={sparklinePoints} trendDirection={sparklineTone} className="h-14 w-full max-w-[12.25rem] lg:max-w-[13.75rem]" />
        {sparklinePoints.length >= 2 ? (
          <div className="mt-1 flex w-full max-w-[12.25rem] min-w-0 items-center justify-between gap-2 text-[9px] text-[var(--text-secondary)] lg:max-w-[13.75rem] lg:text-[10px]">
            <span className="truncate">{formatShortDate(sparklinePoints[0]?.date)}</span>
            <span className="truncate text-right">{formatShortDate(sparklinePoints[sparklinePoints.length - 1]?.date)}</span>
          </div>
        ) : null}
      </div>
      <div className="col-span-2 flex min-w-0 items-end justify-between gap-3 lg:contents">
        <p className="min-w-0 flex-1 text-left text-sm font-semibold text-[var(--text-primary)] lg:justify-self-stretch">
          <span className="inline-grid min-w-0 grid-cols-[minmax(0,max-content)_0.75rem] items-center gap-1.5 tabular-nums lg:w-full lg:grid-cols-[minmax(0,1fr)_0.75rem]">
            <span className="min-w-0 text-right">{price === null ? "N/A" : formatCurrency(price)}</span>
            <span className="inline-flex w-3 justify-center">
              {price !== null ? <DeltaTrendIcon value={displayDeltaAmount ?? displayDelta} size="sm" /> : null}
            </span>
          </span>
        </p>
        {displayDeltaAmount !== null || displayDelta !== null ? (
          <div className="inline-flex min-w-[4.7rem] flex-none flex-col items-end gap-px justify-self-end rounded-md border px-1.5 py-1 text-right text-xs font-semibold leading-[1.12] tabular-nums" style={getDeltaBadgeStyle(displayDeltaAmount ?? displayDelta)}>
            {displayDeltaAmount !== null ? <p>{formatSignedCurrency(displayDeltaAmount)}</p> : null}
            {displayDelta !== null ? <p>{displayDelta > 0 ? "+" : ""}{displayDelta.toFixed(1)}%</p> : null}
          </div>
        ) : (
          <p className="flex-none text-right text-[11px] text-[var(--text-secondary)]">Awaiting trend</p>
        )}
      </div>
    </div>
  );
}

function TopMarketCardsContent({ cards, status, error, maxRows = 10 }) {
  const [selectedWindowKey, setSelectedWindowKey] = useState(null);
  const availableDeltaWindows = useMemo(
    () => getTopCardsAvailableDeltaWindows(cards),
    [cards]
  );
  const effectiveWindowKey =
    selectedWindowKey && availableDeltaWindows.some((entry) => entry.key === selectedWindowKey)
      ? selectedWindowKey
      : getPreferredDeltaWindowKey(availableDeltaWindows, "30D");

  useEffect(() => {
    if (!effectiveWindowKey || selectedWindowKey === effectiveWindowKey) {
      return;
    }
    setSelectedWindowKey(effectiveWindowKey);
  }, [effectiveWindowKey, selectedWindowKey]);

  if (status === "loading" || status === "idle") {
    return <p className="text-sm text-[var(--text-secondary)]">Loading market cards...</p>;
  }

  if (status === "error") {
    return <p className="text-sm text-red-300">{error || "Unable to load market cards for this set."}</p>;
  }

  if (cards.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No priced cards are available yet for this set.</p>;
  }

  return (
    <div className="space-y-3">
      <MarketWindowSelector
        windows={availableDeltaWindows}
        value={effectiveWindowKey}
        onChange={setSelectedWindowKey}
      />
      <div className="overflow-visible rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/42">
        <div className="hidden grid-cols-[3.5rem_minmax(13.75rem,1fr)_minmax(11.25rem,14.5rem)_6.875rem_6rem] items-center gap-3.5 border-b border-[var(--border-subtle)] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] lg:grid">
          <span>Rank</span>
          <span>Card</span>
          <span className="text-center">Trend</span>
          <span className="grid grid-cols-[minmax(0,1fr)_0.75rem] items-center gap-1.5">
            <span className="text-right">Price</span>
            <span aria-hidden="true"></span>
          </span>
          <span className="text-right">Change</span>
        </div>
        <div className="divide-y divide-[var(--border-subtle)]">
          {cards.slice(0, maxRows).map((card, index) => (
            <TopMarketCardRow
              key={`top-market-card:${card?.id || card?.cardNumber || card?.name || index}`}
              card={card}
              index={index}
              selectedWindowKey={effectiveWindowKey}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function getTopCardDeltaEntries(card) {
  const deltas = card?.deltas && typeof card.deltas === "object" ? card.deltas : {};
  return extractDeltaWindows({ deltas }).map((entry) => ({ label: entry.label, value: entry.percent, key: entry.key }));
}

function getTopCardDeltaWindow(card, historyPoints, selectedWindowKey) {
  const historyWindows = computeDeltaWindowsFromHistory(historyPoints, { dateKey: "date", valueKey: "value" });
  const selectedHistoryWindow = historyWindows.find((entry) => entry.key === selectedWindowKey);
  if (selectedHistoryWindow) {
    return selectedHistoryWindow;
  }

  const fieldWindows = extractDeltaWindows({ deltas: card?.deltas });
  const selectedFieldWindow = fieldWindows.find((entry) => entry.key === selectedWindowKey);
  if (selectedFieldWindow) {
    return selectedFieldWindow;
  }
  if (selectedWindowKey) {
    return null;
  }

  const preferredHistoryKey = getPreferredDeltaWindowKey(historyWindows, "30D");
  return preferredHistoryKey ? historyWindows.find((entry) => entry.key === preferredHistoryKey) || null : null;
}

function getTopCardsAvailableDeltaWindows(cards) {
  return Array.isArray(cards) && cards.length > 0 ? getStandardDeltaWindowDefinitions() : [];
}

function getTopCardPriceHistory(card) {
  const history = Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [];
  const points = history
    .map((point) => ({
      date: getHistoryDateKey(point?.date),
      value: toNumber(point?.marketPrice ?? point?.market_price ?? point?.price),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      sourceDate: getHistoryDateKey(point?.sourceDate ?? point?.source_date),
    }))
    .filter((point) => point.date);

  return forwardFillDailyHistoryThroughToday(points, {
    dateField: "date",
    valueKeys: ["value"],
  });
}

function TopChaseCardsModule({ cards, status, error, infoText }) {
  return (
    <SectionCard title="Top Chase Cards" titleInfoText={infoText}>
      <TopMarketCardsContent cards={cards} status={status} error={error} maxRows={10} />
    </SectionCard>
  );
}

function normalizePullRateAssumptions(explorePayload) {
  const source = explorePayload?.pull_rate_assumptions || explorePayload?.pullRateAssumptions || null;

  if (!source || typeof source !== "object") {
    return null;
  }

  const normalizeRow = (row) => {
    if (!row || typeof row !== "object") {
      return row;
    }

    return {
      ...row,
      cardCount: row.cardCount ?? row.card_count ?? row.eligibleCardCount ?? row.eligible_card_count ?? null,
      specificCardOddsDenominator:
        row.specificCardOddsDenominator ?? row.specific_card_odds_denominator ?? null,
      expectedCardsPerPack: row.expectedCardsPerPack ?? row.expected_cards_per_pack ?? null,
      rarityOddsDenominator: row.rarityOddsDenominator ?? row.rarity_odds_denominator ?? null,
    };
  };

  return {
    ...source,
    groups: Array.isArray(source.groups)
      ? source.groups.map((group) => ({
          ...group,
          rows: Array.isArray(group?.rows) ? group.rows.map(normalizeRow) : [],
        }))
      : source.groups,
    rows: Array.isArray(source.rows) ? source.rows.map(normalizeRow) : source.rows,
  };
}

function SectionViewTabs({ value, onChange, options, className = "", variant = "default" }) {
  const tabOptions = Array.isArray(options) ? options : [];
  if (tabOptions.length === 0) {
    return null;
  }

  if (variant === "primary") {
    return (
      <div className={className}>
        <div
          className="grid w-full items-center gap-0.5 rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.72)] p-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_20px_rgba(2,6,23,0.18)] backdrop-blur-md"
          style={{ gridTemplateColumns: `repeat(${tabOptions.length}, minmax(0, 1fr))` }}
        >
          {tabOptions.map((option) => {
            const isActive = value === option.value;

            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onChange(option.value)}
                aria-pressed={isActive}
                className={`min-w-0 rounded-md px-2 py-1 text-xs font-semibold leading-none transition-all duration-200 sm:px-3 sm:py-1.5 ${
                  isActive
                    ? "bg-[linear-gradient(135deg,rgba(16,185,129,0.95),rgba(20,184,166,0.78))] text-white shadow-[0_4px_12px_rgba(20,184,166,0.18),inset_0_1px_0_rgba(255,255,255,0.16)]"
                    : "bg-transparent text-[color:color-mix(in_srgb,var(--text-secondary)_82%,transparent)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="block truncate">{option.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  if (variant === "secondary") {
    return (
      <SegmentedControl
        className={className}
        options={tabOptions}
        value={value}
        onChange={onChange}
        ariaLabel="Section view"
      />
    );
  }

  return (
    <div className={className}>
      <div
        className="grid w-full items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5"
        style={{ gridTemplateColumns: `repeat(${tabOptions.length}, minmax(0, 1fr))` }}
      >
        {tabOptions.map((option) => {
          const isActive = value === option.value;

          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              aria-pressed={isActive}
              className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${
                isActive
                  ? "bg-[var(--brand)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="block truncate">{option.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
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

function getLossAmountFromMeanAndCost(meanValue, packCost) {
  const mean = toNumber(meanValue);
  const cost = toNumber(packCost);
  if (mean === null || cost === null) {
    return null;
  }
  return Math.max(cost - mean, 0);
}

function getHistoryMetricValue(point, metricKey) {
  if (!point) {
    return null;
  }

  const rawPoint = point.rawPoint || {};
  const directValue = toNumber(point[metricKey]);
  if (directValue !== null) {
    return directValue;
  }

  switch (metricKey) {
    case "packCost":
      return toNumber(point.packCost) ?? getFirstNumericValue(rawPoint, ["pack_cost", "packCost", "cost"]);
    case "meanValue":
      return toNumber(point.meanValue) ?? getFirstNumericValue(rawPoint, ["mean_value", "meanValue", "average_pack_value", "averagePackValue"]);
    case "medianValue":
      return toNumber(point.medianValue) ?? getFirstNumericValue(rawPoint, ["median_value", "medianValue", "typical_pack_value", "typicalPackValue"]);
    case "meanCostRatio":
      return toNumber(point.meanCostRatio) ?? getFirstNumericValue(rawPoint, ["mean_value_to_cost_ratio", "meanValueToCostRatio", "average_return_vs_cost", "averageReturnVsCost"]);
    case "medianCostRatio":
      return toNumber(point.medianCostRatio) ?? getFirstNumericValue(rawPoint, ["median_value_to_cost_ratio", "medianValueToCostRatio", "typical_return_vs_cost", "typicalReturnVsCost"]);
    case "p95CostRatio":
      return toNumber(point.p95CostRatio) ?? getFirstNumericValue(rawPoint, ["p95_value_to_cost_ratio", "p95ValueToCostRatio", "big_hit_upside", "bigHitUpside"]);
    default:
      return getFirstNumericValue(rawPoint, HISTORY_METRIC_ALIASES[metricKey] || []);
  }
}

function getMetricDirection(metricKey, fallbackDirection = "higher") {
  return METRIC_TREND_DIRECTIONS[metricKey] || fallbackDirection;
}

function getMetricTrend({ currentValue, previousValue, direction = "higher", metricKey = null } = {}) {
  const current = toNumber(currentValue);
  const previous = toNumber(previousValue);
  const resolvedDirection = metricKey ? getMetricDirection(metricKey, direction) : direction;

  if (current === null || previous === null) {
    return { trend: "unknown", isImprovement: null };
  }

  const delta = current - previous;
  if (Math.abs(delta) < 0.000001) {
    return { trend: "flat", isImprovement: null };
  }

  const trend = delta > 0 ? "up" : "down";
  if (resolvedDirection === "neutral") {
    return { trend, isImprovement: null };
  }

  const isImprovement = resolvedDirection === "lower" ? delta < 0 : delta > 0;
  return { trend, isImprovement };
}

function getHistoryMetricTrend({ metricKey, currentValue, previousPoint, previousValue = null, direction = "higher" }) {
  return getMetricTrend({
    currentValue,
    previousValue: previousValue ?? getHistoryMetricValue(previousPoint, metricKey),
    direction,
    metricKey,
  });
}

function TrendIndicator({ trend, className = "" }) {
  if (!trend || trend.trend === "unknown") {
    return null;
  }

  const isFlat = trend.trend === "flat";
  const iconClassName = isFlat ? "h-4 w-4" : "h-6 w-6";
  const wrapperClassName = isFlat ? "h-5 w-5" : "h-7 w-7";
  const displayTrend =
    trend.isImprovement === true
      ? "up"
      : trend.isImprovement === false
      ? "down"
      : "flat";
  const color =
    trend.isImprovement === true
      ? "var(--success,#10B981)"
      : trend.isImprovement === false
      ? "var(--danger,#EF4444)"
      : "var(--text-secondary)";
  const label =
    trend.isImprovement === true
      ? "Improved from previous snapshot"
      : trend.isImprovement === false
      ? "Worsened from previous snapshot"
      : isFlat
      ? "Unchanged from previous snapshot"
      : "Neutral trend from previous snapshot";

  return (
    <span
      className={["inline-flex flex-none items-center justify-center", wrapperClassName, className].filter(Boolean).join(" ")}
      style={{ color }}
      title={label}
      aria-label={label}
    >
      <svg viewBox="0 0 20 20" aria-hidden="true" className={iconClassName}>
        {displayTrend === "flat" ? (
          <path d="M4.5 10h11" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
        ) : displayTrend === "up" ? (
          <>
            <path d="M4.4 13.1 8.1 9.4l2.6 2.5 4.9-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12.1 6.9h3.5v3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : (
          <>
            <path d="M4.4 6.9 8.1 10.6l2.6-2.5 4.9 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12.1 13.1h3.5V9.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}
      </svg>
    </span>
  );
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

function MetricRow({ label, value, infoText, trend = null, content = null }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");

  if (content) {
    return (
      <div className="border-b border-[var(--border-subtle)] py-2 last:border-b-0 last:pb-0 first:pt-0">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="text-sm font-medium text-[var(--text-primary)]">{friendlyLabel}</span>
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
        <div className="mt-2">{content}</div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0 last:pb-0 first:pt-0">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="text-sm text-[var(--text-secondary)]">{friendlyLabel}</span>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <span className="inline-flex flex-none items-center gap-1.5 text-sm font-medium" style={isNegativeValue ? getDangerValueStyle() : undefined}>
        <TrendIndicator trend={trend} />
        <span>{value}</span>
      </span>
    </div>
  );
}

function formatDriverScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? null : parsed.toFixed(1);
}

function normalizeCollectorAppealDriverCard(card) {
  if (!card || typeof card !== "object") {
    return null;
  }

  const linkedPokemonSource = card.linkedPokemon || card.linked_pokemon || [];
  const linkedPokemon = Array.isArray(linkedPokemonSource)
    ? linkedPokemonSource
        .map((entry) => ({
          pokemonName: entry?.pokemonName || entry?.pokemon_name || entry?.name || null,
          pokemonReferenceId: toNumber(entry?.pokemonReferenceId ?? entry?.pokemon_reference_id),
        }))
        .filter((entry) => entry.pokemonName || entry.pokemonReferenceId !== null)
    : [];

  const nestedImageSources = [
    card,
    card.card,
    card.canonicalCard,
    card.canonical_card,
    card.variant,
    card.cardVariant,
    card.card_variant,
  ].filter(Boolean);
  const pickImageField = (...fields) => {
    for (const source of nestedImageSources) {
      for (const field of fields) {
        const value = source?.[field];
        if (typeof value === "string" && value.trim()) {
          return value.trim();
        }
      }
      const nestedSmall = source?.images?.small;
      const nestedLarge = source?.images?.large;
      if (fields.includes("imageSmallUrl") && typeof nestedSmall === "string" && nestedSmall.trim()) {
        return nestedSmall.trim();
      }
      if (fields.includes("imageLargeUrl") && typeof nestedLarge === "string" && nestedLarge.trim()) {
        return nestedLarge.trim();
      }
    }
    return null;
  };

  const imageSmallUrl = pickImageField("imageSmallUrl", "image_small_url", "smallImageUrl", "small_image_url");
  const imageLargeUrl = pickImageField("imageLargeUrl", "image_large_url", "largeImageUrl", "large_image_url");
  const imageUrl = pickImageField("imageUrl", "image_url", "cardImageUrl", "card_image_url", "image") || imageSmallUrl || imageLargeUrl;

  const normalized = {
    name: card.name || card.card_name || card.cardName || null,
    printedNumber:
      card.printedNumber ||
      card.printed_number ||
      card.card_number ||
      card.cardNumber ||
      card.number ||
      null,
    rarity: card.rarity || null,
    cardDesirabilityScore:
      toNumber(
        card.cardDesirabilityScore ??
          card.card_desirability_score ??
          card.desirability_score ??
          card.desirabilityScore
      ),
    linkedPokemon,
    imageUrl,
    imageSmallUrl,
    imageLargeUrl,
    marketPrice:
      toNumber(
        card.marketPrice ??
          card.market_price ??
          card.current_near_mint_price ??
          card.currentNearMintPrice
      ),
    favoriteScore: toNumber(card.favoriteScore ?? card.favorite_score ?? card.fanScore ?? card.fan_score),
    trendScore: toNumber(card.trendScore ?? card.trend_score),
    matchedPokemon: card.matchedPokemon || card.matched_pokemon || card.matchedSubject || card.matched_subject || null,
  };

  return normalized.name ? normalized : null;
}

function getTopCollectorAppealDrivers(explorePayload, summary, openingPayload) {
  const candidateLists = [
    openingPayload?.topCollectorAppealDrivers,
    explorePayload?.openingDesirability?.topCollectorAppealDrivers,
    openingPayload?.collectorAppealDrivers,
    explorePayload?.topCollectorAppealDrivers,
    explorePayload?.collectorAppealDrivers,
    summary?.top_collector_appeal_drivers,
    summary?.topCollectorAppealDrivers,
    summary?.top_desirability_cards,
    summary?.topDesirabilityCards,
    summary?.desirabilityDrivers,
  ];

  for (const list of candidateLists) {
    if (!Array.isArray(list) || list.length === 0) {
      continue;
    }
    const normalized = list.map(normalizeCollectorAppealDriverCard).filter(Boolean);
    if (normalized.length > 0) {
      return normalized;
    }
  }

  return [];
}

function formatScoreWithOptionalRank(score, rank, { unavailableLabel = "—" } = {}) {
  const parsedScore = toNumber(score);
  if (parsedScore === null) {
    return unavailableLabel;
  }

  const parsedRank = toNumber(rank);
  if (parsedRank === null) {
    return parsedScore.toFixed(1);
  }

  return `${parsedScore.toFixed(1)} · Rank #${Math.round(parsedRank)}`;
}

function isMissingChaseDataState(openingPayload) {
  const status = String(openingPayload?.displayStatus || "").toLowerCase();
  const dataQuality = String(openingPayload?.chaseAppealDataQuality || "").toLowerCase();

  return (
    status === "collector_only" ||
    status === "insufficient_chase_data" ||
    status === "missing_chase_data" ||
    status === "no_chase_data" ||
    dataQuality === "missing" ||
    dataQuality === "insufficient" ||
    dataQuality === "unavailable"
  );
}

function getDesirabilityOverviewMetrics(openingPayload) {
  const payload = openingPayload || {};
  const needsChaseData = isMissingChaseDataState(payload);

  const chaseValue =
    toNumber(payload?.chaseAppealScore) === null && needsChaseData
      ? "Needs chase data"
      : formatScoreWithOptionalRank(payload?.chaseAppealScore, payload?.chaseAppealRank);

  return [
    {
      label: "Collector Appeal",
      value: formatScoreWithOptionalRank(payload?.collectorAppealScore, payload?.collectorAppealRank),
      infoText:
        "Collector Appeal reflects pure collector demand for the Pokémon and card subjects in this set, independent of current market price.",
      trend: null,
    },
    {
      label: "Chase Appeal",
      value: chaseValue,
      infoText:
        "Chase Appeal reflects the strength, depth, and upside of the set's meaningful chase cards.",
      trend: null,
    },
  ];
}

function normalizeOpeningDesirabilityPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const topCollectorAppealDrivers = [
    payload.topCollectorAppealDrivers,
    payload.top_collector_appeal_drivers,
    payload.collectorAppealDrivers,
    payload.collector_appeal_drivers,
    payload.desirabilityDrivers,
    payload.desirability_drivers,
    payload.topDesirableCards,
    payload.top_desirable_cards,
  ].find((value) => Array.isArray(value));

  return {
    openingDesirabilityScore: toNumber(payload.openingDesirabilityScore ?? payload.opening_desirability_score),
    openingDesirabilityRank: toNumber(payload.openingDesirabilityRank ?? payload.opening_desirability_rank),
    collectorAppealScore: toNumber(payload.collectorAppealScore ?? payload.collector_appeal_score),
    collectorAppealRank: toNumber(payload.collectorAppealRank ?? payload.collector_appeal_rank),
    chaseAppealScore: toNumber(payload.chaseAppealScore ?? payload.chase_appeal_score),
    chaseAppealRank: toNumber(payload.chaseAppealRank ?? payload.chase_appeal_rank),
    chaseAppealDataQuality: payload.chaseAppealDataQuality ?? payload.chase_appeal_data_quality ?? "missing",
    displayStatus: payload.displayStatus ?? payload.display_status ?? "insufficient_chase_data",
    summary: payload.summary ?? "",
    tooltipCopy: payload.tooltipCopy ?? payload.tooltip_copy ?? {},
    builtAt: payload.builtAt ?? payload.built_at ?? null,
    topCollectorAppealDrivers: Array.isArray(topCollectorAppealDrivers)
      ? topCollectorAppealDrivers.map(normalizeCollectorAppealDriverCard).filter(Boolean)
      : [],
  };
}

function getCollectorDriverSubjects(card) {
  if (!card || !Array.isArray(card.linkedPokemon)) {
    return [];
  }

  const names = card.linkedPokemon
    .map((entry) => String(entry?.pokemonName || "").trim())
    .filter(Boolean);

  return [...new Set(names)];
}

function CollectorAppealDriverRow({ card, index }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl || null;
  const [hasImageError, setHasImageError] = useState(false);
  const name = card?.name || "Unknown card";
  const printedNumber = card?.printedNumber || null;
  const rarity = card?.rarity || null;
  const subjects = getCollectorDriverSubjects(card);
  const cardAppeal = formatDriverScore(card?.cardDesirabilityScore);
  const shouldRenderImage = Boolean(imageUrl) && !hasImageError;

  useEffect(() => {
    setHasImageError(false);
  }, [imageUrl]);

  return (
    <article className="rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.62)] p-3">
      <div className="flex items-start gap-3">
        <div className="flex h-14 w-10 flex-none items-center justify-center overflow-hidden rounded-md border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.48)]">
          {shouldRenderImage ? (
            <img
              src={imageUrl}
              alt={name}
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
              onError={() => setHasImageError(true)}
            />
          ) : (
            <span className="px-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
              {getCardInitials(name)}
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {index + 1}. {name}
          </p>
          <p className="text-xs text-[var(--text-secondary)]">
            {[rarity, printedNumber].filter(Boolean).join(" · ") || "Card details unavailable"}
          </p>
          <p className="text-xs text-[var(--text-secondary)]">Pokémon Appeal: {cardAppeal || "—"}</p>
          <p className="text-xs text-[var(--text-secondary)]">Subject: {subjects.length > 0 ? subjects.join(", ") : "—"}</p>
        </div>
      </div>
    </article>
  );
}

function TopDesirabilityDrivers({ drivers = [] }) {
  const cards = Array.isArray(drivers)
    ? drivers.map(normalizeCollectorAppealDriverCard).filter(Boolean).slice(0, 3)
    : [];

  if (cards.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">Top Collector Appeal drivers are not available for this set yet.</p>;
  }

  return (
    <div className="space-y-2.5">
      {cards.map((card, index) => (
        <CollectorAppealDriverRow
          key={`${card?.name || "driver"}-${card?.printedNumber || index}`}
          card={card}
          index={index}
        />
      ))}
    </div>
  );
}

function HeroMetricTile({ label, value, trend = null }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  const infoText =
    label === RIP_COPY.simpleMetrics.averageHitValue
      ? "Average market value of pulled hit cards in the simulation. Pattern overlays are excluded."
      : getMetricTooltip(label);
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--surface-page)_78%,transparent)] p-3 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03),0_8px_20px_rgba(2,6,23,0.12)] backdrop-blur-[2px]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[color:color-mix(in_srgb,var(--text-primary)_72%,var(--text-secondary))]">{friendlyLabel}</p>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </div>
      <div className="mt-2 inline-flex items-center gap-1.5 text-lg font-bold leading-tight" style={isNegativeValue ? getDangerValueStyle() : { color: "var(--text-primary)" }}>
        <span>{value}</span>
        <TrendIndicator trend={trend} className="translate-y-px" />
      </div>
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

  return <InterpretationBadge label={label} rankTier={rankTier} className="px-3 py-1 text-[12px] tracking-[0.08em]" />;
}

function MobileMetricAccordion({
  title,
  children,
  defaultOpen = false,
  className = "",
  style = undefined,
  preserveViewportOnToggle = false,
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const accordionId = useId();
  const contentId = `${accordionId.replace(/[:]/g, "")}-content`;
  const rootRef = useRef(null);

  const handleToggle = () => {
    if (!preserveViewportOnToggle || typeof window === "undefined" || !rootRef.current) {
      setIsOpen((current) => !current);
      return;
    }

    const beforeTop = rootRef.current.getBoundingClientRect().top;
    setIsOpen((current) => !current);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!rootRef.current) {
          return;
        }

        const afterTop = rootRef.current.getBoundingClientRect().top;
        const delta = afterTop - beforeTop;

        if (Math.abs(delta) > 1) {
          window.scrollBy({ top: delta, left: 0, behavior: "auto" });
        }
      });
    });
  };

  return (
    <div ref={rootRef} className={["lg:hidden", className].filter(Boolean).join(" ")} style={style}>
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-3 py-2.5">
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={contentId}
          onClick={handleToggle}
          className="flex w-full items-center justify-between gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/70"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</span>
          <span
            aria-hidden="true"
            className={[
              "text-xs text-[var(--text-secondary)] transition-transform duration-200",
              isOpen ? "rotate-180" : "",
            ].join(" ")}
          >
            ▾
          </span>
        </button>

        <div
          id={contentId}
          className={[
            "grid overflow-hidden transition-all duration-200 ease-out",
            isOpen ? "mt-3 grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
          ].join(" ")}
        >
          <div className="min-h-0 overflow-hidden">{children}</div>
        </div>
      </div>
    </div>
  );
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
    scoreFields: ["relative_experience_score", "experience_score"],
    tierField: "experience_tier",
    rankField: "experience_rank",
    format: "score",
    heading: "How this set feels to open",
    simpleCardSummary:
      "This shows what the set usually feels like to open - whether packs feel exciting, painful, balanced, or swingy.",
    simpleDetailSummary:
      "This lens explains the day-to-day opening feel. It helps you gauge whether most packs feel satisfying, rough, or all over the place.",
    description:
      "This lens weighs typical pack value, chance to beat cost, miss protection, big-pull frequency, and consistency.",
    evidenceKeys: ["prob_profit", "mean_value", "expected_loss_when_losing"],
  },
  {
    key: "chase",
    label: "Chase Potential",
    scoreFields: ["relative_chase_potential_score", "chase_potential_score"],
    tierField: "chase_potential_tier",
    rankField: "chase_potential_rank",
    format: "score",
    heading: "How strong the chase setup is",
    simpleCardSummary:
      "This shows how exciting the chase-card setup is compared with other sets.",
    simpleDetailSummary:
      "This lens explains how compelling the chase is overall. It reflects whether the headline cards and chase depth feel worth the rip experience.",
    description:
      "This lens weighs big-pull frequency, high-end upside, chase depth, affordability, and profit profile.",
    evidenceKeys: ["prob_big_hit", "p95_value_to_cost_ratio", "effective_chase_count"],
  },
  {
    key: "upside",
    label: "Biggest Upside",
    scoreFields: ["relative_biggest_upside_score", "biggest_upside_score"],
    tierField: "biggest_upside_tier",
    rankField: "biggest_upside_rank",
    format: "score",
    heading: "How high the top outcomes can run",
    simpleCardSummary:
      "Top upside compared with the field.",
    simpleDetailSummary:
      "This lens focuses on ceiling. It helps you understand whether the strongest possible pulls can feel truly special for this set.",
    description:
      "This lens blends Big Hit Upside (P95) with God Pull Upside (P99) to represent total ceiling quality.",
    evidenceKeys: ["p95_value_to_cost_ratio", "p99_value_to_cost_ratio", "big_hit_threshold", "max_value"],
  },
  {
    key: "averageReturn",
    label: "Average Return",
    scoreFields: [
      "relative_average_return_score",
      "relative_mean_value_to_cost_score",
      "average_return_score",
      "mean_value_to_cost_score",
    ],
    tierField: "mean_value_to_cost_tier",
    rankField: "mean_value_to_cost_rank",
    format: "score",
    heading: "Average value compared with cost",
    simpleCardSummary:
      "This shows whether the set tends to give back more or less value compared with similar sets.",
    simpleDetailSummary:
      "This lens describes the typical value return profile. It sets expectations for whether average openings tend to feel closer to cost or noticeably behind it.",
    description:
      "This lens compares average simulated pack value against current estimated pack cost.",
    evidenceKeys: ["mean_value", "pack_cost", "expected_loss_per_pack"],
  },
];

function resolveLensScore(lens, summary) {
  const candidateFields = Array.isArray(lens?.scoreFields) ? lens.scoreFields : [lens?.scoreField];
  for (const field of candidateFields) {
    if (!field) continue;
    const value = toNumber(summary[field]);
    if (value !== null) {
      return {
        score: value,
        format: lens.format || "score",
        source: field,
        usedRawFallback: false,
      };
    }
  }

  if (lens?.key === "upside") {
    const p95 = toNumber(summary.p95_value_to_cost_ratio);
    const p99 = toNumber(summary.p99_value_to_cost_ratio);
    if (p95 !== null || p99 !== null) {
      const parts = [];
      if (p95 !== null) parts.push(`P95 ${p95.toFixed(1)}x`);
      if (p99 !== null) parts.push(`P99 ${p99.toFixed(1)}x`);
      return {
        score: null,
        format: "raw-text",
        source: "p95_p99_ratio_fallback",
        usedRawFallback: true,
        rawText: parts.join(" / "),
      };
    }
  }

  return {
    score: null,
    format: lens.format || "score",
    source: null,
    usedRawFallback: false,
  };
}

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
      return { label: "Big Hit Upside", value: fmtMult(summary.p95_value_to_cost_ratio) };
    case "p99_value_to_cost_ratio":
      return { label: "God Pull Upside", value: fmtMult(summary.p99_value_to_cost_ratio) };
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

function getLensTagline(lens, summary, resolvedLensScore = null) {
  const tier = toOptionalUpper(summary[lens.tierField]);
  const score = resolvedLensScore?.score ?? resolveLensScore(lens, summary).score;
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
    if (tier === "S" || tier === "A") return "Top upside compared with the field.";
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

function getSimpleLensCopy(lens) {
  return lens?.simpleCardSummary || getLensTagline(lens, {});
}

const BACKEND_SET_INTELLIGENCE_KEY_MAP = {
  opening_experience: "experience",
  chase_potential: "chase",
  biggest_upside: "upside",
  average_return: "averageReturn",
};

const PILLAR_TITLE_TO_KEY = {
  Profit: "profit",
  Safety: "safety",
  Desirability: "desirability",
  Stability: "stability",
};

function toDisplayStateLabel(value) {
  if (!value) return null;
  return String(value)
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeBackendSetIntelligence(setIntelligenceMeta) {
  if (!Array.isArray(setIntelligenceMeta)) return new Map();

  const entries = setIntelligenceMeta
    .map((lens) => {
      const mappedKey = BACKEND_SET_INTELLIGENCE_KEY_MAP[lens?.key];
      if (!mappedKey) return null;
      return [mappedKey, lens];
    })
    .filter(Boolean);

  return new Map(entries);
}

function SetIntelligenceSection({ summary, simpleMode = false, setIntelligenceMeta = [] }) {
  const [selectedLensKey, setSelectedLensKey] = useState("experience");
  const backendLensByKey = useMemo(
    () => normalizeBackendSetIntelligence(setIntelligenceMeta),
    [setIntelligenceMeta]
  );
  const resolvedLenses = useMemo(
    () =>
      SET_INTELLIGENCE_LENSES.map((lens) => {
        const backendLens = backendLensByKey.get(lens.key) || null;
        return {
          ...lens,
          label: backendLens?.label || lens.label,
          backend: backendLens,
        };
      }),
    [backendLensByKey]
  );

  useEffect(() => {
    if (!resolvedLenses.some((lens) => lens.key === selectedLensKey)) {
      setSelectedLensKey(resolvedLenses[0]?.key || "experience");
    }
  }, [resolvedLenses, selectedLensKey]);

  const selectedLens =
    resolvedLenses.find((lens) => lens.key === selectedLensKey) || resolvedLenses[0] || SET_INTELLIGENCE_LENSES[0];

  const selectedTier = toOptionalUpper(selectedLens?.backend?.tier ?? summary[selectedLens.tierField]);
  const selectedTierConfig = selectedTier ? RANK_CONFIG[selectedTier] : null;
  const selectedDetailBorder = selectedTierConfig?.color ? withAlpha(selectedTierConfig.color, 0.36) : undefined;
  const selectedLongSummary =
    selectedLens?.backend?.long_summary || (simpleMode ? selectedLens.simpleDetailSummary : selectedLens.description);
  const selectedSupportingSignals = Array.isArray(selectedLens?.backend?.supporting_signals)
    ? selectedLens.backend.supporting_signals.filter(Boolean)
    : [];
  const selectedEvidence = Array.isArray(selectedLens?.backend?.evidence) && selectedLens.backend.evidence.length > 0
    ? selectedLens.backend.evidence.filter(Boolean)
    : selectedLens.evidenceKeys
        .map((key) => getLensEvidenceRow(key, summary))
        .filter(Boolean);

  const setIntelligenceInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Set Intelligence</p>
      {simpleMode ? (
        <p className="text-[var(--text-secondary)]">
          High-level lenses for how this set behaves so you can quickly understand what opening it tends to feel like.
        </p>
      ) : (
        <p className="text-[var(--text-secondary)]">
          Quick lenses for how this set opens, chases, and returns value. Select a lens to see what is driving that view.
        </p>
      )}
    </div>
  );

  return (
    <section id="set-detail-set-intelligence" className="scroll-mt-24 pt-4 md:scroll-mt-28 md:pt-5">
      <article className="w-full max-w-full min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] sm:p-5">
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">Set Intelligence</h2>
            <InfoPopover text={setIntelligenceInfo} />
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {resolvedLenses.map((lens) => {
            const resolvedLensScore = resolveLensScore(lens, summary);
            const tier = toOptionalUpper(lens?.backend?.tier ?? summary[lens.tierField]);
            const rank = toNumber(summary[lens.rankField]);
            const isSelected = selectedLensKey === lens.key;
            const shortSummary = lens?.backend?.short_summary || (simpleMode ? getSimpleLensCopy(lens) : getLensTagline(lens, summary, resolvedLensScore));

            return (
              <button
                key={lens.key}
                type="button"
                onClick={() => setSelectedLensKey(lens.key)}
                aria-pressed={isSelected}
                className={[
                  "relative flex h-full min-w-0 cursor-pointer flex-col rounded-xl border px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]/70",
                  isSelected
                    ? "bg-[var(--surface-page)]/70 border-[var(--accent)]"
                    : "bg-[var(--surface-page)]/45 border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]",
                ].join(" ")}
                style={
                  isSelected
                    ? {
                        borderColor: "var(--accent)",
                        boxShadow: "0 0 0 1px rgba(250, 204, 21, 0.35), 0 0 16px rgba(250, 204, 21, 0.18)",
                      }
                    : undefined
                }
              >
                <span className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  {lens.label}
                </span>
                {simpleMode ? (
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {tier ? (
                      <RankBadge rank={tier} format="tier" size="default" subtle />
                    ) : (
                      <span className="text-xs text-[var(--text-secondary)] opacity-60">Not ranked</span>
                    )}
                    {rank !== null ? (
                      <span className="text-[9px] text-[var(--text-secondary)] opacity-70 sm:text-[10px]">Rank #{Math.round(rank)}</span>
                    ) : null}
                  </div>
                ) : (
                  <div className="flex items-baseline gap-1.5 sm:gap-2">
                    <span className="text-lg font-bold leading-none text-[var(--text-primary)]">
                      {resolvedLensScore.usedRawFallback
                        ? resolvedLensScore.rawText || "—"
                        : formatLensScore(resolvedLensScore.score, resolvedLensScore.format)}
                    </span>
                    {tier ? (
                      <RankBadge rank={tier} format="tier" size="default" subtle />
                    ) : (
                      <span className="text-xs text-[var(--text-secondary)] opacity-60">Not ranked</span>
                    )}
                  </div>
                )}
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute right-2.5 top-2 text-[var(--text-secondary)] opacity-40"
                >
                  ›
                </span>
                {!simpleMode && rank !== null ? (
                  <span className="mt-1.5 text-[9px] text-[var(--text-secondary)] opacity-70 sm:text-[10px]">
                    Rank #{Math.round(rank)}
                  </span>
                ) : null}
                <span className="mt-2 line-clamp-2 text-[11px] leading-snug text-[var(--text-secondary)]">
                  {shortSummary}
                </span>
              </button>
            );
          })}
        </div>

        <details
          className="group mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3.5 py-3"
          style={selectedDetailBorder ? { borderLeftColor: selectedDetailBorder, borderLeftWidth: "2px" } : undefined}
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-[var(--text-primary)]">
            <span className="min-w-0 truncate">{selectedLens.heading}</span>
            <span className="inline-flex flex-none items-center gap-2 text-[10px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {selectedLens.label}
              <svg
                aria-hidden="true"
                viewBox="0 0 20 20"
                className="h-4 w-4 transition-transform group-open:rotate-180"
                fill="currentColor"
              >
                <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
              </svg>
            </span>
          </summary>
          <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">
            {selectedLongSummary}
          </p>
          {!simpleMode && selectedSupportingSignals.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-2">
              {selectedSupportingSignals.map((signal) => (
                <span
                  key={signal}
                  className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-[11px] text-[var(--text-secondary)]"
                >
                  {signal}
                </span>
              ))}
            </div>
          ) : null}
          {!simpleMode && selectedEvidence.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-2">
              {selectedEvidence.map((item, idx) => (
                <span
                  key={`${item?.label || "evidence"}-${idx}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                >
                  <span className="flex-none">{item?.label || "Signal"}:</span>
                  <span className="font-medium text-[var(--text-primary)]">{item?.value ?? "—"}</span>
                </span>
              ))}
            </div>
          ) : null}
        </details>
      </article>
    </section>
  );
}

function ScorePillarCard({
  title,
  score,
  scoreTrend = null,
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
  const keySignals = Array.isArray(simpleMetrics) ? simpleMetrics.slice(0, 2) : [];

  return (
    <article className="flex h-full flex-col rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2.5">
            <h3 className="text-base font-semibold tracking-[0.01em] text-[var(--text-secondary)]">{title}</h3>
            <p className="inline-flex items-center gap-1.5 text-2xl font-bold leading-none text-[var(--text-primary)]">
              <span>{formatScore(score)}</span>
              <TrendIndicator trend={scoreTrend} className="translate-y-0.5" />
            </p>
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

      {keySignals.length > 0 ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
          {keySignals.map((metric) => (
            <div key={`${title}-signal-${metric.label}`} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{metric.label}</p>
              <p className="mt-1 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
                <span>{metric.value}</span>
                <TrendIndicator trend={metric.trend} className="translate-y-px" />
              </p>
            </div>
          ))}
        </div>
      ) : null}

      <details className="group mt-auto border-t border-[var(--border-subtle)] pt-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]">
          <span>Details</span>
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-4 w-4 flex-none transition-transform group-open:rotate-180"
            fill="currentColor"
          >
            <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
          </svg>
        </summary>
        <div className="mt-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
              <InfoPopover text="Switch between simple collector-facing metrics and score details." />
            </div>
            <CompactMetricModeToggle mode={metricMode} onChange={setMetricMode} />
          </div>
          <div className="space-y-1">
            {metricsToDisplay.map((metric) => (
              <MetricRow
                key={`${title}-${metricMode}-${metric.label}`}
                label={metric.label}
                value={metric.value}
                trend={metric.trend}
                infoText={metric.infoText || getMetricTooltip(metric.label)}
                content={metric.content}
              />
            ))}
          </div>
        </div>
      </details>
    </article>
  );
}

function SimplePillarSummaryCard({
  title,
  rankTier,
  infoText,
  sectionMeta,
  backendPillar,
  fallbackSummary,
}) {
  const backendStateLabel = toDisplayStateLabel(backendPillar?.state);
  const label = sectionMeta?.label || backendStateLabel || null;
  const summary =
    backendPillar?.short_summary ||
    sectionMeta?.summary ||
    fallbackSummary ||
    "No interpretation summary is available for this pillar yet.";
  const backendSeverity =
    backendPillar?.tone === "positive"
      ? "positive"
      : backendPillar?.tone === "negative"
      ? "negative"
      : sectionMeta?.severity;
  const tone = getInterpretationTone({ label, rankTier, severity: backendSeverity });

  return (
    <article
      className="flex h-full flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/62 p-4 sm:p-5"
      style={{ boxShadow: `0 0 0 1px ${withAlpha(tone.accentColor, 0.08)}` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-nowrap items-center gap-1.5 sm:gap-2">
          <h4 className="whitespace-nowrap text-[13px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)] sm:text-sm sm:tracking-[0.08em]">{title}</h4>
          {rankTier ? (
            <span className="flex-none">
              <RankBadge rank={rankTier} format="tier" size="supporting" subtle />
            </span>
          ) : null}
        </div>
        <div className="flex flex-none items-center gap-1">
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
      </div>

      {label ? (
        <div className="mt-2.5 inline-flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
          <span className="h-1.5 w-1.5 rounded-full" aria-hidden="true" style={{ backgroundColor: tone.dotColor }} />
          <InterpretationBadge label={label} rankTier={rankTier} severity={backendSeverity} className="px-2 py-0.5 text-[10px] tracking-[0.08em]" />
        </div>
      ) : null}

      <p className="mt-3 text-sm leading-relaxed text-[var(--text-primary)]">{summary}</p>
    </article>
  );
}

function getPillarStatusLabel({ label, score }) {
  const normalizedLabel = toDisplayStateLabel(label) || String(label || "").trim();
  if (normalizedLabel) {
    return normalizedLabel;
  }

  const numericScore = toNumber(score);
  if (numericScore === null) {
    return "Mixed";
  }
  if (numericScore >= 80) return "Strong Support";
  if (numericScore >= 65) return "Support";
  if (numericScore >= 45) return "Mixed";
  if (numericScore >= 30) return "Drag";
  return "Major Risk";
}

function getPillarSignalHighlight(title, score) {
  const numericScore = toNumber(score);
  const isStrong = numericScore !== null && numericScore >= 80;
  const isSolid = numericScore !== null && numericScore >= 65;
  const isWeak = numericScore !== null && numericScore < 45;

  if (title === "Profit") {
    if (isStrong) return "Strong average, meaningful upside";
    if (isSolid) return "Playable return profile";
    if (isWeak) return "Average return trails cost";
    return "Mixed profit profile";
  }

  if (title === "Safety") {
    if (isStrong) return "Controlled misses";
    if (isSolid) return "Manageable downside";
    if (isWeak) return "Misses can bite";
    return "Mixed miss protection";
  }

  if (title === "Desirability") {
    if (isStrong) return "High opening desirability";
    if (isSolid) return "Clear collector demand";
    if (isWeak) return "Demand signal is muted";
    return "Mixed desirability signal";
  }

  if (title === "Stability") {
    if (isStrong) return "Value spread is healthy";
    if (isSolid) return "Some depth beyond top hits";
    if (isWeak) return "Fragile value spread";
    return "Mixed value spread";
  }

  return "Signal available";
}

function OverviewPillarSignalTile({ title, score, scoreTrend = null, rankTier, rankValue, highlight, infoText }) {
  const parsedRank = toNumber(rankValue);

  return (
    <article className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-2.5">
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <p className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</p>
            {infoText ? <InfoPopover text={infoText} /> : null}
          </div>
          {highlight ? (
            <p className="mt-1 truncate text-xs leading-snug text-[var(--text-primary)]">{highlight}</p>
          ) : null}
        </div>
        <div className="flex flex-none items-center gap-2">
          <p className="inline-flex items-center gap-1 text-lg font-semibold leading-none text-[var(--text-primary)]">
            <span>{formatScore(score)}</span>
            <TrendIndicator trend={scoreTrend} className="translate-y-px" />
          </p>
          <div className="flex flex-col items-end gap-1">
            <RankBadge
              rank={rankTier}
              format="tier"
              size="supporting"
              subtle
              title={parsedRank === null ? "Rank unavailable" : `Rank #${Math.round(parsedRank)}`}
            />
            <span className="text-[10px] leading-none text-[var(--text-secondary)]">
              {parsedRank === null ? "Rank --" : `#${Math.round(parsedRank)}`}
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}

function OverviewPillarSignalsCard({ signals }) {
  const visibleSignals = Array.isArray(signals) ? signals.filter(Boolean) : [];
  if (visibleSignals.length === 0) {
    return null;
  }

  return (
    <SectionCard
      title="RIP Signals"
      titleInfoText="Compact overview signals from the four RIP pillars. Full details are in Insights -> RIP Score Breakdown."
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
        {visibleSignals.map((signal) => (
          <OverviewPillarSignalTile key={`overview-pillar:${signal.title}`} {...signal} />
        ))}
      </div>
    </SectionCard>
  );
}

function OpeningProfileSignalTile({ lens }) {
  const parsedRank = toNumber(lens.rank);

  return (
    <article className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-2.5">
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div className="min-w-0">
          <p className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{lens.label}</p>
          {lens.highlight ? (
            <p className="mt-1 truncate text-xs leading-snug text-[var(--text-primary)]">{lens.highlight}</p>
          ) : null}
        </div>
        <div className="flex flex-none items-center gap-2">
          {lens.scoreText ? (
            <p className="text-lg font-semibold leading-none text-[var(--text-primary)]">{lens.scoreText}</p>
          ) : null}
          <div className="flex flex-col items-end gap-1">
            <RankBadge
              rank={lens.tier}
              format="tier"
              size="supporting"
              subtle
              title={parsedRank === null ? "Rank unavailable" : `Rank #${Math.round(parsedRank)}`}
            />
            <span className="text-[10px] leading-none text-[var(--text-secondary)]">
              {parsedRank === null ? "Rank --" : `#${Math.round(parsedRank)}`}
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}

function OpeningProfileSignalsCard({ summary, setIntelligenceMeta = [] }) {
  const backendLensByKey = useMemo(
    () => normalizeBackendSetIntelligence(setIntelligenceMeta),
    [setIntelligenceMeta]
  );

  const signals = useMemo(
    () =>
      SET_INTELLIGENCE_LENSES.map((lens) => {
        const backendLens = backendLensByKey.get(lens.key) || null;
        const resolvedScore = resolveLensScore(lens, summary);
        const tier = toOptionalUpper(backendLens?.tier ?? summary[lens.tierField]);
        const rank = toNumber(summary[lens.rankField]);
        const hasScore = resolvedScore.usedRawFallback || toNumber(resolvedScore.score) !== null;
        const scoreText = resolvedScore.usedRawFallback
          ? resolvedScore.rawText || null
          : hasScore
          ? formatLensScore(resolvedScore.score, resolvedScore.format)
          : null;
        const highlight =
          backendLens?.short_summary ||
          (hasScore || tier || rank !== null ? getLensTagline(lens, summary, resolvedScore) : null);

        if (!hasScore && !tier && rank === null && !highlight) {
          return null;
        }

        return {
          label: backendLens?.label || lens.label,
          scoreText,
          tier,
          rank,
          highlight,
        };
      }).filter(Boolean),
    [backendLensByKey, summary]
  );

  if (signals.length === 0) {
    return null;
  }

  return (
    <SectionCard
      title="Opening Profile"
      titleInfoText="Compact at-a-glance opening lenses for experience, chase potential, upside, and average return."
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
        {signals.map((signal) => (
          <OpeningProfileSignalTile key={`opening-profile:${signal.label}`} lens={signal} />
        ))}
      </div>
    </SectionCard>
  );
}

function DecisionSignalRow({ signal, expanded }) {
  const parsedRank = toNumber(signal.rankValue);
  const summaryText = expanded
    ? signal.detailSummary || signal.summary
    : signal.summary || signal.detailSummary;

  return (
    <article className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-3">
      <div className="grid min-w-0 gap-2.5 sm:grid-cols-[minmax(0,1fr)_4.25rem_5.75rem_3.25rem] sm:items-center">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{signal.label}</p>
          <p className={`mt-1 text-xs leading-snug text-[var(--text-primary)] ${expanded ? "" : "line-clamp-2"}`}>
            {summaryText}
          </p>
        </div>
        <span className="inline-flex min-w-[4.25rem] items-center justify-start gap-1 text-base font-semibold leading-none text-[var(--text-primary)] tabular-nums sm:min-w-0 sm:justify-end">
          {signal.scoreText || "—"}
          {signal.scoreTrend ? <TrendIndicator trend={signal.scoreTrend} className="translate-y-px" /> : null}
        </span>
        <div className="flex min-w-[5.75rem] justify-start sm:min-w-0 sm:justify-center">
          <RankBadge
            rank={signal.rankTier}
            format="tier"
            size="supporting"
            subtle
            title={parsedRank === null ? "Rank unavailable" : `Rank #${Math.round(parsedRank)}`}
          />
        </div>
        <span className="min-w-[3.25rem] text-left text-[10px] leading-none text-[var(--text-secondary)] tabular-nums sm:min-w-0 sm:text-right">
          {parsedRank === null ? "Rank --" : `#${Math.round(parsedRank)}`}
        </span>
      </div>
    </article>
  );
}

function DecisionSignalsCard({ pillarSignals, summary, setIntelligenceMeta = [] }) {
  const [displayMode, setDisplayMode] = useState("compact");
  const expanded = displayMode === "expanded";
  const backendLensByKey = useMemo(
    () => normalizeBackendSetIntelligence(setIntelligenceMeta),
    [setIntelligenceMeta]
  );

  const signals = useMemo(() => {
    const compactSummaries = {
      Profitability: "Strong average upside",
      Safety: "Manageable downside",
      Desirability: "High collector demand",
      Stability: "Fragile value spread",
      "Opening Experience": "Swingy pack feel",
      "Chase Potential": "Rare top-heavy chase",
      "Biggest Upside": "Huge but rare spikes",
      "Average Return": "Strong average return",
    };
    const signalByTitle = new Map(
      (Array.isArray(pillarSignals) ? pillarSignals : [])
        .filter(Boolean)
        .map((signal) => [signal.title, signal])
    );
    const pillarRows = [
      ["Profit", "Profitability", "Profit profile", "Compares average value, upside, and pack cost pressure."],
      ["Safety", "Safety", "Miss protection", "Shows how well the set protects against rough openings and downside outcomes."],
      ["Desirability", "Desirability", "Collector demand", "Reflects collector appeal and chase-card strength for this set."],
      ["Stability", "Stability", "Value spread", "Shows whether value is broadly distributed or concentrated in a few cards."],
    ]
      .map(([title, label, fallbackSummary, detailSummary]) => {
        const signal = signalByTitle.get(title);
        if (!signal) return null;
        return {
          label,
          scoreText: formatScore(signal.score),
          scoreTrend: signal.scoreTrend,
          rankTier: signal.rankTier,
          rankValue: signal.rankValue,
          summary: compactSummaries[label] || signal.highlight || fallbackSummary,
          detailSummary: signal.highlight || detailSummary,
        };
      })
      .filter(Boolean);

    const openingRows = SET_INTELLIGENCE_LENSES.map((lens) => {
      const backendLens = backendLensByKey.get(lens.key) || null;
      const resolvedScore = resolveLensScore(lens, summary);
      const rankTier = toOptionalUpper(backendLens?.tier ?? summary[lens.tierField]);
      const rankValue = toNumber(summary[lens.rankField]);
      const hasScore = resolvedScore.usedRawFallback || toNumber(resolvedScore.score) !== null;
      const summaryText =
        backendLens?.short_summary ||
        (hasScore || rankTier || rankValue !== null ? getLensTagline(lens, summary, resolvedScore) : null);

      if (!hasScore && !rankTier && rankValue === null && !summaryText) {
        return null;
      }

      return {
        label: backendLens?.label || lens.label,
        scoreText: resolvedScore.usedRawFallback
          ? resolvedScore.rawText || null
          : hasScore
          ? formatLensScore(resolvedScore.score, resolvedScore.format)
          : null,
        scoreTrend: null,
        rankTier,
        rankValue,
        summary: compactSummaries[backendLens?.label || lens.label] || summaryText || lens.simpleCardSummary || lens.description,
        detailSummary:
          backendLens?.long_summary ||
          backendLens?.summary ||
          summaryText ||
          lens.simpleDetailSummary ||
          lens.description,
      };
    }).filter(Boolean);

    return [...pillarRows, ...openingRows].filter(Boolean);
  }, [backendLensByKey, pillarSignals, summary]);

  if (signals.length === 0) {
    return null;
  }

  return (
    <SectionCard
      title="Decision Signals"
      titleInfoText="Decision signals combining the four RIP pillars with opening profile lenses."
    >
      <SectionViewTabs
        className="mb-4"
        value={displayMode}
        onChange={setDisplayMode}
        variant="secondary"
        options={[
          { value: "compact", label: "Compact" },
          { value: "expanded", label: "Expanded" },
        ]}
      />
      <div className="grid gap-2">
        {signals.map((signal) => (
          <DecisionSignalRow key={`decision-signal:${signal.label}`} signal={signal} expanded={expanded} />
        ))}
      </div>
    </SectionCard>
  );
}

function CompactPillarSignalTile({
  title,
  score,
  scoreTrend = null,
  rankValue,
  rankTier,
  statusLabel,
  highlight,
  metrics = [],
  infoText,
  detailsExpanded = false,
}) {
  const parsedRank = toNumber(rankValue);

  return (
    <article className="flex h-full flex-col rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <h3 className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</h3>
            {infoText ? <InfoPopover text={infoText} /> : null}
          </div>
          <p className="mt-1 inline-flex items-center gap-1.5 text-2xl font-semibold leading-none text-[var(--text-primary)]">
            <span>{formatScore(score)}</span>
            <TrendIndicator trend={scoreTrend} className="translate-y-px" />
          </p>
        </div>
        <RankBadge
          rank={rankTier}
          format="tier"
          size="supporting"
          subtle
          title={parsedRank === null ? "Rank unavailable" : `Rank #${Math.round(parsedRank)}`}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <InterpretationBadge label={statusLabel} rankTier={rankTier} className="px-2 py-0.5 text-[10px] tracking-[0.08em]" />
        {parsedRank !== null ? (
          <span className="text-[10px] text-[var(--text-secondary)]">Rank #{Math.round(parsedRank)}</span>
        ) : null}
      </div>

      {highlight ? (
        <p className="mt-2 line-clamp-2 text-xs leading-snug text-[var(--text-secondary)]">{highlight}</p>
      ) : null}

      {detailsExpanded && metrics.length > 0 ? (
        <div className="mt-3 flex-1 border-t border-[var(--border-subtle)] pt-2">
          <div className="mt-2 space-y-1.5">
            {metrics.map((metric) => (
              <MetricRow
                key={`${title}-detail-${metric.label}`}
                label={metric.label}
                value={metric.value}
                trend={metric.trend}
                infoText={metric.infoText || getMetricTooltip(metric.label)}
                content={metric.content}
              />
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function RipScoreBreakdownModule({
  score,
  scoreTrend = null,
  rankTier,
  rankValue,
  verdict,
  explanation,
  pillars,
  titleInfoText,
}) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const parsedRank = toNumber(rankValue);

  return (
    <section id="set-detail-rip-score" className="scroll-mt-24 md:scroll-mt-28">
      <article className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] sm:p-5">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">RIP Score Breakdown</h2>
            {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
          </div>
          <button
            type="button"
            onClick={() => setDetailsExpanded((current) => !current)}
            className="inline-flex flex-none items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-1.5 text-xs font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/55"
            aria-expanded={detailsExpanded}
          >
            {detailsExpanded ? "Hide Details" : "Show Details"}
            <svg
              viewBox="0 0 20 20"
              aria-hidden="true"
              className={`h-3.5 w-3.5 opacity-70 transition-transform duration-200 ${detailsExpanded ? "rotate-180" : ""}`}
              fill="currentColor"
            >
              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
            </svg>
          </button>
        </div>

        <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <p className="inline-flex items-end gap-1.5 text-4xl font-semibold leading-none text-[var(--text-primary)]">
                <span>{formatRawScore(score)}</span>
                <span className="pb-1 text-xs font-medium text-[var(--text-secondary)]">/100</span>
                <TrendIndicator trend={scoreTrend} className="mb-1" />
              </p>
              <RankBadge
                rank={rankTier}
                label="Rank"
                size="supporting"
                title={parsedRank === null ? "Rank unavailable" : `Rank #${Math.round(parsedRank)}`}
              />
              <RecommendationBadge label={verdict} rankTier={rankTier} />
              {explanation ? <InfoPopover text={explanation} /> : null}
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {pillars.map((pillar) => (
            <CompactPillarSignalTile key={`rip-pillar:${pillar.title}`} {...pillar} detailsExpanded={detailsExpanded} />
          ))}
        </div>
      </article>
    </section>
  );
}

function StatTile({ label, value, valueClassName = "text-lg", infoText = null, trend = null }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/60 p-4">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-left text-[11px] font-semibold uppercase leading-tight tracking-[0.08em] text-[var(--text-secondary)]">
          {label}
        </p>
        {infoText ? (
          <span className="flex-none shrink-0 pt-0.5">
            <InfoPopover text={infoText} />
          </span>
        ) : null}
      </div>
      <p className={`mt-2 inline-flex items-center gap-1.5 font-semibold text-[var(--text-primary)] ${valueClassName}`}>
        <span>{value}</span>
        <TrendIndicator trend={trend} className="translate-y-px" />
      </p>
    </div>
  );
}

function SectionCard({ title, subtitle, titleInfoText, children, className = "", bodyClassName = "" }) {
  return (
    <article className={["w-full max-w-full min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(2,6,23,0.62))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_18px_44px_rgba(2,6,23,0.22)] sm:p-5", className].filter(Boolean).join(" ")}>
      <div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
          {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
        </div>
        {subtitle ? <p className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className={["mt-4 min-w-0 max-w-full", bodyClassName].filter(Boolean).join(" ")}>{children}</div>
    </article>
  );
}

const TOP_CARD_IMAGE_CONTAINER_CLASS = "h-[5rem] w-[3.5rem] sm:h-[6.125rem] sm:w-[4.25rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]";

function TopHitRow({ name, evContribution, evShare, nearMintPrice, imageUrl, imageSmallUrl, imageLargeUrl, condensed = false }) {
  const imageSrc = imageUrl || imageSmallUrl || imageLargeUrl || null;
  const [hasImageError, setHasImageError] = useState(false);

  useEffect(() => {
    setHasImageError(false);
  }, [imageSrc]);

  const shouldRenderImage = Boolean(imageSrc) && !hasImageError;

  return (
    <div className={`w-full max-w-full min-w-0 box-border rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 ${condensed ? "p-2" : "p-2.5"}`}>
      <div className={`flex min-w-0 flex-col ${condensed ? "gap-2" : "gap-3"} sm:grid sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center`}>
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
        <div className={`grid min-w-0 grid-cols-2 text-left sm:mt-0 sm:text-right ${condensed ? "mt-1 gap-2 sm:min-w-[11rem]" : "mt-3 gap-3 sm:min-w-[14rem]"}`}>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{condensed ? "Market Price" : "Estimated Card Market Price"}</p>
            <p className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{nearMintPrice === null ? "—" : formatCurrency(nearMintPrice)}</p>
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Value Contribution</p>
            <p className={`mt-1 truncate font-semibold text-[var(--text-primary)] ${condensed ? "text-sm" : "text-base"}`}>{formatCurrency(evContribution)}</p>
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
    toNumber(hit?.currentNearMintPrice) ??
    toNumber(hit?.price_used) ??
    toNumber(hit?.priceUsed) ??
    toNumber(hit?.market_price) ??
    toNumber(hit?.marketPrice) ??
    toNumber(hit?.card_price) ??
    toNumber(hit?.cardPrice) ??
    toNumber(hit?.card_market_price) ??
    toNumber(hit?.cardMarketPrice) ??
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

function TopEVDriversContent({ topHits, meanValue, condensed = false }) {
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
      <div className={`${condensed ? "mb-2" : "mb-3"} flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between`}>
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{totalLabel}</span>
          {totalEV !== null ? <InfoPopover text={SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT} /> : null}
        </div>
        <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(totalValue)}</span>
      </div>
      {!condensed ? <p className="text-xs text-[var(--text-secondary)]">Price-based metrics use estimated third-party market snapshots and may change over time.</p> : null}

      <div className={condensed ? "grid gap-2 lg:grid-cols-2" : "space-y-2"}>
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
            condensed={condensed}
          />
        );
      })}
      </div>
    </div>
  );
}

function RarityContributionContent({ rankings, condensed = false }) {
  const rows = useMemo(() => (Array.isArray(rankings) ? rankings : []), [rankings]);

  const evRows = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => (toNumber(b?.total_sampled_value) ?? 0) - (toNumber(a?.total_sampled_value) ?? 0)
    );
    const totalEV = sorted.reduce((sum, row) => sum + (toNumber(row?.total_sampled_value) ?? 0), 0);
    const maxEV = Math.max(...sorted.map((row) => toNumber(row?.total_sampled_value) ?? 0), 0);
    const totalPulls = sorted.reduce((sum, row) => sum + (toNumber(row?.pulled_count) ?? 0), 0);
    return { sorted, totalEV, maxEV, totalPulls };
  }, [rows]);

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No rarity ranking rows are available.</p>;
  }

  return (
    <>
      <div className="mb-3 flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Total Simulated Value</span>
          <InfoPopover text={TOTAL_SIMULATED_VALUE_INFO_TEXT} />
        </div>
        <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(evRows.totalEV)}</span>
      </div>

      {evRows.maxEV === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No value contribution data available.</p>
      ) : (
        <div className={condensed ? "grid gap-x-4 gap-y-1 md:grid-cols-2" : "space-y-1"}>
          {evRows.sorted.map((ranking) => {
            const value = toNumber(ranking?.total_sampled_value) ?? 0;
            const valueShare = evRows.totalEV > 0 ? ((value / evRows.totalEV) * 100).toFixed(1) : null;
            const pullCount = toNumber(ranking?.pulled_count) ?? null;
            const pullShare =
              pullCount !== null && evRows.totalPulls > 0
                ? ((pullCount / evRows.totalPulls) * 100).toFixed(1)
                : null;
            const hasPullData = pullCount !== null && evRows.totalPulls > 0;

            return (
              <div key={`ev:${ranking?.rarity_bucket || "unknown"}`} className="py-1.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-[var(--text-primary)]">{titleCaseStateLabel(ranking?.rarity_bucket)}</span>
                    {hasPullData ? (
                      <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                        {pullCount.toLocaleString("en-US")} pulls in {evRows.totalPulls.toLocaleString("en-US")} simulated pulls
                        {pullShare !== null ? ` \u2022 ${pullShare}% of pulls` : ""}
                      </p>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{formatCurrency(value)}</span>
                    {valueShare !== null ? (
                      <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{valueShare}% of total value</p>
                    ) : null}
                  </div>
                </div>
                <HorizontalBar widthPercent={normalizeBarWidth(value, evRows.maxEV)} />
              </div>
            );
          })}
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

function PackBreakdownContent({ packPaths, normalStateRows, evidenceRows = [], condensed = false }) {
  return (
    <>
      {evidenceRows.length > 0 ? (
        <div className={`${condensed ? "mb-3" : "mb-4"} flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2`}>
          {evidenceRows.map(([label, value]) => (
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
      <div className={`grid ${condensed ? "gap-4 md:grid-cols-2" : "gap-5 md:grid-cols-2"}`}>
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>
          <PackPathBars packPaths={packPaths} />
        </div>
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Normal States</p>
          <StateBars stateRows={normalStateRows} />
        </div>
      </div>
    </>
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

function SetPageRailButton({ label, active, onClick, level = "primary" }) {
  const isSubLink = level === "sub";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "location" : undefined}
      className={[
        "group flex w-full items-center justify-between rounded-lg border text-left transition-colors",
        isSubLink ? "px-2.5 py-1.5 text-xs" : "px-3 py-2 text-sm font-medium",
        active
          ? "border-[rgba(94,234,212,0.26)] bg-[color:color-mix(in_srgb,var(--accent)_10%,transparent)] text-[var(--text-primary)]"
          : "border-transparent text-[var(--text-secondary)] hover:border-[var(--border-subtle)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]",
      ].join(" ")}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden="true"
          className={[
            "rounded-full transition-colors",
            isSubLink ? "h-1.5 w-1.5" : "h-2 w-2",
            active ? "bg-[var(--accent)]" : "bg-[var(--border-subtle)] group-hover:bg-[var(--text-secondary)]",
          ].join(" ")}
        />
        <span className="min-w-0 truncate">{label}</span>
      </span>
    </button>
  );
}

function SetPageNavigationRail({
  targets,
  requestedTargetId,
  selectedTarget,
  selectedName,
  isPending,
  activeTab,
  activeCardsSubTab,
  activeGraphMode,
  showTopMarketCards = false,
  onTargetChange,
  onNavigate,
}) {
  const topSections = [
    { id: "overview", label: "Overview" },
    { id: "cards", label: "Cards" },
    { id: "pull-rates", label: "Pull Rates" },
    { id: "insights", label: "Insights" },
  ];

  const visibleSubLinks =
    activeTab === "overview"
      ? [
          { id: "performance-vs-cost", label: "Market Snapshot", tab: "overview", section: "performance-vs-cost", graphMode: "historical-trend", targetId: "set-detail-overview-performance", active: activeGraphMode === "historical-trend" },
          ...(showTopMarketCards
            ? [{ id: "top-market-cards", label: "Top Chase Cards", tab: "overview", section: "top-market-cards", targetId: "set-detail-top-market-cards", active: false }]
            : []),
          { id: "set-signals", label: "Decision Signals", tab: "overview", section: "set-signals", targetId: "set-detail-set-intelligence", active: activeGraphMode !== "historical-trend" },
        ]
      : activeTab === "cards"
      ? [
          { id: "all-cards", label: "All Cards", tab: "cards", cardsSubTab: "checklist", active: activeCardsSubTab === "checklist" },
        ]
      : activeTab === "pull-rates"
      ? [
          { id: "pull-rate-assumptions", label: "Pull Rate Assumptions", tab: "pull-rates", active: true },
        ]
      : [
          { id: "rip-score", label: "RIP Score Breakdown", tab: "insights", section: "rip-score", targetId: "set-detail-rip-score", active: false },
          { id: "opening-outcomes", label: "Opening Outcomes", tab: "insights", section: "opening-outcomes", graphMode: "outcome-distribution", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "outcome-distribution" },
          { id: "simulation-cards", label: "Simulation Drivers", tab: "insights", section: "simulation-cards", graphMode: "simulation-drivers", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "simulation-drivers" },
          { id: "value", label: "Value Structure", tab: "insights", section: "value", graphMode: "value-contribution", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "value-contribution" },
          { id: "pack-breakdown", label: "Pack Paths", tab: "insights", section: "pack-breakdown", graphMode: "pack-breakdown", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "pack-breakdown" },
        ];

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--surface-page)_78%,transparent)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_12px_30px_rgba(2,6,23,0.18)] backdrop-blur-md">
      <div className="space-y-2">
        <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
          Set Control
        </p>
        <label htmlFor="set-page-rail-target" className="sr-only">
          Switch set
        </label>
        <select
          id="set-page-rail-target"
          value={requestedTargetId || ""}
          onChange={onTargetChange}
          disabled={isPending || targets.length === 0}
          title={targets.length > 0 ? "Switch set" : "No sets available"}
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm font-medium text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-70"
        >
          {targets.map((target) => (
            <option key={`rail-set:${target.target_type}:${target.target_id}`} value={target.target_id}>
              {target.name}
            </option>
          ))}
        </select>
        {selectedTarget?.era ? (
          <div className="flex items-center gap-2 px-1">
            <span className="text-[11px] font-medium text-[var(--text-secondary)]">Era</span>
            <span className="inline-flex min-w-0 max-w-full items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
              <span className="truncate">{selectedTarget.era}</span>
            </span>
          </div>
        ) : (
          <p className="px-1 text-[11px] text-[var(--text-secondary)]">{selectedName}</p>
        )}
      </div>

      <div className="h-px w-full bg-[var(--border-subtle)]" />

      <nav aria-label="Set page navigation" className="space-y-3">
        <div>
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            Sections
          </p>
          <div className="mt-2 space-y-1">
            {topSections.map((section) => (
              <SetPageRailButton
                key={section.id}
                label={section.label}
                active={activeTab === section.id}
                onClick={() => onNavigate({ tab: section.id })}
              />
            ))}
          </div>
        </div>

        <div>
          <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            In This View
          </p>
          <div className="mt-2 space-y-1">
            {visibleSubLinks.map((link) => (
              <SetPageRailButton
                key={link.id}
                label={link.label}
                level="sub"
                active={link.active}
                onClick={() => onNavigate(link)}
              />
            ))}
          </div>
        </div>
      </nav>
    </div>
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
  profileBaseHref = "/Explore/rip-statistics",
  targetHrefById = null,
  setDetailMode = false,
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
  const normalizedOpeningDesirability = useMemo(
    () =>
      normalizeOpeningDesirabilityPayload(
        explorePayload?.openingDesirability || explorePayload?.opening_desirability
      ),
    [explorePayload?.openingDesirability, explorePayload?.opening_desirability]
  );
  const pullRateAssumptions = normalizePullRateAssumptions(explorePayload);
  const ripStatistics = explorePayload?.rip_statistics;
  const interpretation = explorePayload?.interpretation || {};
  const interpretationMeta = interpretation?.meta || {};
  const pillarMetaByKey = useMemo(() => {
    const entries = Array.isArray(interpretationMeta?.pillars)
      ? interpretationMeta.pillars
          .filter((pillar) => pillar?.key)
          .map((pillar) => [pillar.key, pillar])
      : [];
    return Object.fromEntries(entries);
  }, [interpretationMeta?.pillars]);
  const packScoreMeta = interpretationMeta?.packScore;
  const profitMeta = interpretationMeta?.profit;
  const safetyMeta = interpretationMeta?.safety;
  const desirabilityMeta = interpretationMeta?.desirability;
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
  const [, setInsightsValueView] = useState("value-structure");
  const effectiveViewMode = setDetailMode ? "expert" : viewMode;
  const isExpertMode = effectiveViewMode === "expert";
  const effectiveValueView = setDetailMode ? "value" : isExpertMode ? activeValueView : "cards";
  const [activeSection, setActiveSection] = useState("pack-score");
  const [heroSetPickerOpen, setHeroSetPickerOpen] = useState(false);
  // TODO: Direct or unknown set page visits may default to Overview later once this surface is mature.
  const [setDetailTab, setSetDetailTab] = useState(() => getSetDetailTabParam(searchParams));
  const [cardsSubTab, setCardsSubTab] = useState("checklist");
  const [checklistState, setChecklistState] = useState({
    status: "idle",
    cards: [],
    error: null,
  });
  const [topMarketCardsState, setTopMarketCardsState] = useState({
    status: "idle",
    cards: [],
    error: null,
    meta: null,
  });
  const [setValueHistoryState, setSetValueHistoryState] = useState({
    status: "idle",
    history: [],
    historiesByScope: {},
    availableScopes: SET_VALUE_SCOPE_OPTIONS,
    error: null,
    meta: null,
  });
  const heroSetPickerRef = useRef(null);
  const checklistCacheRef = useRef(new Map());
  const topMarketCardsCacheRef = useRef(new Map());
  const setValueHistoryCacheRef = useRef(new Map());
  const pendingNavSelectionRef = useRef(null);
  const pendingNavTimeoutRef = useRef(null);
  const pendingNavStartedAtRef = useRef(0);
  const activeInsightsGraphMode =
    setDetailMode && setDetailTab === "insights" && graphMode === "historical-trend"
      ? "outcome-distribution"
      : graphMode;

  const graphSectionMeta =
    activeInsightsGraphMode === "historical-trend"
      ? historicalTrendMeta
      : activeInsightsGraphMode === "pack-breakdown"
      ? packBreakdownMeta
      : activeInsightsGraphMode === "value-contribution"
      ? rarityContributionMeta
      : outcomeDistributionMeta;

  const graphSectionFallback =
    activeInsightsGraphMode === "historical-trend"
      ? interpretation?.historicalTrend
      : activeInsightsGraphMode === "pack-breakdown"
      ? interpretation?.packBreakdown
      : activeInsightsGraphMode === "value-contribution"
      ? interpretation?.rarityContribution
      : interpretation?.outcomeDistribution;

  const outcomeDistributionInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Opening Outcomes</p>
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2"><span className="flex-none">â€¢</span><span>{getSimulationContextSubtitle(summary.simulation_count ?? summary.packs_simulated)}</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Bars show how often packs land in each value range.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>The line shows how often a pack reaches at least a given value.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Marker chips let you compare pack cost, typical and average outcomes, floor outcomes, and upper-end upside markers against the distribution.</span></li>
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

  const showDebugTimings =
    process.env.NODE_ENV === "development" &&
    process.env.NEXT_PUBLIC_SHOW_BACKEND_TIMINGS === "true";

  const sectionNavItems = useMemo(
    () => [
      { id: "pack-score", label: RIP_COPY.sections.packScore },
      { id: "outcome-distribution", label: RIP_COPY.sections.outcomeDistribution },
      { id: "top-ev-drivers", label: RIP_COPY.sections.topEvDrivers },
      { id: "rarity-contribution", label: RIP_COPY.sections.rarityContribution },
    ],
    []
  );
  const displayedSectionNavItems = effectiveViewMode === "simple"
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

  const scrollToSetDetailElement = (targetId = "set-detail-content") => {
    if (typeof document === "undefined" || typeof window === "undefined") {
      return;
    }

    window.requestAnimationFrame(() => {
      const target = getVisibleSectionElement(targetId);
      if (!target) {
        return;
      }

      const stickyOffset = getExploreStickyOffset();
      const targetTop = target.getBoundingClientRect().top + window.scrollY - stickyOffset;
      window.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
    });
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

  const pushSetDetailRouteState = ({ tab, section } = {}) => {
    if (!setDetailMode) {
      return;
    }

    const nextHref = updateSetDetailQueryParams({
      pathname,
      searchParams,
      tab: tab || setDetailTab,
      section,
    });
    router.push(nextHref, { scroll: false });
  };

  const handleSetDetailTabChange = (nextTab) => {
    const normalizedTab = normalizeSetDetailTab(nextTab);
    setSetDetailTab(normalizedTab);
    if (normalizedTab === "insights" && graphMode === "historical-trend") {
      setGraphMode("outcome-distribution");
      setActiveSection("outcome-distribution");
    }
    pushSetDetailRouteState({ tab: normalizedTab });
  };

  const handleSetDetailNavSelect = ({ tab, section, cardsSubTab: nextCardsSubTab, graphMode: nextGraphMode, targetId } = {}) => {
    const nextTab = normalizeSetDetailTab(tab || setDetailTab);

    if (nextTab) {
      setSetDetailTab(nextTab);
    }

    if (nextCardsSubTab) {
      setCardsSubTab(nextCardsSubTab);
    }

    if (nextGraphMode) {
      setGraphMode(nextGraphMode);
      setActiveSection(nextGraphMode);
      if (nextGraphMode === "pack-breakdown") {
        setInsightsValueView("pack-paths");
      } else if (nextGraphMode === "value-contribution") {
        setInsightsValueView("value-structure");
      }
    } else if (nextTab === "insights" && graphMode === "historical-trend") {
      setGraphMode("outcome-distribution");
      setActiveSection("outcome-distribution");
    }

    pushSetDetailRouteState({ tab: nextTab, section });

    scrollToSetDetailElement(targetId || getSetDetailFallbackTargetId(nextTab));
  };

  useEffect(() => {
    if (!setDetailMode) {
      return;
    }

    const rawTab = searchParams?.get?.("tab");
    const nextTab = getSetDetailTabParam(searchParams);
    const nextSection = getSetDetailSectionParam(searchParams);
    const rawSectionTarget = isValidSetDetailTab(rawTab) ? SET_DETAIL_SECTION_TARGETS[nextSection] || null : null;
    const sectionTarget = rawSectionTarget?.tab === nextTab ? rawSectionTarget : null;
    const resolvedTab = nextTab;

    setSetDetailTab(resolvedTab);

    if (sectionTarget?.graphMode) {
      setGraphMode(sectionTarget.graphMode);
      setActiveSection(sectionTarget.graphMode);
      if (sectionTarget.graphMode === "pack-breakdown") {
        setInsightsValueView("pack-paths");
      } else if (sectionTarget.graphMode === "value-contribution") {
        setInsightsValueView("value-structure");
      } else if (sectionTarget.graphMode === "simulation-drivers") {
        setInsightsValueView("simulation-drivers");
      }
    } else if (resolvedTab === "insights") {
      setGraphMode("outcome-distribution");
      setActiveSection("outcome-distribution");
    }

    if (!nextSection) {
      return;
    }

    scrollToSetDetailElement(sectionTarget?.targetId || getSetDetailFallbackTargetId(resolvedTab));
  }, [setDetailMode, searchParams]);

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
              frameId = null;
              return;
            }
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

  const packCostValue = toNumber(summary.pack_cost);
  const p95ValueToCostRatio = toNumber(summary.p95_value_to_cost_ratio);
  const p99ValueToCostRatio = toNumber(summary.p99_value_to_cost_ratio);

  const chartMarkers = [
    { key: "pack-cost", label: RIP_COPY.chartMarkers.packCost, value: summary.pack_cost },
    { key: "median", label: RIP_COPY.chartMarkers.typicalPack, value: percentileP50 ?? summary.median_value },
    { key: "mean", label: RIP_COPY.chartMarkers.averagePack, value: summary.mean_value },
    { key: "bad-floor", label: RIP_COPY.chartMarkers.badFloor, value: percentileP5 ?? summary.tail_value_p05 },
    { key: "big-hit", label: RIP_COPY.chartMarkers.bigHit, value: summary.big_hit_threshold },
    {
      key: "big-hit-upside",
      label: RIP_COPY.chartMarkers.bigHitUpside,
      value: packCostValue !== null && p95ValueToCostRatio !== null ? p95ValueToCostRatio * packCostValue : null,
    },
    {
      key: "god-pull-upside",
      label: RIP_COPY.chartMarkers.godPullUpside,
      value: packCostValue !== null && p99ValueToCostRatio !== null ? p99ValueToCostRatio * packCostValue : null,
    },
    { key: "max", label: RIP_COPY.chartMarkers.bestPull, value: summary.max_value },
  ];

  const topScoreRaw = toNumber(summary.relative_pack_score) ?? toNumber(summary.pack_score);
  const displayedTopScore = formatRawScore(topScoreRaw);

  const displayedProfitScore =
    toNumber(summary.relative_profit_score) ?? toNumber(summary.profit_score);
  const displayedSafetyScore =
    toNumber(summary.relative_safety_score) ?? toNumber(summary.safety_score);
  const displayedDesirabilityScore =
    toNumber(summary.relative_desirability_score) ?? toNumber(summary.desirability_score);
  const displayedStabilityScore =
    toNumber(summary.relative_stability_score) ?? toNumber(summary.stability_score);
  const desirabilitySummary = getDesirabilitySummary(summary);
  const topDesirabilityCards = getTopCollectorAppealDrivers(
    explorePayload,
    summary,
    normalizedOpeningDesirability
  );
  const desirabilityOverviewMetrics = getDesirabilityOverviewMetrics(normalizedOpeningDesirability);
  const heroLogoUrl =
    selectedTarget?.logo_image_url || selectedTarget?.hero_image_url || selectedTarget?.symbol_image_url || null;

  const recommendationSummary = packScoreMeta?.summary || interpretation?.packScore || null;
  const recommendationBadge = packScoreMeta?.label || null;
  const recommendationTone = getInterpretationTone({ label: recommendationBadge, rankTier: summary.pack_tier });
  const simpleAverageLossValue = getSimpleAverageLossValue(summary);
  const averageHitValue = getFirstNumericValue(summary, [
    "average_hit_value",
    "average_hit_value_when_hit",
    "hit_average_value",
    "average_value_when_hit",
    "big_pull_average",
    "hit_pack_average_value",
    "average_hit_pack_value",
    "average_pack_value_of_hits",
  ]);
  const setValue = getFirstNumericValue(summary, [
    "simulated_set_value",
    "set_value",
    "total_set_value",
    "total_card_value",
    "set_market_value",
    "collection_value",
    "total_value",
  ]);

  const averageHitValueDisplay = averageHitValue === null ? "Coming soon" : formatCurrency(averageHitValue);
  const setValueDisplay = setValue === null ? "Coming soon" : formatCurrency(setValue);
  const normalizedTopShareForMarket =
    toNumber(summary.top1_ev_share) === null
      ? null
      : toNumber(summary.top1_ev_share) <= 1
      ? toNumber(summary.top1_ev_share) * 100
      : toNumber(summary.top1_ev_share);
  const marketReadSummary = getMarketReadSummary({
    packCost: toNumber(summary.pack_cost),
    averagePackValue: toNumber(summary.mean_value),
    returnRatio: toNumber(meanValueToCostRatio),
    setValue,
    topShare: normalizedTopShareForMarket,
    chaseDepth: toNumber(summary.effective_chase_count),
  });
  const compactMarketReadSummary = getCompactMarketRead({
    packCost: toNumber(summary.pack_cost),
    averagePackValue: toNumber(summary.mean_value),
    returnRatio: toNumber(meanValueToCostRatio),
    setValue,
    topShare: normalizedTopShareForMarket,
    chaseDepth: toNumber(summary.effective_chase_count),
  });
  const simulationCount = summary.simulation_count ?? summary.packs_simulated;
  const openingOutcomesSubtitle = getSimulationContextSubtitle(simulationCount);
  const normalizedHistoryTrendPoints = Array.isArray(historyTrend)
    ? historyTrend.map((row, index) => normalizeHistoryTrendPoint(row, index, null))
    : [];
  const previousTrendPoint =
    normalizedHistoryTrendPoints.length >= 2
      ? normalizedHistoryTrendPoints[normalizedHistoryTrendPoints.length - 2]
      : null;
  const currentAverageLossAmount = getLossAmountFromMeanAndCost(summary.mean_value, summary.pack_cost);
  const previousAverageLossAmount = getLossAmountFromMeanAndCost(
    previousTrendPoint?.meanValue,
    previousTrendPoint?.packCost
  );
  const trendByMetricKey = {
    ripScore: getHistoryMetricTrend({
      metricKey: "ripScore",
      currentValue: topScoreRaw,
      previousPoint: previousTrendPoint,
    }),
    profitScore: getHistoryMetricTrend({
      metricKey: "profitScore",
      currentValue: displayedProfitScore,
      previousPoint: previousTrendPoint,
    }),
    safetyScore: getHistoryMetricTrend({
      metricKey: "safetyScore",
      currentValue: displayedSafetyScore,
      previousPoint: previousTrendPoint,
    }),
    desirabilityScore: getHistoryMetricTrend({
      metricKey: "desirabilityScore",
      currentValue: displayedDesirabilityScore,
      previousPoint: previousTrendPoint,
    }),
    stabilityScore: getHistoryMetricTrend({
      metricKey: "stabilityScore",
      currentValue: displayedStabilityScore,
      previousPoint: previousTrendPoint,
    }),
    packCost: getHistoryMetricTrend({
      metricKey: "packCost",
      currentValue: summary.pack_cost,
      previousPoint: previousTrendPoint,
    }),
    setValue: getHistoryMetricTrend({
      metricKey: "setValue",
      currentValue: setValue,
      previousPoint: previousTrendPoint,
    }),
    averagePackValue: getHistoryMetricTrend({
      metricKey: "meanValue",
      currentValue: summary.mean_value,
      previousPoint: previousTrendPoint,
    }),
    averageHitValue: getHistoryMetricTrend({
      metricKey: "averageHitValue",
      currentValue: averageHitValue,
      previousPoint: previousTrendPoint,
    }),
    averageLoss: getMetricTrend({
      currentValue: currentAverageLossAmount,
      previousValue: previousAverageLossAmount,
      metricKey: "averageLoss",
    }),
    chanceToBeatPackCost: getHistoryMetricTrend({
      metricKey: "probProfit",
      currentValue: normalizeProbability(summary.prob_profit),
      previousPoint: previousTrendPoint,
    }),
    chanceToMissPackCost: getHistoryMetricTrend({
      metricKey: "chanceToMissPackCost",
      currentValue: normalizeProbability(summary.prob_profit) === null ? null : 1 - normalizeProbability(summary.prob_profit),
      previousValue:
        getHistoryMetricValue(previousTrendPoint, "probProfit") === null
          ? null
          : 1 - normalizeProbability(getHistoryMetricValue(previousTrendPoint, "probProfit")),
      direction: "lower",
    }),
    chanceAtBigPull: getHistoryMetricTrend({
      metricKey: "probBigHit",
      currentValue: normalizeProbability(summary.prob_big_hit),
      previousPoint: previousTrendPoint,
    }),
    averageReturnVsCost: getHistoryMetricTrend({
      metricKey: "meanCostRatio",
      currentValue: meanValueToCostRatio,
      previousPoint: previousTrendPoint,
    }),
    typicalReturnVsCost: getHistoryMetricTrend({
      metricKey: "medianCostRatio",
      currentValue: medianValueToCostRatio,
      previousPoint: previousTrendPoint,
    }),
    bigHitUpside: getHistoryMetricTrend({
      metricKey: "p95CostRatio",
      currentValue: summary.p95_value_to_cost_ratio,
      previousPoint: previousTrendPoint,
    }),
    godPullUpside: getHistoryMetricTrend({
      metricKey: "p99ValueToCostRatio",
      currentValue: summary.p99_value_to_cost_ratio,
      previousPoint: previousTrendPoint,
    }),
    typicalPackValue: getHistoryMetricTrend({
      metricKey: "medianValue",
      currentValue: percentileP50 ?? summary.median_value,
      previousPoint: previousTrendPoint,
    }),
    badPackFloorValue: getHistoryMetricTrend({
      metricKey: "tailValueP05",
      currentValue: percentileP5 ?? summary.tail_value_p05,
      previousPoint: previousTrendPoint,
    }),
    averageLossWhenYouMiss: getHistoryMetricTrend({
      metricKey: "expectedLossWhenLosing",
      currentValue: summary.expected_loss_when_losing,
      previousPoint: previousTrendPoint,
    }),
    typicalLossWhenYouMiss: getHistoryMetricTrend({
      metricKey: "medianLossWhenLosing",
      currentValue: summary.median_loss_when_losing,
      previousPoint: previousTrendPoint,
    }),
    worstFivePercentShortfall: getHistoryMetricTrend({
      metricKey: "p05ShortfallToCost",
      currentValue: p05ShortfallToCost,
      previousPoint: previousTrendPoint,
    }),
    outcomeVolatility: getHistoryMetricTrend({
      metricKey: "coefficientOfVariation",
      currentValue: summary.coefficient_of_variation,
      previousPoint: previousTrendPoint,
    }),
    evConcentration: getHistoryMetricTrend({
      metricKey: "hhiEvConcentration",
      currentValue: summary.hhi_ev_concentration,
      previousPoint: previousTrendPoint,
    }),
    chaseDepth: getHistoryMetricTrend({
      metricKey: "effectiveChaseCount",
      currentValue: summary.effective_chase_count,
      previousPoint: previousTrendPoint,
    }),
    top1Share: getHistoryMetricTrend({
      metricKey: "top1Share",
      currentValue: summary.top1_ev_share,
      previousPoint: previousTrendPoint,
    }),
    top3Share: getHistoryMetricTrend({
      metricKey: "top3Share",
      currentValue: summary.top3_ev_share,
      previousPoint: previousTrendPoint,
    }),
    top5Share: getHistoryMetricTrend({
      metricKey: "top5Share",
      currentValue: summary.top5_ev_share,
      previousPoint: previousTrendPoint,
    }),
    bestPull: getHistoryMetricTrend({
      metricKey: "maxValue",
      currentValue: summary.max_value,
      previousPoint: previousTrendPoint,
    }),
  };

  const marketReadMetrics = [
    {
      label: "Set Value",
      rawValue: setValue,
      value: setValueDisplay,
      trend: trendByMetricKey.setValue,
      infoText: "Simulated set value: one priced copy per unique card identity in this simulation universe.",
    },
    {
      label: "Pack Price",
      rawValue: toNumber(summary.pack_cost),
      value: formatCurrency(summary.pack_cost),
      trend: trendByMetricKey.packCost,
      infoText: "Estimated current pack market price used by the simulation.",
    },
    {
      label: "Average Pack Value",
      rawValue: toNumber(summary.mean_value),
      value: formatCurrency(summary.mean_value),
      trend: trendByMetricKey.averagePackValue,
      infoText: SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT,
    },
    {
      label: "Return vs Cost",
      rawValue: toNumber(meanValueToCostRatio),
      value: formatNumber(meanValueToCostRatio, 2),
      trend: trendByMetricKey.averageReturnVsCost,
      infoText: "Modeled average pack value divided by estimated pack market price.",
    },
  ].filter((metric) => metric.rawValue !== null);
  const topPricedCardsResult = getTopPricedCards({
    topMarketCards: topMarketCardsState.cards,
    checklistCards: checklistState.cards,
  });
  const topPricedCards = topPricedCardsResult.cards;
  const hasTopPricedCards = topPricedCards.length > 0;
  const shouldShowTopMarketCards =
    topMarketCardsState.status === "loading" || topMarketCardsState.status === "error" || hasTopPricedCards;
  const topPricedCardsStatus =
    topMarketCardsState.status === "error" && !hasTopPricedCards
      ? "error"
      : hasTopPricedCards
      ? "success"
      : topMarketCardsState.status === "loading" || topMarketCardsState.status === "idle"
      ? "loading"
      : "success";
  const topPricedCardsInfo =
    topPricedCardsResult.source === "topMarketCards"
      ? "Highest priced chase-card variants from the current set calculation, sorted by estimated card market price descending."
      : "Highest checklist card market prices in this set, sorted by estimated card market price descending.";

  const decisionMetrics = [
    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost), trend: trendByMetricKey.packCost },
    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value), trend: trendByMetricKey.averagePackValue },
    { label: RIP_COPY.simpleMetrics.averageHitValue, value: averageHitValueDisplay, trend: trendByMetricKey.averageHitValue },
    { label: RIP_COPY.simpleMetrics.averageLoss, value: formatSignedCurrency(simpleAverageLossValue), trend: trendByMetricKey.averageLoss },
    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }), trend: trendByMetricKey.chanceToBeatPackCost },
    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }), trend: trendByMetricKey.chanceAtBigPull },
  ];
  const primaryDecisionMetricOrder = [
    RIP_COPY.simpleMetrics.currentPackCost,
    RIP_COPY.simpleMetrics.averagePackValue,
    RIP_COPY.simpleMetrics.averageHitValue,
    RIP_COPY.simpleMetrics.averageLoss,
  ];
  const primaryDecisionMetrics = primaryDecisionMetricOrder
    .map((label) => decisionMetrics.find((metric) => metric.label === label))
    .filter(Boolean);
  const secondaryDecisionMetrics = decisionMetrics.filter(
    (metric) => !primaryDecisionMetricOrder.includes(metric.label)
  );
  const technicalScoreMetrics = [
    { label: "Average Return vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
    { label: "Typical Return vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
    { label: "Big Hit Upside", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
    { label: "God Pull Upside", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
    { label: "Outcome Volatility", value: formatNumber(summary.coefficient_of_variation, 2), trend: trendByMetricKey.outcomeVolatility },
    { label: "Value Spread", value: formatNumber(summary.hhi_ev_concentration, 3), trend: trendByMetricKey.evConcentration },
    { label: "Cards Carrying Value", value: formatNumber(summary.effective_chase_count, 2), trend: trendByMetricKey.chaseDepth },
  ];
  const chanceToMissPackCostValue =
    normalizeProbability(summary.prob_profit) === null ? null : 1 - normalizeProbability(summary.prob_profit);
  const profitPillarMetrics = [
    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost), trend: trendByMetricKey.packCost },
    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value), trend: trendByMetricKey.averagePackValue },
    { label: RIP_COPY.simpleMetrics.averageLoss, value: formatSignedCurrency(simpleAverageLossValue), trend: trendByMetricKey.averageLoss },
    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }), trend: trendByMetricKey.chanceToBeatPackCost },
    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }), trend: trendByMetricKey.chanceAtBigPull },
    { label: "Average Return vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
    { label: "Typical Return vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
    { label: "Big Hit Upside", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
    { label: "God Pull Upside", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
  ];
  const safetyPillarMetrics = [
    { label: "Typical Pack Value", value: formatCurrency(percentileP50 ?? summary.median_value), trend: trendByMetricKey.typicalPackValue, infoText: getMetricTooltip("Typical Pack Value") },
    { label: "Bad Pack Floor Value", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.badPackFloorValue, infoText: getMetricTooltip("Bad Pack Floor Value") },
    { label: "Chance to Miss Pack Cost", value: formatPercent(chanceToMissPackCostValue, { probability: true }), trend: trendByMetricKey.chanceToMissPackCost, infoText: getMetricTooltip("Chance to Miss Pack Cost") },
    { label: "Average Loss When You Miss", value: formatLossCurrency(summary.expected_loss_when_losing), trend: trendByMetricKey.averageLossWhenYouMiss, infoText: getMetricTooltip("Average Loss When You Miss") },
    { label: "Typical Loss When You Miss", value: formatLossCurrency(summary.median_loss_when_losing), trend: trendByMetricKey.typicalLossWhenYouMiss, infoText: getMetricTooltip("Typical Loss When You Miss") },
    { label: "Worst 5% Outcome", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.worstFivePercentShortfall?.trend === "unknown" ? trendByMetricKey.badPackFloorValue : trendByMetricKey.worstFivePercentShortfall, infoText: getMetricTooltip("Worst 5% Outcome") },
  ];
  const desirabilityPillarMetrics = [
    ...desirabilityOverviewMetrics,
    {
      label: "Top Collector Appeal Drivers",
      value: null,
      content: <TopDesirabilityDrivers drivers={topDesirabilityCards} />,
      trend: null,
    },
  ];
  const stabilityPillarMetrics = [
    { label: "Cards Carrying Value", value: formatNumber(summary.effective_chase_count, 2), trend: trendByMetricKey.chaseDepth },
    { label: "Top Chase Share", value: formatPercent(summary.top1_ev_share), trend: trendByMetricKey.top1Share },
    { label: "Value Spread", value: formatNumber(summary.hhi_ev_concentration, 3), trend: trendByMetricKey.evConcentration },
    { label: "Outcome Volatility", value: formatNumber(summary.coefficient_of_variation, 2), trend: trendByMetricKey.outcomeVolatility },
    { label: "Top 3 Share", value: formatPercent(summary.top3_ev_share), trend: trendByMetricKey.top3Share },
    { label: "Top 5 Share", value: formatPercent(summary.top5_ev_share), trend: trendByMetricKey.top5Share },
  ];
  const ripBreakdownInfo =
    "RIP Score combines profit, safety, desirability, and stability into a collector-facing opening score.";
  const ripPillarTiles = [
    {
      title: "Profit",
      score: displayedProfitScore,
      scoreTrend: trendByMetricKey.profitScore,
      rankValue: summary.profit_rank,
      rankTier: summary.profit_tier,
      statusLabel: getPillarStatusLabel({ label: profitMeta?.label || pillarMetaByKey[PILLAR_TITLE_TO_KEY.Profit]?.state, score: displayedProfitScore }),
      highlight: getPillarSignalHighlight("Profit", displayedProfitScore),
      metrics: profitPillarMetrics,
      infoText: getFormattedTooltip("Profit"),
    },
    {
      title: "Safety",
      score: displayedSafetyScore,
      scoreTrend: trendByMetricKey.safetyScore,
      rankValue: summary.safety_rank,
      rankTier: summary.safety_tier,
      statusLabel: getPillarStatusLabel({ label: safetyMeta?.label || pillarMetaByKey[PILLAR_TITLE_TO_KEY.Safety]?.state, score: displayedSafetyScore }),
      highlight: getPillarSignalHighlight("Safety", displayedSafetyScore),
      metrics: safetyPillarMetrics,
      infoText: getFormattedTooltip("Safety"),
    },
    {
      title: "Desirability",
      score: displayedDesirabilityScore,
      scoreTrend: trendByMetricKey.desirabilityScore,
      rankValue: summary.desirability_rank,
      rankTier: summary.desirability_tier,
      statusLabel: getPillarStatusLabel({ label: desirabilityMeta?.label || pillarMetaByKey[PILLAR_TITLE_TO_KEY.Desirability]?.state, score: displayedDesirabilityScore }),
      highlight: getPillarSignalHighlight("Desirability", displayedDesirabilityScore),
      metrics: desirabilityPillarMetrics,
      infoText: SIMPLE_PILLAR_INFO_COPY.Desirability,
    },
    {
      title: "Stability",
      score: displayedStabilityScore,
      scoreTrend: trendByMetricKey.stabilityScore,
      rankValue: summary.stability_rank,
      rankTier: summary.stability_tier,
      statusLabel: getPillarStatusLabel({ label: stabilityMeta?.label || pillarMetaByKey[PILLAR_TITLE_TO_KEY.Stability]?.state, score: displayedStabilityScore }),
      highlight: getPillarSignalHighlight("Stability", displayedStabilityScore),
      metrics: stabilityPillarMetrics,
      infoText: getFormattedTooltip("Stability"),
    },
  ];
  const overviewPillarSignals = ripPillarTiles.map(({ metrics, ...signal }) => signal);

  const handleTargetIdChange = (nextTargetId, options = {}) => {
    if (!nextTargetId) {
      return;
    }

    if (typeof options.closeToolsPanel === "function") {
      options.closeToolsPanel();
    }

    const nextHref = setDetailMode
      ? appendSetDetailIntentToHref(targetHrefById?.[nextTargetId] || null, { tab: setDetailTab })
      : targetHrefById?.[nextTargetId] || null;

    startTransition(() => {
      if (nextHref) {
        router.push(nextHref);
        return;
      }

      const nextParams = new URLSearchParams(searchParams?.toString() || "");
      nextParams.set("target_type", requestedTargetType || "set");
      nextParams.set("target_id", nextTargetId);
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

  useEffect(() => {
    const shouldLoadChecklist =
      setDetailMode &&
      ((setDetailTab === "market" || setDetailTab === "overview") ||
        (setDetailTab === "cards" && cardsSubTab === "checklist"));

    if (!shouldLoadChecklist) {
      return undefined;
    }

    const setId = String(requestedTargetId || "").trim();
    if (!setId) {
      setChecklistState({ status: "empty", cards: [], error: null });
      return undefined;
    }

    const cached = checklistCacheRef.current.get(setId);
    if (cached) {
      setChecklistState({ status: "success", cards: cached, error: null });
      return undefined;
    }

    let isCancelled = false;
    setChecklistState((previous) => ({
      status: "loading",
      cards: previous.status === "success" ? previous.cards : [],
      error: null,
    }));

    getPokemonSetCards(setId)
      .then((payload) => {
        if (isCancelled) {
          return;
        }
        const cards = Array.isArray(payload?.cards) ? payload.cards : [];
        checklistCacheRef.current.set(setId, cards);
        setChecklistState({
          status: cards.length > 0 ? "success" : "empty",
          cards,
          error: null,
        });
      })
      .catch((error) => {
        if (isCancelled) {
          return;
        }
        setChecklistState({
          status: "error",
          cards: [],
          error: error?.message || "Unable to load cards for this set.",
        });
      });

    return () => {
      isCancelled = true;
    };
  }, [setDetailMode, setDetailTab, cardsSubTab, requestedTargetId]);

  useEffect(() => {
    const shouldLoadMarketData =
      setDetailMode && setDetailTab === "overview";

    if (!shouldLoadMarketData) {
      return undefined;
    }

    const setId = String(requestedTargetId || "").trim();
    if (!setId) {
      setTopMarketCardsState({ status: "empty", cards: [], error: null, meta: null });
      setSetValueHistoryState({ status: "empty", history: [], error: null, meta: null });
      return undefined;
    }

    const cachedTopCards = topMarketCardsCacheRef.current.get(setId);
    if (cachedTopCards) {
      setTopMarketCardsState({
        status: cachedTopCards.cards.length > 0 ? "success" : "empty",
        cards: cachedTopCards.cards,
        error: null,
        meta: cachedTopCards.meta,
      });
    } else {
      let isTopCardsCancelled = false;
      setTopMarketCardsState((previous) => ({
        status: "loading",
        cards: previous.status === "success" ? previous.cards : [],
        error: null,
        meta: previous.meta,
      }));

      getPokemonSetTopMarketCards(setId, { limit: 10 })
        .then((payload) => {
          if (isTopCardsCancelled) {
            return;
          }
          const cards = Array.isArray(payload?.cards) ? payload.cards : [];
          const cacheEntry = { cards, meta: payload?.meta || null };
          topMarketCardsCacheRef.current.set(setId, cacheEntry);
          setTopMarketCardsState({
            status: cards.length > 0 ? "success" : "empty",
            cards,
            error: null,
            meta: cacheEntry.meta,
          });
        })
        .catch((error) => {
          if (isTopCardsCancelled) {
            return;
          }
          setTopMarketCardsState({
            status: "error",
            cards: [],
            error: error?.message || "Unable to load market cards for this set.",
            meta: null,
          });
        });

      return () => {
        isTopCardsCancelled = true;
      };
    }

    return undefined;
  }, [setDetailMode, setDetailTab, requestedTargetId]);

  useEffect(() => {
    const shouldLoadValueHistory =
      setDetailMode && setDetailTab === "overview";

    if (!shouldLoadValueHistory) {
      return undefined;
    }

    const setId = String(requestedTargetId || "").trim();
    if (!setId) {
      setSetValueHistoryState({
        status: "empty",
        history: [],
        historiesByScope: {},
        availableScopes: SET_VALUE_SCOPE_OPTIONS,
        error: null,
        meta: null,
      });
      return undefined;
    }

    const cached = setValueHistoryCacheRef.current.get(setId);
    if (cached) {
      setSetValueHistoryState({
        status: cached.history.length > 0 ? "success" : "empty",
        history: cached.history,
        historiesByScope: cached.historiesByScope || {},
        availableScopes: cached.availableScopes || SET_VALUE_SCOPE_OPTIONS,
        error: null,
        meta: cached.meta,
      });
      return undefined;
    }

    let isCancelled = false;
    setSetValueHistoryState((previous) => ({
      status: "loading",
      history: previous.status === "success" ? previous.history : [],
      historiesByScope: previous.status === "success" ? previous.historiesByScope : {},
      availableScopes: previous.availableScopes || SET_VALUE_SCOPE_OPTIONS,
      error: null,
      meta: previous.meta,
    }));

    Promise.allSettled(
      SET_VALUE_SCOPE_OPTIONS.map((scopeOption) =>
        getPokemonSetValueHistory(setId, {
          days: SET_VALUE_HISTORY_REQUEST_DAYS,
          scope: scopeOption.key,
        }).then((payload) => ({ scope: scopeOption.key, payload }))
      )
    )
      .then((results) => {
        if (isCancelled) {
          return;
        }
        const fulfilled = results
          .filter((result) => result.status === "fulfilled")
          .map((result) => result.value);
        if (fulfilled.length === 0) {
          const rejected = results.find((result) => result.status === "rejected");
          throw rejected?.reason || new Error("Unable to load set value history for this set.");
        }

        const historiesByScope = {};
        const availableScopeKeys = new Set();
        let meta = null;
        fulfilled.forEach(({ scope, payload }) => {
          const history = Array.isArray(payload?.history) ? payload.history : [];
          historiesByScope[scope] = history;
          if (history.length > 0) {
            availableScopeKeys.add(scope);
          }
          if (!meta || scope === "standard") {
            meta = payload?.meta || null;
          }
          (payload?.meta?.availableScopes || []).forEach((entry) => {
            if (entry?.key) {
              availableScopeKeys.add(entry.key);
            }
          });
        });

        const availableScopes = SET_VALUE_SCOPE_OPTIONS.filter((entry) =>
          availableScopeKeys.size === 0 ? true : availableScopeKeys.has(entry.key)
        );
        const history = historiesByScope.standard || [];
        const hasAnyHistory = Object.values(historiesByScope).some((scopeHistory) => scopeHistory.length > 0);
        const cacheEntry = { history, historiesByScope, availableScopes, meta };
        setValueHistoryCacheRef.current.set(setId, cacheEntry);
        setSetValueHistoryState({
          status: hasAnyHistory ? "success" : "empty",
          history,
          historiesByScope,
          availableScopes,
          error: null,
          meta: cacheEntry.meta,
        });
      })
      .catch((error) => {
        if (isCancelled) {
          return;
        }
        setSetValueHistoryState({
          status: "error",
          history: [],
          historiesByScope: {},
          availableScopes: SET_VALUE_SCOPE_OPTIONS,
          error: error?.message || "Unable to load set value history for this set.",
          meta: null,
        });
      });

    return () => {
      isCancelled = true;
    };
  }, [setDetailMode, setDetailTab, requestedTargetId]);

  const setDetailSidebarContent = (
    <SetPageNavigationRail
      targets={targets}
      requestedTargetId={requestedTargetId}
      selectedTarget={selectedTarget}
      selectedName={selectedName}
      isPending={isPending}
      activeTab={setDetailTab}
      activeCardsSubTab={cardsSubTab}
      activeGraphMode={graphMode}
      showTopMarketCards={shouldShowTopMarketCards}
      onTargetChange={handleTargetChange}
      onNavigate={handleSetDetailNavSelect}
    />
  );

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
        profileBaseHref={profileBaseHref}
        mode="public"
        sectionItems={[]}
        mobileNavItems={[]}
        desktopSidebarContent={setDetailMode ? setDetailSidebarContent : desktopSidebarContent}
        mobileToolsPanelContent={setDetailMode ? null : renderMobileToolsPanelContent}
        mobileToolsTitle="Explore Filters & Navigation"
        mobileToolsDescription="Switch TCG and set filters."
        mobileToolsPanelAriaLabel="Explore filters and navigation"
        mobileToolsTriggerLabel="Filters & Tools"
        mobileToolsTriggerTitle="Open filters and navigation"
        useFloatingToolsOnTablet={!setDetailMode}
        forceCompactToolsBelow2xl={!setDetailMode}
        centerContentIgnoringSidebar={!setDetailMode}
        desktopSidebarClassName={setDetailMode ? "xl:w-[244px] xl:min-w-[244px] xl:pl-4 xl:pr-3" : ""}
        desktopContentOffsetClassName="xl:flex xl:justify-center"
        contentShellClassName={setDetailMode ? "lg:w-full lg:max-w-[1440px] lg:px-4 2xl:px-5" : undefined}
        wrapDesktopContentInFrame={false}
        mobileBottomNavVariant="flat"
        mobileBottomNavContent={() => (
          !setDetailMode && effectiveViewMode === "expert" ? (
            <CompactBottomSectionNav
              activeSection={activeSection}
              onSelect={handleSectionSelect}
            />
          ) : null
        )}
      >
        <div
          className={`dashboard-container w-full max-w-full min-w-0 !p-0 !bg-transparent !border-0 !rounded-none ${
            setDetailMode
              ? "mx-auto max-w-[1400px] space-y-4 xl:!p-0 xl:!bg-transparent xl:!rounded-none xl:!border-0"
              : "space-y-8 xl:!p-6 xl:!bg-[rgba(255,255,255,0.02)] xl:!rounded-2xl xl:!border"
          }`}
        >
        {pageError ? (
          <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6">
            <p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p>
            <p className="mt-2 text-sm text-red-300">{pageError}</p>
          </section>
        ) : null}

        {!pageError && explorePayload ? (
          <>
            {setDetailMode ? (
              <>
                <section className="page-hero-panel relative overflow-visible rounded-xl px-4 py-4 md:rounded-2xl md:px-6 md:py-5">
                  <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-xl md:rounded-2xl">
                    {heroLogoUrl ? (
                      <div className="absolute left-1/2 top-1/2 h-[112%] w-[112%] -translate-x-1/2 -translate-y-1/2 select-none">
                        <img
                          src={heroLogoUrl}
                          alt=""
                          aria-hidden="true"
                          className="h-full w-full object-contain opacity-[0.08] [filter:drop-shadow(0_0_20px_rgba(148,163,184,0.12))]"
                          loading="lazy"
                          decoding="async"
                        />
                      </div>
                    ) : null}
                  </div>

                  <div className="relative z-10 mx-auto flex w-full max-w-[1360px] flex-col gap-4">
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)] lg:items-stretch">
                      <div className="flex h-full min-h-full flex-col gap-3">
                      <div ref={heroSetPickerRef} data-hero-picker className="relative z-20 rounded-xl border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--surface-page)_78%,transparent)] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03),0_8px_20px_rgba(2,6,23,0.12)] backdrop-blur-[2px]">
                        <div className="space-y-4">
                          <div>
                            <button
                              type="button"
                              onClick={() => setHeroSetPickerOpen((open) => !open)}
                              disabled={isPending || targets.length === 0}
                              aria-expanded={heroSetPickerOpen}
                              aria-haspopup="listbox"
                              aria-controls="hero-set-picker-list"
                              className="flex w-full min-w-0 items-start justify-between gap-3 rounded-lg text-left text-xl font-semibold text-[var(--text-primary)] transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] md:text-2xl disabled:cursor-not-allowed disabled:opacity-90"
                              title={targets.length > 0 ? "Switch set" : "No sets available"}
                            >
                              <span className="min-w-0 flex-1 whitespace-normal break-words leading-tight">{selectedName}</span>
                              <span aria-hidden="true" className="mt-1 inline-flex h-6 w-6 flex-none items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/70">
                                <svg
                                  aria-hidden="true"
                                  viewBox="0 0 20 20"
                                  className={`h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform ${heroSetPickerOpen ? "rotate-180" : ""}`}
                                  fill="currentColor"
                                >
                                  <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                                </svg>
                              </span>
                            </button>

                            {heroSetPickerOpen ? (
                              <div
                                id="hero-set-picker-list"
                                role="listbox"
                                aria-label="Available sets"
                                className="index-scrollbar absolute left-0 top-[calc(100%+0.5rem)] z-50 max-h-56 w-full max-w-full overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1.5 text-left shadow-[0_14px_34px_rgba(0,0,0,0.45)]"
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
                                      className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm leading-5 transition-colors ${
                                        isSelected
                                          ? "bg-[var(--surface-page)] text-[var(--text-primary)]"
                                          : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)]/70 hover:text-[var(--text-primary)]"
                                      }`}
                                    >
                                      <span className="min-w-0 flex-1 truncate whitespace-nowrap">{target.name}</span>
                                      {isSelected ? (
                                        <span className="shrink-0 text-xs font-medium text-[var(--accent)]">Current</span>
                                      ) : null}
                                    </button>
                                  );
                                })}
                              </div>
                            ) : null}
                          </div>

                          <div className="space-y-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{RIP_COPY.scoreLabel}</p>
                            <div className="flex items-end gap-2">
                              <span className="inline-flex items-end gap-1.5 text-5xl font-semibold leading-none tracking-[-0.04em] text-[var(--text-primary)] md:text-6xl">
                                <span>{displayedTopScore}</span>
                                <span className="pb-1 text-xs font-medium tracking-normal text-[var(--text-secondary)]">/100</span>
                                <TrendIndicator trend={trendByMetricKey.ripScore} className="mb-1 md:mb-1.5" />
                              </span>
                            </div>
                            <ScoreMeter score={topScoreRaw} rankTier={summary.pack_tier} />
                            <div className="flex flex-wrap items-center gap-2">
                              <RankBadge
                                rank={summary.pack_tier}
                                label="Rank"
                                size="supporting"
                                title={
                                  summary.pack_rank === null || summary.pack_rank === undefined
                                    ? "Rank unavailable"
                                    : `Rank #${summary.pack_rank}`
                                }
                              />
                              <RecommendationBadge label={recommendationBadge} rankTier={summary.pack_tier} />
                            </div>
                            <button
                              type="button"
                              onClick={() => handleSetDetailNavSelect({ tab: "insights", section: "rip-score", targetId: "set-detail-rip-score" })}
                              className="inline-flex w-fit items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-1.5 text-xs font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                            >
                              View RIP Breakdown
                            </button>
                          </div>
                        </div>
                      </div>

                      <div className="flex min-h-[8.25rem] flex-1 flex-col rounded-xl border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--surface-page)_78%,transparent)] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03),0_8px_20px_rgba(2,6,23,0.12)] backdrop-blur-[2px]">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[color:color-mix(in_srgb,var(--text-primary)_72%,var(--text-secondary))]">Set Value</p>
                          <InfoPopover text="Simulated set value: one priced copy per unique card identity in this simulation universe. Variant and pattern rows are collapsed, so future canonical checklist pricing may differ." />
                        </div>
                        <p className="mt-2 inline-flex items-center gap-1.5 text-lg font-bold text-[var(--text-primary)] [text-shadow:0_1px_1px_rgba(2,6,23,0.18)]">
                          <span>{setValueDisplay}</span>
                          <TrendIndicator trend={trendByMetricKey.setValue} className="translate-y-px" />
                        </p>
                      </div>
                      </div>

                      <div className="flex h-full flex-col justify-between gap-2.5">
                        <div
                          className="rounded-xl border-l-2 border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-4 py-3"
                          style={getCalloutAccentStyle({ label: recommendationBadge, rankTier: summary.pack_tier })}
                        >
                          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{RIP_COPY.recommendationLabel}</p>
                          <p className="mt-1.5 text-sm text-[var(--text-primary)]">{recommendationSummary || "No interpretation summary is available for this set yet."}</p>
                        </div>

                        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                          {decisionMetrics.map((metric) => (
                            <HeroMetricTile key={`set-compact-${metric.label}`} label={metric.label} value={metric.value} trend={metric.trend} />
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <div id="set-detail-content" className="scroll-mt-24 md:scroll-mt-28">
                  <SectionViewTabs
                    className="mt-2"
                    value={setDetailTab}
                    onChange={handleSetDetailTabChange}
                    variant="primary"
                    options={[
                      { value: "overview", label: "Overview" },
                      { value: "cards", label: "Cards" },
                      { value: "pull-rates", label: "Pull Rates" },
                      { value: "insights", label: "Insights" },
                    ]}
                  />
                </div>

                {setDetailTab === "overview" ? (
                  <section id="set-detail-overview" className="scroll-mt-24 space-y-5 md:scroll-mt-28">
                    <div id="set-detail-overview-performance" className="scroll-mt-24 grid gap-5 lg:grid-cols-[minmax(20rem,1fr)_minmax(0,1.85fr)] lg:items-stretch md:scroll-mt-28">
                      <div className="min-w-0 lg:h-full">
                        <SetValueTrendCard
                          history={setValueHistoryState.history}
                          historiesByScope={setValueHistoryState.historiesByScope}
                          availableScopes={setValueHistoryState.availableScopes}
                          status={setValueHistoryState.status}
                          error={setValueHistoryState.error}
                        />
                      </div>
                      <div className="min-w-0 lg:h-full">
                        <SectionCard
                          title="Performance vs Cost"
                          titleInfoText="Compares current pack price against modeled pack value and recent performance when history is available."
                          className="flex h-full flex-col"
                          bodyClassName="flex min-h-0 flex-1 flex-col"
                        >
                          <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} summary={summary} flush />
                        </SectionCard>
                      </div>
                    </div>

                    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.85fr)_minmax(20rem,1fr)] lg:items-start">
                      {shouldShowTopMarketCards ? (
                        <div id="set-detail-top-market-cards" className="min-w-0 scroll-mt-24 md:scroll-mt-28">
                          <TopChaseCardsModule
                            cards={topPricedCards}
                            status={topPricedCardsStatus}
                            error={topMarketCardsState.error}
                            infoText={topPricedCardsInfo}
                          />
                        </div>
                      ) : null}

                      <div id="set-detail-set-intelligence" className="min-w-0 scroll-mt-24 md:scroll-mt-28">
                        <DecisionSignalsCard
                          pillarSignals={overviewPillarSignals}
                          summary={summary}
                          setIntelligenceMeta={interpretationMeta?.set_intelligence}
                        />
                      </div>
                    </div>
                  </section>
                ) : null}

                {setDetailTab === "cards" ? (
                  <section id="set-detail-cards" className="scroll-mt-24 space-y-5 rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[linear-gradient(180deg,rgba(15,23,42,0.82),rgba(2,6,23,0.68))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_22px_54px_rgba(2,6,23,0.28)] backdrop-blur-md md:scroll-mt-28 md:p-6">
                    <SectionViewTabs
                      value={cardsSubTab}
                      onChange={setCardsSubTab}
                      variant="secondary"
                      options={[
                        { value: "checklist", label: "All Cards" },
                      ]}
                    />

                    {cardsSubTab === "checklist" ? (
                      <div className="min-w-0">
                        {checklistState.status === "loading" ? (
                          <p className="text-sm text-[var(--text-secondary)]">Loading cards...</p>
                        ) : null}

                        {checklistState.status === "error" ? (
                          <p className="text-sm text-red-300">{checklistState.error || "Unable to load cards for this set."}</p>
                        ) : null}

                        {checklistState.status === "empty" ? (
                          <p className="text-sm text-[var(--text-secondary)]">No cards found for this set.</p>
                        ) : null}

                        {checklistState.status === "success" ? (
                          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
                            {checklistState.cards.map((card) => (
                              <ChecklistCardTile
                                key={`${card.id || card.cardNumber || card.name}`}
                                card={card}
                              />
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {setDetailTab === "pull-rates" ? (
                  <section id="set-detail-pull-rates" className="scroll-mt-24 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/70 p-4 md:scroll-mt-28 md:p-5">
                    {pullRateAssumptions ? (
                      <PullRateAssumptionsCard pullRateAssumptions={pullRateAssumptions} embedded />
                    ) : (
                      <p className="text-sm text-[var(--text-secondary)]">Pull-rate data coming soon for this set.</p>
                    )}
                  </section>
                ) : null}
              </>
            ) : null}

            {!setDetailMode || setDetailTab === "insights" ? (
              <>
            {!setDetailMode ? (
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
                        <div className="inline-flex items-end gap-1.5 leading-none">
                          <span className="text-[clamp(3.25rem,10vw,5rem)] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                            {displayedTopScore}
                          </span>
                          <span className="pb-2 text-sm font-medium text-[var(--text-secondary)] sm:pb-3">/100</span>
                          <TrendIndicator trend={trendByMetricKey.ripScore} className="mb-2 sm:mb-3" />
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

                    <div className="mx-auto mt-5 w-full max-w-5xl text-left">
                      {effectiveViewMode === "simple" ? (
                        <>
                          <div className="hidden lg:block">
                            <div className="mb-3 flex items-center gap-2">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
                              <InfoPopover text="Core decision metrics first. Expand to view more context metrics." />
                            </div>
                            <div className="grid gap-2 sm:grid-cols-3">
                              {primaryDecisionMetrics.map((metric) => (
                                <HeroMetricTile key={metric.label} label={metric.label} value={metric.value} trend={metric.trend} />
                              ))}
                            </div>
                            {secondaryDecisionMetrics.length > 0 ? (
                              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                {secondaryDecisionMetrics.map((metric) => (
                                  <HeroMetricTile key={metric.label} label={metric.label} value={metric.value} trend={metric.trend} />
                                ))}
                              </div>
                            ) : null}
                          </div>

                          <MobileMetricAccordion
                            title="Metrics"
                            defaultOpen={false}
                            style={{ overflowAnchor: "none" }}
                            preserveViewportOnToggle
                          >
                            <div className="mb-3 flex items-center gap-2">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
                              <InfoPopover text="Core decision metrics first. Expand to view more context metrics." />
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {primaryDecisionMetrics.map((metric) => (
                                <HeroMetricTile key={`simple-mobile-${metric.label}`} label={metric.label} value={metric.value} trend={metric.trend} />
                              ))}
                              {secondaryDecisionMetrics.map((metric) => (
                                <HeroMetricTile key={`simple-mobile-secondary-${metric.label}`} label={metric.label} value={metric.value} trend={metric.trend} />
                              ))}
                            </div>
                          </MobileMetricAccordion>

                          <div className="mt-4 grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-4 md:gap-3">
                            <SimplePillarSummaryCard
                              title="Profit"
                              rankTier={summary.profit_tier}
                              infoText={SIMPLE_PILLAR_INFO_COPY.Profit}
                              sectionMeta={profitMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Profit]}
                              fallbackSummary={interpretation?.profit}
                            />
                            <SimplePillarSummaryCard
                              title="Safety"
                              rankTier={summary.safety_tier}
                              infoText={SIMPLE_PILLAR_INFO_COPY.Safety}
                              sectionMeta={safetyMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Safety]}
                              fallbackSummary={interpretation?.safety}
                            />
                            <SimplePillarSummaryCard
                              title="Desirability"
                              rankTier={summary.desirability_tier}
                              infoText={SIMPLE_PILLAR_INFO_COPY.Desirability}
                              sectionMeta={desirabilityMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Desirability]}
                              fallbackSummary={desirabilitySummary}
                            />
                            <SimplePillarSummaryCard
                              title="Stability"
                              rankTier={summary.stability_tier}
                              infoText={SIMPLE_PILLAR_INFO_COPY.Stability}
                              sectionMeta={stabilityMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Stability]}
                              fallbackSummary={interpretation?.stability}
                            />
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="hidden lg:block">
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
                                trend={metric.trend}
                                infoText={metric.infoText || getMetricTooltip(metric.label)}
                              />
                            ))}
                          </div>

                          <MobileMetricAccordion
                            title="Metrics"
                            defaultOpen={false}
                            style={{ overflowAnchor: "none" }}
                            preserveViewportOnToggle
                          >
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                              <div className="flex items-center gap-2">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Metrics</p>
                                <InfoPopover text="Overview shows collector-friendly metrics. Score Details shows the technical inputs behind the score." />
                              </div>
                              <MetricViewToggle metricView={heroMetricView} onChange={setHeroMetricView} />
                            </div>
                            {(heroMetricView === "overview" ? decisionMetrics : technicalScoreMetrics).map((metric) => (
                              <MetricRow
                                key={`expert-mobile-${metric.label}`}
                                label={metric.label}
                                value={metric.value}
                                trend={metric.trend}
                                infoText={metric.infoText || getMetricTooltip(metric.label)}
                              />
                            ))}
                          </MobileMetricAccordion>
                        </>
                      )}
                    </div>

                    {effectiveViewMode === "expert" ? (
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
            ) : null}

            {effectiveViewMode === "simple" ? (
              <SetIntelligenceSection
                summary={summary}
                simpleMode
                setIntelligenceMeta={interpretationMeta?.set_intelligence}
              />
            ) : null}

            {effectiveViewMode === "simple" ? (
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

            {setDetailMode ? (
              <section id="set-detail-insights" className="scroll-mt-24 space-y-4 pt-0 md:scroll-mt-28">
                <RipScoreBreakdownModule
                  score={topScoreRaw}
                  scoreTrend={trendByMetricKey.ripScore}
                  rankTier={summary.pack_tier}
                  rankValue={summary.pack_rank}
                  verdict={recommendationBadge}
                  explanation={recommendationSummary}
                  pillars={ripPillarTiles}
                  titleInfoText={ripBreakdownInfo}
                />

                <section id={ANALYSIS_SECTION_ID} className="scroll-mt-24 md:scroll-mt-28">
                  <SectionCard
                    title="Opening Outcomes"
                    className="min-h-[38rem]"
                    bodyClassName="min-h-[32rem]"
                    subtitle={activeInsightsGraphMode === "outcome-distribution" ? openingOutcomesSubtitle : null}
                    titleInfoText={
                      activeInsightsGraphMode === "value-contribution"
                        ? rarityContributionInfo
                        : activeInsightsGraphMode === "simulation-drivers"
                        ? "Cards contributing most to modeled pack value after pull odds are applied."
                        : activeInsightsGraphMode === "pack-breakdown"
                        ? "Simulation pack paths and normal pack states used by this set model."
                        : outcomeDistributionInfo
                    }
                  >
                    <SectionViewTabs
                      className="mb-4"
                      value={activeInsightsGraphMode}
                      onChange={(nextView) => {
                        setGraphMode(nextView);
                        setActiveSection(nextView);
                        if (nextView === "pack-breakdown") {
                          setInsightsValueView("pack-paths");
                        } else if (nextView === "value-contribution") {
                          setInsightsValueView("value-structure");
                        } else if (nextView === "simulation-drivers") {
                          setInsightsValueView("simulation-drivers");
                        }
                      }}
                      variant="secondary"
                      options={[
                        { value: "outcome-distribution", label: "Outcome Distribution" },
                        { value: "simulation-drivers", label: "Simulation Drivers" },
                        { value: "value-contribution", label: "Value Structure" },
                        { value: "pack-breakdown", label: "Pack Paths" },
                      ]}
                    />

                    {activeInsightsGraphMode === "simulation-drivers" ? (
                      <div id="set-detail-simulation-drivers" className="max-h-[32rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">
                        <InterpretationInsight
                          sectionMeta={topEvDriversMeta}
                          fallbackSummary={collectorFriendlyText(interpretation?.topEvDrivers)}
                          compact
                          showEvidence={false}
                          className="mb-3"
                        />
                        <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} condensed />
                      </div>
                    ) : activeInsightsGraphMode === "value-contribution" ? (
                      <div id="set-detail-value-structure" className="max-h-[32rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">
                        <InterpretationInsight
                          sectionMeta={rarityContributionMeta}
                          fallbackSummary={collectorFriendlyText(interpretation?.rarityContribution)}
                          compact
                          showEvidence
                          maxEvidence={4}
                          className="mb-3"
                        />
                        <RarityContributionContent rankings={rankings} condensed />
                      </div>
                    ) : activeInsightsGraphMode === "pack-breakdown" ? (
                      <div id="set-detail-pack-breakdown" className="max-h-[32rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">
                        <PackBreakdownContent
                          packPaths={ripStatistics?.pack_paths}
                          normalStateRows={normalStateRows}
                          evidenceRows={packBreakdownEvidenceRows}
                          condensed
                        />
                      </div>
                    ) : (
                      <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
                    )}
                  </SectionCard>
                </section>
              </section>
            ) : null}

            {effectiveViewMode === "expert" && !setDetailMode ? (
            <section className="scroll-mt-24 space-y-4 pt-4 md:scroll-mt-28">
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
                {/* Expert pillar metrics: Overview should be user-readable outcomes; Details should prioritize direct score inputs or close precursors. Context rows are allowed only when they clarify pillar behavior. Do not reuse hero Score Details mappings for pillar Details without ownership audit. */}
                <ScorePillarCard
                  title="Profit"
                  score={displayedProfitScore}
                  scoreTrend={trendByMetricKey.profitScore}
                  rankValue={summary.profit_rank}
                  rankTier={summary.profit_tier}
                  rankLabel="Profit Rank"
                  sectionMeta={profitMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Profit")}
                  simpleMetrics={[
                    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost), trend: trendByMetricKey.packCost },
                    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value), trend: trendByMetricKey.averagePackValue },
                    { label: RIP_COPY.simpleMetrics.averageLoss, value: formatSignedCurrency(simpleAverageLossValue), trend: trendByMetricKey.averageLoss },
                    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }), trend: trendByMetricKey.chanceToBeatPackCost },
                    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }), trend: trendByMetricKey.chanceAtBigPull },
                  ]}
                  advancedMetrics={[
                    { label: "Average Return vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
                    { label: "Typical Return vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
                    { label: "Big Hit Upside", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
                    { label: "God Pull Upside", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={displayedSafetyScore}
                  scoreTrend={trendByMetricKey.safetyScore}
                  rankValue={summary.safety_rank}
                  rankTier={summary.safety_tier}
                  rankLabel="Safety Rank"
                  sectionMeta={safetyMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Safety")}
                  simpleMetrics={[
                    { label: "Typical Pack Value", value: formatCurrency(percentileP50 ?? summary.median_value), trend: trendByMetricKey.typicalPackValue, infoText: getMetricTooltip("Typical Pack Value") },
                    { label: "Bad Pack Floor Value", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.badPackFloorValue, infoText: getMetricTooltip("Bad Pack Floor Value") },
                    { label: "Chance to Miss Pack Cost", value: formatPercent(1 - (toNumber(summary.prob_profit) > 1 ? toNumber(summary.prob_profit) / 100 : toNumber(summary.prob_profit)), { probability: true }), trend: trendByMetricKey.chanceToMissPackCost, infoText: getMetricTooltip("Chance to Miss Pack Cost") },
                  ]}
                  advancedMetrics={[
                    { label: "Average Loss When You Miss", value: formatLossCurrency(summary.expected_loss_when_losing), trend: trendByMetricKey.averageLossWhenYouMiss, infoText: getMetricTooltip("Average Loss When You Miss") },
                    { label: "Typical Loss When You Miss", value: formatLossCurrency(summary.median_loss_when_losing), trend: trendByMetricKey.typicalLossWhenYouMiss, infoText: getMetricTooltip("Typical Loss When You Miss") },
                    { label: "Worst 5% Outcome", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.worstFivePercentShortfall?.trend === "unknown" ? trendByMetricKey.badPackFloorValue : trendByMetricKey.worstFivePercentShortfall, infoText: getMetricTooltip("Worst 5% Outcome") },
                  ]}
                />
                <div id="set-detail-desirability" className="h-full scroll-mt-24 md:scroll-mt-28">
                  <ScorePillarCard
                    title="Desirability"
                    score={displayedDesirabilityScore}
                    scoreTrend={trendByMetricKey.desirabilityScore}
                    rankValue={summary.desirability_rank}
                    rankTier={summary.desirability_tier}
                    rankLabel="Desirability Rank"
                    sectionMeta={desirabilityMeta}
                    fallbackSummary={desirabilitySummary}
                    infoText={SIMPLE_PILLAR_INFO_COPY.Desirability}
                    simpleMetrics={desirabilityOverviewMetrics}
                    advancedMetrics={[
                      {
                        label: "Top Collector Appeal Drivers",
                        value: null,
                        content: <TopDesirabilityDrivers drivers={topDesirabilityCards} />,
                        trend: null,
                      },
                    ]}
                  />
                </div>
                <ScorePillarCard
                  title="Stability"
                  score={displayedStabilityScore}
                  scoreTrend={trendByMetricKey.stabilityScore}
                  rankValue={summary.stability_rank}
                  rankTier={summary.stability_tier}
                  rankLabel="Stability Rank"
                  sectionMeta={stabilityMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Stability")}
                  simpleMetrics={[
                    { label: "Cards Carrying Value", value: formatNumber(summary.effective_chase_count, 2), trend: trendByMetricKey.chaseDepth },
                    { label: "Top Chase Share", value: formatPercent(summary.top1_ev_share), trend: trendByMetricKey.top1Share },
                    { label: "Value Spread", value: formatNumber(summary.hhi_ev_concentration, 3), trend: trendByMetricKey.evConcentration },
                  ]}
                  advancedMetrics={[
                    { label: "Outcome Volatility", value: formatNumber(summary.coefficient_of_variation, 2), trend: trendByMetricKey.outcomeVolatility },
                    { label: "Effective Chase Count", value: formatNumber(summary.effective_chase_count, 2), trend: trendByMetricKey.chaseDepth },
                    { label: "EV Concentration", value: formatNumber(summary.hhi_ev_concentration, 3), trend: trendByMetricKey.evConcentration },
                    { label: "Top 3 Share", value: formatPercent(summary.top3_ev_share), trend: trendByMetricKey.top3Share },
                    { label: "Top 5 Share", value: formatPercent(summary.top5_ev_share), trend: trendByMetricKey.top5Share },
                  ]}
                />
              </div>
              {setDetailMode ? (
                <div id="set-detail-simulation-cards" className="scroll-mt-24 md:scroll-mt-28">
                  <SectionCard
                    title="Cards Driving the Simulation"
                    subtitle="Cards contributing most to modeled pack value."
                  >
                    <InterpretationInsight
                      sectionMeta={topEvDriversMeta}
                      fallbackSummary={collectorFriendlyText(interpretation?.topEvDrivers)}
                      compact
                      showEvidence={false}
                      className="mb-3"
                    />
                    <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} />
                  </SectionCard>
                </div>
              ) : null}
            </section>
            ) : null}

            {effectiveViewMode === "expert" && !setDetailMode ? (
              <SetIntelligenceSection
                summary={summary}
                simpleMode={false}
                setIntelligenceMeta={interpretationMeta?.set_intelligence}
              />
            ) : null}

            {effectiveViewMode === "expert" && !setDetailMode ? (
            <section id={ANALYSIS_SECTION_ID} style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="scroll-mt-24 pt-4 md:scroll-mt-28">
              <SectionCard
                title={
                  activeInsightsGraphMode === "historical-trend"
                    ? RIP_COPY.sections.historicalTrend
                    : activeInsightsGraphMode === "pack-breakdown"
                    ? RIP_COPY.sections.packBreakdown
                    : activeInsightsGraphMode === "value-contribution"
                    ? "Value Contribution"
                    : RIP_COPY.sections.outcomeDistribution
                }
                subtitle={
                  activeInsightsGraphMode === "outcome-distribution"
                    ? openingOutcomesSubtitle
                    : null
                }
                titleInfoText={
                  activeInsightsGraphMode === "outcome-distribution"
                    ? outcomeDistributionInfo
                    : activeInsightsGraphMode === "value-contribution"
                    ? rarityContributionInfo
                    : null
                }
              >
                <SectionViewTabs
                  className="mb-4"
                  value={activeInsightsGraphMode}
                  onChange={handleSectionSelect}
                  options={[
                    { value: "outcome-distribution", label: RIP_COPY.sections.outcomeDistribution },
                    ...(!setDetailMode ? [{ value: "historical-trend", label: RIP_COPY.sections.historicalTrend }] : []),
                    { value: "pack-breakdown", label: RIP_COPY.sections.packBreakdown },
                    ...(setDetailMode ? [{ value: "value-contribution", label: "Value Contribution" }] : []),
                  ]}
                />

                <InterpretationInsight
                  sectionMeta={graphSectionMeta}
                  fallbackSummary={graphSectionFallback}
                  compact
                  showEvidence={false}
                  className="mb-3"
                />

                {activeInsightsGraphMode === "pack-breakdown" && packBreakdownEvidenceRows.length > 0 ? (
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

                {activeInsightsGraphMode === "historical-trend" ? (
                  <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} summary={summary} />
                ) : activeInsightsGraphMode === "pack-breakdown" ? (
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
                ) : activeInsightsGraphMode === "value-contribution" ? (
                  <div className="space-y-3">
                    <div>
                      <p className="text-base font-semibold text-[var(--text-primary)]">Where the Value Comes From</p>
                      <p className="mt-0.5 text-sm text-[var(--text-secondary)]">See how each rarity bucket contributes to modeled pack value in this simulation.</p>
                    </div>
                    <RarityContributionContent rankings={rankings} />
                  </div>
                ) : (
                  <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} />
                )}

                {activeInsightsGraphMode !== "pack-breakdown" && activeInsightsGraphMode !== "value-contribution" ? (
                  <>
                    {activeInsightsGraphMode === "historical-trend" ? (
                      <div className="mt-4 hidden gap-3 sm:grid-cols-3 lg:grid lg:grid-cols-6">
                        <StatTile label={RIP_COPY.chartStats.chanceToBeatPackCost} value={formatPercent(summary.prob_profit, { probability: true })} trend={trendByMetricKey.chanceToBeatPackCost} />
                        <StatTile label={RIP_COPY.chartStats.chanceAtBigPull} value={formatPercent(summary.prob_big_hit, { probability: true })} trend={trendByMetricKey.chanceAtBigPull} />
                        <StatTile label={RIP_COPY.chartStats.typicalPack} value={formatCurrency(percentileP50 ?? summary.median_value)} trend={trendByMetricKey.typicalPackValue} />
                        <StatTile label={RIP_COPY.chartStats.bigHitUpside} value={formatMultiplier(summary.p95_value_to_cost_ratio, 1)} trend={trendByMetricKey.bigHitUpside} />
                        <StatTile
                          label={RIP_COPY.chartStats.godPullUpside}
                          value={formatMultiplier(summary.p99_value_to_cost_ratio, 1)}
                          trend={trendByMetricKey.godPullUpside}
                          infoText={
                            <div className="space-y-1 text-left">
                              <p>Simple: Rare monster-hit outcome compared with pack price.</p>
                              <p>Expert: P99 outcome vs pack cost.</p>
                            </div>
                          }
                        />
                        <StatTile label={RIP_COPY.chartStats.bestPull} value={formatCurrency(summary.max_value)} trend={trendByMetricKey.bestPull} />
                      </div>
                    ) : null}

                    {activeInsightsGraphMode === "historical-trend" ? (
                      <MobileMetricAccordion title="Metrics" defaultOpen={false} className="mt-4">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <StatTile label={RIP_COPY.chartStats.chanceToBeatPackCost} value={formatPercent(summary.prob_profit, { probability: true })} trend={trendByMetricKey.chanceToBeatPackCost} />
                          <StatTile label={RIP_COPY.chartStats.chanceAtBigPull} value={formatPercent(summary.prob_big_hit, { probability: true })} trend={trendByMetricKey.chanceAtBigPull} />
                          <StatTile label={RIP_COPY.chartStats.typicalPack} value={formatCurrency(percentileP50 ?? summary.median_value)} trend={trendByMetricKey.typicalPackValue} />
                          <StatTile label={RIP_COPY.chartStats.bigHitUpside} value={formatMultiplier(summary.p95_value_to_cost_ratio, 1)} trend={trendByMetricKey.bigHitUpside} />
                          <StatTile
                            label={RIP_COPY.chartStats.godPullUpside}
                            value={formatMultiplier(summary.p99_value_to_cost_ratio, 1)}
                            trend={trendByMetricKey.godPullUpside}
                            infoText={
                              <div className="space-y-1 text-left">
                                <p>Simple: Rare monster-hit outcome compared with pack price.</p>
                                <p>Expert: P99 outcome vs pack cost.</p>
                              </div>
                            }
                          />
                          <StatTile label={RIP_COPY.chartStats.bestPull} value={formatCurrency(summary.max_value)} trend={trendByMetricKey.bestPull} />
                        </div>
                      </MobileMetricAccordion>
                    ) : null}
                  </>
                ) : null}
              </SectionCard>
            </section>
            ) : null}

            {effectiveViewMode === "expert" && !setDetailMode ? (
            <section id="explore-drivers" style={{ scrollMarginTop: "calc(var(--app-header-offset,64px) + 4rem)" }} className="w-full max-w-full min-w-0 scroll-mt-24 pt-1 md:scroll-mt-28">
              <SectionCard title={RIP_COPY.sections.rarityContribution} subtitle={null} titleInfoText={rarityContributionInfo}>
                {!setDetailMode ? (
                  <SectionViewTabs
                    className="mb-4"
                    value={activeValueView}
                    onChange={setActiveValueView}
                    options={[
                      { value: "cards", label: "Cards Carrying the Set" },
                      { value: "value", label: "Value Contribution" },
                      { value: "pull-rates", label: "Pull Rates" },
                    ]}
                  />
                ) : null}

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
                ) : effectiveValueView === "value" ? (
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
                    />
                  </>
                ) : (
                  <div className="space-y-3">
                    <div>
                      <p className="text-base font-semibold text-[var(--text-primary)]">Pull Rate Assumptions</p>
                      <p className="mt-0.5 text-sm text-[var(--text-secondary)]">Modeled rarity frequency and specific-card odds used by this simulation.</p>
                      <p className="mt-1 text-xs text-[var(--text-tertiary,var(--text-secondary))]">These are modeled estimates, not official Pokémon odds.</p>
                    </div>
                    <PullRateAssumptionsCard pullRateAssumptions={pullRateAssumptions} embedded />
                  </div>
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
          </>
        ) : null}
        </div>
      </PublicProfileLocalScaffold>
    </main>
  );
}
