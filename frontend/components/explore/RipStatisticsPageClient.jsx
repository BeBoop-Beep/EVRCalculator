"use client";

import { startTransition, useCallback, useEffect, useId, useMemo, useReducer, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Area,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import ChartEdgeDateTick from "@/components/explore/ChartEdgeDateTick";
import ChartFrame from "@/components/explore/ChartFrame";
import MarketWindowSelector from "@/components/explore/MarketWindowSelector";
import MarketTrendTooltipCard from "@/components/explore/MarketTrendTooltipCard";
import SimulationSectionSelector from "@/components/explore/SimulationSectionSelector";
import {
  MINIMAL_Y_AXIS_PROPS,
  buildEdgeDateTicks,
  getMinimalPlotMargin,
} from "@/components/explore/minimalChartAxis.mjs";
import DeltaTrendIcon from "@/components/ui/DeltaTrendIcon";
import CompactRankedBarChart from "@/components/explore/CompactRankedBarChart";
import PackValueHistoryChart from "@/components/explore/PackValueHistoryChart";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import InterpretationInsight from "@/components/explore/InterpretationInsight";
import RipDistributionChart from "@/components/explore/RipDistributionChart";
import PokemonSetMobileHero from "@/components/pokemon/set-page/PokemonSetHero/PokemonSetMobileHero";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";
import SealedMarketTrendCard from "@/components/pokemon/set-page/Overview/SealedMarketTrendCard";
import { selectMobileHeroModel } from "@/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs";
import PullRateAssumptionsCard from "@/components/pokemon/set-page/PullRates/PullRateAssumptionsCard";
import PullRatesTab from "@/components/pokemon/set-page/PullRates/PullRatesTab";
import SetTabLoadingPanel from "@/components/explore/SetTabLoadingPanel";
import InDexLogoLoader from "@/components/brand/InDexLogoLoader";
import SectionBoundary from "@/components/ui/SectionBoundary";
import SectionErrorBoundary from "@/components/ui/SectionErrorBoundary";
import { useSectionTiming } from "@/hooks/useSectionTiming";
import { useSectionFetchState } from "@/hooks/useSectionFetchState";
import useMediaQuery from "@/hooks/useMediaQuery";
import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";
import {
  TAP_MOVEMENT_THRESHOLD_PX,
  classifyPointerGesture,
  clampTooltipX,
  findNearestPointIndex,
} from "./compactSparklineInteraction.mjs";
import { markSectionTiming, debugSectionTiming } from "@/lib/perf/sectionTiming";
import InfoPopover from "@/components/ui/InfoPopover";
import MarketValueChange from "@/components/ui/MarketValueChange";
import MoversTickerViewport from "@/components/explore/MoversTickerViewport";
import SevenDayMarketMoversTicker from "@/components/explore/SevenDayMarketMoversTicker";
import InterpretationBadge from "@/components/ui/InterpretationBadge";
import RankBadge from "@/components/ui/RankBadge";
import SegmentedControl from "@/components/ui/SegmentedControl";
import {
  ALL_CARDS_SORT_OPTIONS,
  CARD_TIMEFRAMES,
  DEFAULT_MARKET_MOVER_METRIC,
  MARKET_MOVER_METRIC_OPTIONS,
  getAllCardsDirectionLabel,
  getEffectiveRarityFilter,
  resolveCardsRequest,
} from "@/components/pokemon/set-page/Cards/cardsControls.mjs";
import {
  getCardAppealSampleDiagnostics,
  hasUsableCardAppealCorrelation,
  resolvePreferredCardAppealCorrelation,
} from "./cardAppealSampleDiagnostics.mjs";
import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";
import FinancialRipV3Breakdown from "./FinancialRipV3Breakdown.jsx";
import CollectorAppealBreakdown from "./CollectorAppealBreakdown.jsx";
import OverviewRipSummary from "./OverviewRipSummary.jsx";
import RipDecisionPage from "./RipDecisionPage.jsx";
import InsightsSummaryModule from "./InsightsSummaryModule.jsx";
import { selectSimulationDrivers } from "./simulationDriversSelector.mjs";
import { aggregateNormalStateRows } from "./packStateLabels.mjs";
import { formatShareFromCounts, formatImpliedOdds, buildPackPathDisplayRows } from "./packPathShare.mjs";
import { formatAbbreviatedCount, formatAbbreviatedCurrency } from "./rankedBarChartFormatting.mjs";
import {
  buildPercentileStripModel,
  buildPercentileTakeaway,
  formatMetricCount,
  formatMetricCurrency,
  formatMetricNumber,
  formatMetricPercent,
  formatMetricProbability,
  formatMetricRatio,
  formatMetricSignedPercent,
  getCoefficientOfVariationTag,
  getHhiConcentrationTag,
  shouldMergeLossFractionRows,
} from "./simulationMetricsDisplay.mjs";
import {
  computeModelAgreement,
  computeMonteCarloBand,
  computeStandardError,
  selectCalculatedExpectedValue,
  selectPercentileValue,
  selectSimulatedExpectedValue,
} from "./simulationMetricsSelector.mjs";
import { buildSetValueContract, selectSetValueTrendFromContract } from "./setValueContract.mjs";
import { buildSetHeaderSummary } from "./setHeaderSummarySelector.mjs";
import { selectTrendScores } from "./trendScoresSelector.mjs";
import { getCardMovement7d, selectMoversTickerItems } from "./moversTickerSelector.mjs";
import { resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";
import { RIP_SCORE_HELPER, selectRipHeroScoreMode } from "./ripHeroScoreMode.mjs";
// `selectOpeningExperiencePresentation` / `selectSetDesirabilityPresentation`
// were imported from Insights/openingExperienceSelector.mjs for the removed
// public Collector Profile. This page has no other consumer of either, so the
// import is gone; the selector module itself is left in place for its remaining
// callers rather than deleted from under them.
import { RANK_CONFIG } from "@/constants/rankConfig";
import { getFriendlyMetricLabel, getFormattedTooltip, getMetricTooltip } from "@/constants/interpretabilityConfig";
import {
  NEGATIVE_VALUE_COLOR,
  POSITIVE_VALUE_COLOR,
  getDangerValueStyle,
  getInterpretationTone,
  getRipTierPresentation,
} from "@/lib/explore/interpretationTone";
import {
  getCachedPokemonSetCards,
  getPokemonSetCardsPage,
  getPokemonSetCardsValidation,
} from "@/lib/pokemon/pokemonSetCardsClient";
import { PRICING_SNAPSHOT_CONTRACT_VERSION } from "@/lib/pokemon/pricingSnapshotContract.mjs";
import {
  getCachedPokemonSetMarketDashboard,
  getPokemonSetMarketMovers,
  getPokemonSetOverview,
  getPokemonSetTopChase,
  getPokemonSetValueHistory,
} from "@/lib/pokemon/pokemonSetMarketClient";
import { getPokemonSetPullRates } from "@/lib/pokemon/pokemonSetPullRatesClient";
import { getPokemonSetInsightsCritical } from "@/lib/pokemon/pokemonSetInsightsCriticalClient";
import { getPokemonSetInsightsSecondary } from "@/lib/pokemon/pokemonSetInsightsSecondaryClient";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import {
  buildMarketDashboardStateFromPayload,
  createMarketDashboardState,
  hydrateMarketDashboardStateFromCachedPayload,
  marketDashboardReducer,
} from "./marketDashboardState.mjs";
import {
  announceNavigationStart,
  debugLoadingTiming,
} from "@/lib/navigation/loadingPolicy";
import {
  extractDeltaWindows,
  filterHistoryPointsForDeltaWindow,
  getDeltaWindowLabel,
  getPreferredDeltaWindowKey,
  getSelectedDeltaWindowFromHistory,
  getStandardDeltaWindowDefinitions,
  getVisibleHistoryWindowMetrics,
} from "@/lib/explore/marketDeltaWindows.mjs";
import { formatHistoryDate, getHistoryDateKey } from "./historyDateFormatting.mjs";
import { forwardFillDailyHistoryThroughDate, normalizeHistoryTrendPoint } from "./packValueHistoryNormalization.mjs";
import {
  getMarketDateSourceFromPayload,
  resolveMarketAsOfDate,
  warnOnMixedMarketDates,
} from "./marketAsOfDate.mjs";
import {
  buildSetPageMarketDiagnostics,
  getHistoryPointsEndDate,
  reportSetPageMarketDiagnostics,
} from "./setPageMarketDiagnostics.mjs";
import {
  getTopCardPreferredHistoryEndDate,
  getTopCardTrendStatusMessage,
  resolveTopCardWindowState,
  warnForTopCardWindowState,
} from "./topChaseWindowState.mjs";
import { validateTopChasePayload } from "@/lib/pokemon/topChasePayloadContract.mjs";
import {
  chooseFresherOverviewPayload,
  getLatestRealPerformanceDate,
  selectOverviewPerformanceHistoryState,
} from "./performanceHistorySelector.mjs";
import { buildOpeningSimulationFreshness } from "./openingSimulationFreshness.mjs";
import { selectOverviewSetValueTrendByScope } from "./setValueTrendSelector.mjs";
import {
  adaptSetShell,
  adaptMarketDashboardFromSources,
  adaptSetValueHistoriesFromSources,
} from "@/lib/pokemon/set-page/setPageAdapters.mjs";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const REQUIRED_PACK_PATHS = ["normal", "demi_god_pack", "god_pack"];
const ANALYSIS_SECTION_ID = "explore-outcomes";
const GRAPH_SECTION_KEYS = new Set(["outcome-distribution", "historical-trend", "simulation-drivers", "pack-breakdown", "value-contribution", "simulation-metrics"]);
const SECTION_ID_MAP = {
  "pack-score": "explore-score",
  "outcome-distribution": "explore-outcomes",
  "historical-trend": "explore-outcomes",
  "pack-breakdown": "explore-outcomes",
  "simulation-metrics": "explore-outcomes",
  "top-ev-drivers": "explore-drivers",
  "rarity-contribution": "explore-rarity",
};
const SECTION_SCROLL_ORDER = [
  { sectionId: "explore-score", navId: "pack-score" },
  { sectionId: ANALYSIS_SECTION_ID, navId: "outcome-distribution" },
  { sectionId: "explore-drivers", navId: "top-ev-drivers" },
  { sectionId: "explore-rarity", navId: "rarity-contribution" },
];
const SET_DETAIL_DEFAULT_TAB = "overview";
const SET_DETAIL_TABS = new Set(["overview", "cards", "pull-rates", "insights"]);
// No set-detail tab renders content sourced from the full set /page snapshot
// anymore. Pull Rates moved off this list in Phase 4A (getPokemonSetPullRates)
// and Insights moved off it in Phase 4B (getPokemonSetInsights — see the
// Insights tab fetch effect below). Kept as an always-empty set (rather than
// removed outright) so the two legacy full-page effects below stay inert
// without needing to delete fetchPokemonSetPageSnapshot or its supporting
// state — a wider cleanup for a future phase.
const SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD = new Set([]);
const CANONICAL_SET_VALUE_SCOPE = "standard";
const SET_VALUE_SCOPE_OPTIONS = [
  { key: "standard", label: "Set" },
  { key: "hits", label: "Hits" },
  { key: "top10", label: "Top 10" },
];
// Hits stays in the backend/data contract but is temporarily hidden from the
// user-facing selector while hit-eligibility membership is under audit.
const VISIBLE_SET_VALUE_SCOPE_OPTIONS = SET_VALUE_SCOPE_OPTIONS.filter((entry) => entry.key !== "hits");
// Matches backend DEFAULT_CARDS_PAGE_SIZE (pokemon_public_snapshot_service.py).
const CARDS_PAGE_SIZE = 60;
const DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW = "365d";
const DEFAULT_TOP_MARKET_CARDS_WINDOW = "30D";
// Fixed request window for the slim /market/top-chase fetch — unrelated to
// topMarketCardsWindowKey, which only picks which already-fetched delta to
// display client-side.
const DEFAULT_TOP_CHASE_MARKET_WINDOW = "365d";
const TOP_CHASE_MOBILE_PREVIEW_LIMIT = 5;
const MOBILE_SET_MENU_HIDE_DISTANCE_PX = 10;
const MOBILE_SET_MENU_REVEAL_DISTANCE_PX = 56;
const MOBILE_SET_MENU_SCROLL_NOISE_PX = 2;
const MOBILE_SET_MENU_TOP_BOUNDARY_PX = 20;
const MOBILE_SET_MENU_BOTTOM_EDGE_PX = 64;
const MOBILE_SET_MENU_GESTURE_NOISE_PX = 4;
const MOBILE_RETURN_TO_TOP_THRESHOLD_PX = 12;
// The Overview 7D Movers ticker always requests the 7D window — deliberately
// independent of every other time-range selector on the page — and shows the
// complete eligible movement list ranked by |7D %|, capped at 10 items.
const MOVERS_TICKER_WINDOW = "7D";
// This endpoint limit caps its directional summary arrays; the payload's
// complete eligible `all` collection remains the ticker's membership source.
const MOVERS_TICKER_FETCH_LIMIT = 10;
// Adjacent-set prefetching previously fired cards + dashboard + 3 value-history
// requests per adjacent set on every navigation, saturating the browser's
// per-origin connection limit and starving the actual destination fetch.
// Keep the mechanism but disable it by default — the active destination set
// is enough; bump this only behind a deliberate, measured decision.
const SET_PREFETCH_ADJACENT_LIMIT = 0;
// Insights sections that depend on the /insights payload show skeletons while
// it loads; after this long they switch to an explicit "taking longer than
// expected" fallback instead of shimmering forever.
const INSIGHTS_PENDING_TIMEOUT_MS = 8000;
const isDevPerfLoggingEnabled = process.env.NODE_ENV !== "production";
const SET_DETAIL_TAB_ALIASES = {
  rip: "overview",
  analysis: "insights",
  analytics: "insights",
  market: "overview",
};
// The ONE preferred DOM id for the canonical Collector Appeal block.
const COLLECTOR_APPEAL_SECTION_ID = "set-detail-collector-appeal";

// The ids the removed public Collector Profile and its predecessors owned.
// They are rendered as invisible anchors on the canonical Collector Appeal
// block so every existing bookmark, internal link and indexed URL still lands
// on real content. They are compatibility only — nothing links to them by
// choice, and `set-detail-collector-appeal` is what new links use.
const LEGACY_COLLECTOR_APPEAL_ANCHOR_IDS = [
  "set-detail-collector-profile",
  "set-detail-set-desirability",
  "set-detail-desirability-evidence",
  "set-detail-desirability-proof",
  "set-detail-desirability-validation",
  "set-detail-card-desirability-price",
  "set-detail-opening-experience",
];

const SET_DETAIL_SECTION_TARGETS = {
  "set-intelligence": { tab: "overview", targetId: "set-detail-set-intelligence" },
  "set-signals": { tab: "overview", targetId: "set-detail-set-intelligence" },
  "rip-score": { tab: "insights", targetId: "set-detail-rip-score", graphMode: "outcome-distribution" },
  // COLLECTOR APPEAL — one destination, many legacy names.
  //
  // `collector-appeal` is the preferred alias. Every other key here addressed
  // the removed public Collector Profile or one of the standalone desirability
  // sections that preceded it, and each now resolves to the SAME canonical
  // Collector Appeal block. They point at surviving content, not at a deleted
  // section: a legacy link scrolls to the three Collector Appeal V3 factors.
  "collector-appeal": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "collector-profile": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "set-desirability": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "desirability-evidence": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "opening-experience": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "desirability-proof": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "desirability-validation": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  "card-desirability-price": { tab: "insights", targetId: COLLECTOR_APPEAL_SECTION_ID },
  // Simulation Results card (formerly "Opening Outcomes"). `opening-outcomes`
  // stays for backwards-compatible deep links; `simulation-results` is the
  // preferred alias for the same card/default sub-view.
  "opening-outcomes": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "outcome-distribution" },
  "simulation-results": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "outcome-distribution" },
  "simulation-cards": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "simulation-drivers" },
  value: { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "value-contribution" },
  "pack-breakdown": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "pack-breakdown" },
  "simulation-metrics": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "simulation-metrics" },
  // The technical "Opening P vs C" sub-view of Simulation Results. Kept as a
  // distinct section id from `performance-vs-cost` so Overview's quick-read
  // Performance vs Cost chart (below) stays exactly where it is — same data,
  // different story.
  "opening-performance-cost": { tab: "insights", targetId: ANALYSIS_SECTION_ID, graphMode: "historical-trend" },
  "performance-vs-cost": { tab: "overview", targetId: "set-detail-overview-performance", graphMode: "historical-trend" },
  "set-value-trend": { tab: "overview", targetId: "set-detail-set-value-trend" },
  "top-market-cards": { tab: "overview", targetId: "set-detail-top-market-cards" },
  "market-movers": { tab: "cards", targetId: "set-detail-cards", cardsSubTab: "checklist" },
  "all-cards": { tab: "cards", targetId: "set-detail-cards", cardsSubTab: "checklist" },
};

function debugSetPagePerf(label, details = {}) {
  if (!isDevPerfLoggingEnabled) {
    return;
  }
  console.debug(`[pokemon-set-perf] ${label}`, details);
}

function markSetPagePerformance(name, detail = {}) {
  if (!isDevPerfLoggingEnabled || typeof performance === "undefined") {
    return;
  }
  try {
    performance.mark(name, { detail });
  } catch {
    try {
      performance.mark(name);
    } catch {
      // Ignore mark failures in older browsers.
    }
  }
}

function schedulePostShellWarmup(callback) {
  if (typeof window === "undefined") {
    return () => {};
  }
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(callback, { timeout: 1200 });
    return () => window.cancelIdleCallback?.(id);
  }
  const id = window.setTimeout(callback, 120);
  return () => window.clearTimeout(id);
}

function toStableIdentifier(value) {
  const text = String(value || "").trim();
  if (!text || text === "undefined" || text === "null") {
    return null;
  }
  return text;
}

function normalizeSetIdentityToken(value) {
  const text = toStableIdentifier(value);
  return text ? text.toLowerCase().replace(/[^a-z0-9]+/g, "") : null;
}

function getSetIdentityTokens(identity) {
  if (!identity || typeof identity !== "object") {
    return [];
  }
  return [
    identity.id,
    identity.set_id,
    identity.target_id,
    identity.name,
    identity.set_name,
    identity.slug,
    identity.canonical_key,
    identity.pokemon_api_set_id,
  ]
    .map(normalizeSetIdentityToken)
    .filter(Boolean);
}

function setIdentityMatchesTarget(identity, targetId) {
  const targetToken = normalizeSetIdentityToken(targetId);
  return Boolean(targetToken && getSetIdentityTokens(identity).includes(targetToken));
}

function isStateForResolvedSet(stateSetId, resolvedSetResourceId) {
  const stateToken = normalizeSetIdentityToken(stateSetId);
  const resolvedToken = normalizeSetIdentityToken(resolvedSetResourceId);
  return Boolean(stateToken && resolvedToken && stateToken === resolvedToken);
}

function getSetSnapshotIdentity(explorePayload) {
  const meta = explorePayload?.meta || {};
  return (
    explorePayload?.set ||
    explorePayload?.setIdentity ||
    explorePayload?.set_identity ||
    meta.set ||
    meta.setIdentity ||
    meta.set_identity ||
    meta.snapshot?.set ||
    meta.snapshot?.setIdentity ||
    meta.snapshot?.set_identity ||
    explorePayload?.summary ||
    null
  );
}

function isSetPageRequestTimeoutFallback(explorePayload) {
  const meta = explorePayload?.meta || {};
  if (meta.requestTimeout === true || meta.fallbackReason === "request_timeout" || meta.isTransportFallback === true) {
    return true;
  }
  const errors = Array.isArray(meta.errors) ? meta.errors : [];
  return errors.some((error) => String(error?.code || "").includes("TIMEOUT"));
}

function isSetPagePrimarySnapshotUnavailable(explorePayload) {
  const meta = explorePayload?.meta || {};
  return Boolean(meta.fallback === true || meta.requestTimeout === true || meta.isTransportFallback === true);
}

function isSetPageTransportFallback(explorePayload) {
  const meta = explorePayload?.meta || {};
  return Boolean(meta.requestTimeout === true || meta.isTransportFallback === true || meta.fallbackReason === "request_timeout");
}

function hasRealSetPageIdentity(explorePayload, resolvedSetResourceId) {
  if (!explorePayload) {
    // Cards/Overview intentionally render without the full explore payload —
    // the shell (or selected target) is a valid identity source for those
    // tabs, so the absence of explorePayload alone must not read as "unknown".
    return Boolean(resolvedSetResourceId);
  }
  if (isSetPagePrimarySnapshotUnavailable(explorePayload)) {
    return false;
  }
  const identity = getSetSnapshotIdentity(explorePayload);
  const identityId = toStableIdentifier(identity?.id ?? identity?.set_id ?? identity?.target_id);
  if (!identityId) {
    return false;
  }
  return !resolvedSetResourceId || setIdentityMatchesTarget(identity, resolvedSetResourceId);
}

async function fetchPokemonSetPageSnapshot(setId, { signal } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }
  const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/page?retry=1`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message = payload?.message || payload?.error || `Set page snapshot request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

// Insights tab (Phase 4B): the slim getPokemonSetInsights contract is
// camelCase-only on the wire, but the Insights render tree below (RIP score
// breakdown, RipDistributionChart, RarityContributionContent, PackValueHistoryChart,
// InterpretationInsight, etc.) still reads explorePayload/summary fields in
// snake_case, the same shape the old full /page payload used. Rather than
// touch every one of those read sites, dualKeyCase mechanically adds the
// snake_case sibling for every camelCase key (the same dual-key convention
// pokemon_public_snapshot_service.py already uses elsewhere, e.g.
// enrich_cards_payload_with_desirability) so both spellings resolve to the
// same value. No analytics/derivation logic lives here — it is a pure
// key-casing adapter.
function dualKeyCase(value) {
  if (Array.isArray(value)) {
    return value.map(dualKeyCase);
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const [key, inner] of Object.entries(value)) {
      const convertedInner = dualKeyCase(inner);
      result[key] = convertedInner;
      const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
      if (snakeKey !== key && !(snakeKey in value)) {
        result[snakeKey] = convertedInner;
      }
    }
    return result;
  }
  return value;
}

function adaptPokemonSetInsightsPayloadToExplorePayload(normalized) {
  const outcomeDistribution = normalized?.outcomeDistribution || {};
  const meta = normalized?.meta || { warnings: [] };
  const isEmptyFallback = String(meta.source || "").startsWith("empty_fallback");
  return {
    set: normalized?.set || null,
    summary: dualKeyCase(normalized?.summary || {}),
    interpretation: normalized?.interpretation || {},
    // Canonical Financial RIP V3 / Overall RIP V5, carried through verbatim.
    // Without these the set page would render the V3 breakdown as permanently
    // unavailable even when the snapshot carries a complete V3 result.
    financialRipV3: normalized?.financialRipV3 || null,
    overallRipV5: normalized?.overallRipV5 || null,
    publicRipContractV5: normalized?.publicRipContractV5 || null,
    overallRipV6: normalized?.overallRipV6 || null,
    publicRipContractV6: normalized?.publicRipContractV6 || null,
    // CANONICAL: what every current public surface reads (see canonicalRipV7).
    overallRipV7: normalized?.overallRipV7 || null,
    publicRipContractV7: normalized?.publicRipContractV7 || null,
    rip_statistics: dualKeyCase(normalized?.ripStatistics || {}),
    percentiles: dualKeyCase(outcomeDistribution.percentiles || []),
    distribution_bins: dualKeyCase(outcomeDistribution.distributionBins || []),
    threshold_bins: dualKeyCase(outcomeDistribution.thresholdBins || []),
    top_hits: dualKeyCase(normalized?.simulationDrivers || []),
    rankings: dualKeyCase(normalized?.rarityContribution || []),
    history_trend: dualKeyCase(normalized?.historyTrend || []),
    openingDesirability: normalized?.desirability || null,
    desirabilityValidation: normalized?.desirabilityValidation || null,
    meta: isEmptyFallback ? { ...meta, fallback: true } : meta,
  };
}

// Progressive-rendering split of the adapter above: the critical fetch
// (priorities 1-3 — RIP Score hero, pillar cards, recommendation copy) and
// secondary fetch (priorities 4-5 — charts/distributions, deep diagnostics)
// each merge only their own slice into explorePayload, via functional
// updates in the two effects below, so they can arrive independently without
// clobbering each other regardless of which settles first.
function adaptPokemonSetInsightsCriticalPayloadToExplorePayload(critical) {
  return {
    set: critical?.set || null,
    summary: dualKeyCase(critical?.summary || {}),
    interpretation: critical?.interpretation || {},
    // The RIP Score hero and Breakdown are priority-1 surfaces, so the canonical
    // V7 objects have to arrive in the CRITICAL slice - deferring them to the
    // secondary fetch would leave the headline score unavailable until the
    // second request settled.
    financialRipV3: critical?.financialRipV3 || null,
    overallRipV5: critical?.overallRipV5 || null,
    publicRipContractV5: critical?.publicRipContractV5 || null,
    overallRipV6: critical?.overallRipV6 || null,
    publicRipContractV6: critical?.publicRipContractV6 || null,
    overallRipV7: critical?.overallRipV7 || null,
    publicRipContractV7: critical?.publicRipContractV7 || null,
  };
}

function adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(secondary) {
  const outcomeDistribution = secondary?.outcomeDistribution || {};
  return {
    rip_statistics: dualKeyCase(secondary?.ripStatistics || {}),
    percentiles: dualKeyCase(outcomeDistribution.percentiles || []),
    distribution_bins: dualKeyCase(outcomeDistribution.distributionBins || []),
    threshold_bins: dualKeyCase(outcomeDistribution.thresholdBins || []),
    top_hits: dualKeyCase(secondary?.simulationDrivers || []),
    rankings: dualKeyCase(secondary?.rarityContribution || []),
    history_trend: dualKeyCase(secondary?.historyTrend || []),
    openingDesirability: secondary?.desirability || null,
    desirabilityValidation: secondary?.desirabilityValidation || null,
  };
}

function hasNonEmptyArray(value) {
  return Array.isArray(value) && value.length > 0;
}

function hasMeaningfulObjectFields(value, keys = null) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const entries = keys
    ? keys.map((key) => [key, value[key]])
    : Object.entries(value);
  return entries.some(([, inner]) => {
    if (inner === null || inner === undefined) {
      return false;
    }
    if (Array.isArray(inner)) {
      return inner.length > 0;
    }
    if (typeof inner === "object") {
      return Object.keys(inner).length > 0;
    }
    return typeof inner === "string" ? inner.trim().length > 0 : true;
  });
}

function hasInsightsPayloadData(payload) {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  if (
    hasNonEmptyArray(payload.distribution_bins || payload.distributionBins) ||
    hasNonEmptyArray(payload.threshold_bins || payload.thresholdBins) ||
    hasNonEmptyArray(payload.percentiles) ||
    hasNonEmptyArray(payload.top_hits || payload.topHits) ||
    hasNonEmptyArray(payload.rankings) ||
    hasNonEmptyArray(payload.history_trend || payload.historyTrend)
  ) {
    return true;
  }

  const ripStatistics = payload.rip_statistics || payload.ripStatistics;
  if (
    hasMeaningfulObjectFields(ripStatistics, [
      "pack_paths",
      "packPaths",
      "normal_pack_states",
      "normalPackStates",
      "distribution_bins",
      "distributionBins",
      "threshold_bins",
      "thresholdBins",
      "percentiles",
    ])
  ) {
    return true;
  }

  const openingDesirability = payload.openingDesirability || payload.opening_desirability;
  if (
    hasMeaningfulObjectFields(openingDesirability, [
      "score",
      "status",
      "band",
      "rank",
      "desirability_score",
      "desirabilityScore",
      "opening_desirability_score",
      "openingDesirabilityScore",
      "opening_desirability_rank",
      "openingDesirabilityRank",
    ])
  ) {
    return true;
  }

  // desirabilityValidation is retired; nothing else marks the payload renderable.
  return false;
}

function getResolvedPokemonSetResourceId({ requestedTargetId, selectedTarget, explorePayload, shellPayload }) {
  const requestedResourceId = toStableIdentifier(requestedTargetId);
  const selectedResourceId =
    toStableIdentifier(selectedTarget?.id ?? selectedTarget?.set_id) ||
    toStableIdentifier(selectedTarget?.target_id);
  const snapshotIdentity = getSetSnapshotIdentity(explorePayload);
  const snapshotResourceId = toStableIdentifier(snapshotIdentity?.id ?? snapshotIdentity?.set_id);
  // The shell snapshot is a valid identity source too — Cards/Overview only
  // ever load the shell (not the full explore payload), so without this the
  // set id can fail to resolve for those tabs even though the shell already
  // knows which set it is.
  const shellIdentity = getSetSnapshotIdentity(shellPayload);
  const shellResourceId = toStableIdentifier(shellIdentity?.id ?? shellIdentity?.set_id);

  if (selectedResourceId && (!requestedResourceId || setIdentityMatchesTarget(selectedTarget, requestedResourceId))) {
    return selectedResourceId;
  }
  if (snapshotResourceId && setIdentityMatchesTarget(snapshotIdentity, requestedResourceId)) {
    return snapshotResourceId;
  }
  if (shellResourceId && (!requestedResourceId || setIdentityMatchesTarget(shellIdentity, requestedResourceId))) {
    return shellResourceId;
  }
  if (requestedResourceId) {
    return requestedResourceId;
  }
  return snapshotResourceId || shellResourceId || null;
}

function isSetStateForActiveSet(stateSetId, { requestedTargetId, selectedTarget, resolvedSetResourceId }) {
  const stateToken = normalizeSetIdentityToken(stateSetId);
  if (!stateToken) {
    return false;
  }
  const selectedTargetMatchesRequest = !requestedTargetId || setIdentityMatchesTarget(selectedTarget, requestedTargetId);
  const activeTokens = [
    resolvedSetResourceId,
    requestedTargetId,
    ...(selectedTargetMatchesRequest
      ? [
          selectedTarget?.id,
          selectedTarget?.set_id,
          selectedTarget?.target_id,
          selectedTarget?.slug,
          selectedTarget?.canonical_key,
          selectedTarget?.pokemon_api_set_id,
        ]
      : []),
  ]
    .map(normalizeSetIdentityToken)
    .filter(Boolean);
  return activeTokens.includes(stateToken);
}

function getSetValueScopeLabel(scope) {
  const scopeKey = String(scope || CANONICAL_SET_VALUE_SCOPE).trim() || CANONICAL_SET_VALUE_SCOPE;
  return SET_VALUE_SCOPE_OPTIONS.find((entry) => entry.key === scopeKey)?.label || scopeKey;
}

function getSetValueMetricLabel(scope) {
  return `${getSetValueScopeLabel(scope)} Set Value`;
}

function createSetValueHistoryState({
  status = "idle",
  setId = null,
  historiesByScope = {},
  loadedScopes = [],
  availableScopes = SET_VALUE_SCOPE_OPTIONS,
  meta = null,
  error = null,
} = {}) {
  return {
    status,
    setId: toStableIdentifier(setId),
    historiesByScope: historiesByScope && typeof historiesByScope === "object" ? historiesByScope : {},
    loadedScopes: Array.isArray(loadedScopes) ? loadedScopes.filter(Boolean) : [],
    availableScopes: Array.isArray(availableScopes) && availableScopes.length > 0 ? availableScopes : SET_VALUE_SCOPE_OPTIONS,
    meta: meta || null,
    error: error || null,
  };
}

function extractSnapshotCardsFromExplorePayload(payload) {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  if (Array.isArray(payload.cards)) {
    return payload.cards;
  }
  if (Array.isArray(payload?.cardPayload?.cards)) {
    return payload.cardPayload.cards;
  }
  if (Array.isArray(payload?.card_payload?.cards)) {
    return payload.card_payload.cards;
  }
  if (Array.isArray(payload?.cardsPayload?.cards)) {
    return payload.cardsPayload.cards;
  }
  if (Array.isArray(payload?.cards_payload?.cards)) {
    return payload.cards_payload.cards;
  }
  if (Array.isArray(payload?.setCards?.cards)) {
    return payload.setCards.cards;
  }
  if (Array.isArray(payload?.set_cards?.cards)) {
    return payload.set_cards.cards;
  }
  if (Array.isArray(payload?.cardsSnapshot?.cards)) {
    return payload.cardsSnapshot.cards;
  }
  if (Array.isArray(payload?.cards_snapshot?.cards)) {
    return payload.cards_snapshot.cards;
  }
  return [];
}

function buildInitialSetPageDataSeed({
  explorePayload = null,
  cardsPayload = null,
  marketDashboardPayload = null,
  overviewPayload = null,
} = {}) {
  const source = explorePayload && typeof explorePayload === "object" ? explorePayload : {};
  const cardsSource = cardsPayload && typeof cardsPayload === "object" ? cardsPayload : null;
  const marketDashboardSource =
    marketDashboardPayload && typeof marketDashboardPayload === "object" ? marketDashboardPayload : null;
  // Server-seeded slim /overview snapshot (Overview-tab direct entries only) —
  // already normalized via normalizeOverviewPayload server-side, passed
  // through untouched for overviewState hydration.
  const overviewSource = overviewPayload && typeof overviewPayload === "object" ? overviewPayload : null;
  const cards = Array.isArray(cardsSource?.cards) && cardsSource.cards.length > 0
    ? cardsSource.cards
    : extractSnapshotCardsFromExplorePayload(source);
  const cardPayload =
    cardsSource ||
    source.cardPayload ||
    source.card_payload ||
    source.cardsPayload ||
    source.cards_payload ||
    source.setCards ||
    source.set_cards ||
    null;
  const cardAppealMarketPriceCorrelation = resolvePreferredCardAppealCorrelation({
    explorePayload: source,
    cardsPayload: cardPayload,
  });
  const setValue = marketDashboardSource
    ? adaptSetValueHistoriesFromSources({ marketSnapshotPayload: marketDashboardSource })
    : adaptSetValueHistoriesFromSources({ explorePayload: source });
  const market = marketDashboardSource
    ? adaptMarketDashboardFromSources({ marketSnapshotPayload: marketDashboardSource })
    : adaptMarketDashboardFromSources({ explorePayload: source });
  const topMarketCards =
    Array.isArray(marketDashboardSource?.topChaseCards)
      ? marketDashboardSource.topChaseCards
      : Array.isArray(marketDashboardSource?.top_chase_cards)
      ? marketDashboardSource.top_chase_cards
      : Array.isArray(marketDashboardSource?.topMarketCards)
      ? marketDashboardSource.topMarketCards
      : Array.isArray(marketDashboardSource?.top_market_cards)
      ? marketDashboardSource.top_market_cards
      : market?.cards?.length > 0
      ? market.cards
      : Array.isArray(source.topMarketCards)
      ? source.topMarketCards
      : Array.isArray(source.top_market_cards)
      ? source.top_market_cards
      : Array.isArray(source.marketDashboard?.topMarketCards)
      ? source.marketDashboard.topMarketCards
      : Array.isArray(source.market_dashboard?.top_market_cards)
      ? source.market_dashboard.top_market_cards
      : Array.isArray(source.top_hits)
      ? source.top_hits
      : [];
  const setValueHistoriesByScope = setValue?.historiesByScope || {};
  const seededMarketDashboardPayload =
    marketDashboardSource ||
    (topMarketCards.length > 0 || hasAnySetValueHistory(setValueHistoriesByScope)
      ? {
          topChaseCards: topMarketCards,
          top_chase_cards: topMarketCards,
          marketMovers: market?.marketMovers || { heatingUp: [], coolingOff: [], all: [] },
          market_movers: market?.marketMovers || { heatingUp: [], coolingOff: [], all: [] },
          marketMoversByWindow: market?.marketMoversByWindow || null,
          market_movers_by_window: market?.marketMoversByWindow || null,
          setValueHistoriesByScope,
          set_value_histories_by_scope: setValueHistoriesByScope,
          performanceVsCostHistory: market?.performanceVsCostHistory || [],
          performance_vs_cost_history: market?.performanceVsCostHistory || [],
          availableScopes: setValue?.availableScopes || SET_VALUE_SCOPE_OPTIONS,
          meta: source.meta || {},
        }
      : null);

  return {
    cards,
    cardAppealMarketPriceCorrelation,
    setValueHistoriesByScope,
    marketDashboard: seededMarketDashboardPayload,
    overview: overviewSource,
    topMarketCards,
    simulationDrivers: selectSimulationDrivers(source).rows,
  };
}

function hasCompleteSetValueScopes(historiesByScope = {}) {
  return SET_VALUE_SCOPE_OPTIONS.every((scope) => Array.isArray(historiesByScope?.[scope.key]) && historiesByScope[scope.key].length > 0);
}

function hasAnySetValueHistory(historiesByScope = {}) {
  return Object.values(historiesByScope || {}).some((history) => Array.isArray(history) && history.length > 0);
}

function isExplicitNoCardsPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  if (cards.length > 0) {
    return false;
  }
  const snapshotCardCount = toNumber(payload?.meta?.snapshot?.cardCount ?? payload?.meta?.snapshot?.card_count);
  if (snapshotCardCount === 0) {
    return true;
  }
  const source = String(payload?.meta?.sources?.cards || "").toLowerCase();
  return source === "pokemon_canonical_cards";
}

function shouldSuppressSetPageWarning(warning, { hasTopHits, hasDecisionRanks }) {
  const text = String(warning || "").toLowerCase();
  if (!text) {
    return true;
  }
  if (hasTopHits && (text.includes("top hits") || text.includes("simulation drivers unavailable") || text.includes("simulation_input_cards_with_near_mint_price"))) {
    return true;
  }
  if (hasDecisionRanks && text.includes("rankings snapshot is stale relative to set page snapshot")) {
    return true;
  }
  if (text.includes("skipped live repair during route render")) {
    return true;
  }
  return false;
}

const RIP_COPY = {
  scoreLabel: "Rip Score",
  scoreRankLabel: "Rip Rank",
  summaryQuestion: "Should You Open This Set?",
  scoreDetailsLabel: "Show details",
  advancedLabel: "Advanced Score Details",
  recommendationLabel: "Recommendation",
  simpleMetrics: {
    chanceToBeatPackCost: "Chance to Beat Pack Cost",
    averagePackValue: "Expected Value",
    averageHitValue: "Average Hit Value",
    currentPackCost: "Pack Market Price",
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
    packCost: "Pack Market Price",
    typicalPack: "Typical Opening",
    averagePack: "Average Pack",
    badFloor: "Bad Floor",
    bigHit: "Big Hit Threshold",
    bigHitUpside: "Strong Upside",
    godPullUpside: "Jackpot Upside",
    bestPull: "Best Pull",
  },
  chartStats: {
    typicalPack: "Typical Opening",
    badPackFloor: "Bad Pack Floor Value",
    chanceToBeatPackCost: "Chance to Beat Pack Cost",
    chanceAtBigPull: "Chance at a Big Pull",
    bigHitUpside: "Strong Upside",
    godPullUpside: "Jackpot Upside",
    bestPull: "Best Simulated Pull",
  },
  advancedStats: {
    bigHitUpside: "Strong Upside",
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

function updateSetDetailQueryParams({ pathname, searchParams, tab, section, cardSort, movementFilter }) {
  const nextParams = new URLSearchParams(searchParams?.toString() || "");
  const nextTab = normalizeSetDetailTab(tab);
  nextParams.set("tab", nextTab);

  if (section) {
    nextParams.set("section", section);
  } else {
    nextParams.delete("section");
  }

  if (nextTab === "cards" && cardSort) {
    nextParams.set("card_sort", cardSort);
  } else if (nextTab !== "cards" || section !== "market-movers") {
    nextParams.delete("card_sort");
  }
  if (nextTab === "cards" && movementFilter) {
    nextParams.set("movement", movementFilter);
  } else if (nextTab !== "cards" || section !== "market-movers") {
    nextParams.delete("movement");
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
    "Profit explains how often simulated openings beat cost, how Expected Value compares with pack cost, and how much upside the better pulls create. A strong profit profile does not guarantee a profitable pack.",
  Safety:
    "Safety explains how painful the misses can feel. A set can have a strong overall score but still feel risky if the lower-end packs give back very little value.",
  "Set Desirability":
    "Set Desirability measures the popularity and depth of the Pokémon subjects represented in this set. It does not use card prices or predict future value. It supports Collector Appeal as its roster base and does not receive a separate RIP Score weight of its own.",
  // The trailing sentence used to read "It contributes 20% to Overall RIP,
  // alongside Financial RIP at 80%." That published a composition weight — and
  // published the WRONG one, since the canonical blend is 0.90 Financial RIP +
  // 0.10 Collector Appeal. No public surface states a weight, a contribution
  // or a split, so the claim is removed rather than corrected to 90/10.
  "Collector Appeal":
    "Collector Appeal combines the set's roster desirability with how often a modeled pack delivers a desirable card and how meaningful its elite chase paths are. It needs the set's modeled pull structure and uses no card prices.",
  // Legacy key kept only for stale render paths.
  Desirability:
    "Set Desirability measures the popularity and depth of the Pokémon subjects in the set. It does not use card prices or predict future value.",
  Stability:
    "Stability explains whether value is spread across the set or concentrated in only a few cards. Better stability means the set is less dependent on one or two major hits.",
};

const DESIRABILITY_FALLBACK_COPY = "Using a fallback Opening Desirability estimate until this set has enough data.";
const DESIRABILITY_NOT_CALCULATED_COPY = "Not calculated yet.";
const PERFORMANCE_VS_COST_INFO_TEXT = (
  <div className="space-y-2 text-left">
    <p className="font-semibold text-[var(--text-primary)]">Opening Profit vs Cost</p>
    <p>Tracks how simulated opening outcomes compare against pack market price over time.</p>
    <ul className="space-y-1 pl-3">
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span>
          <span className="font-semibold text-[var(--text-primary)]">Strong Upside:</span> P95 threshold. Roughly 5% of simulated packs landed above this value.
        </span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span>
          <span className="font-semibold text-[var(--text-primary)]">Expected Value:</span> average simulated pack value.
        </span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span>
          <span className="font-semibold text-[var(--text-primary)]">Typical Opening:</span> median (P50) simulated pack value.
        </span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span>Above 1.0x means that outcome is above pack market price; below 1.0x means it is below pack market price.</span>
      </li>
    </ul>
  </div>
);

// Stable info bubble for the whole Simulation Results card (its title icon).
// Per-sub-tab explanations live in the section headers below the tab strip.
const SIMULATION_RESULTS_INFO_TEXT = (
  <div className="space-y-2 text-left">
    <p className="font-semibold text-[var(--text-primary)]">Simulation Results</p>
    <p>Everything the pack-opening simulation produced for this set: how outcomes are distributed, how value compares with cost over time, which cards and rarities carry the value, the pack paths modeled, and the raw metrics behind it.</p>
    <p>Modeled from simulated pack openings using current pack price, card values, pull rates, and pack path assumptions.</p>
  </div>
);

// Section header for the Opening Performance vs Cost sub-tab. Describes the
// technical (simulation-variant) series names the chart actually renders.
const OPENING_PERFORMANCE_VS_COST_INFO_TEXT = (
  <div className="space-y-2 text-left">
    <p className="font-semibold text-[var(--text-primary)]">Opening Profit vs Cost</p>
    <p>How simulated opening value compares with pack market price over time, kept technical for the simulation view.</p>
    <ul className="space-y-1 pl-3">
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span><span className="font-semibold text-[var(--text-primary)]">Expected Value vs Cost:</span> average simulated pack value ÷ pack price.</span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span><span className="font-semibold text-[var(--text-primary)]">Typical Opening (P50) vs Cost:</span> the median simulated pack value ÷ pack price.</span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span><span className="font-semibold text-[var(--text-primary)]">Strong Upside (P95) vs Cost:</span> the P95 threshold ÷ pack price.</span>
      </li>
      <li className="flex gap-2">
        <span className="flex-none">•</span>
        <span>Above 1.0x means that outcome exceeds pack market price; below 1.0x means it is below.</span>
      </li>
    </ul>
  </div>
);

const SIMULATION_DRIVERS_INFO_TEXT =
  "Cards contributing most to modeled pack value after pull odds and card prices are applied.";
const PACK_PATHS_INFO_TEXT =
  "Counts of the normal and special pack-path outcome states the simulation model uses for this set.";
const SIMULATION_METRICS_INFO_TEXT =
  "The raw simulation and EV-derived metrics for this set — not the RIP pillar score presentation. Missing fields show an honest “not available” state rather than an invented number.";

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
  // Average Loss is displayed as a signed value ≤ $0 (mean − cost), and its
  // trend inputs use that same signed scale — so "higher" (toward $0) = good.
  averageLoss: "higher",
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
  setValue: ["set_value_for_validation", "setValueForValidation", "current_checklist_set_value", "currentChecklistSetValue", "checklist_set_value", "checklistSetValue", "simulated_set_value", "simulatedSetValue", "set_value", "setValue"],
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

const DESIRABILITY_VALIDATION_METRICS = [
  {
    key: "setValue",
    label: "Set Value",
    summaryLabel: "Set Value",
    sampleLabel: "opening sets with value data",
    description: "This is the cleanest market confirmation check. Higher desirability should generally align with stronger total checklist value.",
    resolver: getValidationSetValueMetric,
    formatter: formatCurrency,
    tickFormatter: formatCompactCurrency,
  },
  {
    key: "packCost",
    label: "Pack Cost",
    summaryLabel: "Pack Market Price",
    sampleLabel: "opening sets with pack cost",
    description: "Highly desirable sets often become more expensive to open. This helps explain why cost-adjusted upside can fall even when chase cards are strong.",
    valueKeys: ["pack_cost", "packCost", "current_pack_cost", "currentPackCost", "pack_market_price", "packMarketPrice"],
    formatter: formatCurrency,
    tickFormatter: formatCompactCurrency,
  },
  {
    key: "expectedValue",
    label: "Expected Value",
    summaryLabel: "Expected Value",
    sampleLabel: "simulated opening sets",
    description: "EV can align with desirability, but it is also affected by pack price, pull rates, and value distribution.",
    valueKeys: ["mean_value", "meanValue", "expected_value", "expectedValue", "average_pack_value", "averagePackValue"],
    formatter: formatCurrency,
    tickFormatter: formatCompactCurrency,
  },
  {
    key: "p95",
    label: "Strong Upside (P95)",
    summaryLabel: "Strong Upside (P95) vs Cost",
    sampleLabel: "simulated opening sets",
    description: "P95 is cost-adjusted upper-tail upside. A negative relationship can happen when highly desirable sets become expensive to open.",
    valueKeys: ["p95_value_to_cost_ratio", "p95ValueToCostRatio", "big_hit_upside", "bigHitUpside"],
    formatter: formatMultiplier,
    tickFormatter: formatCompactMultiplier,
  },
];

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getFirstNumericValue(source, keys = []) {
  return getFirstNumericMetric(source, keys).value;
}

function getFirstNumericMetric(source, keys = []) {
  for (const key of keys) {
    const value = toNumber(source?.[key]);
    if (value !== null) {
      return { key, value };
    }
  }
  return { key: null, value: null };
}

function getFirstNumericFromValues(entries = []) {
  for (const entry of entries) {
    const value = toNumber(entry?.value);
    if (value !== null && value > 0) {
      return { key: entry?.key || null, value };
    }
  }
  return { key: null, value: null };
}

function getLatestSetValueFromHistory(history, sourceKey) {
  if (!Array.isArray(history) || history.length === 0) {
    return { key: null, value: null };
  }
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const point = history[index];
    const value = toNumber(point?.setValue ?? point?.set_value ?? point?.value);
    if (value !== null && value > 0) {
      return { key: sourceKey, value };
    }
  }
  return { key: null, value: null };
}

function getValidationSetValueMetric(setRow) {
  if (!setRow) {
    return { key: null, value: null };
  }

  const historiesByScope =
    setRow.setValueHistoriesByScope ||
    setRow.set_value_histories_by_scope ||
    setRow.market?.setValueHistoriesByScope ||
    setRow.market?.set_value_histories_by_scope ||
    setRow.marketDashboard?.setValueHistoriesByScope ||
    setRow.marketDashboard?.set_value_histories_by_scope ||
    setRow.snapshot?.setValueHistoriesByScope ||
    setRow.snapshot?.set_value_histories_by_scope ||
    null;
  const standardHistory = historiesByScope?.standard || historiesByScope?.checklist || null;
  const historyMetric = getLatestSetValueFromHistory(standardHistory, "setValueHistoriesByScope.standard");
  if (historyMetric.value !== null) {
    return historyMetric;
  }
  const directHistoryMetric = getLatestSetValueFromHistory(setRow.setValueHistory || setRow.set_value_history, "setValueHistory");
  if (directHistoryMetric.value !== null) {
    return directHistoryMetric;
  }

  const directMetric = getFirstNumericFromValues([
    { key: "currentChecklistSetValue", value: setRow.currentChecklistSetValue },
    { key: "current_checklist_set_value", value: setRow.current_checklist_set_value },
    { key: "set_value_for_validation", value: setRow.set_value_for_validation },
    { key: "setValueForValidation", value: setRow.setValueForValidation },
    { key: "checklistSetValue", value: setRow.checklistSetValue },
    { key: "checklist_set_value", value: setRow.checklist_set_value },
    { key: "latestChecklistSetValue", value: setRow.latestChecklistSetValue },
    { key: "latest_checklist_set_value", value: setRow.latest_checklist_set_value },
    { key: "currentSetValue", value: setRow.currentSetValue },
    { key: "current_set_value", value: setRow.current_set_value },
    { key: "marketSetValue", value: setRow.marketSetValue },
    { key: "market_set_value", value: setRow.market_set_value },
    { key: "setValue", value: setRow.setValue },
    { key: "set_value", value: setRow.set_value },
    { key: "totalSetValue", value: setRow.totalSetValue },
    { key: "total_set_value", value: setRow.total_set_value },
    { key: "summary.checklistSetValue", value: setRow.summary?.checklistSetValue },
    { key: "summary.checklist_set_value", value: setRow.summary?.checklist_set_value },
    { key: "summary.setValue", value: setRow.summary?.setValue },
    { key: "summary.set_value", value: setRow.summary?.set_value },
    { key: "market.checklistSetValue", value: setRow.market?.checklistSetValue },
    { key: "market.checklist_set_value", value: setRow.market?.checklist_set_value },
    { key: "market.setValue", value: setRow.market?.setValue },
    { key: "market.set_value", value: setRow.market?.set_value },
    { key: "metrics.checklistSetValue", value: setRow.metrics?.checklistSetValue },
    { key: "metrics.checklist_set_value", value: setRow.metrics?.checklist_set_value },
  ]);
  if (directMetric.value !== null) {
    return directMetric;
  }

  return getFirstNumericFromValues([
    { key: "simulated_set_value", value: setRow.simulated_set_value },
    { key: "simulatedSetValue", value: setRow.simulatedSetValue },
    { key: "summary.simulated_set_value", value: setRow.summary?.simulated_set_value },
    { key: "summary.simulatedSetValue", value: setRow.summary?.simulatedSetValue },
  ]);
}

function getValueRelatedKeys(source, prefix = "") {
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    return [];
  }
  return Object.keys(source)
    .filter((key) => /value|set|market|checklist/i.test(key))
    .map((key) => (prefix ? `${prefix}.${key}` : key));
}

function getDesirabilityValidationMissingSetValueSample(rows) {
  return rows
    .filter((row) => {
      const desirability = getFirstNumericValue(row, ["desirability_score", "desirabilityScore", "relative_desirability_score", "relativeDesirabilityScore"]);
      return desirability !== null && getValidationSetValueMetric(row).value === null;
    })
    .slice(0, 6)
    .map((row) => ({
      name: row.name || row.set_name || row.target_id || null,
      slug: row.slug || row.canonical_key || row.target_id || null,
      desirabilityScore: getFirstNumericValue(row, ["desirability_score", "desirabilityScore", "relative_desirability_score", "relativeDesirabilityScore"]),
      rowKeys: row && typeof row === "object" ? Object.keys(row).sort() : [],
      valueRelatedKeys: [
        ...getValueRelatedKeys(row),
        ...getValueRelatedKeys(row.summary, "summary"),
        ...getValueRelatedKeys(row.market, "market"),
        ...getValueRelatedKeys(row.marketDashboard, "marketDashboard"),
        ...getValueRelatedKeys(row.metrics, "metrics"),
        ...getValueRelatedKeys(row.snapshot, "snapshot"),
      ],
    }));
}

function getDesirabilityValidationDiagnostics(rows, metric, points) {
  const sourceRows = Array.isArray(rows) ? rows : [];
  const selectedMetric = metric || DESIRABILITY_VALIDATION_METRICS[0];
  const samples = {
    missingDesirability: [],
    missingMetric: [],
    plotted: [],
  };
  const counts = sourceRows.reduce(
    (acc, row) => {
      const desirability = getFirstNumericValue(row, ["desirability_score", "desirabilityScore", "pure_desirability_score", "pureDesirabilityScore", "relative_desirability_score", "relativeDesirabilityScore"]);
      const metricResult = selectedMetric.resolver ? selectedMetric.resolver(row) : getFirstNumericMetric(row, selectedMetric.valueKeys);
      const metricValue = metricResult.value;
      const sample = {
        name: row?.name || row?.set_name || row?.target_id || null,
        slug: row?.slug || row?.canonical_key || row?.target_id || null,
        desirability,
        metricValue,
        metricSourceKey: metricResult.key,
      };

      if (desirability !== null) {
        acc.rowsWithDesirability += 1;
      } else if (samples.missingDesirability.length < 3) {
        samples.missingDesirability.push(sample);
      }

      if (metricValue !== null) {
        acc.rowsWithSelectedMetric += 1;
      } else if (samples.missingMetric.length < 3) {
        samples.missingMetric.push(sample);
      }

      if (desirability !== null && metricValue !== null && samples.plotted.length < 3) {
        samples.plotted.push(sample);
      }

      return acc;
    },
    {
      totalRows: sourceRows.length,
      rowsWithDesirability: 0,
      rowsWithSelectedMetric: 0,
      finalPlottedRows: Array.isArray(points) ? points.length : 0,
    }
  );

  return {
    metricKey: selectedMetric.key,
    metricLabel: selectedMetric.label,
    ...counts,
    samples,
  };
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

function getFirstNumericFromSources(sources, keys = []) {
  for (const source of sources) {
    const value = getFirstNumericValue(source, keys);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function getFirstTextFromSources(sources, keys = []) {
  for (const source of sources) {
    for (const key of keys) {
      const text = String(source?.[key] || "").trim();
      if (text) {
        return text;
      }
    }
  }
  return null;
}

// The legacy "Without/With Desirability" comparison helpers were retired with
// the strip they fed, and that strip has since been retired too.
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

function formatCompactCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "";
  }
  if (Math.abs(parsed) >= 1000000) {
    return `$${(parsed / 1000000).toFixed(1)}M`;
  }
  if (Math.abs(parsed) >= 1000) {
    return `$${(parsed / 1000).toFixed(0)}K`;
  }
  return `$${parsed.toFixed(0)}`;
}

function formatCompactMultiplier(value) {
  const parsed = toNumber(value);
  return parsed === null ? "" : `${parsed.toFixed(1)}x`;
}

function formatCorrelationValue(value) {
  const parsed = toNumber(value);
  return parsed === null ? "n/a" : parsed.toFixed(2);
}

function getAverageRanks(values) {
  const sorted = values
    .map((value, index) => ({ value, index }))
    .sort((a, b) => a.value - b.value);
  const ranks = new Array(values.length);
  let cursor = 0;

  while (cursor < sorted.length) {
    let end = cursor;
    while (end + 1 < sorted.length && sorted[end + 1].value === sorted[cursor].value) {
      end += 1;
    }
    const averageRank = (cursor + 1 + end + 1) / 2;
    for (let index = cursor; index <= end; index += 1) {
      ranks[sorted[index].index] = averageRank;
    }
    cursor = end + 1;
  }

  return ranks;
}

function calculatePearsonCorrelation(points) {
  if (!Array.isArray(points) || points.length < 3) {
    return null;
  }
  const n = points.length;
  const meanX = points.reduce((sum, point) => sum + point.x, 0) / n;
  const meanY = points.reduce((sum, point) => sum + point.y, 0) / n;
  let numerator = 0;
  let xVariance = 0;
  let yVariance = 0;

  points.forEach((point) => {
    const xDelta = point.x - meanX;
    const yDelta = point.y - meanY;
    numerator += xDelta * yDelta;
    xVariance += xDelta * xDelta;
    yVariance += yDelta * yDelta;
  });

  const denominator = Math.sqrt(xVariance * yVariance);
  return denominator === 0 ? null : numerator / denominator;
}

function calculateSpearmanCorrelation(points) {
  if (!Array.isArray(points) || points.length < 3) {
    return null;
  }
  const xRanks = getAverageRanks(points.map((point) => point.x));
  const yRanks = getAverageRanks(points.map((point) => point.y));
  return calculatePearsonCorrelation(points.map((point, index) => ({ x: xRanks[index], y: yRanks[index] })));
}

function calculateRegressionLine(points) {
  if (!Array.isArray(points) || points.length < 3) {
    return [];
  }
  const n = points.length;
  const meanX = points.reduce((sum, point) => sum + point.x, 0) / n;
  const meanY = points.reduce((sum, point) => sum + point.y, 0) / n;
  let numerator = 0;
  let denominator = 0;

  points.forEach((point) => {
    const xDelta = point.x - meanX;
    numerator += xDelta * (point.y - meanY);
    denominator += xDelta * xDelta;
  });

  if (denominator === 0) {
    return [];
  }

  const slope = numerator / denominator;
  const intercept = meanY - slope * meanX;
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  if (!Number.isFinite(slope) || !Number.isFinite(intercept) || minX === maxX) {
    return [];
  }

  return [
    { x: minX, y: slope * minX + intercept, kind: "pearsonTrend" },
    { x: maxX, y: slope * maxX + intercept, kind: "pearsonTrend" },
  ];
}

function getRelationshipLabel(correlation) {
  const parsed = toNumber(correlation);
  if (parsed === null) {
    return "Not enough data";
  }
  const magnitude = Math.abs(parsed);
  if (magnitude < 0.2) {
    return "Little/no relationship";
  }
  if (parsed < 0) {
    return "Negative relationship";
  }
  if (magnitude >= 0.7) {
    return "Strong positive";
  }
  if (magnitude >= 0.4) {
    return "Moderate positive";
  }
  return "Weak positive";
}

function getPaddedNumberDomain(values, { floorAtZero = false, fallback = [0, 100] } = {}) {
  const numeric = (Array.isArray(values) ? values : []).map(toNumber).filter((value) => value !== null);
  if (numeric.length === 0) {
    return fallback;
  }
  let min = Math.min(...numeric);
  let max = Math.max(...numeric);
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.08, 1);
    min -= pad;
    max += pad;
  } else {
    const pad = (max - min) * 0.08;
    min -= pad;
    max += pad;
  }
  if (floorAtZero) {
    min = Math.max(0, min);
  }
  return [Number(min.toFixed(2)), Number(max.toFixed(2))];
}

function hasRenderableOutcomeDistributionRows(distributionRows, thresholdRows) {
  const thresholdSource = Array.isArray(thresholdRows) ? thresholdRows : [];
  const distributionSource = Array.isArray(distributionRows) ? distributionRows : [];
  const source = thresholdSource.length > 0 ? thresholdSource : distributionSource;
  return source.some((row) => {
    const floor = toNumber(row?.threshold_floor ?? row?.bin_floor);
    const ceiling = toNumber(row?.threshold_ceiling ?? row?.bin_ceiling);
    const probability = toNumber(row?.probability);
    return (floor !== null || ceiling !== null) && probability !== null;
  });
}

function hasRenderablePackPathRows(packPaths, normalStateRows) {
  const source = packPaths && typeof packPaths === "object" ? packPaths : {};
  const hasPackPathCounts = Object.values(source).some((value) => {
    const count = toNumber(value);
    return count !== null && count > 0;
  });
  const hasNormalStateCounts = (Array.isArray(normalStateRows) ? normalStateRows : []).some(([, value]) => {
    const count = toNumber(value);
    return count !== null && count > 0;
  });
  return hasPackPathCounts || hasNormalStateCounts;
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
    return `The current pack price is ${pricePosition} modeled Expected Value, so this reads like ${setType} at today's inputs. ${concentration}. The price/value relationship points to ${returnRatio !== null && returnRatio >= 1 ? "long-run EV that can meet or clear cost before fees" : "openings that still need strong pulls to overcome pack cost"}.`;
  }

  if (setValue !== null) {
    return `Market context is partially available for this set, with set value at ${formatCurrency(setValue)}. ${concentration}, so the read is more useful for understanding where value sits than for judging pack price today.`;
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
    return `Expected Value is ${formatCurrency(averagePackValue)} against a ${formatCurrency(packCost)} pack price, with ${ratioText} and ${concentration}.`;
  }

  if (setValue !== null) {
    return `Set value is ${formatCurrency(setValue)}, with pack price context still limited for this set.`;
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

function getCardMovement30d(card) {
  const nested = card?.movement30d ?? card?.movement_30d ?? {};
  const amount = (
    toNumber(card?.change30dAmount) ??
    toNumber(card?.change_30d_amount) ??
    toNumber(nested?.changeAmount) ??
    toNumber(nested?.change_amount) ??
    null
  );
  const percent = (
    toNumber(card?.change30dPercent) ??
    toNumber(card?.change_30d_percent) ??
    toNumber(nested?.changePercent) ??
    toNumber(nested?.change_percent) ??
    null
  );
  const score = (
    toNumber(card?.movementScore) ??
    toNumber(card?.movement_score) ??
    toNumber(nested?.score) ??
    toNumber(nested?.movementScore) ??
    null
  );
  const label = card?.movementLabel || card?.movement_label || nested?.label || null;
  const enoughHistory = Boolean(card?.enoughHistory ?? card?.enough_history ?? nested?.enoughHistory ?? nested?.enough_history);
  if (amount === null && percent === null && score === null) {
    return null;
  }
  return {
    amount,
    percent,
    score,
    label,
    enoughHistory,
    fullWindowCoverage: Boolean(nested?.fullWindowCoverage ?? nested?.full_window_coverage),
    isPartialWindow: Boolean(nested?.isPartialWindow ?? nested?.is_partial_window),
    windowCoverageDays: toNumber(nested?.windowCoverageDays ?? nested?.window_coverage_days),
    requestedWindowDays: toNumber(nested?.requestedWindowDays ?? nested?.requested_window_days) ?? 30,
  };
}

function getMovementAccessiblePeriod(movement) {
  if (!movement?.isPartialWindow) {
    return null;
  }
  const coverageDays = toNumber(movement?.windowCoverageDays);
  return coverageDays === null
    ? "since the first available observation"
    : `since the first available observation, covering ${coverageDays} ${coverageDays === 1 ? "day" : "days"}`;
}

// Card-shaped placeholder for the checklist grid's image slot: a faint
// trading-card silhouette inside the tile's aspect-ratio box. `shimmer`
// pulses while the remote image is still loading; the static variant with a
// label is the settled "image unavailable" presentation (missing URL or a
// failed load) — intentionally distinct from the loading state so a slow
// image never reads as a broken card.
function CardImagePlaceholder({ shimmer = false, label = null }) {
  return (
    <div
      className={`absolute inset-1 flex flex-col items-center justify-center gap-1.5 rounded-md border border-[rgba(255,255,255,0.05)] ${
        shimmer ? "animate-pulse bg-[rgba(148,163,184,0.09)]" : "bg-[rgba(148,163,184,0.05)]"
      }`}
      aria-hidden={label ? undefined : "true"}
    >
      <svg viewBox="0 0 24 24" className="h-9 w-9 text-[rgba(148,163,184,0.35)]" fill="none" stroke="currentColor" strokeWidth="1.25" aria-hidden="true">
        <rect x="5.5" y="3" width="13" height="18" rx="1.8" />
        <circle cx="12" cy="9.5" r="2.4" />
        <path d="M8.4 16.6c1-1.7 2.2-2.6 3.6-2.6s2.6.9 3.6 2.6" />
      </svg>
      {label ? (
        <span className="px-2 text-center text-[10px] font-medium leading-tight text-[rgba(148,163,184,0.6)]">{label}</span>
      ) : null}
    </div>
  );
}

function ChecklistCardTile({ card, movementWindow = "7D" }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || null;
  const name = card?.name || "Unknown card";
  const number = card?.printedNumber || card?.cardNumber || null;
  const rarity = card?.rarity || null;
  const subtypeLabel = Array.isArray(card?.subtypes) && card.subtypes.length > 0 ? card.subtypes.join(" / ") : null;
  const marketPrice = getCardMarketPrice(card);
  const marketDelta = (movementWindow === "7D" ? getCardMovement7d(card) : getCardMovement30d(card)) || getCardMarketDelta(card);
  const hasPriceData = marketPrice !== null;
  // Remote card art lands well after the tile's data (about a second on a
  // cold cache), so the aspect-ratio box shows a shimmering card silhouette
  // and the image fades in once loaded — the grid keeps its final layout
  // instead of flashing empty frames. Cached images may complete before
  // React attaches onLoad (SSR-seeded grids), so the ref checks .complete.
  const [isImageLoaded, setIsImageLoaded] = useState(false);
  const [hasImageFailed, setHasImageFailed] = useState(false);

  useEffect(() => {
    setIsImageLoaded(false);
    setHasImageFailed(false);
  }, [imageUrl]);

  // Priority 5 (secondary metadata): price/delta badges are already part of
  // the same fetched payload as name/number/rarity — there's nothing extra to
  // fetch — but computing and painting them for a full batch of tiles at once
  // is deprioritized behind the base grid via startTransition, so the name +
  // image (the part that makes a tile identifiable/usable) commits first. The
  // badge slot's width is reserved from the tile's first commit either way,
  // so this reveal never shifts the surrounding layout.
  const [isMetaRevealed, setIsMetaRevealed] = useState(false);
  const cardMetaKey = `${getChecklistCardKey(card)}:${marketPrice ?? ""}:${marketDelta?.amount ?? ""}:${marketDelta?.percent ?? ""}:${movementWindow}`;

  useEffect(() => {
    setIsMetaRevealed(false);
    if (!hasPriceData) {
      return;
    }
    startTransition(() => {
      setIsMetaRevealed(true);
    });
  }, [cardMetaKey, hasPriceData]);

  return (
    // The tile shell is intentionally transparent: the set artwork behind the
    // Cards grid must stay visible through the tile and through the metadata
    // strip under the image. Only borders, the card art, and text carry weight
    // here — no surface fill, no frost, no full-tile gradient. Hover keeps the
    // lift and the accent border but must never paint an opaque fill back in.
    <article className="group h-full overflow-hidden rounded-lg border border-[rgba(255,255,255,0.10)] bg-transparent backdrop-blur-none transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(94,234,212,0.40)]">
      <div className="relative aspect-[3/4] w-full border-b border-[rgba(255,255,255,0.07)] bg-transparent p-1">
        {imageUrl && !hasImageFailed ? (
          <>
            {!isImageLoaded ? <CardImagePlaceholder shimmer /> : null}
            {/* The card art itself stays fully opaque and carries its own drop
                shadow so it reads as a solid object floating over the set
                artwork now that the tile behind it is transparent. */}
            <img
              ref={(node) => {
                if (node && node.complete && node.naturalWidth > 0) {
                  setIsImageLoaded(true);
                }
              }}
              src={imageUrl}
              alt={name}
              onLoad={() => setIsImageLoaded(true)}
              onError={() => setHasImageFailed(true)}
              className={`h-full w-full object-contain drop-shadow-[0_4px_12px_rgba(2,6,23,0.55)] transition-all duration-300 group-hover:scale-[1.01] ${isImageLoaded ? "opacity-100" : "opacity-0"}`}
              loading="lazy"
              decoding="async"
            />
          </>
        ) : (
          <CardImagePlaceholder label="Image unavailable" />
        )}
      </div>
      {/* Metadata sits directly on the set artwork — no plate, no frost. A
          text-shadow (inherited by the name/number/price/movement/rarity
          children) keeps it legible over bright artwork without reintroducing
          a surface. */}
      <div className="space-y-1 bg-transparent px-2.5 py-2 [text-shadow:0_1px_3px_rgba(2,6,23,0.9)]">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-[13px] font-semibold leading-snug text-[var(--text-primary)]">{name}</p>
            {number ? <p className="truncate text-[11px] text-[var(--text-secondary)]">No. {number}</p> : null}
          </div>
          <div className="min-w-[7.5rem] shrink-0 text-right">
            {isMetaRevealed || !hasPriceData ? (
              <MarketValueChange
                value={marketPrice}
                changeAmount={marketDelta?.amount}
                changePercent={marketDelta?.percent}
                windowLabel={movementWindow}
                windowLabelPlacement="below"
                unavailable={!marketDelta}
                accessiblePeriodLabel={getMovementAccessiblePeriod(marketDelta)}
                alignment="right"
                variant="card-tile"
                accessibleLabel={`${name} market price`}
              />
            ) : (
              <div className="ml-auto space-y-1" aria-hidden="true">
                <div className="ml-auto h-3.5 w-12 animate-pulse rounded bg-[rgba(148,163,184,0.12)]" />
                <div className="ml-auto h-3 w-24 animate-pulse rounded bg-[rgba(148,163,184,0.10)]" />
                <div className="ml-auto h-2.5 w-6 animate-pulse rounded bg-[rgba(148,163,184,0.08)]" />
              </div>
            )}
          </div>
        </div>
        {rarity || subtypeLabel ? (
          <p className="truncate text-[11px] text-[var(--text-secondary)]">
            {[rarity, subtypeLabel].filter(Boolean).join(" · ")}
          </p>
        ) : null}
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
    toNumber(card?.currentPrice) ??
    toNumber(card?.current_price) ??
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

// Same stable identity the checklist grid uses for React keys — appended
// pages must never introduce a duplicate of a card that is already rendered.
function getChecklistCardKey(card) {
  return String(card?.id || card?.cardNumber || card?.card_number || card?.name || "");
}

function dedupeChecklistCards(cards) {
  const seen = new Set();
  const result = [];
  for (const card of cards) {
    const key = getChecklistCardKey(card);
    if (key && seen.has(key)) {
      continue;
    }
    if (key) {
      seen.add(key);
    }
    result.push(card);
  }
  return result;
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

function formatLongDate(value) {
  if (!value) {
    return "Date unavailable";
  }
  return formatHistoryDate(value, { year: "numeric", month: "short", day: "numeric" }) || String(value);
}

function formatSectionFreshnessInfo(freshness) {
  if (!freshness || typeof freshness !== "object") {
    return "";
  }
  const details = [];
  if (freshness.dataAsOf) {
    details.push(`Data as of ${formatLongDate(freshness.dataAsOf)}`);
  }
  if (freshness.lastSuccessfulAt) {
    details.push(`Last refreshed ${formatLongDate(freshness.lastSuccessfulAt)}`);
  }
  if (freshness.status === "stale") {
    details.push("Showing the last valid snapshot while the latest build is incomplete.");
  }
  return details.length > 0 ? ` ${details.join(". ")}.` : "";
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

function SetValueScopeSelector({ scopes, value, onChange }) {
  const scopeOptions = Array.isArray(scopes) && scopes.length > 0 ? scopes : VISIBLE_SET_VALUE_SCOPE_OPTIONS;

  return (
    <SegmentedControl
      className="flex justify-center"
      options={scopeOptions.map((entry) => ({ value: entry.key, label: entry.label }))}
      value={value}
      onChange={onChange}
      ariaLabel="Set scope"
      equalWidth
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
  const row = active && payload?.[0]?.payload;
  if (!row) {
    return null;
  }
  return (
    <MarketTrendTooltipCard
      date={row.date}
      value={row.setValue}
      deltaAmount={row.deltaFromPrevious}
      deltaPercent={row.deltaPercentFromPrevious}
      isCarriedForward={row.isCarriedForward}
      sourceDate={row.sourceDate}
    />
  );
}

function CompactSparkline({ points, valueKey = "value", trendDirection = "neutral", className = "", showTooltip = true, emptyLabel = "Awaiting trend" }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [tooltipX, setTooltipX] = useState(null);
  const pointerMode = usePointerMode();
  const isCoarsePointer = pointerMode === POINTER_MODE_COARSE;
  const containerRef = useRef(null);
  const gestureRef = useRef(null);
  const chartId = useId().replace(/:/g, "");
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
  const selectAtClientX = (clientX) => {
    const element = containerRef.current;
    if (!element || numericPoints.length === 0) {
      return;
    }
    const bounds = element.getBoundingClientRect();
    const ratio = bounds.width > 0 ? (clientX - bounds.left) / bounds.width : 0;
    setActiveIndex(findNearestPointIndex(numericPoints, chartPoints.length, ratio));
    setTooltipX(
      clampTooltipX({
        chartLeft: bounds.left,
        chartWidth: bounds.width,
        pointerX: clientX - bounds.left,
        // Matches MarketTrendTooltipCard's max-w-[14rem].
        tooltipWidth: 224,
        viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth,
        gutter: 8,
      })
    );
  };

  const clearSelection = () => {
    setActiveIndex(null);
    setTooltipX(null);
  };

  // Mouse and trackpad keep the exact hover behaviour they have today.
  const handlePointerMove = (event) => {
    if (event.pointerType === "mouse") {
      selectAtClientX(event.clientX);
      return;
    }
    const gesture = gestureRef.current;
    if (!gesture) {
      return;
    }
    const classification = classifyPointerGesture({
      startX: gesture.startX,
      startY: gesture.startY,
      currentX: event.clientX,
      currentY: event.clientY,
      threshold: TAP_MOVEMENT_THRESHOLD_PX,
    });
    if (classification === "scroll") {
      // The finger is heading down the page. Hand it back and stop tracking.
      gestureRef.current = null;
      return;
    }
    if (classification === "scrub") {
      gesture.moved = true;
      selectAtClientX(event.clientX);
    }
  };

  const handlePointerDown = (event) => {
    if (event.pointerType === "mouse") {
      return;
    }
    gestureRef.current = { startX: event.clientX, startY: event.clientY, moved: false };
  };

  const handlePointerUp = (event) => {
    if (event.pointerType === "mouse") {
      return;
    }
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.moved) {
      // A scrub already selected as it went; leave the selection visible.
      return;
    }
    // A tap on the already-selected point dismisses it; any other tap selects.
    const element = containerRef.current;
    if (element && activePoint) {
      const bounds = element.getBoundingClientRect();
      const ratio = bounds.width > 0 ? (event.clientX - bounds.left) / bounds.width : 0;
      if (findNearestPointIndex(numericPoints, chartPoints.length, ratio) === activeIndex) {
        clearSelection();
        return;
      }
    }
    selectAtClientX(event.clientX);
  };

  const handlePointerLeave = (event) => {
    // Touch selections must survive the finger leaving the screen — that is the
    // whole point of tap-to-inspect. Only hover clears on leave.
    if (event?.pointerType === "mouse" || !isCoarsePointer) {
      clearSelection();
    }
  };

  if (numericPoints.length < 2) {
    return (
      <div className={["flex h-16 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 text-xs text-[var(--text-secondary)] max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent", className].filter(Boolean).join(" ")}>
        {emptyLabel}
      </div>
    );
  }

  const minY = Math.min(...numericPoints.map((point) => point.y));
  const maxY = Math.max(...numericPoints.map((point) => point.y));
  const yRange = maxY - minY || 1;
  const xRange = chartPoints.length - 1 || numericPoints.length - 1 || 1;
  const polylinePoints = numericPoints
    .map((point) => {
      const x = 2 + (point.index / xRange) * 96;
      const y = 36 - ((point.y - minY) / yRange) * 28;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const areaPath = numericPoints.length > 0
    ? `M ${polylinePoints.replaceAll(" ", " L ")} L 98 40 L 2 40 Z`
    : "";
  const activeX = activePoint ? 2 + (activePoint.index / xRange) * 96 : null;
  const activeY = activePoint ? 36 - ((activePoint.y - minY) / yRange) * 28 : null;
  const gradientId = `compact-sparkline-gradient-${chartId}`;
  const glowId = `compact-sparkline-glow-${chartId}`;

  return (
    <div
      ref={containerRef}
      data-compact-sparkline
      data-pointer-mode={pointerMode}
      role="img"
      aria-label={
        activePoint
          ? `Price trend. Selected ${formatLongDate(activePoint.date)}: ${formatCurrency(activePoint.y)}.`
          : "Price trend"
      }
      // touch-pan-y emits touch-action: pan-y - the browser keeps vertical
      // scrolling and this component gets horizontal movement for scrubbing.
      //
      // z-30, and it must stay below the pinned set-control block.
      // `.dashboard-container` is `isolate`, so this element and
      // `.set-detail-sticky-tabs` (z-index 40) are painted in the SAME stacking
      // context. At 60 — the value this carried — every Top Chase sparkline
      // drew straight over the pinned block as its row scrolled underneath,
      // which is what read as the title card being see-through. The tooltip
      // below is scoped to this element's stacking context, so it rides on this
      // value too: 30 still clears sibling rows and card chrome (all z-auto)
      // while staying beneath the pinned block.
      className={["group relative z-30 touch-pan-y overflow-visible rounded-lg", className].filter(Boolean).join(" ")}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={() => { gestureRef.current = null; }}
      onPointerLeave={handlePointerLeave}
      onFocus={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setActiveIndex(numericPoints.length - 1);
        setTooltipX(
          clampTooltipX({
            chartLeft: bounds.left,
            chartWidth: bounds.width,
            pointerX: bounds.width / 2,
            tooltipWidth: 224,
            viewportWidth: typeof window === "undefined" ? bounds.width : window.innerWidth,
            gutter: 8,
          })
        );
      }}
      onBlur={clearSelection}
      onKeyDown={(event) => {
        if (numericPoints.length === 0) return;
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault();
          const step = event.key === "ArrowRight" ? 1 : -1;
          const base = activeIndex === null ? numericPoints.length - 1 : activeIndex;
          setActiveIndex(Math.max(0, Math.min(numericPoints.length - 1, base + step)));
        } else if (event.key === "Escape") {
          clearSelection();
        }
      }}
      tabIndex={0}
    >
      {/* Below 1200px the sparkline is integrated into the row instead of
          sitting in its own mini-card: the border and fill are dropped so the
          plot reads as part of the row and uses the full row width. Desktop
          keeps the framed treatment. */}
      <svg
        aria-hidden="true"
        viewBox="0 0 100 42"
        preserveAspectRatio="none"
        className="h-full w-full overflow-visible rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity="0.12" />
            <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
          </linearGradient>
          <filter id={glowId} x="-10%" y="-25%" width="120%" height="150%">
            <feGaussianBlur stdDeviation="1.4" />
          </filter>
        </defs>
        {[8, 22, 36].map((y) => (
          <path key={y} d={`M2 ${y}H98`} stroke="rgba(255,255,255,0.045)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={areaPath} fill={`url(#${gradientId})`} />
        <polyline points={polylinePoints} fill="none" stroke={strokeColor} strokeWidth="6" strokeOpacity="0.1" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" filter={`url(#${glowId})`} />
        <polyline points={polylinePoints} fill="none" stroke={strokeColor} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {activePoint && activeX !== null && activeY !== null ? (
          <line x1={activeX} x2={activeX} y1="6" y2="38" stroke="rgba(255,255,255,0.12)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ) : null}
      </svg>
      {activePoint && activeX !== null && activeY !== null ? (
        <span
          data-compact-sparkline-marker
          aria-hidden="true"
          className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-current bg-[rgba(2,6,23,0.78)] shadow-[0_0_8px_currentColor]"
          style={{ left: `${activeX}%`, top: `${(activeY / 42) * 100}%`, color: strokeColor }}
        >
          <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
        </span>
      ) : null}
      {showTooltip && activePoint && tooltipX !== null ? (
        <MarketTrendTooltipCard
          data-compact-sparkline-tooltip
          date={activePoint.date}
          value={activePoint.y}
          deltaAmount={activeDeltaAmount}
          deltaPercent={activeDeltaPercent}
          isCarriedForward={activePoint.isCarriedForward}
          sourceDate={activePoint.sourceDate}
          className="pointer-events-none absolute bottom-[calc(100%+0.55rem)] z-[9999] max-w-[min(14rem,calc(100vw-1.5rem))] -translate-x-1/2"
          style={{ left: tooltipX }}
        />
      ) : null}
    </div>
  );
}

function normalizeSetValueHistoryPoints(points, { marketAsOfDate = null } = {}) {
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

  return forwardFillDailyHistoryThroughDate(
    Array.from(dailyPointMap.values()).sort((a, b) => a.date.localeCompare(b.date)),
    {
      dateField: "date",
      valueKeys: ["setValue"],
      // Canonical end date from the snapshot generation; when absent the fill
      // stops at the latest real observation — never the runtime's today.
      endDateKey: marketAsOfDate,
    }
  );
}

function getSetValueHistoryForScope({ history, historiesByScope, scope = CANONICAL_SET_VALUE_SCOPE }) {
  if (Array.isArray(historiesByScope?.[scope])) {
    return historiesByScope[scope];
  }
  return scope === CANONICAL_SET_VALUE_SCOPE ? history : [];
}

function getSetValueHistoryMetrics(rawHistory, { preferredWindowKey = "30D", marketAsOfDate = null } = {}) {
  const points = normalizeSetValueHistoryPoints(rawHistory, { marketAsOfDate });
  const valuedPoints = points.filter((point) => toNumber(point?.setValue) !== null);
  const { effectiveKey, selectedWindow } = getSelectedDeltaWindowFromHistory(valuedPoints, {
    selectedKey: preferredWindowKey,
    preferredKey: preferredWindowKey,
    dateKey: "date",
    valueKey: "setValue",
  });
  const visibleWindowMetrics = getVisibleHistoryWindowMetrics(points, selectedWindow, {
    dateKey: "date",
    valueKey: "setValue",
  });
  const currentValue = visibleWindowMetrics.currentValue;
  const baselineValue = toNumber(visibleWindowMetrics.firstPoint?.setValue);

  return {
    points,
    visiblePoints: visibleWindowMetrics.points,
    valuedPoints,
    selectedWindow,
    effectiveWindowKey: effectiveKey,
    currentValue,
    deltaAmount: visibleWindowMetrics.deltaAmount,
    deltaPercent: visibleWindowMetrics.deltaPercent,
    asOf: visibleWindowMetrics.latestPoint?.date || valuedPoints[valuedPoints.length - 1]?.date || null,
    sourcePoint: visibleWindowMetrics.latestPoint || valuedPoints[valuedPoints.length - 1] || null,
    trend:
      currentValue !== null && baselineValue !== null && visibleWindowMetrics.firstPoint !== visibleWindowMetrics.latestPoint
        ? getMetricTrend({ currentValue, previousValue: baselineValue, metricKey: "setValue" })
        : { trend: "unknown", isImprovement: null },
  };
}

function getCanonicalChecklistSetValueMetrics({
  history,
  historiesByScope,
  meta,
  fallbackMetric,
  fallbackAsOf,
  sourcePrefix = "market_dashboard",
  marketAsOfDate = null,
}) {
  const marketMetrics = getSetValueHistoryMetrics(
    getSetValueHistoryForScope({ history, historiesByScope, scope: CANONICAL_SET_VALUE_SCOPE }),
    { preferredWindowKey: "30D", marketAsOfDate }
  );

  if (marketMetrics.currentValue !== null) {
    return {
      ...marketMetrics,
      value: marketMetrics.currentValue,
      valueScope: CANONICAL_SET_VALUE_SCOPE,
      source: `${sourcePrefix}.setValueHistoriesByScope.${CANONICAL_SET_VALUE_SCOPE}`,
      sourcePayloadKey: `setValueHistoriesByScope.${CANONICAL_SET_VALUE_SCOPE}`,
      asOf:
        marketMetrics.asOf ||
        meta?.asOfDate ||
        meta?.as_of_date ||
        meta?.windowEnd ||
        meta?.window_end ||
        null,
      isFallback: false,
    };
  }

  return {
    ...marketMetrics,
    value: fallbackMetric?.value ?? null,
    valueScope: CANONICAL_SET_VALUE_SCOPE,
    source: fallbackMetric?.key ? `set_page_snapshot.summary.${fallbackMetric.key}` : "set_page_snapshot.summary",
    sourcePayloadKey: fallbackMetric?.key || null,
    asOf: fallbackAsOf || null,
    isFallback: true,
    trend: { trend: "unknown", isImprovement: null },
  };
}

function SetValueLineChart({ points, trendDirection = "neutral", scopeLabel = "Set" }) {
  const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;
  // No width branch left to make: the axis treatment is now identical at every
  // size, so this chart no longer reads the desktop composition at all. Pointer
  // mode still decides tap-vs-hover, which is a capability, not a width.
  const chartId = useId().replace(/:/g, "");
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
      <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-4 py-3 text-sm text-[var(--text-secondary)]">
        Not enough set value history yet. The trend chart appears after a few days of market observations.
      </p>
    );
  }

  const values = valuedPoints.map((point) => point.setValue);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || Math.max(maxValue, 1) * 0.08 || 1;
  const yAxisTicks = buildCurrencyTicks(valuedPoints);
  const yMin = Math.max(0, Math.min(...yAxisTicks, minValue - range * 0.14));
  const yMax = Math.max(...yAxisTicks, maxValue + range * 0.14);
  // One date system at every width: the first and last date of the visible
  // series, printed on the axis directly under the line they describe. The
  // every-day / preserveStartEnd desktop tick set and the external bookend-date
  // row it used to pair with are both gone — see minimalChartAxis.mjs.
  const edgeDateTicks = buildEdgeDateTicks(numericPoints, "date");
  const trendColor =
    trendDirection === "negative"
      ? NEGATIVE_VALUE_COLOR
      : trendDirection === "positive"
      ? POSITIVE_VALUE_COLOR
      : "rgba(148,163,184,0.9)";
  const fillGradientId = `set-value-fill-${chartId}`;
  const glowFilterId = `set-value-glow-${chartId}`;

  return (
    <div className="min-h-[clamp(220px,31dvh,280px)] w-full desk:min-h-[21rem]">
      <ChartFrame className="h-[clamp(220px,31dvh,280px)] w-full desk:h-[21rem]">
        <ResponsiveContainer width="100%" height="100%">
          {/* Shared insets: with the y-axis reserving no width at any size, a
              zero left margin would put the first data point exactly on x=0,
              where the SVG clips half its stroke and all of its 7px glow. */}
          {/* The completed mobile values become the shared ones, so the phone
              and tablet plot is byte-identical to before and desktop simply
              adopts it (it had top 12 / bottom 8 to sit under its old axis). */}
          <ComposedChart data={numericPoints} margin={getMinimalPlotMargin({ top: 6, bottom: 2 })}>
            <defs>
              <linearGradient id={fillGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={trendColor} stopOpacity="0.13" />
                <stop offset="68%" stopColor={trendColor} stopOpacity="0.035" />
                <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
              </linearGradient>
              <filter id={glowFilterId} x="-12%" y="-18%" width="124%" height="136%">
                <feGaussianBlur stdDeviation="1.8" />
              </filter>
            </defs>
            <Area
              type="linear"
              dataKey="setValue"
              baseValue={yMin}
              fill={`url(#${fillGradientId})`}
              stroke="none"
              dot={false}
              activeDot={false}
              legendType="none"
              tooltipType="none"
              isAnimationActive={false}
            />
            <CartesianGrid stroke="var(--border-subtle)" strokeOpacity={0.28} strokeDasharray="2 8" vertical={false} />
            {/* The two edge dates are the only dates, at every width, and they
                are anchored inward so the SVG cannot clip them. */}
            <XAxis
              dataKey="date"
              ticks={edgeDateTicks}
              tickLine={false}
              axisLine={false}
              tick={<ChartEdgeDateTick ticks={edgeDateTicks} formatter={(value) => formatShortDate(value) || ""} />}
              tickFormatter={(value) => formatShortDate(value) || ""}
              minTickGap={0}
              interval={0}
            />
            {/* Scale unchanged — the domain is still computed from the data and
                still drives the gridlines. Only the printed labels and the
                58px gutter they reserved are gone, so the series uses the full
                card width. Exact values stay available by hover and tap/scrub. */}
            <YAxis
              {...MINIMAL_Y_AXIS_PROPS}
              domain={[yMin, yMax]}
              tickCount={4}
              tickFormatter={formatAxisCurrency}
            />
            {/* Touch gets an explicit tap trigger: it persists after the finger
                lifts, and it binds click rather than touchmove, so scrolling
                past the chart can never select a random point. Mouse and
                trackpad keep hover at every width. */}
            <RechartsTooltip
              trigger={isCoarsePointer ? "click" : "hover"}
              content={<SetValueTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}
            />
            <Line
              type="linear"
              dataKey="setValue"
              stroke={trendColor}
              strokeWidth={7}
              strokeOpacity={0.16}
              filter={`url(#${glowFilterId})`}
              dot={false}
              activeDot={false}
              legendType="none"
              tooltipType="none"
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="setValue"
              name={`${scopeLabel} Set Value`}
              stroke={trendColor}
              strokeWidth={2.5}
              dot={{ r: 2.5, fill: trendColor, strokeWidth: 0 }}
              activeDot={{ r: 4.5, stroke: "var(--surface-page)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function SetValueTrendCard({
  setId,
  setValueContract,
  history,
  historiesByScope,
  availableScopes,
  status,
  error,
  selectedScope = CANONICAL_SET_VALUE_SCOPE,
  onSelectedScopeChange,
  marketAsOfDate = null,
}) {
  const [selectedWindowKey, setSelectedWindowKey] = useState(null);
  const scopeOptions = useMemo(() => {
    const optionMap = new Map(VISIBLE_SET_VALUE_SCOPE_OPTIONS.map((entry) => [entry.key, entry]));
    (Array.isArray(availableScopes) ? availableScopes : []).forEach((entry) => {
      if (entry?.key && entry.key !== "hits") {
        const defaultOption = VISIBLE_SET_VALUE_SCOPE_OPTIONS.find((option) => option.key === entry.key);
        optionMap.set(entry.key, {
          key: entry.key,
          label: defaultOption?.label || entry.label || entry.key,
        });
      }
    });
    return VISIBLE_SET_VALUE_SCOPE_OPTIONS.filter((entry) => optionMap.has(entry.key)).map((entry) => optionMap.get(entry.key));
  }, [availableScopes]);
  const resolvedSelectedScope = scopeOptions.some((entry) => entry.key === selectedScope)
    ? selectedScope
    : CANONICAL_SET_VALUE_SCOPE;
  const handleSelectedScopeChange = useCallback(
    (nextScope) => {
      onSelectedScopeChange?.(nextScope);
    },
    [onSelectedScopeChange]
  );
  const selectedTrend = useMemo(
    () =>
      setValueContract
        ? selectSetValueTrendFromContract({
            contract: setValueContract,
            selectedScope: resolvedSelectedScope,
            selectedWindowKey,
          })
        : selectOverviewSetValueTrendByScope({
            history,
            historiesByScope,
            selectedScope: resolvedSelectedScope,
            allowedScopes: scopeOptions.map((entry) => entry.key),
            selectedWindowKey,
            preferredWindowKey: "30D",
            marketAsOfDate,
          }),
    [historiesByScope, history, marketAsOfDate, resolvedSelectedScope, scopeOptions, selectedWindowKey, setValueContract]
  );
  const selectedScopeLabel = selectedTrend.label;
  const selectedMetricLabel = selectedTrend.metricLabel;
  const points = selectedTrend.points;
  const chartPoints = selectedTrend.series;
  const firstPoint = selectedTrend.firstPoint;
  const lastPoint = selectedTrend.lastPoint;
  const currentValue = selectedTrend.currentValue;
  const deltaAmount = selectedTrend.deltaAmount;
  const deltaPercent = selectedTrend.deltaPercent;
  const availableDeltaWindows = selectedTrend.availableDeltaWindows;
  const effectiveWindowKey = selectedTrend.effectiveWindowKey;
  const deltaWindowLabel = effectiveWindowKey ? getDeltaWindowLabel(effectiveWindowKey) : "Trend";
  const hasTrend = selectedTrend.hasTrend;
  const trendDirection = deltaAmount === null ? "neutral" : deltaAmount < 0 ? "negative" : deltaAmount > 0 ? "positive" : "neutral";
  const seriesStartDate = firstPoint?.date || "start";
  const seriesEndDate = lastPoint?.date || "latest";
  const chartKey = `${setId || "set"}-${selectedTrend.scope}-${effectiveWindowKey || "window"}-${seriesStartDate}-${seriesEndDate}-${chartPoints.length}`;

  useEffect(() => {
    setSelectedWindowKey(null);
  }, [setId, selectedScope]);

  useEffect(() => {
    if (!effectiveWindowKey || selectedWindowKey === effectiveWindowKey) {
      return;
    }
    setSelectedWindowKey(effectiveWindowKey);
  }, [effectiveWindowKey, selectedWindowKey, setSelectedWindowKey]);

  useEffect(() => {
    if (scopeOptions.some((entry) => entry.key === selectedScope) && selectedScope !== "hits") {
      return;
    }
    handleSelectedScopeChange(scopeOptions[0]?.key || CANONICAL_SET_VALUE_SCOPE);
  }, [handleSelectedScopeChange, scopeOptions, selectedScope]);

  return (
    <SectionCard
      title="Set Value Trend"
      titleInfoText="Tracks the selected set-value scope using daily Near Mint card market observations. Set sums tracked checklist cards, and Top 10 sums the highest-value tracked cards for each date."
      className="h-full"
      bodySpacingClassName="mt-2"
    >
      {(status === "loading" || status === "idle") && points.length === 0 && currentValue === null ? (
        <InlinePanelSkeleton rows={4} />
      ) : status === "error" && currentValue === null ? (
        <p className="text-sm text-red-300">{error || "Unable to load set value history for this set."}</p>
      ) : !hasTrend ? (
        <div className="space-y-3">
          <div>
            <MarketValueChange
              value={currentValue}
              windowLabel={deltaWindowLabel}
              unavailable
              variant="chart-summary"
              accessibleLabel={`Current ${selectedMetricLabel}`}
            />
            {selectedTrend.shareOfStandardPercent !== null ? (
              <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                Share of Set Value: {selectedTrend.shareOfStandardPercent.toFixed(1)}%
              </p>
            ) : null}
          </div>
          <p className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/42 px-3 py-3 text-sm text-[var(--text-secondary)]">
            {currentValue !== null
              ? "Current value is available; historical trend is still loading/unavailable."
              : "Not enough set value history yet."}
          </p>
          <div className="pt-1">
            <SetValueScopeSelector scopes={scopeOptions} value={selectedTrend.scope} onChange={handleSelectedScopeChange} />
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-col space-y-4 desk:min-h-[29rem]">
          <div className="min-w-0">
            <div className="min-w-0">
              <MarketValueChange
                value={currentValue}
                changeAmount={deltaAmount}
                changePercent={deltaPercent}
                windowLabel={deltaWindowLabel}
                variant="chart-summary"
                accessibleLabel={`Current ${selectedMetricLabel}`}
              />
              {selectedTrend.shareOfStandardPercent !== null ? (
                <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                  Share of Set Value: {selectedTrend.shareOfStandardPercent.toFixed(1)}%
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex min-w-0 items-center gap-2">
            <MarketWindowSelector
              windows={availableDeltaWindows}
              value={effectiveWindowKey}
              onChange={setSelectedWindowKey}
            />
          </div>

          <SetValueLineChart key={chartKey} points={chartPoints} trendDirection={trendDirection} scopeLabel={selectedScopeLabel} />

          {/* One date system, at every width. The chart's own axis prints the
              first and last date directly under the series they describe, so
              the bookend dates that used to sit either side of this selector
              stated the same two values a second time. This row is now the
              scope selector alone. */}
          <div className="grid min-w-0 grid-cols-1 items-center gap-x-3 gap-y-2 pb-1 text-xs text-[var(--text-secondary)]">
            <div className="min-w-0 justify-self-start">
              <SetValueScopeSelector scopes={scopeOptions} value={selectedTrend.scope} onChange={handleSelectedScopeChange} />
            </div>
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
    <article className="set-glass-surface w-full max-w-full min-w-0 rounded-2xl border p-4 sm:p-5">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Overview Context</h2>
          <InfoPopover text="Asset-style set context using existing set value, pack price, modeled Expected Value, and return ratio." />
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

function TopMarketCardRow({ card, index, selectedWindowKey, marketAsOfDate = null, href = null }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl || null;
  const name = card?.name || "Unknown card";
  const rarity = card?.rarity || null;
  const price = getChecklistCardMarketPrice(card);
  const historyPoints = getTopCardPriceHistory(card, selectedWindowKey, marketAsOfDate);
  const windowState = resolveTopCardWindowState({ card, historyPoints, selectedWindowKey });
  warnForTopCardWindowState(windowState, card, selectedWindowKey);
  const sparklinePoints = windowState.chartWindow
    ? filterHistoryPointsForDeltaWindow(historyPoints, windowState.chartWindow, { dateKey: "date" })
    : [];
  const displayDeltaAmount = windowState.displayMovement?.amount ?? null;
  const displayDelta = windowState.displayMovement?.percent ?? null;
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
  // How the movement was sourced is a diagnostic, not product copy — it stays
  // in windowState.warnings, warnForTopCardWindowState's dev console output and
  // the data-trend-source attribute below. The user is told only whether a
  // trend exists. See getTopCardTrendStatusMessage.
  const trendStatusMessage = getTopCardTrendStatusMessage(windowState);

  // Correction 3: the information region is the link; the sparkline is its
  // sibling. Nesting a focusable, arrow-key-driven chart inside an <a> is
  // invalid interactive content, and stopPropagation would only paper over it.
  //
  // Compact ranked market row below 1200px: rank, small image, name + rarity,
  // and price + movement all share one line inside the link, with the sparkline
  // spanning beneath it.
  //
  // At 1200px+ the row is the historical four-column table again — rank | card |
  // trend | price — sharing ONE column template with the header above it. The
  // mobile composition put the price inside the link, which made a true
  // four-column desktop row impossible: the price and the sparkline would have
  // had to interleave across an element boundary, and the only ways to do that
  // (display:contents on the anchor) destroy the row's hover surface and focus
  // ring. The price cell is therefore rendered per composition — mobile's
  // inside the link, desktop's outside it — the same pattern the card image in
  // this row already uses. Only the wrapper is duplicated; the values, the
  // window state and the accessible label are computed once above.
  const NavigationRegion = href ? "a" : "div";
  const priceCell = (
    <MarketValueChange
      value={price}
      changeAmount={displayDeltaAmount}
      changePercent={displayDelta}
      windowLabel={getDeltaWindowLabel(selectedWindowKey)}
      showWindowLabel={false}
      accessiblePeriodLabel={
        windowState.displayMovement?.isSinceFirstAvailable
          ? getMovementAccessiblePeriod({
              isPartialWindow: true,
              windowCoverageDays: getDateSpanDays(
                windowState.displayMovement.startDate,
                windowState.displayMovement.endDate
              ),
            })
          : null
      }
      alignment="right"
      variant="table-row"
      accessibleLabel={`${name} market price`}
    />
  );

  return (
    // data-trend-source is machine-readable only: it keeps the stored-canonical
    // vs history-fallback distinction available to tests, telemetry and the
    // publication audit without rendering it as copy.
    <div
      data-top-chase-row
      data-trend-source={windowState.source}
      className="grid min-w-0 grid-cols-1 gap-y-1.5 px-3 py-2.5 max-desk:px-0 desk:grid-cols-[3rem_minmax(0,1fr)_minmax(9rem,14.5rem)_minmax(8rem,10rem)] desk:items-center desk:gap-3 desk:px-3 desk:py-3"
    >
      <NavigationRegion
        {...(href ? { href, "aria-label": `${name} — open in Cards` } : {})}
        data-row-nav
        className="grid min-h-11 min-w-0 grid-cols-[1.5rem_2.5rem_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-lg transition-colors hover:bg-[var(--surface-hover)]/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:col-span-2 desk:col-start-1 desk:row-start-1 desk:grid-cols-[3rem_minmax(0,1fr)] desk:gap-3"
      >
        <span className="self-center text-xs font-semibold tabular-nums text-[var(--text-secondary)]">#{index + 1}</span>

        <div className="flex h-[3.4rem] w-[2.5rem] flex-none items-center justify-center overflow-hidden rounded-md border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.48)] desk:hidden">
          {imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={imageUrl} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
          ) : (
            <span className="px-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
              {getCardInitials(name)}
            </span>
          )}
        </div>

        <div className="flex min-w-0 items-center gap-3">
          <div className="hidden h-[4.875rem] w-14 flex-none items-center justify-center overflow-hidden rounded-md border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.48)] shadow-[0_10px_24px_rgba(2,6,23,0.24)] desk:flex">
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

        {/* Mobile/tablet price: on the row's single line, inside the link. */}
        <div data-row-price="compact" className="min-w-0 justify-self-end desk:hidden">
          {priceCell}
        </div>
      </NavigationRegion>

      {/* Trend — the table's third column on desktop, and the full-width strip
          under the link below it. Start and end dates sit at the lower left and
          lower right of the plot, outside the graph box, so this stays graph
          height rather than row height. */}
      <div data-row-chart className="flex min-w-0 flex-col items-stretch desk:col-start-3 desk:row-start-1 desk:items-center">
        {/* ~48px of plot below desktop (was 32px, which flattened real
            movement into a decorative line); the restored 56px on desktop. */}
        <CompactSparkline
          points={sparklinePoints}
          trendDirection={sparklineTone}
          className="h-12 w-full desk:h-14 desk:max-w-[13.75rem]"
        />
        {sparklinePoints.length >= 2 ? (
          <div className="mt-1 flex w-full min-w-0 items-center justify-between gap-2 text-[9px] text-[var(--text-secondary)] desk:max-w-[13.75rem] desk:text-[10px]">
            <span className="truncate">{formatShortDate(sparklinePoints[0]?.date)}</span>
            <span className="truncate text-right">{formatShortDate(sparklinePoints[sparklinePoints.length - 1]?.date)}</span>
          </div>
        ) : null}
        {trendStatusMessage ? (
          <p className="mt-1 truncate text-[10px] text-[var(--text-secondary)] opacity-80 desk:max-w-[13.75rem]" title={trendStatusMessage}>
            {trendStatusMessage}
          </p>
        ) : null}
      </div>

      {/* Desktop price / change: the table's fourth and final column, outside
          the link so the sparkline can occupy column three between it and the
          card. Rendered after the chart so the reading order matches the
          visual order. */}
      <div
        data-row-price="table"
        className="hidden min-w-0 desk:col-start-4 desk:row-start-1 desk:block desk:justify-self-end"
      >
        {priceCell}
      </div>
    </div>
  );
}

function InlinePanelSkeleton({ rows = 3, className = "" }) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={`inline-skeleton:${index}`}
          className="h-12 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50"
        />
      ))}
    </div>
  );
}

function TopMarketCardsContent({
  cards,
  status,
  error,
  maxRows = 10,
  selectedWindowKey: controlledSelectedWindowKey = null,
  onWindowChange = null,
  marketAsOfDate = null,
  rowHref = null,
  onRetry = null,
  mobileExpanded = true,
}) {
  const [localSelectedWindowKey, setLocalSelectedWindowKey] = useState(null);
  const selectedWindowKey = controlledSelectedWindowKey ?? localSelectedWindowKey;
  const setSelectedWindowKey = onWindowChange || setLocalSelectedWindowKey;
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
  }, [effectiveWindowKey, selectedWindowKey, setSelectedWindowKey]);

  const hasCards = Array.isArray(cards) && cards.length > 0;

  if ((status === "loading" || status === "idle") && !hasCards) {
    // The placeholder matches the final compact row box, so data arriving does
    // not shift the page.
    return (
      <div data-top-chase-skeleton className="animate-pulse space-y-2" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, skeletonIndex) => (
          <div
            key={`top-chase-skeleton:${skeletonIndex}`}
            className="max-desk:h-[4.25rem] h-12 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/50"
          />
        ))}
      </div>
    );
  }

  if (status === "error") {
    // Section-local failure + Retry: retries only the top-chase request and
    // never replaces the rest of Overview with a page-level loader.
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-sm text-red-300">{error || "Unable to load market cards for this set."}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.04)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[rgba(255,255,255,0.08)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] max-desk:min-h-11"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  if (!hasCards) {
    return <p className="text-sm text-[var(--text-secondary)]">No priced cards are available yet for this set.</p>;
  }

  return (
    <div className="space-y-3">
      <MarketWindowSelector
        windows={availableDeltaWindows}
        value={effectiveWindowKey}
        onChange={setSelectedWindowKey}
      />
      {/* Below 1200px the outer list box is dropped: the rows already carry
          their own dividers, so wrapping them in another bordered card only
          spent horizontal width the sparkline needs. Desktop keeps the box. */}
      <div className="set-glass-inner overflow-visible rounded-xl border border-[var(--border-subtle)] max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent">
        {/* Column labels follow the desktop row grid, so they move to `desk:`
            with it — in the 1024-1199px tablet band the rows are compact and
            these labels would sit over the wrong columns. */}
        <div className="hidden grid-cols-[3rem_minmax(0,1fr)_minmax(9rem,14.5rem)_minmax(8rem,10rem)] items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] desk:grid">
          <span>Rank</span>
          <span>Card</span>
          <span className="text-center">Trend</span>
          <span className="text-right">Price / Change</span>
        </div>
        <div className="divide-y divide-[var(--border-subtle)]">
          {cards.slice(0, maxRows).map((card, index) => (
            <div
              key={`top-market-card:${card?.id || card?.cardNumber || card?.name || index}`}
              className={index >= TOP_CHASE_MOBILE_PREVIEW_LIMIT && !mobileExpanded ? "max-desk:hidden" : ""}
            >
              <TopMarketCardRow
                card={card}
                index={index}
                selectedWindowKey={effectiveWindowKey}
                marketAsOfDate={marketAsOfDate}
                href={rowHref}
              />
            </div>
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

function getDateSpanDays(startDate, endDate) {
  const start = Date.parse(`${String(startDate || "").slice(0, 10)}T00:00:00Z`);
  const end = Date.parse(`${String(endDate || "").slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return null;
  }
  return Math.round((end - start) / 86400000);
}

function getTopCardsAvailableDeltaWindows(cards) {
  return Array.isArray(cards) && cards.length > 0 ? getStandardDeltaWindowDefinitions() : [];
}

function getTopCardPriceHistory(card, selectedWindowKey, marketAsOfDate = null) {
  const history = Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : [];
  const points = history
    .map((point) => ({
      date: getHistoryDateKey(point?.date),
      value: toNumber(point?.marketPrice ?? point?.market_price ?? point?.price),
      isObserved: Boolean(point?.isObserved ?? point?.is_observed),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      sourceDate: getHistoryDateKey(point?.sourceDate ?? point?.source_date),
    }))
    .filter((point) => point.date);

  const preferredEndDate = getTopCardPreferredHistoryEndDate(card, selectedWindowKey, points);
  const canonicalEndDate = getHistoryDateKey(marketAsOfDate);
  // The canonical marketAsOfDate caps every Top Chase series; the per-card
  // preferred end (stored window end / snapshot market date) may pull it in
  // further but can never extend past the shared cutoff. No point may ever be
  // synthesized for a date after marketAsOfDate.
  const effectiveEndDate =
    preferredEndDate && canonicalEndDate
      ? (preferredEndDate < canonicalEndDate ? preferredEndDate : canonicalEndDate)
      : preferredEndDate || canonicalEndDate;
  const boundedPoints = effectiveEndDate
    ? points.filter((point) => point.date <= effectiveEndDate)
    : points;

  return forwardFillDailyHistoryThroughDate(boundedPoints, {
    dateField: "date",
    valueKeys: ["value"],
    endDateKey: effectiveEndDate,
  });
}

function TopChaseCardsModule({ cards, status, error, infoText, selectedWindowKey, onWindowChange, marketAsOfDate = null, rowHref = null, onRetry = null }) {
  // Default to a 5-row preview so the compact mobile feed stays scannable;
  // "View all chase cards" expands in place to the full fetched list (10 —
  // see the /market/top-chase fetch's limit), reusing the View-all-movers
  // button treatment. There is no dedicated chase-cards destination to link
  // out to, so expand-in-place is the closest existing pattern — and it is
  // what keeps rows 6-10 reachable rather than discarded (parity spec §6).
  const [showAllChaseCards, setShowAllChaseCards] = useState(false);
  const totalRows = Array.isArray(cards) ? cards.length : 0;
  const chaseCardsResetKey = useMemo(
    () => (Array.isArray(cards) ? cards.map((card) => String(card?.id || card?.cardId || card?.cardNumber || card?.name || "")).join("|") : ""),
    [cards]
  );
  const hiddenRowCount = Math.max(0, Math.min(totalRows, 10) - TOP_CHASE_MOBILE_PREVIEW_LIMIT);

  useEffect(() => {
    setShowAllChaseCards(false);
  }, [setShowAllChaseCards, chaseCardsResetKey]);

  return (
    <SectionCard title="Top Chase Cards" titleInfoText={infoText}>
      <TopMarketCardsContent
        cards={cards}
        status={status}
        error={error}
        maxRows={10}
        mobileExpanded={showAllChaseCards}
        selectedWindowKey={selectedWindowKey}
        onWindowChange={onWindowChange}
        marketAsOfDate={marketAsOfDate}
        rowHref={rowHref}
        onRetry={onRetry}
      />
      {totalRows > TOP_CHASE_MOBILE_PREVIEW_LIMIT ? (
        <div className="mt-1 hidden justify-center max-desk:flex">
          {/* Compact visible label below 1200px; the accessible name stays the
              full, descriptive wording at every width.
              The list expands in place, downward — so the affordance is a down
              chevron that flips to point back up when the extra rows are
              showing. The previous label used a right-pointing arrow, which
              promises navigation to another destination; there is no such
              destination, and rows 6-10 appear directly beneath this control. */}
          <button
            type="button"
            onClick={() => setShowAllChaseCards((value) => !value)}
            aria-expanded={showAllChaseCards}
            aria-label={showAllChaseCards ? "Show fewer chase cards" : `Show ${hiddenRowCount} more chase cards`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border-0 bg-transparent px-2 py-2 text-xs font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            <span aria-hidden="true">
              {showAllChaseCards ? "Show less" : `Show ${hiddenRowCount} more`}
            </span>
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
              data-chase-reveal-chevron
              className={`h-4 w-4 flex-none transition-transform ${showAllChaseCards ? "rotate-180" : ""}`}
            >
              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
            </svg>
          </button>
        </div>
      ) : null}
    </SectionCard>
  );
}

function hasMarketMoverRows(entry) {
  return (
    (Array.isArray(entry?.all) && entry.all.length > 0) ||
    (Array.isArray(entry?.movements) && entry.movements.length > 0) ||
    (Array.isArray(entry?.heatingUp) && entry.heatingUp.length > 0) ||
    (Array.isArray(entry?.heating_up) && entry.heating_up.length > 0) ||
    (Array.isArray(entry?.coolingOff) && entry.coolingOff.length > 0) ||
    (Array.isArray(entry?.cooling_off) && entry.cooling_off.length > 0)
  );
}

// ---------------------------------------------------------------------------
// 7D Movers ticker — Overview's slim replacement for the Market Movers card.
// Eligible movements ranked by |7D %| descending, capped at ten. Fixed 7D
// window regardless of any other time-range
// state on the page. This static strip IS the prefers-reduced-motion
// presentation; the auto-scroll loop layers on top separately and must
// degrade back to exactly this markup.
// ---------------------------------------------------------------------------

function MoversTickerItemChip({ card, movement, href, tabIndex }) {
  const imageUrl = card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl || null;
  const name = card?.name || "Unknown card";
  const price = getCardMarketPrice(card) ?? toNumber(card?.currentPrice);

  return (
    <a
      href={href}
      tabIndex={tabIndex}
      title={`${name} — view all market movers`}
      className="flex min-w-0 flex-none items-center gap-2 rounded-lg px-2 py-1 transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
      <span className="flex h-10 w-7 flex-none items-center justify-center overflow-hidden rounded border border-[rgba(255,255,255,0.08)] bg-[rgba(2,6,23,0.45)]">
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl} alt="" className="h-full w-full object-contain" loading="lazy" decoding="async" />
        ) : (
          <span className="text-[8px] font-semibold text-[var(--text-secondary)]">{getCardInitials(name)}</span>
        )}
      </span>
      <span className="min-w-0 max-w-[11rem]">
        <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">{name}</span>
        <MarketValueChange
          value={price}
          changeAmount={movement?.amount}
          changePercent={movement?.percent}
          windowLabel="7D"
          showWindowLabel={false}
          variant="ticker"
          accessibleLabel={`${name} market price`}
        />
      </span>
    </a>
  );
}

function MarketMoversTicker({ items, status, error, viewAllHref, onRetry = null }) {
  const hasItems = Array.isArray(items) && items.length > 0;
  // Overflow/reduced-motion choose the marquee structure. Focus and hover
  // only pause that existing structure, so neither can remount a clicked link.
  const renderSequence = (ariaHidden, sequenceRef) => (
    <div
      ref={sequenceRef}
      aria-hidden={ariaHidden ? "true" : undefined}
      className={`flex items-center gap-1 pr-1 ${ariaHidden ? "index-ticker-duplicate" : ""}`.trim()}
    >
      {items.map(({ card, movement }, index) => (
        <MoversTickerItemChip
          key={`movers-ticker${ariaHidden ? ":dup" : ""}:${card?.cardId || card?.id || card?.name || index}`}
          card={card}
          movement={movement}
          href={viewAllHref}
          tabIndex={ariaHidden ? -1 : undefined}
        />
      ))}
    </div>
  );

  return (
    // Fixed strip height from first paint (h-14): loading, error, empty, and
    // populated states all render inside the same box, so the ticker never
    // shifts the Overview content below it.
    // Below 1200px this is a plain full-width utility row: no outer card, no
    // border, no rounding — just the label, the ticker and a compact
    // destination arrow, separated from the feed by the divider the feed
    // already draws between sections. Desktop keeps its boxed strip.
    <div className="flex h-14 min-w-0 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[color:color-mix(in_srgb,var(--surface-page)_78%,transparent)] py-1 pl-3 pr-2 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:px-0">
      <span className="flex-none rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:px-0">
        7D Movers
      </span>
      <MoversTickerViewport
        hasItems={hasItems}
        items={items}
        renderSequence={renderSequence}
        fallback={status === "loading" ? (
          <div className="h-6 w-full max-w-[28rem] animate-pulse rounded-md bg-[rgba(148,163,184,0.10)]" aria-hidden="true" />
        ) : status === "error" ? (
          // Compact, section-local failure state inside the same fixed-height
          // strip: a stalled or failed movers fetch is now a retryable message
          // rather than an endless pulse, and Retry re-requests only movers.
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-xs text-red-300">{error || "Unable to load 7D movers for this set."}</span>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="flex-none rounded-md border border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.04)] px-2 py-1 text-[11px] font-semibold text-[var(--text-primary)] transition-colors hover:bg-[rgba(255,255,255,0.08)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              >
                Retry
              </button>
            ) : null}
          </span>
        ) : (
          <p className="truncate text-xs text-[var(--text-secondary)]">No reliable 7D movers yet.</p>
        )}
      />
      {/* One destination, two presentations. Below 1200px the verbose button
          collapses to an icon-sized arrow that keeps a 44px touch target; the
          accessible name stays "View all movers" at every width. */}
      <a
        href={viewAllHref}
        aria-label="View all movers"
        className="flex-none whitespace-nowrap rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50 px-2.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] max-desk:inline-flex max-desk:h-11 max-desk:w-8 max-desk:items-center max-desk:justify-center max-desk:rounded-md max-desk:border-0 max-desk:bg-transparent max-desk:px-0 max-desk:py-0"
      >
        <span aria-hidden="true" className="max-desk:hidden">View all movers →</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" className="hidden h-4 w-4 max-desk:block" fill="currentColor">
          <path d="M7.21 5.23a.75.75 0 0 1 1.06-.02l4.45 4.25a.75.75 0 0 1 0 1.08l-4.45 4.25a.75.75 0 1 1-1.04-1.08L11.12 10 7.23 6.29a.75.75 0 0 1-.02-1.06Z" />
        </svg>
      </a>
    </div>
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

// `mobileEmphasisValue` is OPT-IN and SCOPED, and it is used by exactly one
// caller: the set-detail tab bar, which passes "insights".
//
// What it does: when that option is the ACTIVE one, it adds `max-desk:`-only
// utilities that deepen the existing teal/green filled treatment below 1200px.
// What it deliberately does not do: touch desktop (every added utility is
// max-desk-scoped, so at 1200px+ the tab bar renders byte-identical CSS to
// before), touch the inactive tabs, touch tab order, routing, aria-pressed or
// hit area, or leak into any other segmented control on the site — a control
// that does not pass the prop cannot receive the treatment.
function SectionViewTabs({ value, onChange, options, className = "", variant = "default", mobileScroll = false, equalWidth = false, mobileFullWidth = false, mobileEmphasisValue = null, ariaLabel = "Section view" }) {
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
            // Mobile-only, active-only, and only for the one option the caller
            // named. Every utility here is `max-desk:`-scoped.
            const mobileEmphasisClass =
              isActive && mobileEmphasisValue && option.value === mobileEmphasisValue
                ? "max-desk:bg-[linear-gradient(135deg,rgba(16,185,129,0.98),rgba(20,184,166,0.9))] max-desk:text-white max-desk:shadow-[0_6px_16px_rgba(20,184,166,0.26),inset_0_1px_0_rgba(255,255,255,0.2)]"
                : "";

            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onChange(option.value)}
                aria-pressed={isActive}
                className={`min-h-12 min-w-0 rounded-md px-1.5 py-1 text-[13px] font-semibold leading-none transition-all duration-200 desk:min-h-0 desk:px-2 desk:py-1 desk:text-xs sm:px-2.5 sm:py-1.5 ${
                  isActive
                    ? "bg-[linear-gradient(135deg,rgba(16,185,129,0.95),rgba(20,184,166,0.78))] text-white shadow-[0_4px_12px_rgba(20,184,166,0.18),inset_0_1px_0_rgba(255,255,255,0.16)]"
                    : "bg-transparent text-[color:color-mix(in_srgb,var(--text-secondary)_82%,transparent)] hover:bg-[rgba(255,255,255,0.045)] hover:text-[var(--text-primary)]"
                } ${mobileEmphasisClass}`}
              >
                <span className="flex min-w-0 items-center justify-center gap-1.5">{option.icon ? <SetPageIcon name={option.icon} className="h-3.5 w-3.5 flex-none" /> : null}<span className="truncate">{option.label}</span></span>
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
        ariaLabel={ariaLabel}
        mobileScroll={mobileScroll}
        equalWidth={equalWidth}
        mobileFullWidth={mobileFullWidth}
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

// Trend-arrow semantics — one shared rule for every stat tile/row:
//   • the arrow GLYPH encodes the direction the displayed value moved
//   • the arrow COLOR encodes whether that movement is favorable for the
//     metric (green = improving, red = worsening, gray = no judgment)
// Per-metric polarity (up = good / up = bad / neutral) is declared once in
// METRIC_TREND_DIRECTIONS above and resolved into `trend.isImprovement` by
// getMetricTrend — components never re-derive it. Hero stat card polarities
// (task 1.5 audit):
//   • Pack Market Price      — neutral (direction shown, no color judgment)
//   • Expected Value         — up = good
//   • Average Hit Value      — up = good
//   • Average Loss           — displayed as a signed value ≤ $0, so up
//                              (toward $0) = good — see trendByMetricKey
//   • Chance to Beat Pack Cost — up = good
//   • Chance at a Big Pull   — up = good
function TrendIndicator({ trend, className = "" }) {
  if (!trend || trend.trend === "unknown") {
    return null;
  }

  const isFlat = trend.trend === "flat";
  // A metric can have a direction (up/down) without an "is this good?"
  // judgment (e.g. pack cost, or top-share concentration) — isImprovement is
  // null for those, but the arrow must still reflect real movement instead
  // of collapsing to flat, which would hide that the value changed at all.
  const hasDirectionalMovement = trend.trend === "up" || trend.trend === "down";
  const iconClassName = isFlat ? "h-4 w-4" : "h-6 w-6";
  const wrapperClassName = isFlat ? "h-5 w-5" : "h-7 w-7";
  const displayTrend = hasDirectionalMovement ? trend.trend : "flat";
  const color =
    trend.isImprovement === true
      ? "var(--success,#10B981)"
      : trend.isImprovement === false
      ? "var(--danger,#EF4444)"
      : "var(--text-secondary)";
  const directionText = hasDirectionalMovement
    ? trend.trend === "up"
      ? "Up"
      : "Down"
    : isFlat
    ? "Unchanged"
    : "Neutral trend";
  const judgmentText =
    trend.isImprovement === true ? " (improving)" : trend.isImprovement === false ? " (worsening)" : "";
  const label = `${directionText} from previous snapshot${judgmentText}`;

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

function OpeningMetricTrendIndicator({ trend, neutral = false }) {
  if (!trend || trend.trend === "unknown") {
    return null;
  }

  if (trend.trend !== "up" && trend.trend !== "down") {
    return (
      <span
        className="inline-flex h-4 w-4 flex-none items-center justify-center leading-none text-[var(--text-secondary)]"
        title="Unchanged from previous snapshot"
        aria-label="Unchanged from previous snapshot"
      >
        {"\u2014"}
      </span>
    );
  }

  const directionText = trend.trend === "up" ? "Up" : "Down";
  return (
    <DeltaTrendIcon
      direction={trend.trend}
      size="md"
      className="h-4 w-4 justify-center"
      color={neutral ? "var(--text-primary)" : null}
      title={`${directionText} from previous snapshot`}
    />
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

// Section-level header (title + info bubble) rendered inside the Simulation
// Results card, below the tab strip, for the active sub-view. The card's own
// title info bubble stays high-level; these explain the specific sub-view.
function SimulationSectionHeader({ title, infoText, className = "mb-3" }) {
  return (
    <div className={`${className} flex items-center gap-2`}>
      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</h3>
      {infoText ? <InfoPopover text={infoText} /> : null}
    </div>
  );
}

// Flush body wrapper for the non-Metrics Simulation Results sub-tabs: no border,
// no rounded panel, no background, and no internal scroll — the parent card is
// the only large container, so every sub-tab reads as one premium canvas
// (Opening Performance vs Cost is the visual reference). Metrics deliberately keeps
// its own scroll wrapper and does NOT use this.
function SimulationResultsPanel({ id, children, className = "" }) {
  return (
    <div id={id} className={`min-h-[24rem] w-full min-w-0 scroll-mt-24 md:scroll-mt-28 ${className}`}>
      {children}
    </div>
  );
}

// ─── Simulation Results → Metrics tab ────────────────────────────────────────
// A deliberately technical read of the raw simulation + EV-derived fields.
// Uses its own compact row (NOT MetricRow) so labels are shown verbatim and are
// never remapped into the simplified/pillar copy getFriendlyMetricLabel applies.
function countMetricEntries(value) {
  if (Array.isArray(value)) {
    return value.length;
  }
  if (value && typeof value === "object") {
    return Object.keys(value).length;
  }
  return null;
}

// Shared "Simulation context surface": one restrained, premium panel treatment
// (elevated navy tone + subtle inset highlight + soft outer shadow + faint blur)
// reused so Total Simulated Value and every Metrics card (verdict stats,
// percentile strip, disclosure groups) read as the same visual family as the
// Value Structure / Pack Paths contribution charts they sit beside. The navy tone matches the rails' bg-[rgba(2,6,23,0.24)] so the boxes
// share the same background opacity/depth; the inset+shadow adds the depth the
// older flat /40 and /55 surfaces lacked. No accent outline, no teal glow.
const SIMULATION_CONTEXT_SURFACE_CLASS =
  "rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.24)] shadow-[inset_0_1px_0_rgba(255,255,255,0.035),0_8px_20px_rgba(2,6,23,0.12)] backdrop-blur-[2px]";

function SimulationContextSurface({ as: Component = "section", className = "", children }) {
  return <Component className={`${SIMULATION_CONTEXT_SURFACE_CLASS} ${className}`}>{children}</Component>;
}

// Semantic tint pattern for the small judgment pills next to expert metrics.
// Tones map to the global semantic tokens (--success / --warning / --danger).
const METRIC_TAG_TONE_CLASSES = {
  success:
    "border-[color:color-mix(in_srgb,var(--success)_45%,transparent)] bg-[color:color-mix(in_srgb,var(--success)_12%,transparent)] text-[var(--success)]",
  warning:
    "border-[color:color-mix(in_srgb,var(--warning)_45%,transparent)] bg-[color:color-mix(in_srgb,var(--warning)_12%,transparent)] text-[var(--warning)]",
  danger:
    "border-[color:color-mix(in_srgb,var(--danger)_45%,transparent)] bg-[color:color-mix(in_srgb,var(--danger)_12%,transparent)] text-[var(--danger)]",
  neutral: "border-[var(--border-subtle)] bg-[var(--surface-page)]/55 text-[var(--text-secondary)]",
};

// The tone pill for a metric's qualitative tag ("low", "concentrated", ...).
// Extracted so the below-desktop Metrics rows show the SAME badge as the
// desktop metric row rather than a second, drifting copy of it.
function SimMetricTag({ tag }) {
  if (!tag) {
    return null;
  }
  return (
    <span
      className={`flex-none rounded-full border px-1.5 py-[1px] text-[10px] font-semibold leading-4 ${
        METRIC_TAG_TONE_CLASSES[tag.tone] || METRIC_TAG_TONE_CLASSES.neutral
      }`}
    >
      {tag.label}
    </span>
  );
}

function SimMetricRow({ label, value, infoText = null, muted = false, tag = null }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-white/5 py-1.5 last:border-b-0 last:pb-0 first:pt-0">
      <span className="inline-flex min-w-0 items-center gap-1.5 text-[13px] text-[var(--text-secondary)]">
        <span className="truncate">{label}</span>
        {infoText ? <InfoPopover text={infoText} /> : null}
        <SimMetricTag tag={tag} />
      </span>
      <span className={`flex-none text-[13px] font-semibold tabular-nums ${muted ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]"}`}>
        {value}
      </span>
    </div>
  );
}

// One-line definition for every Metrics row. Keyed by the exact row label so
// SimMetricLine can auto-attach an info bubble to every row (Task 6: every
// metric row must be explainable).
const SIMULATION_METRIC_INFO = {
  "Pack Market Price": "Current pack price used as the cost baseline for every ratio and profit figure.",
  "Simulated Packs": "Number of simulated pack openings this result is computed from.",
  "Run / As-of Date": "Date/time of the simulation snapshot these metrics come from.",
  "Pack Paths": "Count of pack-path types (e.g. normal, demi-god, god) the model simulates.",
  "Normal Pack States": "Count of modeled normal-pack outcome states used by the simulation.",
  "Min Pack": "Lowest simulated pack value across the run.",
  P5: "5th-percentile pack value — 95% of simulated packs landed above this.",
  P25: "25th-percentile pack value across simulated packs.",
  "Typical Opening (P50)": "Median (50th-percentile) simulated pack value — half of simulated openings are above it and half below it.",
  P75: "75th-percentile pack value across simulated packs.",
  P90: "90th-percentile pack value across simulated packs.",
  P95: "Strong Upside threshold — roughly 5% of simulated packs beat this value.",
  P99: "Jackpot Upside threshold — the top 1% begins at this value.",
  "Max (Best Pull)": "Highest simulated pack value across the run.",
  "Mean (Expected Value)": "Average simulated pack value across every simulated pack.",
  "Std Dev": "Spread of simulated pack values around the mean; higher means noisier outcomes.",
  Variance: "Square of standard deviation; derived from std dev when the backend does not export it explicitly.",
  "Expected Value": "Average simulated pack value.",
  "Typical Opening": "Median (P50) simulated pack value.",
  "EV / Cost": "Expected value ÷ pack market price. Above 1.0x means value exceeds cost.",
  "Typical / Cost": "Median pack value ÷ pack market price.",
  "P95 / Cost": "95th-percentile pack value ÷ pack market price.",
  "P99 / Cost": "99th-percentile pack value ÷ pack market price.",
  "ROI %": "Expected value return relative to pack cost.",
  "Chance to Beat Pack Cost": "Share of simulated packs worth at least the pack price.",
  "Chance at Big Pull": "Share of simulated packs above the big-hit threshold.",
  "Big Hit Threshold": "Value threshold used to count big-hit (big-pull) outcomes.",
  "Average Hit Value": "Average value of hit-card output per pack, where available.",
  "Expected Loss / Pack": "Average downside relative to cost across all simulated packs.",
  "Coefficient of Variation": "Std dev ÷ mean; higher means outcomes swing more relative to the average.",
  "Bad Pack Floor (P05)": "5th-percentile pack value — a rough floor for a bad pack.",
  "P05 Shortfall to Cost": "How far the P05 (bad-floor) outcome falls short of pack cost, as a ratio.",
  "Average Loss When Missing": "Average loss on packs that came in below cost.",
  "Typical Loss When Missing": "Median loss on packs that came in below cost.",
  "Loss Fraction (Avg)": "Average loss-when-missing as a fraction of pack cost.",
  "Loss Fraction (Typical)": "Median loss-when-missing as a fraction of pack cost.",
  "Loss Fraction": "Loss-when-missing as a fraction of pack cost (average and median round to the same value here).",
  "HHI EV Concentration": "Herfindahl index of how concentrated expected value is among chase cards.",
  "Effective Chase Count": "Concentration-adjusted count of meaningful value-carrying chase outcomes.",
  "Top Chase Share": "Share of expected value carried by the single top contributing card.",
  "Top 3 Share": "Share of expected value carried by the top 3 contributing cards.",
  "Top 5 Share": "Share of expected value carried by the top 5 contributing cards.",
  "Hit EV": "Expected value coming from hit cards.",
  "Hit EV / Pack": "Hit-card expected value expressed per pack.",
  "Non-hit EV": "Expected value coming from non-hit / bulk cards.",
  "Hit EV Share": "Portion of total expected value carried by hit cards.",
  "Simulated Set Value": "Modeled total set value based on the simulation's card values.",
  "Simulated Set Value Cards": "Number of cards included in the simulated set value calculation.",
  "Calculated EV": "Deterministic expected value, if exported by the backend.",
  "Simulated EV": "Monte Carlo mean expected value from the simulated packs.",
  "Model Agreement": "Model Agreement compares deterministic/calculated EV against the Monte Carlo mean. It does not validate pull-rate assumptions or market price accuracy.",
  "EV Delta": "Simulated EV minus calculated EV.",
  "EV Delta %": "EV delta expressed as a percentage of calculated EV.",
  "Std Error (MC mean)": "Standard error of the Monte Carlo mean = std dev ÷ √n.",
  "95% Monte Carlo Band": "±1.96 × standard error — the sampling band around the Monte Carlo mean.",
  "Simulation As-of": "Date of the simulation snapshot feeding these metrics.",
  "Performance History Latest": "Date of the most recent performance-vs-cost history point.",
};

// Every Metrics row goes through this wrapper so it always carries an info
// bubble (resolved from SIMULATION_METRIC_INFO unless an explicit one is given).
function SimMetricLine({ label, value, muted = false, infoText, tag = null }) {
  return <SimMetricRow label={label} value={value} muted={muted} tag={tag} infoText={infoText ?? SIMULATION_METRIC_INFO[label] ?? null} />;
}

// Tier 2: hand-rolled SVG log-scale strip replacing the 9-row percentile
// table. Major markers (Min, P5, P50, P95, P99, Max) carry staggered labels;
// P25/P75 (the IQR band edges) and P90 stay as hover/focus-only minor markers
// so every percentile from the old table remains accessible. The dashed pack
// cost line is the visual anchor.
const PERCENTILE_STRIP_HEIGHT = 128;
const PERCENTILE_STRIP_BASELINE_Y = 66;

function PercentileStripChart({ model }) {
  const containerRef = useRef(null);
  const [stripWidth, setStripWidth] = useState(0);
  const [activeMarker, setActiveMarker] = useState(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return undefined;
    }
    const measure = () => setStripWidth(element.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const markers = model?.markers || [];
  const majorMarkers = markers.filter((marker) => marker.major);
  const plotPadding = 14;
  const plotWidth = Math.max(0, stripWidth - plotPadding * 2);
  const xFor = (position) => plotPadding + position * plotWidth;
  const clampLabelX = (value) => Math.min(Math.max(value, 30), Math.max(stripWidth - 30, 30));
  const baselineY = PERCENTILE_STRIP_BASELINE_Y;
  const markerColor = (marker) => (marker.aboveCost ? "var(--success)" : "var(--neutral)");

  const ariaLabel = `Simulated pack value percentiles on a log scale. ${majorMarkers
    .map((marker) => `${marker.label} ${formatMetricCurrency(marker.value)}`)
    .join(", ")}${model?.cost ? `. Pack cost ${formatMetricCurrency(model.cost.value)}.` : "."}`;

  if (!model) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative min-w-0 overflow-visible">
      {stripWidth > 0 ? (
        <>
          <svg
            role="img"
            aria-label={ariaLabel}
            width="100%"
            height={PERCENTILE_STRIP_HEIGHT}
            className="block overflow-visible"
          >
            {/* Interquartile band (P25-P75); warm tint only while it sits fully below cost. */}
            {model.band ? (
              <rect
                x={xFor(model.band.fromPosition)}
                y={baselineY - 9}
                width={Math.max(2, xFor(model.band.toPosition) - xFor(model.band.fromPosition))}
                height={18}
                rx={3}
                fill={model.band.belowCost ? "color-mix(in srgb, var(--warning) 16%, transparent)" : "rgba(255,255,255,0.07)"}
              />
            ) : null}

            <line x1={plotPadding} x2={plotPadding + plotWidth} y1={baselineY} y2={baselineY} stroke="rgba(255,255,255,0.16)" strokeWidth={1} />

            {/* Pack cost — the anchor of the whole chart. */}
            {model.cost ? (
              <g>
                <line
                  x1={xFor(model.cost.position)}
                  x2={xFor(model.cost.position)}
                  y1={20}
                  y2={PERCENTILE_STRIP_HEIGHT - 16}
                  stroke="var(--text-primary)"
                  strokeOpacity={0.85}
                  strokeWidth={1.25}
                  strokeDasharray="4 4"
                />
                <text
                  x={clampLabelX(xFor(model.cost.position) + (model.cost.position > 0.72 ? -6 : 6))}
                  y={13}
                  textAnchor={model.cost.position > 0.72 ? "end" : "start"}
                  fontSize={11}
                  fontWeight={650}
                  fill="var(--text-primary)"
                >
                  Pack cost {formatMetricCurrency(model.cost.value)}
                </text>
              </g>
            ) : null}

            {markers.map((marker) => {
              const markerX = xFor(marker.position);
              const isMedian = marker.key === "p50";
              return (
                <g
                  key={`percentile-marker:${marker.key}`}
                  tabIndex={0}
                  aria-label={`${marker.label}: ${formatCurrency(marker.value)}`}
                  className="cursor-pointer focus:outline-none"
                  onMouseEnter={() => setActiveMarker(marker)}
                  onMouseLeave={() => setActiveMarker(null)}
                  onFocus={() => setActiveMarker(marker)}
                  onBlur={() => setActiveMarker(null)}
                >
                  {/* Hit target wider than the mark itself. */}
                  <rect x={markerX - 9} y={baselineY - 20} width={18} height={40} fill="transparent" />
                  {marker.major ? (
                    <line
                      x1={markerX}
                      x2={markerX}
                      y1={baselineY - (isMedian ? 13 : 10)}
                      y2={baselineY + (isMedian ? 13 : 10)}
                      stroke={markerColor(marker)}
                      strokeWidth={isMedian ? 3.5 : 2}
                      strokeLinecap="round"
                    />
                  ) : (
                    <circle cx={markerX} cy={baselineY} r={3.25} fill={markerColor(marker)} fillOpacity={0.9} />
                  )}
                  {marker.major ? (
                    <text
                      x={clampLabelX(markerX)}
                      y={marker.labelSide === "above" ? baselineY - 24 : baselineY + 32}
                      textAnchor="middle"
                      fontSize={10.5}
                    >
                      <tspan fill="var(--text-primary)" fontWeight={650}>{marker.label}</tspan>
                      <tspan fill="var(--text-secondary)" dx={4}>{formatMetricCurrency(marker.value)}</tspan>
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>

          {activeMarker ? (
            <div
              className="pointer-events-none absolute z-[9999]"
              style={{
                left: Math.min(Math.max(xFor(activeMarker.position) - 60, 0), Math.max(stripWidth - 150, 0)),
                top: -8,
              }}
            >
              <SimulationChartTooltipFrame label={activeMarker.key === "p50" ? "Typical Opening (P50)" : activeMarker.label}>
                <p>
                  <span className="font-semibold text-white">{formatCurrency(activeMarker.value)}</span> simulated pack value
                </p>
              </SimulationChartTooltipFrame>
            </div>
          ) : null}

          {/* Screen-reader equivalent of the full percentile table the strip replaces. */}
          <span className="sr-only">
            {markers.map((marker) => `${marker.label}: ${formatCurrency(marker.value)}`).join("; ")}
            {model.cost ? `; Pack cost: ${formatCurrency(model.cost.value)}` : ""}
          </span>
        </>
      ) : null}
    </div>
  );
}

// Tier 3 disclosure card: native <details>/<summary> (keyboard operable,
// expansion state conveyed by the details element) styled onto the shared
// Simulation context surface, mirroring DisclosureSection's summary/chevron
// pattern. Metric rows inside reuse SimMetricLine unchanged.
function SimMetricDisclosureCard({ question, defaultOpen = false, children }) {
  return (
    <details open={defaultOpen} className={`${SIMULATION_CONTEXT_SURFACE_CLASS} group min-w-0 self-start p-3.5`}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md text-left transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/55">
        <span className="text-sm font-semibold text-[var(--text-primary)]">{question}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="h-5 w-5 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
          fill="currentColor"
        >
          <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
        </svg>
      </summary>
      <div className="mt-2.5 border-t border-white/10 pt-1">{children}</div>
    </details>
  );
}

// Metrics below 1200px.
//
// Desktop presents five surfaces: the percentile strip in its own context panel
// and four <details> cards, the first open by default. Stacked on a phone that
// is five bordered boxes and roughly forty labelled rows before the reader has
// chosen anything to look at.
//
// Below desktop it is the interaction the rest of this tab now uses: one row per
// question on a shared column grid, one selected row, one shared detail region
// holding that group's complete existing content. Nothing is summarised away —
// every SimMetricLine the desktop cards render is rendered here too, from the
// same element definitions, one group at a time.
function SimulationMetricsCompactList({ groups }) {
  const [selectedKey, setSelectedKey] = useState(groups[0]?.key || null);
  const detailRegionId = useId();

  if (groups.length === 0) {
    return null;
  }

  const selected = groups.find((group) => group.key === selectedKey) || groups[0];

  return (
    <div data-simulation-metrics-compact className="min-w-0 desk:hidden">
      <div className="min-w-0">
        {groups.map((group) => {
          const isSelected = group.key === selected.key;
          return (
            <button
              key={`simulation-metric-group:${group.key}`}
              type="button"
              onClick={() => setSelectedKey(group.key)}
              aria-expanded={isSelected}
              aria-controls={detailRegionId}
              data-simulation-metric-row
              data-simulation-metric-row-key={group.key}
              data-compact-row
              data-selected={isSelected ? "true" : undefined}
              className={`grid min-h-11 w-full grid-cols-[minmax(0,1fr)_5.5rem] items-center gap-x-2 border-b border-l-2 border-[var(--border-subtle)] py-1 pl-1.5 pr-1.5 text-left transition-colors last:border-b-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                isSelected ? COMPACT_ROW_SELECTED_CLASS : COMPACT_ROW_IDLE_CLASS
              }`}
            >
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">{group.label}</span>
                {/* The caption names WHICH of the group's own lines the value
                    beside it is, so the figure is never unattributed. */}
                <span className="block truncate text-[10px] leading-tight text-[var(--text-secondary)]">
                  {group.caption}
                </span>
              </span>
              <span className="flex min-w-0 items-center justify-end gap-1.5">
                {group.tag ? <SimMetricTag tag={group.tag} /> : null}
                <span className="text-right text-sm font-semibold leading-none tabular-nums text-[var(--text-primary)]">
                  {group.value}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* ONE shared detail region carrying the selected group's complete
          existing content — the same JSX the desktop card renders. */}
      <div
        id={detailRegionId}
        aria-live="polite"
        data-simulation-metric-detail
        className={`mt-2 min-w-0 pl-2.5 pr-1.5 ${COMPACT_DETAIL_CLASS}`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="inline-flex min-w-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-secondary)]">
            <span className="truncate">{selected.label}</span>
            {selected.infoText ? <InfoPopover text={selected.infoText} /> : null}
          </div>
          {selected.key === "where-packs-land" ? (
            <span className="flex-none text-[10px] font-medium uppercase tracking-[0.08em] text-[color:color-mix(in_srgb,var(--text-secondary)_75%,transparent)]">
              log scale
            </span>
          ) : null}
        </div>
        <div className="min-w-0">{selected.body}</div>
      </div>
    </div>
  );
}

function SimulationMetricsContent({
  summary,
  percentiles = [],
  ripStatistics = null,
  historyTrend = [],
  asOfDate = null,
  performanceHistoryLatestDate = null,
}) {
  const safeSummary = summary && typeof summary === "object" ? summary : {};

  // Shared Metrics formatter (simulationMetricsDisplay.mjs): every displayed
  // number in this tab passes through one of these. Missing data stays "—".
  const money = (value) => formatMetricCurrency(value);
  const ratio = (value) => formatMetricRatio(value);
  const probability = (value) => formatMetricProbability(value);
  // Match the app's existing Top-Share convention (percent without the
  // probability normalization — see the advanced concentration tiles).
  const share = (value) => formatMetricPercent(value);
  const countValue = (value) => formatMetricCount(value);
  const dateValue = (value) => {
    if (!value) {
      return "—";
    }
    return formatHistoryDate(value, { year: "numeric", month: "short", day: "numeric" }) || String(value);
  };

  const packCost = toNumber(safeSummary.pack_cost ?? safeSummary.current_market_pack_cost);
  const simulationCount = safeSummary.simulation_count ?? safeSummary.packs_simulated;
  const packPathsCount = countMetricEntries(ripStatistics?.pack_paths);
  const normalStatesCount = countMetricEntries(ripStatistics?.normal_pack_states);

  const p05 = selectPercentileValue(percentiles, 5) ?? toNumber(safeSummary.tail_value_p05);
  const p25 = selectPercentileValue(percentiles, 25);
  const p50 = selectPercentileValue(percentiles, 50) ?? toNumber(safeSummary.median_value);
  const p75 = selectPercentileValue(percentiles, 75);
  const p90 = selectPercentileValue(percentiles, 90);
  const p95 = selectPercentileValue(percentiles, 95);
  const p99 = selectPercentileValue(percentiles, 99);

  // TODO(backend): calculated/deterministic EV (evr_runner
  // calculated_expected_value_per_pack) is not yet surfaced into the set-page
  // snapshot summary payload. Once it is, Model Agreement below lights up
  // automatically — no frontend change needed.
  const calculatedEV = selectCalculatedExpectedValue(safeSummary);
  const simulatedEV = selectSimulatedExpectedValue(safeSummary);
  const agreement = computeModelAgreement({ calculatedEV, simulatedEV });
  const standardError = computeStandardError(safeSummary.std_dev, simulationCount);
  const monteCarloBand = computeMonteCarloBand(standardError);

  // "Performance History Latest" must report a real observation date —
  // carried-forward continuity rows are display filler, never an update.
  const historyLatestDate = performanceHistoryLatestDate ?? getLatestRealPerformanceDate(historyTrend);
  const simulationAsOf = asOfDate || safeSummary.run_at || null;

  const roiPercentValue = toNumber(safeSummary.roi_percent);
  const probProfitRaw = toNumber(safeSummary.prob_profit);
  const probProfitPercent = probProfitRaw === null ? null : Math.abs(probProfitRaw) <= 1 ? probProfitRaw * 100 : probProfitRaw;

  // Tier 2 strip model + computed takeaway (both from live values only).
  const stripModel = buildPercentileStripModel({
    min: toNumber(safeSummary.min_value),
    p5: p05,
    p25,
    p50,
    p75,
    p90,
    p95,
    p99,
    max: toNumber(safeSummary.max_value),
    packCost,
  });
  const stripTakeaway = buildPercentileTakeaway({ p50, p95, packCost, probProfitPercent });

  // Tier 3 expert judgment tags + loss-fraction dedupe.
  const coefficientOfVariationTag = getCoefficientOfVariationTag(safeSummary.coefficient_of_variation);
  const hhiConcentrationTag = getHhiConcentrationTag(safeSummary.hhi_ev_concentration);
  const lossFractionMerged = shouldMergeLossFractionRows(
    safeSummary.expected_loss_when_losing_fraction,
    safeSummary.median_loss_when_losing_fraction
  );

  // Each group's rows are defined ONCE and handed to both presentations, so the
  // below-desktop list cannot drift from the 1200px+ cards: same SimMetricLine
  // components, same labels, same formatters, same order, same tags.
  const packsLandBody = (
    <>
      <div className="mt-1 min-w-0 overflow-visible">
        {stripModel ? (
          <PercentileStripChart model={stripModel} />
        ) : (
          <p className="py-3 text-sm text-[var(--text-secondary)]">Percentile data is not available in the current snapshot.</p>
        )}
      </div>
      {stripTakeaway ? <p className="text-[12px] leading-snug text-[var(--text-secondary)]">{stripTakeaway}</p> : null}
    </>
  );

  const loseMoneyLines = (
    <>
      <SimMetricLine label="EV / Cost" value={ratio(safeSummary.mean_value_to_cost_ratio)} />
      <SimMetricLine label="Typical / Cost" value={ratio(safeSummary.median_value_to_cost_ratio)} />
      <SimMetricLine label="ROI %" value={roiPercentValue === null ? "—" : formatMetricSignedPercent(roiPercentValue)} />
      <SimMetricLine label="Chance to Beat Pack Cost" value={probability(safeSummary.prob_profit)} />
      <SimMetricLine label="P05 Shortfall to Cost" value={ratio(safeSummary.p05_shortfall_to_cost)} />
      <SimMetricLine label="Bad Pack Floor (P05)" value={money(p05)} />
      <SimMetricLine label="Average Loss When Missing" value={money(safeSummary.expected_loss_when_losing)} />
      <SimMetricLine label="Typical Loss When Missing" value={money(safeSummary.median_loss_when_losing)} />
      {lossFractionMerged ? (
        <SimMetricLine label="Loss Fraction" value={share(safeSummary.expected_loss_when_losing_fraction)} />
      ) : (
        <>
          <SimMetricLine label="Loss Fraction (Avg)" value={share(safeSummary.expected_loss_when_losing_fraction)} />
          <SimMetricLine label="Loss Fraction (Typical)" value={share(safeSummary.median_loss_when_losing_fraction)} />
        </>
      )}
      <SimMetricLine label="Expected Loss / Pack" value={money(safeSummary.expected_loss_per_pack)} />
    </>
  );

  const upsideLines = (
    <>
      <SimMetricLine label="Chance at Big Pull" value={probability(safeSummary.prob_big_hit)} />
      <SimMetricLine label="Big Hit Threshold" value={money(safeSummary.big_hit_threshold)} />
      <SimMetricLine label="Strong Upside (P95) vs Cost" value={ratio(safeSummary.p95_value_to_cost_ratio)} />
      <SimMetricLine label="Jackpot Upside (P99 / Top 1%) vs Cost" value={ratio(safeSummary.p99_value_to_cost_ratio)} />
      <SimMetricLine label="Max (Best Pull)" value={money(safeSummary.max_value)} />
      <SimMetricLine label="Average Hit Value" value={money(safeSummary.average_hit_value)} />
      <SimMetricLine label="Hit EV" value={money(safeSummary.hit_ev)} />
      <SimMetricLine label="Hit EV / Pack" value={money(safeSummary.hit_ev_per_pack)} />
      <SimMetricLine label="Hit EV Share" value={share(safeSummary.hit_ev_share)} />
      <SimMetricLine label="Non-hit EV" value={money(safeSummary.non_hit_ev)} />
    </>
  );

  const swingyLines = (
    <>
      <SimMetricLine label="Std Dev" value={money(safeSummary.std_dev)} />
      <SimMetricLine
        label="Coefficient of Variation"
        value={formatMetricNumber(safeSummary.coefficient_of_variation, 2)}
        tag={coefficientOfVariationTag}
      />
      <SimMetricLine
        label="HHI EV Concentration"
        value={formatMetricNumber(safeSummary.hhi_ev_concentration, 3)}
        tag={hhiConcentrationTag}
      />
      <SimMetricLine label="Effective Chase Count" value={formatMetricNumber(safeSummary.effective_chase_count, 2)} />
      <SimMetricLine label="Top Chase Share" value={share(safeSummary.top1_ev_share)} />
      <SimMetricLine label="Top 3 Share" value={share(safeSummary.top3_ev_share)} />
      <SimMetricLine label="Top 5 Share" value={share(safeSummary.top5_ev_share)} />
    </>
  );

  const howSimulatedLines = (
    <>
      <SimMetricLine label="Pack Market Price" value={money(packCost)} />
      <SimMetricLine label="Simulated Packs" value={countValue(simulationCount)} />
      <SimMetricLine label="Run / As-of Date" value={dateValue(simulationAsOf)} />
      <SimMetricLine label="Pack Paths" value={packPathsCount === null ? "—" : countValue(packPathsCount)} />
      <SimMetricLine label="Normal Pack States" value={normalStatesCount === null ? "—" : countValue(normalStatesCount)} />
      {agreement.available ? (
        <>
          <SimMetricLine label="Calculated EV" value={money(calculatedEV)} />
          <SimMetricLine label="Simulated EV" value={money(simulatedEV)} />
          <SimMetricLine label="EV Delta" value={formatSignedCurrency(agreement.delta)} />
          <SimMetricLine label="EV Delta %" value={formatMetricSignedPercent(agreement.deltaPercent)} />
          <SimMetricLine label="Model Agreement" value={formatMetricPercent(agreement.score)} />
        </>
      ) : (
        <p className="border-b border-[var(--border-subtle)] pb-2 text-[12px] leading-snug text-[var(--text-secondary)]">
          Calculated-vs-simulated agreement is not available in this snapshot yet.
        </p>
      )}
      {standardError !== null ? (
        <>
          <SimMetricLine label="Std Error (MC mean)" value={money(standardError)} />
          <SimMetricLine label="95% Monte Carlo Band" value={monteCarloBand === null ? "—" : `± ${money(monteCarloBand)}`} />
        </>
      ) : null}
      <SimMetricLine label="Simulation As-of" value={dateValue(simulationAsOf)} />
      <SimMetricLine label="Performance History Latest" value={dateValue(historyLatestDate)} />
      <SimMetricLine label="Simulated Set Value" value={money(safeSummary.simulated_set_value)} />
      <SimMetricLine label="Simulated Set Value Cards" value={countValue(safeSummary.simulated_set_value_card_count)} />
    </>
  );

  const packsLandInfoText =
    "Distribution of simulated per-pack value across the run, plotted against pack market price. The shaded band spans P25-P75 (the middle half of packs); hover any marker for its exact value.";

  // The below-desktop rows. Each scan value is a figure the group ALREADY
  // displays — the row promotes one of its own lines, it does not compute a new
  // summary — and the caption names which line it is so the number is never
  // unattributed. Group order matches the desktop layout exactly.
  const metricGroups = [
    {
      key: "where-packs-land",
      label: "Where Packs Land",
      caption: "Typical Opening (P50)",
      value: money(p50),
      infoText: packsLandInfoText,
      body: packsLandBody,
    },
    {
      key: "will-i-lose-money",
      label: "Will I lose money?",
      caption: "Chance to beat pack cost",
      value: probability(safeSummary.prob_profit),
      body: loseMoneyLines,
    },
    {
      key: "whats-the-upside",
      label: "What's the upside?",
      caption: "Chance at big pull",
      value: probability(safeSummary.prob_big_hit),
      body: upsideLines,
    },
    {
      key: "how-swingy",
      label: "How swingy is it?",
      caption: "Coefficient of variation",
      value: formatMetricNumber(safeSummary.coefficient_of_variation, 2),
      tag: coefficientOfVariationTag,
      body: swingyLines,
    },
    {
      key: "how-simulated",
      label: "How was this simulated?",
      caption: "Simulated packs",
      value: countValue(simulationCount),
      body: howSimulatedLines,
    },
  ];

  return (
    <div className="space-y-3">
      <p className="text-[12px] leading-snug text-[var(--text-secondary)] max-desk:text-[11px]">
        Raw simulation outputs and the metrics derived from them. Values shown as
        {" "}
        <span className="font-semibold text-[var(--text-primary)]">&mdash;</span> are not available in the current snapshot.
      </p>

      {/* Below 1200px: five compact rows and ONE shared detail region. The four
          disclosure cards plus the percentile surface were five stacked boxes,
          each with its own border and inset, and the first one opened by
          default — so the tab landed on a wall of forty labelled rows. */}
      <SimulationMetricsCompactList groups={metricGroups} />

      {/* 1200px+: unchanged. Same surface, same grid, same first-card-open
          disclosure behaviour. */}
      <div className="hidden space-y-3 desk:block">
        {/* The former Tier-1 verdict cards (Expected Value, EV/Cost, Typical
            Pack, Chance to Profit) were removed — that data already leads the
            Overview hero and the RIP Score Breakdown, and every figure remains
            in the grouped rows below. The percentile strip is now the tab's
            first element. */}

        {/* Tier 2 — percentile strip (replaces the 9-row percentile table). */}
        <SimulationContextSurface as="div" className="min-w-0 overflow-visible p-3.5">
          <div className="flex items-center justify-between gap-3">
            <h4 className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.10em] text-[var(--text-secondary)]">
              Where Packs Land
              <InfoPopover text={packsLandInfoText} />
            </h4>
            <span className="flex-none text-[10px] font-medium uppercase tracking-[0.08em] text-[color:color-mix(in_srgb,var(--text-secondary)_75%,transparent)]">
              log scale
            </span>
          </div>
          {packsLandBody}
        </SimulationContextSurface>

        {/* Tier 3 — grouped by question; first card starts expanded. */}
        <div className="grid items-start gap-3 md:grid-cols-2">
          <SimMetricDisclosureCard question="Will I lose money?" defaultOpen>
            {loseMoneyLines}
          </SimMetricDisclosureCard>

          <SimMetricDisclosureCard question="What's the upside?">{upsideLines}</SimMetricDisclosureCard>

          <SimMetricDisclosureCard question="How swingy is it?">{swingyLines}</SimMetricDisclosureCard>

          <SimMetricDisclosureCard question="How was this simulated?">{howSimulatedLines}</SimMetricDisclosureCard>
        </div>
      </div>
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
          <p className="text-xs text-[var(--text-secondary)]">Subject Demand: {cardAppeal || "—"}</p>
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
    return <p className="text-sm text-[var(--text-secondary)]">Top Desirability Drivers are not available for this set yet.</p>;
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
      "This lens blends Strong Upside (P95) with Jackpot Upside (Top 1% / P99) to represent total ceiling quality.",
    evidenceKeys: ["p95_value_to_cost_ratio", "p99_value_to_cost_ratio", "big_hit_threshold", "max_value"],
  },
  {
    key: "averageReturn",
    label: "Expected Value",
    scoreFields: [
      "relative_average_return_score",
      "relative_mean_value_to_cost_score",
      "average_return_score",
      "mean_value_to_cost_score",
    ],
    tierField: "mean_value_to_cost_tier",
    rankField: "mean_value_to_cost_rank",
    format: "score",
    heading: "Expected Value compared with cost",
    simpleCardSummary:
      "This shows whether the set's mean simulated value gives back more or less value compared with similar sets.",
    simpleDetailSummary:
      "This lens describes the Expected Value profile. It sets long-run expectations for whether mean simulated value sits closer to cost or noticeably behind it.",
    description:
      "This lens compares mean simulated pack value against current pack market price.",
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

// The metadata directly beside a primary RIP score, in one hierarchy:
//
//   1. the score itself (rendered by the caller)
//   2. the TIER in its tier-coloured bubble - the shared RankBadge, so the
//      hero, the pillar cards and Collector Appeal all read one palette
//   3. the RANK as plain inline text - a position, not a judgement
//
// Rank deliberately gets no bubble: two outlined chips in a row read as two
// equally-weighted judgements, when only the tier is a judgement at all. The
// cohort size stays in the rank's tooltip rather than in the compact row, where
// "Rank #20 of 21" crowded the line without helping.
//
// There is NO interpretation pill. It rendered the retired Profit/Safety/
// Stability interpretation engine's verdict, which describes neither Financial
// RIP V3 nor Collector Appeal V3.
function HeroScoreBadges({ rank, tier, cohortSize = null, size = "supporting" }) {
  const numericRank = toNumber(rank);
  const numericCohort = toNumber(cohortSize);
  const normalizedTier = String(tier || "").trim().replace(/\s+tier$/i, "").toUpperCase();
  const roundedRank = numericRank === null ? null : Math.round(numericRank);
  const rankTooltip =
    roundedRank === null
      ? undefined
      : numericCohort === null
      ? `Rank #${roundedRank}`
      : `Rank #${roundedRank} of ${Math.round(numericCohort)} ranked sets`;

  if (!normalizedTier && roundedRank === null) {
    return null;
  }

  return (
    <span
      data-rip-score-metadata
      className={`flex min-w-0 max-w-full flex-wrap items-center justify-center gap-x-3 gap-y-2 ${
        size === "hero" ? "text-sm" : "text-xs"
      }`}
    >
      {normalizedTier ? (
        <RankBadge rank={normalizedTier} format="tier" size={size === "hero" ? "supporting" : "default"} />
      ) : null}
      {roundedRank !== null ? (
        <span
          data-rip-score-rank
          className="font-medium tabular-nums text-[var(--text-secondary)]"
          title={rankTooltip}
        >
          Rank #{roundedRank}
        </span>
      ) : null}
    </span>
  );
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
      return { label: "Expected Value", value: formatCurrency(summary.mean_value) };
    case "expected_loss_when_losing":
      return { label: "Avg loss when missing", value: formatLossCurrency(summary.expected_loss_when_losing) };
    case "prob_big_hit":
      return { label: "Chance at a big pull", value: formatPercent(summary.prob_big_hit, { probability: true }) };
    case "p95_value_to_cost_ratio":
      return { label: "Strong Upside", value: fmtMult(summary.p95_value_to_cost_ratio) };
    case "p99_value_to_cost_ratio":
      return { label: "Jackpot Upside", value: fmtMult(summary.p99_value_to_cost_ratio) };
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
  // A missing numeric score with a known tier still has an honest tier-based
  // line to tell (the tier badge renders next to this copy either way) —
  // only fall back to "no data" when neither is available.
  if (score === null && !tier) return "No data available for this lens.";
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
    if (ratio !== null && ratio >= 1.0) return "Expected Value meets or exceeds pack cost.";
    if (tier === "B" || tier === "A" || tier === "S") return "Stronger EV recovery than peers.";
    if (tier === "C") return "Expected Value trails pack cost modestly.";
    return "Expected Value still trails pack cost.";
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
      <article className="set-glass-surface w-full max-w-full min-w-0 rounded-2xl border p-4 sm:p-5">
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
    <article className="set-glass-surface flex h-full flex-col rounded-2xl border p-4 sm:p-5">
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
      titleInfoText="Compact at-a-glance opening lenses for experience, chase potential, upside, and Expected Value."
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
        {signals.map((signal) => (
          <OpeningProfileSignalTile key={`opening-profile:${signal.label}`} lens={signal} />
        ))}
      </div>
    </SectionCard>
  );
}

// Retained from the removed compact breakdown feed: these two are still the
// presentation used by the surviving compact detail regions (Simulation
// Drivers/Metrics and the Top Chase detail block).
//
// The one selected/idle treatment shared by every compact mobile analytical
// list on this page, so they read as the same interaction rather than as
// lookalikes.
//
// `bg-[var(--surface-page)]` is the load-bearing part: these lists sit directly
// above charts and the page wash, and a translucent highlight let that content
// read through the selected row. The opaque base goes down first and the accent
// tint plus the rail halo arrive from `.compact-row-selected` in globals.css.
const COMPACT_ROW_SELECTED_CLASS =
  "compact-row-selected border-l-[var(--accent)] bg-[var(--surface-page)]";
const COMPACT_ROW_IDLE_CLASS = "border-l-transparent hover:bg-[var(--surface-hover)]";
// The shared detail region continues the selected row's rail instead of drawing
// a second unrelated boundary beside it.
const COMPACT_DETAIL_CLASS =
  "compact-row-detail border-l-2 border-l-[color:color-mix(in_srgb,var(--accent)_45%,transparent)]";

// A metric inside the shared detail region. This is MetricRow's content at
// MetricRow's semantics — same friendly label, same tooltip, same trend, same
// negative-value treatment — at the type size the detail region can afford, so
// a nine-row Profit detail stays readable instead of running two screens.
function RipBreakdownDetailMetric({ label, value, trend = null, infoText = null, content = null }) {
  const friendlyLabel = getFriendlyMetricLabel(label);
  const isNegativeValue = typeof value === "string" && value.trim().startsWith("-");

  if (content) {
    return (
      <div className="min-w-0 border-b border-[var(--border-subtle)] py-1.5 last:border-b-0">
        <div className="flex min-w-0 items-center gap-1">
          <span className="text-[11px] font-medium text-[var(--text-primary)]">{friendlyLabel}</span>
          {infoText ? <InfoPopover text={infoText} /> : null}
        </div>
        <div className="mt-1.5">{content}</div>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 items-center justify-between gap-2 border-b border-[var(--border-subtle)] py-1 last:border-b-0">
      <span className="flex min-w-0 items-center gap-1">
        <span className="truncate text-[11px] leading-snug text-[var(--text-secondary)]">{friendlyLabel}</span>
        {infoText ? <InfoPopover text={infoText} /> : null}
      </span>
      <span
        className="inline-flex flex-none items-center gap-1 text-[11px] font-semibold tabular-nums text-[var(--text-primary)]"
        style={isNegativeValue ? getDangerValueStyle() : undefined}
      >
        <TrendIndicator trend={trend} />
        <span>{value}</span>
      </span>
    </div>
  );
}

// The Overview Decision Signals card, the legacy Profit/Safety/Stability
// pillar tiles, the RIP Core / Collector Appeal composition groups and the
// whole below-desktop compact breakdown feed were removed here.
//
// All of them presented the SUPERSEDED model as current: Decision Signals
// scored Profit, Safety, Stability, Opening Experience and Chase Potential;
// the composition groups drew `Overall RIP v4 = 90% RIP Core + 10% CA7` with
// its per-pillar weights and contribution points; and the compact feed was a
// second presentation of the same rows. The canonical model has six Financial
// RIP V3 components and three Collector Appeal V3 factors, rendered by
// FinancialRipV3Breakdown and CollectorAppealBreakdown respectively.
//
// Nothing was recomputed and no backend field changed - these surfaces simply
// stopped being read.

// The canonical RIP Score section: a compact header, then the two things the
// score is made of.
//
// WHAT IT SHOWS
// -------------
//   RIP Score       - the canonical Overall RIP V7 public score, tier, rank and
//                     cohort denominator, all backend-computed.
//   Collector Appeal - its three V3 factors.
//   Financial RIP    - its six V3 components.
//
// WHAT IT DELIBERATELY NO LONGER SHOWS
// ------------------------------------
//   - The RIP Score / RIP Core mode toggle. "RIP Core" is Financial RIP V2 and
//     is not a current alternative to the RIP Score.
//   - The Opening Outlook paragraph, the interpretation badge and its summary.
//     They came from the retired Profit/Safety/Stability interpretation engine
//     and describe neither Financial RIP V3 nor Collector Appeal V3.
//   - The visible composition weights, the formula expression and the
//     contribution-point copy.
//
// THE COMPACT "Financial RIP · Collector Appeal" TEXT LINE WAS REPLACED HERE.
//
// `RipScoreSupportingValues` printed the two supporting canonical values as two
// runs of inline text under the RIP Score headline. It stated the same three
// metrics the redesigned Insights Summary now states, in a treatment that read
// as a caption rather than as the top of the tab. InsightsSummaryModule renders
// exactly those three metrics — RIP Score, Financial RIP, Collector Appeal — in
// one grouped surface, from the same resolved canonical bundle, computing
// nothing and still printing an em dash for anything the backend did not
// publish. No value, scale or source changed; only the presentation did.

// Nothing here computes a score, a rank, a tier or a denominator.
function RipScoreBreakdownModule({
  score,
  rankTier,
  rankValue,
  cohortSize = null,
  titleInfoText,
  // The page's single resolved canonical bundle, forwarded verbatim to both
  // breakdowns so all three surfaces read one source.
  canonical = null,
  requestTimeout = false,
}) {
  return (
    <section id="set-detail-rip-score" className="scroll-mt-24 md:scroll-mt-28">
      {/* Below 1200px there is NO context card: the section joins the
          continuous mobile feed and the page gutter is the only inset, so the
          rows start at the same left edge as every other mobile section. At
          1200px+ the card is untouched: same glass, same border, same radius,
          same p-5 inset. */}
      <article className="set-glass-surface rounded-2xl border p-4 desk:p-5 max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:p-0 max-desk:shadow-none max-desk:[backdrop-filter:none]">
        <div className="min-w-0">
          <SectionEyebrow>01 · RIP Score</SectionEyebrow>
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">RIP Score</h2>
            {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
          </div>
        </div>

        {/* THE INSIGHTS SUMMARY. One grouped surface, three cards, stated
            ONCE: RIP Score, Financial RIP, Collector Appeal. The Overall
            values are handed down from the page's single hero selection rather
            than re-resolved, so this surface cannot disagree with the sticky
            header, and HeroScoreBadges is still the one metadata component both
            surfaces share.

            SCALES DIFFER ON PURPOSE. The RIP Score card is Overall RIP V7's
            cohort-RELATIVE score. The other two are Financial RIP V3's and
            Collector Appeal V3's own fixed-anchor scores, which is the number
            each of those models is defined to publish. Neither is restated on
            the Overall relative scale to make the three look alike.

            These three rails are the ONLY elevated, glowing bars on the page;
            every rail in the two breakdowns below is deliberately quieter. */}
        <InsightsSummaryModule
          canonical={canonical}
          overallScore={score}
          overallTier={rankTier}
          overallRank={rankValue}
          overallCohortSize={cohortSize}
          overallBadges={<HeroScoreBadges rank={rankValue} tier={rankTier} cohortSize={cohortSize} />}
        />

        {/* The two lenses that explain the score — Financial RIP first, then
            Collector Appeal. They are explanatory views of one model, and
            nothing here states or implies an even split between them. Each
            renders its own components and its own independent unavailable
            state, and both read the same resolved bundle as the score above. */}
        <div className="mt-4 min-w-0">
          <FinancialRipV3Breakdown canonical={canonical} requestTimeout={requestTimeout} />
        </div>

        {/* THE ONE canonical Collector Appeal surface on the page, and the home
            of every deep link the removed Collector Profile used to own.
            `set-detail-collector-appeal` is the PREFERRED id; the rest are
            invisible compatibility anchors so an existing bookmark, an internal
            link or an indexed URL still lands on real Collector Appeal content
            instead of on nothing. They carry the same scroll offset as a real
            section heading. */}
        <div id={COLLECTOR_APPEAL_SECTION_ID} className="mt-4 min-w-0 scroll-mt-24 md:scroll-mt-28">
          {LEGACY_COLLECTOR_APPEAL_ANCHOR_IDS.map((anchorId) => (
            <span
              key={anchorId}
              id={anchorId}
              className="block scroll-mt-24 md:scroll-mt-28"
              aria-hidden="true"
            />
          ))}
          <CollectorAppealBreakdown canonical={canonical} />
        </div>
      </article>
    </section>
  );
}

function StatTile({ label, value, valueClassName = "text-lg", infoText = null, trend = null }) {
  return (
    <div className="set-glass-inner rounded-xl border border-[var(--border-subtle)] p-4">
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

// Small muted chapter marker above a section title ("01 · Verdict"), shared by
// the three Insights sections so the page reads verdict → proof → raw evidence.
function SectionEyebrow({ children }) {
  if (!children) {
    return null;
  }
  return <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">{children}</p>;
}

// tone="plain" flattens the card (lighter surface tint, no inset highlight or
// drop shadow) so neighbouring sections stop reading as identical clones.
// `mobileFlush` is opt-in per caller, not a default: SectionCard renders on
// Explore, the Cards tab and the expert layouts too, and those keep their cards
// at every width. Only the sections that joined the continuous mobile feed pass
// it. The utilities are what actually strip the card — `important: true` in
// tailwind.config.js makes `p-4`/`border`/`rounded-2xl` !important, so the
// non-important `[data-mobile-feed] .set-glass-surface` reset in globals.css
// cannot beat them on its own.
const SECTION_CARD_MOBILE_FLUSH_CLASS =
  "max-desk:rounded-none max-desk:border-0 max-desk:bg-transparent max-desk:p-0 max-desk:shadow-none max-desk:[backdrop-filter:none]";

function SectionCard({
  title,
  subtitle,
  titleInfoText,
  eyebrow = null,
  tone = "default",
  children,
  className = "",
  bodyClassName = "",
  bodySpacingClassName = "mt-4",
  mobileFlush = false,
}) {
  // A flush card states its 1200px+ inset with `desk:p-5`, not `sm:p-5`.
  // `max-desk:` utilities are emitted BEFORE `sm:` in the stylesheet and both
  // are !important, so an sm-scoped inset wins back 640-1199px and the card
  // would still look inset on a tablet — the only band where the reset appears
  // to do nothing. The two produce the identical p-5 at 1200px+; they differ
  // only in the band that is supposed to be flush. Callers that keep their card
  // are untouched.
  const insetClass = mobileFlush ? "p-4 desk:p-5" : "p-4 sm:p-5";
  const toneClass =
    tone === "plain"
      ? `rounded-2xl border border-[var(--border-subtle)] ${insetClass}`
      : `rounded-2xl border border-[var(--border-subtle)] ${insetClass}`;
  return (
    <article
      className={["set-glass-surface w-full max-w-full min-w-0", toneClass, mobileFlush ? SECTION_CARD_MOBILE_FLUSH_CLASS : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <div>
        <SectionEyebrow>{eyebrow}</SectionEyebrow>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
          {titleInfoText ? <InfoPopover text={titleInfoText} /> : null}
        </div>
        {subtitle ? <p className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
      </div>
      <div className={[bodySpacingClassName, "min-w-0 max-w-full", bodyClassName].filter(Boolean).join(" ")}>{children}</div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// THE PUBLIC COLLECTOR PROFILE WAS REMOVED HERE
//
// `CollectorProfileSection` and everything it exclusively owned - the Roster
// Appeal / Opening Paths view tabs, the desktop and mobile roster panels, the
// desktop and mobile opening-path panels, their loading/unavailable wrappers,
// the CollectorPanel/CollectorBand/CollectorMetric* primitives, the
// OpeningPathStepArrow and the path presentation helpers, and the whole
// COLLECTOR_PROFILE_* / SET_DESIRABILITY_* / ROSTER_QUALITY_* /
// DEMAND_DISTRIBUTION_* / OPENING_PATH_SUMMARY_* info-copy set - are gone.
// Every one of them had no consumer outside this block.
//
// WHY: the section presented the retired chain
//     Set Desirability -> Collector Appeal -> RIP Score Contribution
// as the current model. Collector Appeal V3 has THREE PARALLEL FACTORS, not a
// sequential pipeline with roster demand as its first stage, and the section's
// copy stated composition weights and contribution points that are internal to
// the model. Its info bullets also carried the "one of the two halves of RIP
// Score" claim, which the canonical 0.90/0.10 blend does not support.
//
// The canonical Collector Appeal presentation is CollectorAppealBreakdown,
// rendered exactly once inside the RIP Score section above. Every deep link
// this section used to own is relocated there as a compatibility anchor - see
// SET_DETAIL_SECTION_TARGETS and COLLECTOR_APPEAL_SECTION_ID.
//
// NO BACKEND DATA WAS REMOVED. `universalSetDesirability` and
// `openingExperience` are still published and still read elsewhere on the page;
// this block simply stopped rendering a superseded story about them.
// ---------------------------------------------------------------------------

const TOP_CARD_IMAGE_CONTAINER_CLASS = "h-[5rem] w-[3.5rem] sm:h-[6.125rem] sm:w-[4.25rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]";
// ~half-height card art for the Simulation Results → Simulation Drivers panel,
// so the top drivers fit inside the card without an internal scrollbar.
const TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS = "h-11 w-[2rem] sm:h-12 sm:w-[2.25rem] flex-none overflow-hidden rounded-md border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.18)] p-0.5 shadow-[0_2px_5px_rgba(0,0,0,0.32)]";

function TopHitRow({ name, evContribution, evShare, nearMintPrice, imageUrl, imageSmallUrl, imageLargeUrl, condensed = false, compactImage = false }) {
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
          <div className={compactImage ? TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS : TOP_CARD_IMAGE_CONTAINER_CLASS}>
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

function TopDriverListRow({ rank, name, evContribution, evShare, nearMintPrice, imageUrl, imageSmallUrl, imageLargeUrl }) {
  const imageSrc = imageUrl || imageSmallUrl || imageLargeUrl || null;
  const [hasImageError, setHasImageError] = useState(false);

  useEffect(() => {
    setHasImageError(false);
  }, [imageSrc]);

  const shouldRenderImage = Boolean(imageSrc) && !hasImageError;

  return (
    <div className="grid min-w-0 grid-cols-[1.5rem_minmax(0,1fr)] gap-2 py-2.5 sm:grid-cols-[1.5rem_minmax(0,1fr)_minmax(10rem,12rem)] sm:items-center">
      <span className="mt-0.5 text-right text-[11px] font-semibold tabular-nums text-[var(--text-secondary)] sm:mt-0">{rank}</span>
      <div className="flex min-w-0 items-center gap-2.5">
        <div className={TOP_CARD_IMAGE_CONTAINER_COMPACT_CLASS}>
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
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{name || "Unknown Card"}</p>
          {evShare ? <p className="truncate text-xs text-[var(--text-secondary)]">{evShare} of pack value</p> : null}
        </div>
      </div>
      <div className="col-start-2 grid min-w-0 grid-cols-2 gap-2 text-left sm:col-start-auto sm:text-right">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Price</p>
          <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">{nearMintPrice === null ? "—" : formatCurrency(nearMintPrice)}</p>
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Value Contribution</p>
          <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">{formatCurrency(evContribution)}</p>
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

function getSimulationDriversSummaryValue(meanValue, topHits) {
  const totalEV = toNumber(meanValue);
  if (totalEV !== null) {
    return totalEV;
  }
  return (Array.isArray(topHits) ? topHits : []).reduce((sum, hit) => sum + (toNumber(hit?.ev_contribution) ?? 0), 0);
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

// Simulation Drivers below 1200px.
//
// The condensed desktop presentation gives every driver a two-column block of
// labelled values (Market Price, Value Contribution) beside a thumbnail. On a
// phone those stack, so ten drivers became ten four-line cards and the panel ran
// several screens.
//
// Below desktop it is the same interaction the RIP Score Breakdown and Metrics
// use: a ranked list on one column grid, one selected row, one shared detail
// region. The scan line is rank / name / value contribution — the field the list
// is ordered by — and the thumbnail, market price and share move into the detail
// for the selected driver only.
//
// Ordering, values and the row set are the backend's: this maps `hits` in place
// and computes nothing the desktop tree did not already compute.
function SimulationDriversCompactList({ hits, totalEV }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const detailRegionId = useId();

  const rows = hits.map((hit, index) => {
    const ev = toNumber(hit?.ev_contribution);
    const rarityLabel =
      String(
        hit?.rarity ||
          hit?.rarity_bucket ||
          hit?.rarityBucket ||
          hit?.card_rarity ||
          hit?.cardRarity ||
          ""
      ).trim() || null;
    const imageUrl =
      hit?.image_small_url ||
      hit?.imageSmallUrl ||
      hit?.image_url ||
      hit?.imageUrl ||
      hit?.image_large_url ||
      hit?.imageLargeUrl ||
      null;
    return {
      key: `${hit?.card_name || "unknown"}:${hit?.ev_contribution ?? "na"}:${index}`,
      rank: index + 1,
      name: hit?.card_name || "Unknown Card",
      ev,
      // Identical expression to the desktop tree's `evShare`, on the same two
      // backend fields — not a second definition of "share".
      evShare: ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null,
      nearMintPrice: getTopHitNearMintPrice(hit),
      rarityLabel,
      imageUrl,
    };
  });

  const selected = rows[selectedIndex] || rows[0] || null;
  if (!selected) {
    return null;
  }

  return (
    <div data-simulation-drivers-compact className="min-w-0 desk:hidden">
      <div
        aria-hidden="true"
        className="grid grid-cols-[1.5rem_minmax(0,1fr)_4.5rem] items-center gap-x-2 border-b border-l-2 border-[var(--border-subtle)] border-l-transparent pb-1 pl-1.5 pr-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]"
      >
        <span className="text-right">#</span>
        <span />
        <span className="text-right">Value</span>
      </div>

      <div className="min-w-0">
        {rows.map((row, index) => {
          const isSelected = index === selectedIndex;
          return (
            <button
              key={row.key}
              type="button"
              onClick={() => setSelectedIndex(index)}
              aria-expanded={isSelected}
              aria-controls={detailRegionId}
              data-simulation-driver-row
              data-compact-row
              data-selected={isSelected ? "true" : undefined}
              className={`grid min-h-11 w-full grid-cols-[1.5rem_minmax(0,1fr)_4.5rem] items-center gap-x-2 border-b border-l-2 border-[var(--border-subtle)] py-1 pl-1.5 pr-1.5 text-left transition-colors last:border-b-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                isSelected ? COMPACT_ROW_SELECTED_CLASS : COMPACT_ROW_IDLE_CLASS
              }`}
            >
              <span className="text-right text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
                {row.rank}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">{row.name}</span>
                {row.evShare ? (
                  <span className="block truncate text-[10px] leading-tight text-[var(--text-secondary)]">
                    {row.evShare} of pack value
                  </span>
                ) : null}
              </span>
              <span className="text-right text-sm font-semibold leading-none tabular-nums text-[var(--text-primary)]">
                {formatCurrency(row.ev)}
              </span>
            </button>
          );
        })}
      </div>

      {/* ONE shared detail region for whichever driver is selected, and it
          carries only what the row above it does NOT already say.

          The row is already rank / name / share of pack value / value
          contribution. A panel that repeated the value, repeated the share,
          added a thumbnail and closed with a generic price caveat was four
          blocks of chrome for one new number. Market Price is that number, so
          Market Price is what is left. The list is the experience; this is a
          footnote to it.

          Nothing is lost — the desktop tree (TopHitCard) is a separate
          component and still renders the image, the value contribution, the
          share and the caveat at 1200px+. */}
      <div
        id={detailRegionId}
        aria-live="polite"
        data-simulation-driver-detail
        className={`mt-2 min-w-0 pl-2.5 pr-1.5 ${COMPACT_DETAIL_CLASS}`}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-12 w-9 flex-none items-center justify-center overflow-hidden rounded-md border border-[rgba(255,255,255,0.10)] bg-[rgba(2,6,23,0.46)]">
            {selected.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={selected.imageUrl} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
            ) : (
              <span className="px-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
                {getCardInitials(selected.name)}
              </span>
            )}
          </span>
          <div className="min-w-0 flex-1">
            <p className="min-w-0 truncate text-xs font-semibold text-[var(--text-primary)]">{selected.name}</p>
            <p className="mt-0.5 truncate text-[11px] text-[var(--text-secondary)]">{selected.rarityLabel || "Rarity unavailable"}</p>
          </div>
        </div>
        <div className="mt-1.5">
          <RipBreakdownDetailMetric
            label="Market Price"
            value={selected.nearMintPrice === null ? "—" : formatCurrency(selected.nearMintPrice)}
          />
        </div>
      </div>
    </div>
  );
}

function TopEVDriversContent({ topHits, meanValue, condensed = false, diagnostics = null, maxRows = null, compactImage = false, showSummary = true, showHiddenCountFooter = true }) {
  const allHits = Array.isArray(topHits) ? topHits : [];
  const hits = maxRows !== null && maxRows !== undefined ? allHits.slice(0, maxRows) : allHits;
  const hiddenDriverCount = allHits.length - hits.length;
  const totalEV = toNumber(meanValue);
  const visibleTopEV = allHits.reduce((sum, hit) => sum + (toNumber(hit?.ev_contribution) ?? 0), 0);
  const hasPackTotalEV = totalEV !== null;
  const totalLabel = hasPackTotalEV ? "Simulated Expected Value" : "Top 10 Simulated Value";
  const totalValue = hasPackTotalEV ? totalEV : visibleTopEV;
  const freshnessInfo = formatSectionFreshnessInfo(diagnostics?.freshness);

  if (allHits.length === 0) {
    return (
      <div className="space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-3 py-3">
        <p className="text-sm text-[var(--text-secondary)]">
          {diagnostics?.warning || "No card contribution rows are available."}
        </p>
        {diagnostics?.source || diagnostics?.missingBackendSource ? (
          <p className="text-xs text-[var(--text-secondary)] opacity-80">
            Source: {diagnostics?.source || diagnostics?.missingBackendSource}
          </p>
        ) : null}
      </div>
    );
  }

  if (condensed) {
    const driverColumns = hits.length > 5 ? [hits.slice(0, 5), hits.slice(5)] : [hits];

    return (
      <div className="w-full max-w-full min-w-0">
        {/* Below 1200px: the same drivers, in the same order, as a ranked
            compact list with one shared detail region. */}
        <SimulationDriversCompactList hits={hits} totalEV={totalEV} />

        {/* 1200px+: unchanged two-column list of labelled blocks. */}
        <div className="hidden min-w-0 gap-x-5 desk:grid lg:grid-cols-2">
          {driverColumns.map((columnHits, columnIndex) => (
            <div key={`driver-column:${columnIndex}`} className="min-w-0 divide-y divide-white/5 border-t border-white/10">
              {columnHits.map((hit, index) => {
                const ev = toNumber(hit?.ev_contribution);
                const evShare = ev !== null && totalEV !== null && totalEV > 0 ? `${((ev / totalEV) * 100).toFixed(1)}%` : null;
                const nearMintPrice = getTopHitNearMintPrice(hit);

                return (
                  <TopDriverListRow
                    key={`${hit?.card_name || "unknown"}:${hit?.ev_contribution ?? "na"}`}
                    rank={columnIndex * 5 + index + 1}
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
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-full min-w-0 space-y-2">
      {showSummary ? (
        <div className="mb-3 flex min-w-0 flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{totalLabel}</span>
            {totalEV !== null ? <InfoPopover text={`${SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT}${freshnessInfo}`} /> : null}
          </div>
          <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(totalValue)}</span>
        </div>
      ) : null}
      <p className="text-xs text-[var(--text-secondary)]">Price-based metrics use estimated third-party market snapshots and may change over time.</p>

      <div className="space-y-2">
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
            compactImage={compactImage}
          />
        );
      })}
      </div>
      {showHiddenCountFooter && hiddenDriverCount > 0 ? (
        <p className="pt-0.5 text-[11px] text-[var(--text-secondary)]">
          Showing top {hits.length} EV drivers · +{hiddenDriverCount} more
        </p>
      ) : null}
    </div>
  );
}

function formatShare(value, total) {
  const parsedValue = toNumber(value);
  const parsedTotal = toNumber(total);
  if (parsedValue === null || parsedTotal === null || parsedTotal <= 0) {
    return "0.0%";
  }
  return `${((parsedValue / parsedTotal) * 100).toFixed(1)}%`;
}

// Restrained, semantic mapping (PART 2): Normal keeps the site teal, Demi-God
// is a muted cyan/slate-blue, and God Pack is a single restrained amber/gold
// accent for the rare premium event — deliberately NOT a neon rainbow palette.
const PACK_PATH_CHART_COLORS = {
  normal: "rgba(20,184,166,0.88)",
  demi_god_pack: "rgba(34,211,238,0.62)",
  god_pack: "rgba(245,182,74,0.92)",
};

// Non-normal paths are "special" — used for the Special path share chip and the
// rare-path visibility marker.
const SPECIAL_PACK_PATH_KEYS = new Set(["demi_god_pack", "god_pack"]);

function buildTopLevelPackPathRows(packPaths) {
  const source = typeof packPaths === "object" && packPaths !== null ? packPaths : {};
  const counts = {
    normal: toNumber(source.normal) ?? 0,
    demi_god_pack: toNumber(source.demi_god_pack ?? source.demi_god ?? source.demigod) ?? 0,
    god_pack: toNumber(source.god_pack ?? source.god) ?? 0,
  };
  return REQUIRED_PACK_PATHS.map((key) => ({
    key,
    name: formatPackPathLabel(key),
    count: counts[key] ?? 0,
    fill: PACK_PATH_CHART_COLORS[key],
    isSpecial: SPECIAL_PACK_PATH_KEYS.has(key),
  }));
}

// Dominant/Special path chips derived DIRECTLY from the raw pack-path counts so
// they share the exact adaptive formatter (and total) with the donut, instead
// of the backend's fixed 1-decimal format_percent strings that render a
// nonzero rare path as "0.0%". Returns [] when no counts are available so the
// caller can fall back to the interpretation-derived evidence rows.
// The three Pack Paths summary chips that render at 1200px+ only. They are
// still BUILT below desktop — same selector, same backend fields, same rows —
// and only their visible chip is suppressed, so nothing downstream of this
// list changes. Lower-cased because the fallback evidence path and the
// counts path do not agree on capitalisation.
const PACK_PATH_DESKTOP_ONLY_EVIDENCE = new Set([
  "dominant path",
  "dominant path share",
  "special path share",
]);

function getPackPathEvidenceRowsFromCounts(packPaths) {
  const rows = buildTopLevelPackPathRows(packPaths);
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  if (total <= 0) {
    return [];
  }
  const dominant = rows.reduce((largest, row) => (!largest || row.count > largest.count ? row : largest), null);
  const specialCount = rows.reduce((sum, row) => sum + (row.isSpecial ? row.count : 0), 0);
  const evidenceRows = [];
  if (dominant?.name) {
    evidenceRows.push(["Dominant path", dominant.name]);
  }
  evidenceRows.push(["Dominant path share", formatShareFromCounts(dominant?.count ?? 0, total)]);
  evidenceRows.push(["Special path share", formatShareFromCounts(specialCount, total)]);
  return evidenceRows;
}

function buildNormalStateContributionRows(stateRows) {
  const { rows } = aggregateNormalStateRows(Array.isArray(stateRows) ? stateRows : []);
  return rows.map((row) => ({
    ...row,
    name: row.label,
  }));
}

function buildRarityCompositionRows(rankings) {
  const rows = Array.isArray(rankings) ? rankings : [];
  return rows
    .map((ranking, index) => {
      const value = toNumber(ranking?.total_sampled_value) ?? 0;
      const pullCount = toNumber(ranking?.pulled_count) ?? 0;
      const name = titleCaseStateLabel(ranking?.rarity_bucket || "Unknown");
      return {
        key: `rarity:${ranking?.rarity_bucket || name}:${index}`,
        name,
        value,
        pullCount,
      };
    })
    .sort((left, right) => right.value - left.value);
}

function SimulationChartTooltipFrame({ label, children }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[rgba(5,11,18,0.96)] px-3 py-2 shadow-[0_14px_36px_rgba(0,0,0,0.42)] backdrop-blur-md">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-300">{label}</p>
      <div className="mt-1 space-y-0.5 text-xs tabular-nums text-slate-300">{children}</div>
    </div>
  );
}

function PackPathDonutTooltip({ active, payload, totalPacks }) {
  const row = active && payload?.length ? payload[0]?.payload : null;
  if (!row) {
    return null;
  }
  const impliedOdds = formatImpliedOdds(row.count, totalPacks);
  return (
    <SimulationChartTooltipFrame
      label={
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 flex-none rounded-sm" style={{ backgroundColor: row.fill }} />
          {row.name}
        </span>
      }
    >
      <p><span className="font-semibold text-white">{row.count.toLocaleString("en-US")}</span> simulated packs</p>
      <p>{formatShareFromCounts(row.count, totalPacks)} of simulated packs</p>
      {impliedOdds ? <p className="text-slate-400">{impliedOdds}</p> : null}
    </SimulationChartTooltipFrame>
  );
}

// Tooltips for the two CompactRankedBarChart usages. The visible chart shows
// only the category name and the compact "share · abbreviated value" column —
// full exact values live here, read straight off the untouched source row.
function RarityContributionChartTooltip({ active, payload }) {
  const row = active && payload?.length ? payload[0]?.payload : null;
  if (!row) {
    return null;
  }
  return (
    <SimulationChartTooltipFrame label={row.label}>
      <p><span className="font-semibold text-white">{formatCurrency(row.value)}</span> simulated value</p>
      <p>{formatShare(row.value, row.totalValue)} of total simulated value</p>
      <p>{(toNumber(row.pullCount) ?? 0).toLocaleString("en-US")} pulls</p>
      <p>{formatShare(row.pullCount, row.totalPulls)} of pulls</p>
    </SimulationChartTooltipFrame>
  );
}

function NormalStateChartTooltip({ active, payload }) {
  const row = active && payload?.length ? payload[0]?.payload : null;
  if (!row) {
    return null;
  }
  const totalPacks = toNumber(row.totalPacks) ?? 0;
  return (
    <SimulationChartTooltipFrame label={row.label}>
      <p><span className="font-semibold text-white">{(toNumber(row.count) ?? 0).toLocaleString("en-US")}</span> packs</p>
      <p>{formatShare(row.count, row.totalStates)} of normal states</p>
      {totalPacks > 0 ? <p className="text-slate-400">{formatShareFromCounts(row.count, totalPacks)} of all simulated packs</p> : null}
    </SimulationChartTooltipFrame>
  );
}

// Flush contribution section holding an
// internal header row (title + optional info bubble + optional right-aligned
// value) above the compact ranked bar chart. Value Structure and Normal State
// Distribution both render through this so they read as one chart language
// applied to two distributions — no separate floating header box stacked above
// a second box, and no per-row mini-cards. The body wrapper stays
// overflow-visible so the chart tooltip can escape the section flow.
function ContributionBarList({ title, titleInfo = null, headerValue = null, children }) {
  return (
    <div className="min-w-0 overflow-visible">
      <div className="flex items-center justify-between gap-3 pb-2">
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <span className="truncate text-[11px] font-semibold uppercase tracking-[0.10em] text-[var(--text-secondary)]">{title}</span>
          {titleInfo ? <InfoPopover text={titleInfo} /> : null}
        </span>
        {headerValue != null ? (
          <span className="flex-none text-base font-semibold tabular-nums text-[var(--text-primary)]">{headerValue}</span>
        ) : null}
      </div>
      <div className="min-w-0 overflow-visible border-t border-white/10 pt-1.5">{children}</div>
    </div>
  );
}

function NormalStateContributionRails({ rows, totalStates, totalPacks = 0 }) {
  // One chart row per normalized state — already aggregated and sorted
  // descending by count (aggregateNormalStateRows). sharePercent is the REAL
  // share of normal-state outcomes; the chart's nice domain ceiling handles
  // readability without normalizing the largest state to 100%.
  const chartRows = useMemo(
    () =>
      rows.map((row) => ({
        label: row.name,
        sharePercent: totalStates > 0 ? (row.count / totalStates) * 100 : 0,
        count: row.count,
        totalStates,
        totalPacks,
      })),
    [rows, totalStates, totalPacks]
  );

  return (
    <ContributionBarList title="Normal State Distribution">
      <CompactRankedBarChart
        rows={chartRows}
        rightLabelFormatter={(row) => ({
          primary: formatShare(row.count, row.totalStates),
          secondary: ` · ${formatAbbreviatedCount(row.count)}`,
        })}
        tooltipContent={<NormalStateChartTooltip />}
      />
    </ContributionBarList>
  );
}

function PackPathsVisualization({ packPaths, normalStateRows, evidenceRows = [], condensed = false }) {
  const pathRows = useMemo(() => buildTopLevelPackPathRows(packPaths), [packPaths]);
  const totalPacks = pathRows.reduce((sum, row) => sum + row.count, 0);
  const visiblePathRows = pathRows.filter((row) => row.count > 0);
  // Display-only rescaled slice weights so a rare nonzero path (e.g. God Pack)
  // is a recognizable ~7% sliver. Real counts/percentages stay in every label.
  const displayPathRows = buildPackPathDisplayRows(visiblePathRows);
  const dominantPathCandidate = pathRows.reduce((largest, row) => (!largest || row.count > largest.count ? row : largest), null);
  const dominantPath = dominantPathCandidate?.count > 0 ? dominantPathCandidate : null;
  const stateRows = useMemo(() => buildNormalStateContributionRows(normalStateRows), [normalStateRows]);
  const totalStates = stateRows.reduce((sum, row) => sum + row.count, 0);

  return (
    <>
      {evidenceRows.length > 0 ? (
        // Dominant path / Dominant path share / Special path share are hidden
        // below 1200px — approved removals. Each restates something the donut
        // and its legend already show: the legend names every path with its
        // count AND its share, and the donut centre repeats the dominant one.
        // On a phone they were a third printing of the same numbers.
        //
        // Hidden PER CHIP, by label, rather than by dropping rows from
        // `evidenceRows`: the selector, the backend fields and the fallback
        // `getPackBreakdownEvidence` path are untouched, any other evidence row
        // still renders at every width, and desktop keeps all three in order.
        <div
          className={`${condensed ? "mb-3" : "mb-4"} flex max-w-full min-w-0 flex-wrap gap-x-2 gap-y-2${
            evidenceRows.every(([label]) => PACK_PATH_DESKTOP_ONLY_EVIDENCE.has(String(label).toLowerCase()))
              ? " max-desk:hidden"
              : ""
          }`}
        >
          {evidenceRows.map(([label, value]) => (
            <span
              key={`${label}:${value}`}
              data-pack-path-evidence-chip={String(label).toLowerCase()}
              className={`inline-flex max-w-full min-w-0 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-2.5 py-1 text-xs text-[var(--text-secondary)]${
                PACK_PATH_DESKTOP_ONLY_EVIDENCE.has(String(label).toLowerCase()) ? " max-desk:hidden" : ""
              }`}
            >
              <span className="shrink-0 text-[var(--text-secondary)]">{label}</span>
              <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">{String(value)}</span>
            </span>
          ))}
        </div>
      ) : null}

      <div className="grid min-w-0 gap-4 overflow-visible lg:grid-cols-[minmax(15rem,0.75fr)_minmax(0,1.75fr)]">
        <div className="min-w-0">
          <p className="pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Pack Paths</p>
          {/* The donut is the supporting visual; keep it flush with the section
              body instead of adding a separate nested panel.
              The detailed read comes from the ring and legend. */}
          <div className="min-w-0 overflow-visible border-t border-white/10 pt-1.5">
            <div className="relative h-[13.125rem] min-w-0 overflow-visible sm:h-[14.25rem]">
              {visiblePathRows.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-[var(--text-secondary)]">No pack-path counts are available.</div>
              ) : (
                <ChartFrame className="h-full w-full overflow-visible">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={displayPathRows}
                        dataKey="displayWeight"
                        nameKey="name"
                        innerRadius="67%"
                        outerRadius="84%"
                        paddingAngle={0}
                        stroke="none"
                        // dataKey is the display-only rescaled weight (see
                        // buildPackPathDisplayRows): each nonzero special path is
                        // drawn at ~7% so its sector is recognizable even when the
                        // true share is sub-pixel. Every text label (legend,
                        // tooltip, center, chips) still reads the real count/share.
                        // cornerRadius 0 keeps a small sliver undistorted.
                        cornerRadius={0}
                        isAnimationActive={false}
                      >
                        {displayPathRows.map((row) => <Cell key={`path-slice:${row.key}`} fill={row.fill} />)}
                      </Pie>
                      <RechartsTooltip
                        content={<PackPathDonutTooltip totalPacks={totalPacks} />}
                        cursor={false}
                        allowEscapeViewBox={{ x: true, y: true }}
                        wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartFrame>
              )}
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="max-w-[8.5rem] text-center">
                  <p className="text-lg font-semibold tabular-nums text-[var(--text-primary)]">{totalPacks.toLocaleString("en-US")}</p>
                  <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Simulated Packs</p>
                  {dominantPath ? (
                    // Adaptive dominant share so a 99.9536% Normal reads "Normal
                    // 99.95%", never a misleading "Normal 100.0%".
                    <p className="mt-1 truncate text-[10px] text-[var(--text-secondary)]">{dominantPath.name} {formatShareFromCounts(dominantPath.count, totalPacks)}</p>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="mt-1.5 grid gap-1 text-[11px] text-[var(--text-secondary)]">
              {pathRows.map((row) => (
                // Every configured path stays in the legend; zero-count paths
                // keep a subdued swatch/label (no fake wedge) while nonzero paths
                // use their semantic color and the adaptive share.
                <div
                  key={`path-legend:${row.key}`}
                  className={`grid min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2${row.count <= 0 ? " opacity-55" : ""}`}
                >
                  <span className="inline-flex min-w-0 items-center gap-1.5 text-[var(--text-primary)]">
                    <span
                      className="h-2 w-2 flex-none rounded-sm"
                      style={{ backgroundColor: row.count <= 0 ? "rgba(148,163,184,0.45)" : row.fill }}
                    />
                    <span className="truncate">{row.name}</span>
                  </span>
                  <span className="tabular-nums">{row.count.toLocaleString("en-US")}</span>
                  <span className="font-medium tabular-nums text-[var(--text-primary)]">{formatShareFromCounts(row.count, totalPacks)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="min-w-0">
          {stateRows.length === 0 ? (
            <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">No normal-state counts are available.</p>
          ) : (
            // The "NORMAL STATE DISTRIBUTION" header now lives inside the shared
            // ContributionBarList section, matching Value Structure's treatment
            // so the two distributions read as the same chart language. totalPacks
            // feeds the tooltip's "share of all simulated packs" line.
            <NormalStateContributionRails rows={stateRows} totalStates={totalStates} totalPacks={totalPacks} />
          )}
        </div>
      </div>
    </>
  );
}

function RarityContributionRails({ rankings }) {
  const rows = useMemo(() => buildRarityCompositionRows(rankings), [rankings]);
  const totalValue = rows.reduce((sum, row) => sum + row.value, 0);
  const totalPulls = rows.reduce((sum, row) => sum + row.pullCount, 0);
  // One chart row per rarity/value group \u2014 already sorted descending by
  // simulated value (buildRarityCompositionRows), all groups retained.
  // sharePercent is the REAL share of total simulated value; pull count/share
  // live only in the tooltip, never as a second line under every bar.
  const chartRows = useMemo(
    () =>
      rows.map((row) => ({
        label: row.name,
        sharePercent: totalValue > 0 ? (row.value / totalValue) * 100 : 0,
        value: row.value,
        pullCount: row.pullCount,
        totalValue,
        totalPulls,
      })),
    [rows, totalValue, totalPulls]
  );

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No value contribution data available.</p>;
  }

  return (
    <ContributionBarList
      title="Total Simulated Value"
      titleInfo={TOTAL_SIMULATED_VALUE_INFO_TEXT}
      headerValue={formatCurrency(totalValue)}
    >
      <CompactRankedBarChart
        rows={chartRows}
        rightLabelFormatter={(row) => ({
          primary: formatShare(row.value, row.totalValue),
          secondary: ` \u00b7 ${formatAbbreviatedCurrency(row.value)}`,
        })}
        tooltipContent={<RarityContributionChartTooltip />}
      />
    </ContributionBarList>
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

  // Simulation Results (condensed): ONE unified panel. The Total Simulated Value
  // header row now lives INSIDE RarityContributionRails' shared context surface,
  // directly above the ranked contribution bars — no separate floating total box
  // stacked above a second box.
  if (condensed) {
    return <RarityContributionRails rankings={rankings} />;
  }

  // Expert Value Contribution section keeps its existing top total box + bar list
  // (out of scope for the Simulation Results unification pass).
  return (
    <>
      <SimulationContextSurface as="div" className="mb-3 flex min-w-0 flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Total Simulated Value</span>
          <InfoPopover text={TOTAL_SIMULATED_VALUE_INFO_TEXT} />
        </div>
        <span className="text-lg font-semibold text-[var(--text-primary)]">{formatCurrency(evRows.totalEV)}</span>
      </SimulationContextSurface>

      {evRows.maxEV === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No value contribution data available.</p>
      ) : (
        <div className="space-y-1">
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

function PackPathBars({ packPaths, condensed = false }) {
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
    <div className={condensed ? "space-y-2" : "space-y-3"}>
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

function StateBars({ stateRows, condensed = false }) {
  const rawRows = Array.isArray(stateRows) ? stateRows : [];
  const rows = rawRows.map((entry) => ({ label: titleCaseStateLabel(entry?.[0]), count: toNumber(entry?.[1]) ?? 0 }));

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No normal-state counts are available.</p>;
  }

  const maxCount = Math.max(...rows.map((row) => row.count), 1);

  return (
    <div className={condensed ? "space-y-2" : "space-y-3"}>
      {rows.map(({ label, count }) => (
        <div key={`state:${label}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-[var(--text-secondary)]">{label}</span>
            <span className="text-sm font-medium text-[var(--text-primary)]">{count.toLocaleString("en-US")}</span>
          </div>
          <HorizontalBar widthPercent={normalizeBarWidth(count, maxCount)} />
        </div>
      ))}
    </div>
  );
}

function PackBreakdownContent({ packPaths, normalStateRows, evidenceRows = [], condensed = false }) {
  if (condensed) {
    return (
      <PackPathsVisualization
        packPaths={packPaths}
        normalStateRows={normalStateRows}
        evidenceRows={evidenceRows}
        condensed
      />
    );
  }

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
          <PackPathBars packPaths={packPaths} condensed={condensed} />
        </div>
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Normal States</p>
          {/* Non-condensed views keep the original row list; the compact
              Simulation Results view renders all collapsed states as a matrix. */}
          <StateBars
            stateRows={normalStateRows}
            condensed={condensed}
          />
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
  isSwitchingTarget = false,
  activeTab,
  activeCardsSubTab,
  activeCardsSection = "all-cards",
  activeGraphMode,
  showTopMarketCards = false,
  onTargetChange,
  onTargetPrefetch,
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
          // Nav order mirrors the tab's render order: ticker (not a nav
          // target), then the chart row, then Top Chase. There is no Decision
          // Signals entry - the section it pointed at was removed.
          { id: "performance-vs-cost", label: "Market Snapshot", tab: "overview", section: "performance-vs-cost", graphMode: "historical-trend", targetId: "set-detail-overview-performance", active: activeGraphMode === "historical-trend" },
          ...(showTopMarketCards
            ? [{ id: "top-market-cards", label: "Top Chase Cards", tab: "overview", section: "top-market-cards", targetId: "set-detail-top-market-cards", active: false }]
            : []),
        ]
      : activeTab === "cards"
      ? [
          // The active highlight must track the cards *section* (URL
          // `section` param), not just the sub-tab — otherwise
          // ?section=market-movers renders with "All Cards" highlighted.
          { id: "all-cards", label: "All Cards", tab: "cards", section: "all-cards", cardsSubTab: "checklist", targetId: "set-detail-cards", active: activeCardsSubTab === "checklist" && activeCardsSection !== "market-movers" },
          { id: "market-movers", label: "Market Movers", tab: "cards", section: "market-movers", cardsSubTab: "checklist", targetId: "set-detail-cards", active: activeCardsSubTab === "checklist" && activeCardsSection === "market-movers" },
        ]
      : activeTab === "pull-rates"
      ? [
          { id: "pull-rate-assumptions", label: "Pull Rate Assumptions", tab: "pull-rates", active: true },
        ]
      : [
          { id: "rip-score", label: "RIP Score Breakdown", tab: "insights", section: "rip-score", targetId: "set-detail-rip-score", active: false },
          // The "Collector Profile" entry pointed at a section that no longer
          // exists. It is renamed to what actually renders, and points at the
          // canonical block rather than at a legacy anchor.
          { id: "collector-appeal", label: "Collector Appeal", tab: "insights", section: "collector-appeal", targetId: COLLECTOR_APPEAL_SECTION_ID, active: false },
          { id: "simulation-results", label: "Simulation Results", tab: "insights", section: "simulation-results", graphMode: "outcome-distribution", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "outcome-distribution" },
          { id: "opening-performance-cost", label: "Opening Profit vs Cost", tab: "insights", section: "opening-performance-cost", graphMode: "historical-trend", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "historical-trend" },
          { id: "simulation-cards", label: "Simulation Drivers", tab: "insights", section: "simulation-cards", graphMode: "simulation-drivers", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "simulation-drivers" },
          { id: "value", label: "Value Structure", tab: "insights", section: "value", graphMode: "value-contribution", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "value-contribution" },
          { id: "pack-breakdown", label: "Pack Paths", tab: "insights", section: "pack-breakdown", graphMode: "pack-breakdown", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "pack-breakdown" },
          { id: "simulation-metrics", label: "Metrics", tab: "insights", section: "simulation-metrics", graphMode: "simulation-metrics", targetId: ANALYSIS_SECTION_ID, active: activeGraphMode === "simulation-metrics" },
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
          onFocus={() => onTargetPrefetch?.(requestedTargetId, { includeAdjacent: true, reason: "rail-focus" })}
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
        {isSwitchingTarget ? (
          <p className="px-1 text-[11px] font-medium text-[var(--accent)]">Switching set...</p>
        ) : null}
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
      Expected Value is the mean value generated per simulated pack using current card values and pull odds. Value Contribution shows how much each card adds to that mean after pull odds are considered.
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
    .replace(/expected pack value/gi, "Expected Value")
    .replace(/expected value/gi, "Expected Value")
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
  explorePayload: initialExplorePayload,
  shellPayload = null,
  initialModuleSnapshots = null,
  pageError,
  profileBaseHref = "/Explore/rip-statistics",
  targetHrefById = null,
  setDetailMode = false,
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  // Dedicated transition for same-set tab/section navigation, separate from
  // isPending/startTransition above (which only covers the set-switcher).
  // Wrapping router.push here keeps the currently-mounted tab content visible
  // with a pending flag instead of letting Next show the route's fullscreen
  // loading.js fallback during the RSC round-trip — router.push itself is
  // unchanged, still the single call site, still a real navigation (see
  // pushSetDetailRouteState below).
  const [isTabNavPending, startTabTransition] = useTransition();
  const [explorePayload, setExplorePayload] = useState(initialExplorePayload || null);
  const [setPageSnapshotRefreshState, setSetPageSnapshotRefreshState] = useState({
    status: "idle",
    setId: null,
    error: null,
  });
  const timeoutSnapshotRefreshKeyRef = useRef(null);
  const explorePagePayloadFetchKeyRef = useRef(null);
  const activeSetResourceIdRef = useRef(null);
  // "Already-loaded same-set client state" fallback for the title/header card
  // (setHeaderSummary below) — a sticky last-known-good snapshot per set id so
  // the header does not blank out when explorePayload is intentionally reset
  // to null on tab navigation (Cards/Overview never fetch the full payload).
  const setHeaderSummaryCacheRef = useRef(null);

  const rawTargets = targetsPayload?.targets;
  const targets = useMemo(() => (Array.isArray(rawTargets) ? rawTargets : []), [rawTargets]);
  // Set-switcher option lists must match Explore and the public Sets catalog,
  // which exclude hidden/unvalidated-era sets (e.g. Sword & Shield pending
  // validation — see pokemonSetPublicCoverage.js); otherwise hidden sets stay
  // one dropdown away from unvalidated public analytics. The currently
  // requested target is kept even when ineligible so a direct URL to a hidden
  // set still renders a coherent switcher (correct selected option) instead of
  // a blank/mismatched control. Only the switcher surfaces use this list —
  // `targets` above still feeds non-switcher consumers unchanged.
  const switcherTargets = useMemo(() => {
    const requestedId = String(requestedTargetId || "");
    return targets.filter(
      (target) =>
        isPublicAnalyticsEligiblePokemonSet(target) ||
        String(target?.target_id || "") === requestedId
    );
  }, [targets, requestedTargetId]);
  const resolvedSetResourceId = useMemo(
    () => getResolvedPokemonSetResourceId({ requestedTargetId, selectedTarget, explorePayload, shellPayload }),
    [requestedTargetId, selectedTarget, explorePayload, shellPayload]
  );
  // Tracks the freshest resolved set id for async callbacks (e.g. the retry
  // fetch below) so a stale response can detect a set switch even if abort
  // somehow doesn't win the race.
  activeSetResourceIdRef.current = resolvedSetResourceId;
  // A set switch can leave the shellPayload prop holding the PREVIOUS set's
  // data for a render or two before the new set's shell commits. Merging that
  // mismatched shell would render the previous set's title-card metrics under
  // the new set's name (Temporal Forces blank/leak race). Only trust the shell
  // when its own identity matches the active set — but if the shell carries no
  // resolvable identity at all, keep using it (we can't prove a mismatch, and
  // blanking a valid identity-less shell would regress the common case).
  const shellPayloadIsForActiveSet = useMemo(() => {
    if (!shellPayload) {
      return false;
    }
    if (!resolvedSetResourceId) {
      return true;
    }
    const shellIdentity = getSetSnapshotIdentity(shellPayload);
    if (getSetIdentityTokens(shellIdentity).length === 0) {
      return true;
    }
    return setIdentityMatchesTarget(shellIdentity, resolvedSetResourceId);
  }, [shellPayload, resolvedSetResourceId]);
  const effectiveShellPayload = shellPayloadIsForActiveSet ? shellPayload : null;
  // explorePayload and shellPayload carry different field sets for the same
  // set (e.g. shellPayload's setValueHistoriesByScope is populated by a
  // shell-only checklist-set-value enrichment that explorePayload never
  // receives), so this must merge field-by-field rather than picking one
  // payload's summary exclusively — an OR here silently drops whichever
  // payload lost, even when it's the only one carrying a given field.
  const summary = { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) };
  const isTimeoutFallbackPayload = setDetailMode && isSetPageTransportFallback(explorePayload);
  const isPrimarySnapshotUnavailable = setDetailMode && isSetPagePrimarySnapshotUnavailable(explorePayload);
  const hasActiveSetPageIdentity = useMemo(
    () => (setDetailMode ? hasRealSetPageIdentity(explorePayload, resolvedSetResourceId) : true),
    [explorePayload, resolvedSetResourceId, setDetailMode]
  );
  const isPrimarySnapshotReady =
    setDetailMode
      ? Boolean(
          explorePayload &&
            !isPrimarySnapshotUnavailable &&
            resolvedSetResourceId &&
            hasActiveSetPageIdentity
        )
      : true;
  const shouldPauseSetDetailDependentFetches = setDetailMode && !isPrimarySnapshotReady;
  const canFetchSlimMarketModules = setDetailMode && Boolean(resolvedSetResourceId);
  const canFetchSetDetailModules = setDetailMode
    ? Boolean(resolvedSetResourceId) &&
      (!explorePayload || isSetPageTransportFallback(explorePayload) || hasActiveSetPageIdentity)
    : true;
  const timeoutSnapshotRankTitle = "Still loading; retrying.";
  const sectionFreshness = explorePayload?.meta?.sectionFreshness || {};
  const decisionSignalFreshnessInfo = formatSectionFreshnessInfo(sectionFreshness.decisionSignalRanks);
  // Same precedence hazard as `summary` above: explorePayload is fetched (and
  // therefore truthy) on the insights tab (and pull-rates, only if it happens
  // to already be seeded from a prior insights visit — see
  // SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD), but it never carries
  // the shell-only checklist setValueHistoriesByScope enrichment — only
  // shellPayload does. `explorePayload || shellPayload` discarded shellPayload
  // entirely whenever explorePayload was present, so the title-card Set Value
  // stayed blank until a tab switch (e.g. Overview) dropped explorePayload
  // back to null. Merge instead, so explorePayload's fields win on conflict
  // but shellPayload-only fields (like the set value history) survive.
  const setShellContract = useMemo(
    () =>
      setDetailMode
        ? adaptSetShell({
            ...(effectiveShellPayload || {}),
            ...(explorePayload || {}),
            summary: { ...(effectiveShellPayload?.summary || {}), ...(explorePayload?.summary || {}) },
          })
        : null,
    [explorePayload, effectiveShellPayload, setDetailMode]
  );
  // Cards/Overview intentionally skip the full explorePayload fetch for performance,
  // so set-detail pages must be able to render from shellPayload alone.
  const hasSetDetailShellPayload = setDetailMode
    ? Boolean(explorePayload || shellPayload || resolvedSetResourceId)
    : Boolean(explorePayload);
  const canRenderPrimaryContent = !pageError && hasSetDetailShellPayload;
  const percentiles = explorePayload?.percentiles || [];
  const distributionBins = explorePayload?.distribution_bins || [];
  const thresholdBins = explorePayload?.threshold_bins || [];
  const simulationDrivers = useMemo(() => selectSimulationDrivers(explorePayload || {}), [explorePayload]);
  const topHits = simulationDrivers.rows;
  const simulationDriversSummaryValue = getSimulationDriversSummaryValue(summary.mean_value, topHits);
  const rankings = explorePayload?.rankings || [];
  const normalizedOpeningDesirability = useMemo(
    () =>
      normalizeOpeningDesirabilityPayload(
        explorePayload?.openingDesirability || explorePayload?.opening_desirability
      ),
    [explorePayload?.openingDesirability, explorePayload?.opening_desirability]
  );
  const initialCardsPayload = initialModuleSnapshots?.cardsPayload || null;
  const initialMarketDashboardPayload = initialModuleSnapshots?.marketDashboardPayload || null;
  const initialOverviewPayload = initialModuleSnapshots?.overviewPayload || null;
  const initialSetPageDataSeed = useMemo(
    () =>
      buildInitialSetPageDataSeed({
        explorePayload,
        cardsPayload: initialCardsPayload,
        marketDashboardPayload: initialMarketDashboardPayload,
        overviewPayload: initialOverviewPayload,
      }),
    [explorePayload, initialCardsPayload, initialMarketDashboardPayload, initialOverviewPayload]
  );
  // Server-seeded /overview snapshot, trusted only when its set identity
  // matches the resolved set (a stale seed from a previous set must never
  // render under the new set's title) and it was built for the same window
  // overviewState fetches (365d).
  const seededOverviewPayload = useMemo(() => {
    const seed = initialSetPageDataSeed.overview;
    if (!seed || !setIdentityMatchesTarget(seed.set, resolvedSetResourceId)) {
      return null;
    }
    if (seed.window && seed.window !== DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW) {
      return null;
    }
    return seed;
  }, [initialSetPageDataSeed, resolvedSetResourceId]);
  const initialCardAppealMarketPriceCorrelation = initialSetPageDataSeed.cardAppealMarketPriceCorrelation;
  const initialCardAppealRows = useMemo(() => {
    const rows = Array.isArray(initialCardAppealMarketPriceCorrelation?.plotRows)
      ? initialCardAppealMarketPriceCorrelation.plotRows
      : Array.isArray(initialCardAppealMarketPriceCorrelation?.plot_rows)
      ? initialCardAppealMarketPriceCorrelation.plot_rows
      : Array.isArray(initialCardAppealMarketPriceCorrelation?.rows)
      ? initialCardAppealMarketPriceCorrelation.rows
      : [];
    return rows;
  }, [initialCardAppealMarketPriceCorrelation]);
  // Pull Rates tab: slim, dedicated fetch (getPokemonSetPullRates) instead of
  // requiring the full /page payload (Phase 4A). Falls back to an
  // already-seeded explorePayload (e.g. left over from a prior Insights
  // visit) only when this state hasn't loaded data for the active set yet —
  // it never triggers a live /page fetch itself.
  const [pullRatesState, setPullRatesState] = useState(() => ({
    status: "idle",
    setId: resolvedSetResourceId,
    pullRateAssumptions: null,
    error: null,
  }));
  const pullRateAssumptions =
    pullRatesState.setId === resolvedSetResourceId && pullRatesState.pullRateAssumptions
      ? pullRatesState.pullRateAssumptions
      : normalizePullRateAssumptions(explorePayload);
  const ripStatistics = explorePayload?.rip_statistics;
  // Cards/Overview never load the full explorePayload, so interpretation
  // (recommendation badge/summary, pillar metas, set intelligence lenses)
  // must fall back to the shell — otherwise it silently disappears whenever
  // explorePayload isn't the active tab's payload.
  const interpretation = explorePayload?.interpretation || effectiveShellPayload?.interpretation || {};
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

  const decisionRanksPresent = Boolean(
    summary?.pack_rank !== null &&
      summary?.pack_rank !== undefined &&
      summary?.profit_rank !== null &&
      summary?.profit_rank !== undefined
  );
  // The Simulation Drivers diagnostics warning is intentionally NOT part of
  // rawWarnings anymore — whether it is real evidence depends on the insights
  // secondary fetch status, which is derived further down. See
  // visibleSetPageWarnings below.
  const rawWarnings = [
    ...(targetsPayload?.meta?.warnings || []),
    ...(explorePayload?.meta?.warnings || []),
    ...(setPageSnapshotRefreshState.status === "error"
      ? [`Set page snapshot retry failed: ${setPageSnapshotRefreshState.error}`]
      : []),
  ];
  const warningSuppressionContext = {
    hasTopHits: topHits.length > 0,
    hasDecisionRanks: decisionRanksPresent,
  };
  const warnings = rawWarnings.filter((warning) => !shouldSuppressSetPageWarning(warning, warningSuppressionContext));
  const suppressedWarnings = rawWarnings.filter((warning) => shouldSuppressSetPageWarning(warning, warningSuppressionContext));

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
  // There is no hero score mode any more. The retired RIP Core option was a
  // second public presentation of Financial RIP V2; RIP Score is now the one
  // canonical headline and it is always Overall RIP V7.
  const [heroMetricView, setHeroMetricView] = useState("overview");
  const [activeValueView, setActiveValueView] = useState("cards");
  const [, setInsightsValueView] = useState("value-structure");
  const effectiveViewMode = setDetailMode ? "expert" : viewMode;
  const isExpertMode = effectiveViewMode === "expert";
  const effectiveValueView = setDetailMode ? "value" : isExpertMode ? activeValueView : "cards";
  const [activeSection, setActiveSection] = useState("pack-score");
  const [heroSetPickerOpen, setHeroSetPickerOpen] = useState(false);
  const [pendingTargetId, setPendingTargetId] = useState(null);
  const displayedTargetId = pendingTargetId || requestedTargetId;
  // TODO: Direct or unknown set page visits may default to Overview later once this surface is mature.
  const [setDetailTab, setSetDetailTab] = useState(() => getSetDetailTabParam(searchParams));
  // Keep this below the setDetailTab state declaration. Computing it earlier
  // reads setDetailTab during its temporal dead zone and crashes set routes.
  const hasActiveInsightsPayload =
    setDetailMode && setDetailTab === "insights"
      ? hasInsightsPayloadData(explorePayload)
      : Boolean(explorePayload);
  const [cardsSubTab, setCardsSubTab] = useState("checklist");
  // Active Cards-tab section ("all-cards" | "market-movers"). Mirrors the URL
  // `section` param so the sidebar highlight, the section tab strip, and the
  // URL can never diverge — the URL-consumption effect below re-derives it on
  // every searchParams change.
  const [cardsSection, setCardsSection] = useState(() =>
    getSetDetailTabParam(searchParams) === "cards" && getSetDetailSectionParam(searchParams) === "market-movers"
      ? "market-movers"
      : "all-cards"
  );
  // Loading-cohesion escape hatch, keyed by set id so a set switch re-engages
  // the hold for the new set: Insights swaps its skeletons for explicit
  // "taking longer than expected" copy past INSIGHTS_PENDING_TIMEOUT_MS.
  // Overview no longer has an equivalent whole-tab hold — each of its
  // sections (Set Value, Performance vs Cost, Market Movers, Top Chase,
  // Market Signals) now gates independently on its own fetch status instead
  // of one shared cohesive skeleton.
  const [insightsPendingTimeoutState, setInsightsPendingTimeoutState] = useState({ setId: null, timedOut: false });
  const [insightsCriticalPendingTimeoutState, setInsightsCriticalPendingTimeoutState] = useState({ setId: null, timedOut: false });
  // Insights critical (priorities 1-3: RIP Score hero, pillar cards,
  // recommendation copy) and secondary (priorities 4-5: charts/distributions,
  // deep diagnostics) fetches, split from the single getPokemonSetInsights
  // call this replaced. Each merges only its own slice into explorePayload
  // (see the two effects below and the adapters above) so the existing
  // Insights render tree — which still just reads summary/interpretation/
  // rip_statistics/percentiles/etc. off explorePayload — needs no changes;
  // only what feeds it, and how each section gates on it, changed.
  const insightsFetchEnabled =
    setDetailMode && setDetailTab === "insights" && canFetchSetDetailModules && Boolean(resolvedSetResourceId);
  const { state: insightsCriticalFetchState, refetch: refetchInsightsCritical } = useSectionFetchState(
    getPokemonSetInsightsCritical,
    { setId: resolvedSetResourceId, enabled: insightsFetchEnabled }
  );
  const { state: insightsSecondaryFetchState, refetch: refetchInsightsSecondary } = useSectionFetchState(
    getPokemonSetInsightsSecondary,
    { setId: resolvedSetResourceId, enabled: insightsFetchEnabled }
  );
  // Phase 9D.1: same keyed-timeout shape as insightsPendingTimeoutState, for
  // the Pull Rates loading shell (see pullRatesPendingTimedOut below).
  const [pullRatesPendingTimeoutState, setPullRatesPendingTimeoutState] = useState({ setId: null, timedOut: false });
  const [selectedTimeframe, setSelectedTimeframe] = useState("7D");
  const [cardSortMode, setCardSortMode] = useState("set-number");
  const [cardSortDirection, setCardSortDirection] = useState(() =>
    getSetDetailSectionParam(searchParams) === "market-movers" ? "gainers" : "asc"
  );
  // Market Movers ranking metric — the third independent Market Movers control
  // alongside direction (cardSortDirection) and timeframe (selectedTimeframe).
  // Changing it must never disturb either of the other two, so it is its own
  // state rather than another mode folded into cardSortDirection.
  const [cardMovementMetric, setCardMovementMetric] = useState(DEFAULT_MARKET_MOVER_METRIC);
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardRarityFilter, setCardRarityFilter] = useState("");
  // Highest requested page for the current cards scope. Pages are appended
  // (infinite scroll) rather than swapped — the sentinel observer advances
  // this, and the scope-reset effect below rewinds it to 1.
  const [cardsPage, setCardsPage] = useState(1);
  // Bumped by the bottom "Retry" button after a failed load-more so the fetch
  // effect re-runs without changing the page/scope (the request-key ref is
  // already cleared on error).
  const [cardsPageRetryNonce, setCardsPageRetryNonce] = useState(0);
  // Cards tab reads from this slim, paginated state (getPokemonSetCardsPage)
  // instead of the checklistState below — checklistState is now reserved for
  // Insights' card validation chart, sourced from the slim
  // getPokemonSetCardsValidation contract (Phase 3C) rather than the full
  // legacy /cards payload.
  // `cards` accumulates every loaded page for `scopeKey` (set + sort + search
  // + movement filter); `page` is the highest page merged into it.
  const [cardsPageState, setCardsPageState] = useState(() => ({
    status: "idle",
    setId: resolvedSetResourceId,
    scopeKey: null,
    page: 1,
    cards: [],
    pagination: null,
    filters: null,
    meta: null,
    error: null,
  }));
  const initialSnapshotCards = initialSetPageDataSeed.cards;
  const initialSetValueLoadedScopes = SET_VALUE_SCOPE_OPTIONS.map((scope) => scope.key).filter(
    (scope) =>
      Array.isArray(initialSetPageDataSeed.setValueHistoriesByScope?.[scope]) &&
      initialSetPageDataSeed.setValueHistoriesByScope[scope].length > 0
  );
  const [checklistState, setChecklistState] = useState(() => ({
    status: initialSnapshotCards.length > 0 ? "success" : "idle",
    setId: resolvedSetResourceId,
    cards: initialSnapshotCards,
    cardAppealMarketPriceCorrelation: initialCardAppealMarketPriceCorrelation,
    error: null,
  }));
  // Card Desirability/Market Validation reads cards + correlation from the
  // slim getPokemonSetCardsValidation contract (Phase 3C) — this is fetched
  // client-side only (not seeded server-side), so there's normally a brief
  // window before it resolves on first load. This contract distinguishes
  // "still loading" from "genuinely no data" so the card doesn't render a
  // permanent-looking n=0 empty state during that gap.
  // activeCardValidationData (card-validation scatter inputs) retired with the
  // Desirability Evidence section it fed.
  const [topMarketCardsWindowKey, setTopMarketCardsWindowKey] = useState(DEFAULT_TOP_MARKET_CARDS_WINDOW);
  const [marketDashboardState, dispatchMarketDashboard] = useReducer(
    marketDashboardReducer,
    {
      status: initialSetPageDataSeed.marketDashboard ? "success" : "idle",
      setId: resolvedSetResourceId,
      payload: initialSetPageDataSeed.marketDashboard,
      sourceWindow: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
    },
    createMarketDashboardState
  );
  // Overview's Set Value Trend/Performance vs Cost source from this slim
  // /overview endpoint instead of the multi-MB /market/dashboard payload once
  // it loads; marketDashboardState above is still the fallback until it does,
  // and Top Chase Cards/Market Movers still read marketDashboardState only.
  // Hydrated from the route-level /overview seed (Overview direct entries)
  // so both sections render on first paint; the fetch effect below then
  // refreshes it quietly (the reducer's "loading" case keeps a same-set
  // payload as success_stale, so no loading panel replaces seeded data).
  const [overviewState, dispatchOverview] = useReducer(
    marketDashboardReducer,
    {
      status: seededOverviewPayload ? "success" : "idle",
      setId: resolvedSetResourceId,
      payload: seededOverviewPayload,
      sourceWindow: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
    },
    createMarketDashboardState
  );
  // Top Chase Cards and Market Movers each fetch their own slim endpoint
  // (/market/top-chase, /market/movers) instead of riding the monolithic
  // /market/dashboard fetch above; marketDashboardState stays as a temporary
  // seeded/cached fallback for both until these load (see
  // activeTopMarketCardsState below).
  const [topChaseState, dispatchTopChase] = useReducer(
    marketDashboardReducer,
    {
      status: "idle",
      setId: resolvedSetResourceId,
      payload: null,
      sourceWindow: DEFAULT_TOP_CHASE_MARKET_WINDOW,
    },
    createMarketDashboardState
  );
  const [marketMoversState, dispatchMarketMovers] = useReducer(
    marketDashboardReducer,
    {
      status: "idle",
      setId: resolvedSetResourceId,
      payload: null,
      sourceWindow: MOVERS_TICKER_WINDOW,
    },
    createMarketDashboardState
  );
  const [setValueHistoryState, setSetValueHistoryState] = useState(() =>
    createSetValueHistoryState({
      status: initialSetValueLoadedScopes.length > 0 ? "success" : "idle",
      setId: resolvedSetResourceId,
      historiesByScope: initialSetPageDataSeed.setValueHistoriesByScope,
      loadedScopes: initialSetValueLoadedScopes,
      availableScopes: SET_VALUE_SCOPE_OPTIONS,
      meta: initialSetPageDataSeed.marketDashboard?.meta || null,
    })
  );
  const [setValueTrendScope, setSetValueTrendScope] = useState(CANONICAL_SET_VALUE_SCOPE);
  const heroSetPickerRef = useRef(null);
  const checklistCacheRef = useRef(new Map());
  const setPrefetchStartedRef = useRef(new Set());
  const pendingNavSelectionRef = useRef(null);
  const pendingNavTimeoutRef = useRef(null);
  const pendingNavStartedAtRef = useRef(0);
  // Tracks the last getPokemonSetCardsPage request key this effect actually
  // issued, so leaving Cards and coming back (or any other re-render that
  // re-triggers the effect without the set/page/sort/filter actually
  // changing) doesn't refetch the exact same page. Cleared on error so a
  // genuine retry isn't permanently blocked.
  const lastCardsPageRequestKeyRef = useRef(null);
  const activeCardsPageRequestKeyRef = useRef(null);
  // Phase 6C: same request-key guard for the remaining per-tab module
  // fetches. Each ref holds the key of the request its effect last issued;
  // re-runs with an identical key (tab revisit, prop-identity churn after a
  // router transition) skip the refetch, a genuinely new set/window fetches
  // fresh, and the key is released both on error and when the effect is
  // cleaned up mid-flight (so an ignored response can't strand its tab in a
  // permanent loading state).
  const lastPullRatesRequestKeyRef = useRef(null);
  const lastCardsValidationRequestKeyRef = useRef(null);
  const lastOverviewRequestKeyRef = useRef(null);
  const lastTopChaseRequestKeyRef = useRef(null);
  const lastMarketMoversRequestKeyRef = useRef(null);
  // Section-local retry for the three slim Overview modules. Each retry bumps
  // only its own nonce, so it re-runs only its own effect — a failed Movers
  // fetch never restarts Overview or Top Chase, and no retry shows the global
  // page loader. Clearing the request-key ref is what lets the re-run get past
  // that effect's duplicate guard; the shared in-flight key in
  // pokemonSetMarketClient.js is already released once the previous attempt
  // settled (including on timeout), so the retry issues a genuinely new
  // request instead of joining the one that failed. Nothing here loops
  // automatically — a retry only happens when the user asks for one.
  const [overviewRetryNonce, setOverviewRetryNonce] = useState(0);
  const [topChaseRetryNonce, setTopChaseRetryNonce] = useState(0);
  const [marketMoversRetryNonce, setMarketMoversRetryNonce] = useState(0);
  const [isMobileSetContextHidden, setIsMobileSetContextHidden] = useState(false);
  const [showReturnToTop, setShowReturnToTop] = useState(false);
  const mobileSetContextRef = useRef(null);
  const isMobileSetContextHiddenRef = useRef(false);
  const mobileSetContextScrollRef = useRef({
    currentNormalizedY: 0,
    maxNormalizedY: 0,
    previousNormalizedY: 0,
    cumulativeDownwardPx: 0,
    cumulativeUpwardPx: 0,
    direction: "none",
    nearTop: true,
    pickerOpen: false,
  });
  const revealMobileSetContext = useCallback(() => {
    setIsMobileSetContextHidden(false);
  }, []);
  const retryOverviewModule = useCallback(() => {
    lastOverviewRequestKeyRef.current = null;
    setOverviewRetryNonce((nonce) => nonce + 1);
  }, []);
  const retryTopChaseModule = useCallback(() => {
    lastTopChaseRequestKeyRef.current = null;
    setTopChaseRetryNonce((nonce) => nonce + 1);
  }, []);
  const retryMarketMoversModule = useCallback(() => {
    lastMarketMoversRequestKeyRef.current = null;
    setMarketMoversRetryNonce((nonce) => nonce + 1);
  }, []);
  // Every GRAPH_SECTION_KEYS value is now a valid Simulation Results sub-view
  // (Outcome Distribution, Opening P vs C = historical-trend, Simulation
  // Drivers, Value Structure, Pack Paths, Metrics), so the insights card
  // renders whatever graphMode is active. Entering Insights from Overview's
  // Performance vs Cost (historical-trend) still resets to Outcome Distribution
  // via the tab-change / URL-sync handlers below.
  const activeInsightsGraphMode = graphMode;
  const cardsNeededForActiveTab =
    setDetailMode && (setDetailTab === "cards" || setDetailTab === "insights");
  const cardsSeededForActiveSet =
    !cardsNeededForActiveTab ||
    ((checklistState.setId === resolvedSetResourceId || !checklistState.setId) &&
      (checklistState.cards.length > 0 || initialSetPageDataSeed.cards.length > 0));
  const seededSetValueReady = hasAnySetValueHistory(initialSetPageDataSeed.setValueHistoriesByScope);
  const stateSetValueReady =
    setValueHistoryState.setId === resolvedSetResourceId &&
    hasAnySetValueHistory(setValueHistoryState.historiesByScope);
  const marketDashboardReady =
    isStateForResolvedSet(marketDashboardState.setId, resolvedSetResourceId) &&
    (marketDashboardState.status === "success" || marketDashboardState.status === "success_stale") &&
    Boolean(marketDashboardState.payload);
  const marketOrSetValueSeededForActiveTab =
    setDetailTab !== "overview" || seededSetValueReady || stateSetValueReady || marketDashboardReady;
  const activeSetModulesStable =
    isPrimarySnapshotReady &&
    !isSetPageTransportFallback(explorePayload) &&
    cardsSeededForActiveSet &&
    marketOrSetValueSeededForActiveTab;

  useEffect(() => {
    setExplorePayload((previous) => {
      if (initialExplorePayload) {
        return initialExplorePayload;
      }
      // Same-set navigation (tab hops always go through router.push) replaces
      // props with a null payload seed — Cards/Overview routes never seed the
      // full payload. Blanking an already-loaded same-set payload here
      // flashed Insights back to skeletons mid-view, forced a redundant
      // /insights refetch, and stranded the tab on skeletons whenever that
      // refetch was interrupted. Keep the payload when it verifiably belongs
      // to the requested set; a genuine set switch (identity mismatch) still
      // resets to null.
      const previousIdentity = getSetSnapshotIdentity(previous);
      if (
        previous &&
        !isSetPageTransportFallback(previous) &&
        previousIdentity &&
        setIdentityMatchesTarget(previousIdentity, requestedTargetId)
      ) {
        return previous;
      }
      // A payload assembled purely from the split Insights fetches can lack a
      // usable set identity (the secondary slice carries no `set` field), so
      // the identity check above can't vouch for it — blanking here used to
      // clobber freshly-merged insights data on same-set navigation commits,
      // and the merge effects (keyed to fetch state that hadn't changed)
      // never re-ran, stranding Insights on skeletons until the timeout copy
      // appeared even though both fetches had returned 200. Rebuild from the
      // already-successful fetches instead; the fetch-state setId guard keeps
      // a genuinely stale set's data from surviving.
      const criticalSlice =
        insightsCriticalFetchState.status === "success" &&
        isSetStateForActiveSet(insightsCriticalFetchState.setId, { requestedTargetId, selectedTarget, resolvedSetResourceId })
          ? adaptPokemonSetInsightsCriticalPayloadToExplorePayload(insightsCriticalFetchState.data)
          : null;
      const secondarySlice =
        insightsSecondaryFetchState.status === "success" &&
        isSetStateForActiveSet(insightsSecondaryFetchState.setId, { requestedTargetId, selectedTarget, resolvedSetResourceId })
          ? adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(insightsSecondaryFetchState.data)
          : null;
      if (criticalSlice || secondarySlice) {
        debugSetPagePerf("insights.remerged_after_navigation_reset", {
          setId: resolvedSetResourceId,
          hasCriticalSlice: Boolean(criticalSlice),
          hasSecondarySlice: Boolean(secondarySlice),
        });
        return { ...(criticalSlice || {}), ...(secondarySlice || {}) };
      }
      return null;
    });
    setSetPageSnapshotRefreshState({ status: "idle", setId: null, error: null });
    timeoutSnapshotRefreshKeyRef.current = null;
    // Navigation just replaced the payload seed (often with null — Cards/
    // Overview routes never seed the full payload). The insights fetch key
    // stays claimed after a successful fetch, so without releasing it here a
    // same-set revisit to Insights whose payload this reset just cleared
    // would skip its refetch forever and strand the tab without data (seen
    // as Insights sections never loading after a set switch when the RSC
    // navigation response lands after the insights fetch resolved).
    explorePagePayloadFetchKeyRef.current = null;
    const routeSeed = buildInitialSetPageDataSeed({
      explorePayload: initialExplorePayload || {},
      cardsPayload: initialCardsPayload,
      marketDashboardPayload: initialMarketDashboardPayload,
    });
    const seededCards = routeSeed.cards;
    setChecklistState((previous) => {
      const seededCorrelation = resolvePreferredCardAppealCorrelation({
        explorePayload: initialExplorePayload || {},
        cardsPayload:
          initialCardsPayload ||
          initialExplorePayload?.cardPayload ||
          initialExplorePayload?.card_payload ||
          initialExplorePayload?.cardsPayload ||
          initialExplorePayload?.cards_payload ||
          initialExplorePayload?.setCards ||
          initialExplorePayload?.set_cards ||
          null,
        previous: previous?.cardAppealMarketPriceCorrelation,
      }) || routeSeed.cardAppealMarketPriceCorrelation;
      if (seededCards.length === 0) {
        // A prop update that carries no cards (e.g. the active tab's route
        // seed no longer includes cardsPayload) must not blank out cards
        // that are already loaded for the same set — only reset when the
        // previously-held cards belong to a different/stale set.
        const previousCardsSameSet =
          previous?.cards?.length > 0 &&
          isSetStateForActiveSet(previous.setId, { requestedTargetId, selectedTarget, resolvedSetResourceId })
            ? previous.cards
            : [];
        if (previousCardsSameSet.length > 0) {
          return {
            ...previous,
            cardAppealMarketPriceCorrelation: seededCorrelation,
          };
        }
        return {
          status: "idle",
          setId: null,
          cards: [],
          cardAppealMarketPriceCorrelation: seededCorrelation,
          error: null,
        };
      }
      return {
        status: "success",
        setId: resolvedSetResourceId,
        cards: seededCards,
        cardAppealMarketPriceCorrelation: seededCorrelation,
        error: null,
      };
    });
  }, [
    initialExplorePayload,
    initialCardsPayload,
    initialMarketDashboardPayload,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
  ]);

  useEffect(() => {
    // Only retry when this is a true transport fallback/timeout for a stable,
    // resolved active set on a tab that actually needs the full /page
    // payload — never just because the tab or set changed, or because
    // explorePayload is intentionally null on Cards/Overview.
    const activeTabNeedsFullPagePayload = SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD.has(setDetailTab);
    if (
      !setDetailMode ||
      !resolvedSetResourceId ||
      !activeTabNeedsFullPagePayload ||
      !isSetPageTransportFallback(explorePayload)
    ) {
      return undefined;
    }
    const fallbackIdentity = getSetSnapshotIdentity(explorePayload);
    if (fallbackIdentity && !setIdentityMatchesTarget(fallbackIdentity, resolvedSetResourceId)) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    const refreshKey = `${requestedTargetId || ""}:${setId}`;
    if (timeoutSnapshotRefreshKeyRef.current === refreshKey) {
      return undefined;
    }
    timeoutSnapshotRefreshKeyRef.current = refreshKey;

    const controller = new AbortController();
    let isCancelled = false;
    setSetPageSnapshotRefreshState({ status: "loading", setId, error: null });
    debugSetPagePerf("set_page.timeout_retry_start", {
      routeSetId: requestedTargetId,
      resolvedSetId: setId,
    });

    fetchPokemonSetPageSnapshot(setId, { signal: controller.signal })
      .then((payload) => {
        if (isCancelled) {
          return;
        }
        const isStillActiveSet = isSetStateForActiveSet(setId, {
          requestedTargetId,
          selectedTarget,
          resolvedSetResourceId: activeSetResourceIdRef.current,
        });
        if (!isStillActiveSet) {
          debugSetPagePerf("set_page.timeout_retry_stale", {
            routeSetId: requestedTargetId,
            resolvedSetId: setId,
            activeSetResourceId: activeSetResourceIdRef.current,
          });
          return;
        }
        setExplorePayload(payload || null);
        setSetPageSnapshotRefreshState({ status: "success", setId, error: null });
        debugSetPagePerf("set_page.timeout_retry_ready", {
          routeSetId: requestedTargetId,
          resolvedSetId: setId,
          topHits: Array.isArray(payload?.top_hits) ? payload.top_hits.length : 0,
        });
      })
      .catch((error) => {
        if (isCancelled || error?.name === "AbortError") {
          return;
        }
        setSetPageSnapshotRefreshState({
          status: "error",
          setId,
          error: error?.message || "Unable to retry set page snapshot.",
        });
        debugSetPagePerf("set_page.timeout_retry_error", {
          routeSetId: requestedTargetId,
          resolvedSetId: setId,
          status: error?.status,
          error: error?.message || String(error),
        });
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [explorePayload, requestedTargetId, selectedTarget, resolvedSetResourceId, setDetailMode, setDetailTab]);

  // Legacy full-page lazy-fetch effect. SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD
  // is now always empty (Insights moved off it in Phase 4B, Pull Rates in
  // Phase 4A), so `.has(setDetailTab)` below is always false and this effect
  // is permanently inert. Left in place (rather than deleted) alongside
  // fetchPokemonSetPageSnapshot/setPageSnapshotRefreshState as a smaller,
  // lower-risk diff — a future cleanup phase can remove them outright.
  useEffect(() => {
    if (!setDetailMode || explorePayload) {
      return undefined;
    }
    if (!SET_DETAIL_TABS_REQUIRING_FULL_PAGE_PAYLOAD.has(setDetailTab)) {
      return undefined;
    }
    const setId = resolvedSetResourceId || requestedTargetId;
    if (!setId) {
      return undefined;
    }

    const fetchKey = `${requestedTargetId || ""}:${setId}`;
    if (explorePagePayloadFetchKeyRef.current === fetchKey) {
      return undefined;
    }
    explorePagePayloadFetchKeyRef.current = fetchKey;

    const controller = new AbortController();
    let isCancelled = false;
    fetchPokemonSetPageSnapshot(setId, { signal: controller.signal })
      .then((payload) => {
        if (!isCancelled) {
          setExplorePayload(payload || null);
        }
      })
      .catch((error) => {
        if (isCancelled || error?.name === "AbortError") {
          return;
        }
        explorePagePayloadFetchKeyRef.current = null;
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [setDetailMode, setDetailTab, explorePayload, resolvedSetResourceId, requestedTargetId]);

  // Insights tab fetch effects (progressive-rendering split of the former
  // Phase 4B single getPokemonSetInsights call): insightsCriticalFetchState/
  // insightsSecondaryFetchState (declared above via useSectionFetchState)
  // fetch in parallel; each merge effect below writes only its own slice
  // into explorePayload as soon as it settles, via a functional update so
  // the two writes can land in either order without clobbering each other.
  // hasInsightsPayloadData(explorePayload) (used elsewhere) already checks
  // exactly the secondary-owned fields (percentiles/topHits/rankings/
  // historyTrend/rip_statistics/openingDesirability/desirabilityValidation),
  // so it continues to work unchanged as a "secondary data has arrived"
  // signal without needing to know about the split.
  useEffect(() => {
    if (insightsCriticalFetchState.status !== "success" || insightsCriticalFetchState.setId !== resolvedSetResourceId) {
      return;
    }
    setExplorePayload((previous) => ({
      ...(previous || {}),
      ...adaptPokemonSetInsightsCriticalPayloadToExplorePayload(insightsCriticalFetchState.data),
    }));
  }, [insightsCriticalFetchState.status, insightsCriticalFetchState.setId, insightsCriticalFetchState.data, resolvedSetResourceId]);

  useEffect(() => {
    if (insightsSecondaryFetchState.status !== "success" || insightsSecondaryFetchState.setId !== resolvedSetResourceId) {
      return;
    }
    const secondarySlice = adaptPokemonSetInsightsSecondaryPayloadToExplorePayload(insightsSecondaryFetchState.data);
    debugSetPagePerf("insights.secondary_merged", {
      setId: insightsSecondaryFetchState.setId,
      topHitsCount: Array.isArray(secondarySlice.top_hits) ? secondarySlice.top_hits.length : 0,
      percentilesCount: Array.isArray(secondarySlice.percentiles) ? secondarySlice.percentiles.length : 0,
      distributionBinsCount: Array.isArray(secondarySlice.distribution_bins) ? secondarySlice.distribution_bins.length : 0,
      rankingsCount: Array.isArray(secondarySlice.rankings) ? secondarySlice.rankings.length : 0,
      historyTrendCount: Array.isArray(secondarySlice.history_trend) ? secondarySlice.history_trend.length : 0,
      payloadSource: "insights_secondary_fetch",
    });
    setExplorePayload((previous) => ({
      ...(previous || {}),
      ...secondarySlice,
    }));
  }, [insightsSecondaryFetchState.status, insightsSecondaryFetchState.setId, insightsSecondaryFetchState.data, resolvedSetResourceId]);

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

  const warmSetDetailResources = useCallback((setId, { includeAdjacent = false, reason = "prefetch" } = {}) => {
    if (!canFetchSetDetailModules) {
      debugSetPagePerf("set.prefetch_deferred", {
        setId,
        reason,
        deferredReason: !resolvedSetResourceId ? "set_id_unresolved" : "set_identity_mismatch",
      });
      return;
    }

    // Route prefetch only — no cards/market data fetches here. Eagerly
    // fetching module data for a set the user is merely hovering/adjacent to
    // (or has just clicked toward, before navigation even completes) fanned
    // out /cards + /market/dashboard (+ downstream value-history) requests
    // across many set ids on every switch. Each tab's own effect below fetches
    // only the active tab's required module once that tab actually renders.
    const startPrefetch = (targetSetId, prefetchReason) => {
      const resolvedSetId = String(targetSetId || "").trim();
      if (!resolvedSetId || setPrefetchStartedRef.current.has(resolvedSetId)) {
        return;
      }
      setPrefetchStartedRef.current.add(resolvedSetId);
      const targetHref = targetHrefById?.[resolvedSetId] || null;
      if (targetHref) {
        router.prefetch(targetHref);
        debugSetPagePerf("set.route_prefetch", { setId: resolvedSetId, reason: prefetchReason });
      }
    };

    const resolvedSetId = String(setId || "").trim();
    startPrefetch(resolvedSetId, reason);
    if (!includeAdjacent || !activeSetModulesStable || shouldPauseSetDetailDependentFetches || !Array.isArray(targets) || targets.length === 0) {
      return;
    }
    const currentIndex = targets.findIndex((target) => String(target?.id || "") === resolvedSetId);
    if (currentIndex < 0) {
      return;
    }
    const adjacentTargets = [];
    for (let offset = 1; offset <= SET_PREFETCH_ADJACENT_LIMIT; offset += 1) {
      if (targets[currentIndex - offset]?.id) {
        adjacentTargets.push(targets[currentIndex - offset].id);
      }
      if (targets[currentIndex + offset]?.id) {
        adjacentTargets.push(targets[currentIndex + offset].id);
      }
    }
    adjacentTargets.forEach((adjacentSetId) => {
      startPrefetch(adjacentSetId, "adjacent");
    });
  }, [activeSetModulesStable, canFetchSetDetailModules, shouldPauseSetDetailDependentFetches, targets, router, targetHrefById]);

  const outcomeDistributionInfo = (
    <div className="space-y-1.5 text-left">
      <p className="font-semibold text-[var(--text-primary)]">Outcome Distribution</p>
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
        <li className="flex gap-2"><span className="flex-none">•</span><span>Higher contribution means that rarity bucket drives more of the pack&apos;s simulated Expected Value.</span></li>
        <li className="flex gap-2"><span className="flex-none">•</span><span>Use this to see whether value is spread across many rarities or concentrated in a narrow chase tier.</span></li>
      </ul>
    </div>
  );

  const packBreakdownEvidenceRows = useMemo(() => {
    // Prefer chips derived directly from the raw pack-path counts so the
    // Dominant/Special path shares share the donut's adaptive formatter (a
    // nonzero rare path never renders "0.0%"); fall back to the interpretation
    // engine's evidence only when no counts are available.
    const fromCounts = getPackPathEvidenceRowsFromCounts(ripStatistics?.pack_paths);
    return fromCounts.length > 0 ? fromCounts : getPackBreakdownEvidence(packBreakdownMeta);
  }, [ripStatistics?.pack_paths, packBreakdownMeta]);

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
  const showSetPageDiagnostics =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_SHOW_SET_PAGE_DIAGNOSTICS !== "false";

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

    // Measure whatever is actually pinned. At 1200px+ that is the whole set
    // context shell (hero + tabs travel together). Below 1200px the hero
    // scrolls away and only the tab bar stays, so measuring the shell would
    // over-scroll every anchor by the full hero height.
    const isDesktopComposition =
      typeof window.matchMedia === "function" && window.matchMedia("(min-width: 1200px)").matches;
    const pinnedElement = setDetailMode
      ? document.querySelector(isDesktopComposition ? "[data-set-context-shell]" : "[data-set-detail-sticky-tabs]")
      : null;
    const pinnedHeight = pinnedElement instanceof HTMLElement ? pinnedElement.offsetHeight : 0;

    return headerOffset + subNavHeight + pinnedHeight + 8;
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
      cardSort: section === "market-movers" ? "7d-movers" : undefined,
      movementFilter: section === "market-movers" ? "all" : undefined,
    });
    startTabTransition(() => {
      router.push(nextHref, { scroll: false });
    });
  };

  const handleSetDetailTabChange = (nextTab) => {
    revealMobileSetContext();
    const normalizedTab = normalizeSetDetailTab(nextTab);
    if (normalizedTab === "cards") {
      markSetPagePerformance("cards_tab_first_interactive", { setId: resolvedSetResourceId });
    }
    setSetDetailTab(normalizedTab);
    if (normalizedTab === "insights" && graphMode === "historical-trend") {
      setGraphMode("outcome-distribution");
      setActiveSection("outcome-distribution");
    }
    pushSetDetailRouteState({ tab: normalizedTab });
  };

  const handleSetDetailNavSelect = ({ tab, section, cardsSubTab: nextCardsSubTab, graphMode: nextGraphMode, targetId } = {}) => {
    revealMobileSetContext();
    const nextTab = normalizeSetDetailTab(tab || setDetailTab);

    if (nextTab) {
      if (nextTab === "cards") {
        markSetPagePerformance("cards_tab_first_interactive", { setId: resolvedSetResourceId, source: "nav" });
      }
      setSetDetailTab(nextTab);
    }

    if (nextCardsSubTab) {
      setCardsSubTab(nextCardsSubTab);
    }
    if (section === "market-movers") {
      setCardsSection("market-movers");
      setCardSortDirection("gainers");
    } else if (section === "all-cards") {
      // Entering All Cards restores the default checklist view so the
      // rendered controls always match the section the sidebar highlights.
      setCardsSection("all-cards");
      setCardSortMode("set-number");
      setCardSortDirection("asc");
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

  const handleViewSetValueTrend = () => {
    handleSetDetailNavSelect({
      tab: "overview",
      section: "set-value-trend",
      targetId: "set-detail-set-value-trend",
    });
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
    if (sectionTarget?.cardsSubTab) {
      setCardsSubTab(sectionTarget.cardsSubTab);
    }
    if (nextSection === "market-movers") {
      setCardSortDirection("gainers");
    } else if (resolvedTab === "cards") {
      setCardSortMode("set-number");
      setCardSortDirection("asc");
    }
    if (resolvedTab === "cards") {
      // The URL is the source of truth for the active cards section — this
      // keeps the sidebar highlight, section tab strip, and `section` query
      // param from ever diverging (e.g. ?section=market-movers rendering
      // with "All Cards" highlighted).
      setCardsSection(nextSection === "market-movers" ? "market-movers" : "all-cards");
    }

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
    isMobileSetContextHiddenRef.current = isMobileSetContextHidden;
  }, [isMobileSetContextHidden]);

  useEffect(() => {
    mobileSetContextScrollRef.current.pickerOpen = heroSetPickerOpen;
    if (heroSetPickerOpen) {
      setIsMobileSetContextHidden(false);
    }
  }, [heroSetPickerOpen]);

  useEffect(() => {
    if (!setDetailMode || typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(max-width: 1199.98px)");
    const scrollState = mobileSetContextScrollRef.current;
    const clampNormalizedScrollY = (rawY) => {
      const doc = document.documentElement;
      const maxY = Math.max(0, (doc?.scrollHeight || 0) - window.innerHeight);
      const normalizedY = Math.min(maxY, Math.max(0, Number.isFinite(rawY) ? rawY : 0));
      return { normalizedY, maxY };
    };

    const resetTransientScrollState = () => {
      const { normalizedY, maxY } = clampNormalizedScrollY(window.scrollY || 0);
      scrollState.currentNormalizedY = normalizedY;
      scrollState.maxNormalizedY = maxY;
      scrollState.previousNormalizedY = normalizedY;
      scrollState.cumulativeDownwardPx = 0;
      scrollState.cumulativeUpwardPx = 0;
      scrollState.direction = normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX ? "none" : "down";
      scrollState.nearTop = normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX;
      scrollState.pickerOpen = heroSetPickerOpen;
      setShowReturnToTop((previous) => {
        const shouldShow = normalizedY > MOBILE_RETURN_TO_TOP_THRESHOLD_PX;
        return previous === shouldShow ? previous : shouldShow;
      });
    };

    resetTransientScrollState();

    let frameId = null;
    let lastTouchY = null;

    const revealIfNeeded = () => {
      if (!mediaQuery.matches) {
        resetTransientScrollState();
        setIsMobileSetContextHidden(false);
      }
    };

    const hideMenuImmediately = () => {
      scrollState.cumulativeUpwardPx = 0;
      scrollState.direction = "down";
      setIsMobileSetContextHidden((previous) => (previous ? previous : true));
    };

    const updateFromScroll = () => {
      if (frameId !== null) {
        return;
      }

      frameId = window.requestAnimationFrame(() => {
        frameId = null;

        if (!mediaQuery.matches) {
          resetTransientScrollState();
          setIsMobileSetContextHidden(false);
          return;
        }

        const { normalizedY: nextY, maxY } = clampNormalizedScrollY(window.scrollY || 0);
        const previousY = scrollState.previousNormalizedY;
        const delta = nextY - previousY;
        const nearTop = nextY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX;

        scrollState.currentNormalizedY = nextY;
        scrollState.maxNormalizedY = maxY;
        scrollState.previousNormalizedY = nextY;
        scrollState.nearTop = nearTop;
        setShowReturnToTop((previous) => {
          const shouldShow = nextY > MOBILE_RETURN_TO_TOP_THRESHOLD_PX;
          return previous === shouldShow ? previous : shouldShow;
        });

        if (nearTop || scrollState.pickerOpen) {
          scrollState.direction = nearTop ? "none" : "up";
          scrollState.cumulativeDownwardPx = 0;
          scrollState.cumulativeUpwardPx = 0;
          setIsMobileSetContextHidden(false);
          return;
        }

        if (Math.abs(delta) <= MOBILE_SET_MENU_SCROLL_NOISE_PX) {
          return;
        }

        if (delta > 0) {
          scrollState.direction = "down";
          scrollState.cumulativeUpwardPx = 0;
          scrollState.cumulativeDownwardPx += delta;
          if (scrollState.cumulativeDownwardPx >= MOBILE_SET_MENU_HIDE_DISTANCE_PX) {
            scrollState.cumulativeDownwardPx = 0;
            hideMenuImmediately();
          }
          return;
        }

        scrollState.direction = "up";
        scrollState.cumulativeDownwardPx = 0;
        if (!isMobileSetContextHiddenRef.current) {
          scrollState.cumulativeUpwardPx = 0;
          return;
        }

        scrollState.cumulativeUpwardPx += Math.abs(delta);
        if (scrollState.cumulativeUpwardPx >= MOBILE_SET_MENU_REVEAL_DISTANCE_PX) {
          scrollState.cumulativeUpwardPx = 0;
          setIsMobileSetContextHidden((previous) => (previous ? false : previous));
        }
      });
    };

    const shouldUseBottomEdgeIntent = () => {
      if (!mediaQuery.matches || scrollState.pickerOpen) {
        return false;
      }
      if (isMobileSetContextHiddenRef.current) {
        return false;
      }
      const maxY = scrollState.maxNormalizedY;
      const currentY = scrollState.currentNormalizedY;
      return maxY - currentY <= MOBILE_SET_MENU_BOTTOM_EDGE_PX;
    };

    const handleWheel = (event) => {
      if (event.deltaY <= MOBILE_SET_MENU_GESTURE_NOISE_PX || !shouldUseBottomEdgeIntent()) {
        return;
      }
      hideMenuImmediately();
    };

    const handleTouchStart = (event) => {
      const touch = event.touches?.[0];
      lastTouchY = touch ? touch.clientY : null;
    };

    const handleTouchMove = (event) => {
      const touch = event.touches?.[0];
      if (!touch) {
        return;
      }
      if (lastTouchY === null) {
        lastTouchY = touch.clientY;
        return;
      }

      const fingerDeltaUp = lastTouchY - touch.clientY;
      lastTouchY = touch.clientY;
      if (fingerDeltaUp <= MOBILE_SET_MENU_GESTURE_NOISE_PX || !shouldUseBottomEdgeIntent()) {
        return;
      }
      hideMenuImmediately();
    };

    const handleTouchEnd = () => {
      lastTouchY = null;
    };

    revealIfNeeded();
    window.addEventListener("scroll", updateFromScroll, { passive: true });
    window.addEventListener("resize", revealIfNeeded);
    window.addEventListener("wheel", handleWheel, { passive: true });
    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("touchcancel", handleTouchEnd, { passive: true });

    const handleMediaChange = () => {
      revealIfNeeded();
      updateFromScroll();
    };

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleMediaChange);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(handleMediaChange);
    }

    return () => {
      window.removeEventListener("scroll", updateFromScroll);
      window.removeEventListener("resize", revealIfNeeded);
      window.removeEventListener("wheel", handleWheel);
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("touchcancel", handleTouchEnd);
      if (typeof mediaQuery.removeEventListener === "function") {
        mediaQuery.removeEventListener("change", handleMediaChange);
      } else if (typeof mediaQuery.removeListener === "function") {
        mediaQuery.removeListener(handleMediaChange);
      }
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [setDetailMode]);

  useEffect(() => {
    if (!setDetailMode || typeof window === "undefined") {
      return;
    }
    const scrollState = mobileSetContextScrollRef.current;
    const doc = document.documentElement;
    const maxY = Math.max(0, (doc?.scrollHeight || 0) - window.innerHeight);
    const normalizedY = Math.min(maxY, Math.max(0, window.scrollY || 0));
    scrollState.currentNormalizedY = normalizedY;
    scrollState.maxNormalizedY = maxY;
    scrollState.previousNormalizedY = normalizedY;
    scrollState.cumulativeDownwardPx = 0;
    scrollState.cumulativeUpwardPx = 0;
    scrollState.direction = normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX ? "none" : "down";
    scrollState.nearTop = normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX;
  }, [setDetailMode, requestedTargetId]);

  useEffect(() => {
    if (!setDetailMode) {
      return;
    }
    setShowReturnToTop(false);
    setIsMobileSetContextHidden(false);
  }, [setDetailMode, pathname, searchParams, requestedTargetId, setDetailTab]);

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

  // THE canonical RIP resolution for this page. Resolved ONCE, here, and shared
  // by the sticky hero, the Overview RIP Summary, the Insights headline,
  // Financial RIP and Collector Appeal. Every one of those surfaces reads this
  // object, so they cannot disagree about which source answered.
  //
  // WHY ONE CALL AND NOT THREE `||` CHAINS
  // --------------------------------------
  // This replaced three independent `explorePayload?.x || selectedTarget?.x ||
  // summary?.x` memos, one per canonical object. Those were unsafe for two
  // reasons. First, a normalized-but-empty `{}` is TRUTHY, so an empty
  // `explorePayload.publicRipContractV7` won the chain and blocked a populated
  // contract on `selectedTarget` — the page then rendered "unavailable" while
  // holding perfectly good canonical data. Second, three chains can settle on
  // three different sources, so the hero could show one snapshot's RIP Score
  // while Financial RIP showed another's components.
  //
  // `resolveCanonicalRipV7` fixes both: it tests for CONTENT rather than
  // truthiness, and it returns Overall RIP, Financial RIP and Collector Appeal
  // as one bundle from one source. It never defaults to a legacy object — an
  // absent V7 renders as an explicit unavailable state, never as V6, V5,
  // Overall RIP v4, Collector Appeal V2 or legacy CA7 wearing the canonical
  // label. The legacy `rip` / `ripCore` / V5 / V6 objects are still served in
  // the payload for audit consumers and are read by no public surface here.
  const canonicalRip = useMemo(
    () => resolveCanonicalRipV7(explorePayload, selectedTarget, summary),
    [explorePayload, selectedTarget, summary]
  );

  const heroScoreSelection = selectRipHeroScoreMode({ canonical: canonicalRip });
  // The PUBLIC hero number is the cohort-relative 0-100 Overall RIP V7. The raw
  // 90/10 formula output is the model score, shown small beneath as a
  // transparent diagnostic — never competing with the public score.
  const topScoreRaw = heroScoreSelection.score;
  const displayedTopScore = formatRawScore(topScoreRaw);
  const heroModelScoreRaw = heroScoreSelection.absoluteScore;
  const displayedHeroModelScore =
    heroModelScoreRaw === null || heroModelScoreRaw === undefined
      ? null
      : formatRawScore(heroModelScoreRaw);

  // Canonical backend RIP contract: the set-page snapshot payload carries it
  // in set-detail mode, the rankings target carries it on Explore. The pillar
  // scores below are the ACTUAL component scores from rip.components — the
  // legacy relative_*_score min-max presentations are deliberately never read.
  // LEGACY, and read for exactly one surface: the Explore expert-view
  // ScorePillarCard diagnostics below, which are the Profit / Safety /
  // Stability lenses in their own right. `rip` is Overall RIP **v4** and
  // `rip.financialRip` is Financial RIP **V2**. Neither may be read by a
  // surface that says "RIP Score" or "Financial RIP" - those read the V7
  // objects below.
  const legacyExpertRip = useMemo(
    () => explorePayload?.rip || selectedTarget?.rip || summary?.rip || {},
    [explorePayload?.rip, selectedTarget?.rip, summary?.rip]
  );
  const legacyExpertRipComponents =
    legacyExpertRip?.financialRip?.components || legacyExpertRip?.components || {};
  const displayedProfitScore = toNumber(legacyExpertRipComponents.profit?.score);
  const displayedSafetyScore = toNumber(legacyExpertRipComponents.safety?.score);
  const displayedStabilityScore = toNumber(legacyExpertRipComponents.stability?.score);
  const canonicalUniversalSetDesirability = useMemo(
    () =>
      explorePayload?.universalSetDesirability ||
      selectedTarget?.universalSetDesirability ||
      summary?.universalSetDesirability ||
      null,
    [
      explorePayload?.universalSetDesirability,
      selectedTarget?.universalSetDesirability,
      summary?.universalSetDesirability,
    ]
  );
  // `canonicalOpeningExperience` was resolved here for the removed public
  // Collector Profile, the only surface that read it. Collector Appeal is now
  // presented solely from the canonical V7 bundle, so the CA7 service payload
  // has no frontend consumer on this page and is not resolved.
  const desirabilitySummary = getDesirabilitySummary(summary);
  const topDesirabilityCards = getTopCollectorAppealDrivers(
    explorePayload,
    summary,
    normalizedOpeningDesirability
  );
  const desirabilityOverviewMetrics = getDesirabilityOverviewMetrics(normalizedOpeningDesirability);
  const heroLogoUrl =
    selectedTarget?.logo_image_url || selectedTarget?.hero_image_url || selectedTarget?.symbol_image_url || null;
  const ambientSetArtworkUrl =
    selectedTarget?.hero_image_url || selectedTarget?.logo_image_url || selectedTarget?.symbol_image_url || null;

  // `packScoreMeta` (the interpretation engine's label and summary) is NOT read
  // here any more. It produced the hero's "Elite but swingy"-style verdict pill
  // and the Opening Outlook paragraph, both of which described the retired
  // Profit/Safety/Stability model. The backend still emits them for
  // compatibility; no current public surface renders them.
  const setContextRipPresentation = getRipTierPresentation({
    rankTier: heroScoreSelection.tier,
  });
  // The selector owns the name of the score it resolved, so the title card can
  // never name a metric it is not showing.
  const setContextRipLabel = heroScoreSelection.label;
  const setContextRipTier = String(heroScoreSelection.tier || "").trim().replace(/\s+tier$/i, "");
  const setContextRipRank = toNumber(heroScoreSelection.rank);
  const setContextRipCohort = toNumber(heroScoreSelection.cohortSize);

  // --- Mobile / tablet hero ------------------------------------------------
  // Identity only below 1200px. Set Value and RIP were duplicated readings —
  // both already have their own Overview sections — so the mobile header no
  // longer consumes setHeaderSummary at all. That also removes the temporal
  // dead zone this memo used to hit by reading setHeaderSummary before it was
  // declared.
  const isDesktopHeroComposition = useMediaQuery("(min-width: 1200px)", true);
  const mobileHeroModel = useMemo(
    () =>
      selectMobileHeroModel({
        setName: selectedName,
        era: selectedTarget?.era ?? null,
        logoUrl: heroLogoUrl,
      }),
    [heroLogoUrl, selectedName, selectedTarget?.era]
  );

  // Correction 2: two lightweight hero compositions are mounted and one is
  // hidden by CSS, so exactly one of them owns the set picker at a time. One
  // width reading decides; the open state itself stays shared, and crossing the
  // boundary closes an open menu rather than handing a half-open listbox to the
  // other composition.
  useEffect(() => {
    setHeroSetPickerOpen(false);
  }, [isDesktopHeroComposition]);

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
  const setValueSummaryMetric = getFirstNumericMetric(summary, [
    "currentChecklistSetValue",
    "current_checklist_set_value",
    "set_value_for_validation",
    "checklistSetValue",
    "checklist_set_value",
    "simulated_set_value",
    "set_value",
    "total_set_value",
    "total_card_value",
    "set_market_value",
    "collection_value",
    "total_value",
  ]);
  const seededMarketDashboardPayload = useMemo(() => {
    if (initialSetPageDataSeed.marketDashboard) {
      return initialSetPageDataSeed.marketDashboard;
    }
    return null;
  }, [initialSetPageDataSeed]);
  const activeMarketDashboardState =
    isStateForResolvedSet(marketDashboardState.setId, resolvedSetResourceId) &&
    (marketDashboardState.payload || !seededMarketDashboardPayload)
      ? marketDashboardState
      : seededMarketDashboardPayload
      ? createMarketDashboardState({
          status: "success",
          setId: resolvedSetResourceId,
          payload: seededMarketDashboardPayload,
          sourceWindow: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
        })
      : createMarketDashboardState({ setId: resolvedSetResourceId });
  const activeMarketDashboardDerivedState = useMemo(
    () => buildMarketDashboardStateFromPayload(activeMarketDashboardState.payload || seededMarketDashboardPayload),
    [activeMarketDashboardState.payload, seededMarketDashboardPayload]
  );
  // overviewState only resets to this set's "loading"/empty shape once its
  // fetch effect fires post-paint (setDetailTab === "overview"), so a set
  // switch can otherwise render the previous set's overview payload for one
  // commit under the new set's title — guard the same way
  // activeMarketDashboardState/activeDirectSetValueState already do.
  const guardedOverviewState =
    isStateForResolvedSet(overviewState.setId, resolvedSetResourceId)
      ? overviewState
      : createMarketDashboardState({ setId: resolvedSetResourceId, sourceWindow: overviewState.sourceWindow });
  // Until the live fetch has produced a payload for this set, fall back to
  // the identity-checked server seed (covers set switches without a remount,
  // where the reducer initializer can't re-run, and a failed refresh whose
  // seed is still perfectly renderable) — same pattern as
  // seededMarketDashboardPayload above.
  // Client-hydration freshness guard (source-date aware): a stale server seed
  // must never override a newer live response, and a stale-while-revalidate live
  // response must never override a newer seed. When a live payload exists we
  // display the fresher-dated of (seed, live); until it does we fall back to the
  // identity-checked server seed.
  const activeOverviewState = !guardedOverviewState.payload
    ? (seededOverviewPayload
        ? createMarketDashboardState({
            status: "success",
            setId: resolvedSetResourceId,
            payload: seededOverviewPayload,
            sourceWindow: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
          })
        : guardedOverviewState)
    : (() => {
        // Overview-specific: compares real OPvC history end date, then snapshot
        // updatedAt, then market date, then point count. Market date alone
        // cannot separate two payloads that advertise the same date while one's
        // OPvC series ends a day earlier.
        const fresher = chooseFresherOverviewPayload(seededOverviewPayload, guardedOverviewState.payload);
        return fresher === guardedOverviewState.payload
          ? guardedOverviewState
          : { ...guardedOverviewState, payload: fresher };
      })();
  const activeOverviewDerivedState = useMemo(
    () => buildMarketDashboardStateFromPayload(activeOverviewState.payload),
    [activeOverviewState.payload]
  );
  // Set Value Trend/Performance vs Cost prefer the slim /overview snapshot
  // once it has loaded, falling back to the market dashboard payload until
  // then. Top Chase Cards/Market Movers are untouched and always read
  // activeMarketDashboardState/activeMarketDashboardDerivedState directly
  // (see activeTopMarketCardsState below) — /market/dashboard is not removed.
  const overviewHasLoaded = activeOverviewState.status === "success" || activeOverviewState.status === "success_stale";
  const effectiveSetValueDashboardState = overviewHasLoaded ? activeOverviewState : activeMarketDashboardState;
  const effectiveSetValueDerivedState = overviewHasLoaded ? activeOverviewDerivedState : activeMarketDashboardDerivedState;
  // OPvC history selection is section-local and independent of whole payload
  // freshness resolution: seed and live /overview histories are read
  // separately and merged date-by-date, then optionally supplemented by
  // insights history_trend. This prevents an empty "newer" seed payload from
  // masking valid live history points.
  const overviewPerformanceHistoryState = useMemo(
    () =>
      selectOverviewPerformanceHistoryState({
        seedPayload: seededOverviewPayload,
        livePayload: guardedOverviewState.payload,
        liveStatus: guardedOverviewState.status,
        liveError: guardedOverviewState.error,
        insightsHistory: explorePayload?.history_trend,
      }),
    [
      seededOverviewPayload,
      guardedOverviewState.payload,
      guardedOverviewState.status,
      guardedOverviewState.error,
      explorePayload?.history_trend,
    ]
  );
  const historyTrend = overviewPerformanceHistoryState.history;
  const latestRealPerformanceDate = overviewPerformanceHistoryState.latestRealDate;
  // Truthful freshness for Opening Profit vs Cost. The date reported is the last
  // point backed by a real simulation run — carried-forward chart continuity
  // rows are excluded by getLatestRealPerformanceDate — so a simulation batch
  // that stopped can never read as current just because the market advanced.
  const activeDirectSetValueState =
    isStateForResolvedSet(setValueHistoryState.setId, resolvedSetResourceId)
      ? setValueHistoryState
      : createSetValueHistoryState({ setId: resolvedSetResourceId });
  const activeDirectSetValueLoadedScopes = new Set(activeDirectSetValueState.loadedScopes || []);
  const activeSetValueHistoriesByScope = {
    ...(effectiveSetValueDerivedState.setValue.historiesByScope || {}),
  };
  Object.entries(activeDirectSetValueState.historiesByScope || {}).forEach(([scope, history]) => {
    if (activeDirectSetValueLoadedScopes.has(scope)) {
      activeSetValueHistoriesByScope[scope] = Array.isArray(history) ? history : [];
    }
  });
  // The direct set-value fetch and Overview's market dashboard are both lazy
  // client fetches, so on Insights/Pull-Rates first load neither has run yet
  // and the scope above is empty. setShellContract's compact history is
  // already sitting in memory (it rides the always-fetched shell request),
  // so use it to seed the standard scope until a fresher fetch lands —
  // otherwise the title-card sparkline/30D delta show "pending" until the
  // user happens to visit Overview and trigger the market dashboard fetch.
  const shellSetValueVisiblePoints = Array.isArray(setShellContract?.setValueSummary?.compact?.visiblePoints)
    ? setShellContract.setValueSummary.compact.visiblePoints
    : [];
  if (
    (activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] || []).length === 0 &&
    shellSetValueVisiblePoints.length > 0
  ) {
    activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] = shellSetValueVisiblePoints;
  }
  const activeSetValueStandardHistory = activeDirectSetValueLoadedScopes.has(CANONICAL_SET_VALUE_SCOPE)
    ? activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] || []
    : effectiveSetValueDerivedState.setValue.history?.length > 0
    ? effectiveSetValueDerivedState.setValue.history
    : activeSetValueHistoriesByScope[CANONICAL_SET_VALUE_SCOPE] || [];
  const activeSetValueAvailableScopes =
    activeDirectSetValueState.availableScopes?.length > 0
      ? activeDirectSetValueState.availableScopes
      : effectiveSetValueDerivedState.setValue.availableScopes || SET_VALUE_SCOPE_OPTIONS;
  const activeSetValueHasAnyHistory = Object.values(activeSetValueHistoriesByScope).some((scopeHistory) => scopeHistory.length > 0);
  const activeSetValueStatus =
    activeDirectSetValueState.status === "success" || activeDirectSetValueState.status === "success_stale"
      ? activeSetValueHasAnyHistory
        ? activeDirectSetValueState.status
        : "empty"
      : activeDirectSetValueState.status === "error"
      ? effectiveSetValueDashboardState.status === "success" || effectiveSetValueDashboardState.status === "success_stale"
        ? effectiveSetValueDerivedState.setValue.hasAnyHistory
          ? "success_stale"
          : "empty"
        : "error"
      : activeDirectSetValueState.status === "loading"
      ? activeSetValueHasAnyHistory
        ? "success_stale"
        : "loading"
      : effectiveSetValueDashboardState.status === "success" || effectiveSetValueDashboardState.status === "success_stale"
      ? effectiveSetValueDerivedState.setValue.hasAnyHistory
        ? effectiveSetValueDashboardState.status === "success_stale"
          ? "success_stale"
          : "success"
        : "empty"
      : effectiveSetValueDashboardState.status;
  const activeSetValueHistory = {
    status: activeSetValueStatus,
    setId: activeDirectSetValueState.setId || effectiveSetValueDashboardState.setId || resolvedSetResourceId,
    history: activeSetValueStandardHistory,
    historiesByScope: activeSetValueHistoriesByScope,
    availableScopes: activeSetValueAvailableScopes,
    error: activeDirectSetValueState.error || effectiveSetValueDashboardState.error,
    meta: activeDirectSetValueState.meta || effectiveSetValueDerivedState.setValue.meta,
  };
  // Top Chase Cards / Market Movers only reset to this set's "loading"/empty
  // shape once their fetch effects fire post-paint (setDetailTab ===
  // "overview"), so a set switch can otherwise render the previous set's
  // cards/movers for one commit under the new set's title — guard the same
  // way activeMarketDashboardState/activeDirectSetValueState already do.
  const activeTopChaseState =
    isStateForResolvedSet(topChaseState.setId, resolvedSetResourceId)
      ? topChaseState
      : createMarketDashboardState({ setId: resolvedSetResourceId, sourceWindow: topChaseState.sourceWindow });
  const activeMarketMoversState =
    isStateForResolvedSet(marketMoversState.setId, resolvedSetResourceId)
      ? marketMoversState
      : createMarketDashboardState({ setId: resolvedSetResourceId, sourceWindow: marketMoversState.sourceWindow });
  // Top Chase Cards: prefer the slim /market/top-chase fetch; fall back to the
  // (possibly seeded/cached) monolithic dashboard state only while the dedicated
  // fetch is still in flight AND only when that fallback itself carries valid
  // Top Chase histories.
  //
  // The old rule was `topChaseFallbackCards.length > 0`, which is not the same
  // question as "can this render". Plain checklist/dashboard rows carry images
  // and prices but no dedicated Top Chase history series, so a failed dedicated
  // module was reported as `success_stale` and the section filled with cards
  // whose every chart read "Awaiting trend". Row count is never evidence of a
  // usable trend — validated history is.
  const topChaseLiveCards = Array.isArray(activeTopChaseState.payload?.cards) ? activeTopChaseState.payload.cards : [];
  const topChaseLiveHasRows = topChaseLiveCards.length > 0;
  const topChaseFallbackCandidates = activeMarketDashboardDerivedState.topCards.cards;
  // setId is intentionally omitted: these rows are same-set by construction, so
  // only their structural quality is in question here.
  const topChaseFallbackVerdict = validateTopChasePayload(
    { cards: topChaseFallbackCandidates },
    {}
  );
  const topChaseFallbackRenderable = topChaseFallbackVerdict.renderable;
  const topChaseFallbackCards = topChaseFallbackRenderable ? topChaseFallbackCandidates : [];
  const topChaseStatus =
    activeTopChaseState.status === "success" || activeTopChaseState.status === "success_stale"
      ? topChaseLiveHasRows
        ? activeTopChaseState.status
        : "empty"
      : activeTopChaseState.status === "error"
      ? topChaseFallbackRenderable
        ? "success_stale"
        : "error"
      : activeTopChaseState.status === "loading"
      ? topChaseFallbackRenderable
        ? "success_stale"
        : "loading"
      : activeMarketDashboardState.status === "success" || activeMarketDashboardState.status === "success_stale"
      ? topChaseFallbackRenderable
        ? activeMarketDashboardState.status === "success_stale"
          ? "success_stale"
          : "success"
        : "empty"
      : activeMarketDashboardState.status;
  // Market Movers: prefer the slim /market/movers fetch for the selected
  // window; fall back to the dashboard-seeded moversByWindow (all windows,
  // possibly stale) until the dedicated per-window fetch lands.
  // getPokemonSetMarketMovers's normalized payload is already the flat
  // { heatingUp, coolingOff, all, window } shape hasMarketMoverRows/
  // MarketMoversModule expect — it is not nested under a `.marketMovers` key
  // (that nesting only exists on the legacy monolithic /market/dashboard
  // payload, handled separately by buildMarketDashboardStateFromPayload
  // below). Reading `.payload?.marketMovers` here always evaluated to
  // undefined, so the live per-window fetch's data was silently discarded in
  // favor of the (usually empty, since /market/dashboard is no longer
  // fetched) dashboard fallback.
  const marketMoversLive = activeMarketMoversState.payload || null;
  const marketMoversLiveHasRows = hasMarketMoverRows(marketMoversLive);
  // ── Canonical market as-of date ─────────────────────────────────────────
  // One shared cutoff for every market-driven surface on this page, resolved
  // from the loaded snapshot generations' own metadata (marketAsOfDate /
  // movementAsOfDate / latestMarketDate). When mixed generations are
  // temporarily loaded, the minimum authoritative date wins so no section can
  // display a day its siblings do not have. Never derived from the browser's
  // or server's current date.
  const overviewPayloadForMarketDate = activeOverviewState.payload || null;
  const topChasePayloadForMarketDate = activeTopChaseState.payload || null;
  const cardsPageMetaForMarketDate =
    cardsPageState.setId === resolvedSetResourceId ? cardsPageState.meta || null : null;
  const marketDateResolution = useMemo(
    () =>
      resolveMarketAsOfDate([
        getMarketDateSourceFromPayload("overview", overviewPayloadForMarketDate),
        getMarketDateSourceFromPayload("topChase", topChasePayloadForMarketDate),
        getMarketDateSourceFromPayload("marketMovers", marketMoversLive),
        getMarketDateSourceFromPayload("cards", cardsPageMetaForMarketDate ? { meta: cardsPageMetaForMarketDate } : null),
      ]),
    [overviewPayloadForMarketDate, topChasePayloadForMarketDate, marketMoversLive, cardsPageMetaForMarketDate]
  );
  const marketAsOfDate = marketDateResolution.marketAsOfDate;
  // Opening Profit vs Cost advances on the simulation batch, every other market
  // surface on the daily scrape. When those two clocks diverge the section says
  // so in plain dates instead of letting the chart imply they stayed in step.
  const openingSimulationFreshness = useMemo(
    () =>
      buildOpeningSimulationFreshness({
        latestRealSimulationDate: latestRealPerformanceDate,
        marketAsOfDate,
      }),
    [latestRealPerformanceDate, marketAsOfDate]
  );
  useEffect(() => {
    if (!setDetailMode) {
      return;
    }
    warnOnMixedMarketDates(resolvedSetResourceId, marketDateResolution);
  }, [setDetailMode, resolvedSetResourceId, marketDateResolution]);
  const activeTopMarketCardsState = {
    status: topChaseStatus,
    setId: activeTopChaseState.setId || activeMarketDashboardState.setId || resolvedSetResourceId,
    cards: topChaseLiveHasRows ? topChaseLiveCards : topChaseFallbackCards,
    marketMovers: marketMoversLiveHasRows ? marketMoversLive : activeMarketDashboardDerivedState.topCards.marketMovers || null,
    marketMoversByWindow: activeMarketDashboardDerivedState.topCards.marketMoversByWindow || null,
    error: activeTopChaseState.error || activeMarketDashboardState.error,
    meta: topChaseLiveHasRows ? activeTopChaseState.payload?.meta : activeMarketDashboardDerivedState.topCards.meta,
  };
  const fallbackSetValueAsOf =
    setShellContract?.setValueSummary?.asOf ||
    explorePayload?.meta?.asOfDate ||
    explorePayload?.meta?.as_of_date ||
    explorePayload?.meta?.run_at ||
    summary.run_at ||
    null;
  const shellSetValueSummary = setShellContract?.setValueSummary || null;
  const setValueSummaryKey = shellSetValueSummary?.sourceKey || setValueSummaryMetric.key;
  const setValueSummaryValue = shellSetValueSummary?.currentValue ?? setValueSummaryMetric.value;
  const activeSetValueContract = useMemo(
    () =>
      buildSetValueContract({
        setId: resolvedSetResourceId,
        current: {
          value: setValueSummaryValue,
          asOf: fallbackSetValueAsOf,
          source: setValueSummaryKey,
        },
        history: activeSetValueHistory.history,
        historiesByScope: activeSetValueHistory.historiesByScope,
        availableScopes: activeSetValueHistory.availableScopes,
        status: activeSetValueHistory.status,
        error: activeSetValueHistory.error,
        marketAsOfDate,
      }),
    [
      activeSetValueHistory.availableScopes,
      activeSetValueHistory.error,
      activeSetValueHistory.historiesByScope,
      activeSetValueHistory.history,
      activeSetValueHistory.status,
      fallbackSetValueAsOf,
      marketAsOfDate,
      resolvedSetResourceId,
      setValueSummaryKey,
      setValueSummaryValue,
    ]
  );
  const heroSetValueHistory = {
    history: activeDirectSetValueLoadedScopes.has(CANONICAL_SET_VALUE_SCOPE)
      ? activeDirectSetValueState.historiesByScope?.[CANONICAL_SET_VALUE_SCOPE] || []
      : [],
    historiesByScope: activeDirectSetValueLoadedScopes.has(CANONICAL_SET_VALUE_SCOPE)
      ? {
          [CANONICAL_SET_VALUE_SCOPE]: activeDirectSetValueState.historiesByScope?.[CANONICAL_SET_VALUE_SCOPE] || [],
        }
      : {},
    meta: activeDirectSetValueLoadedScopes.has(CANONICAL_SET_VALUE_SCOPE) ? activeDirectSetValueState.meta : null,
  };
  const canonicalSetValueMetrics = useMemo(
    () =>
      getCanonicalChecklistSetValueMetrics({
        history: heroSetValueHistory.history,
        historiesByScope: heroSetValueHistory.historiesByScope,
        meta: heroSetValueHistory.meta,
        fallbackMetric: { key: setValueSummaryKey, value: setValueSummaryValue },
        fallbackAsOf: fallbackSetValueAsOf,
        sourcePrefix: "direct_set_value_history",
        marketAsOfDate,
      }),
    [
      heroSetValueHistory.history,
      heroSetValueHistory.historiesByScope,
      heroSetValueHistory.meta,
      fallbackSetValueAsOf,
      marketAsOfDate,
      setValueSummaryKey,
      setValueSummaryValue,
    ]
  );
  const standardSetValueScope = activeSetValueContract.scopes.standard;
  const setValue = activeSetValueContract.current.value ?? canonicalSetValueMetrics.value;

  const averageHitValueDisplay = averageHitValue === null ? "Coming soon" : formatCurrency(averageHitValue);
  const setValueDisplay = setValue === null ? "Coming soon" : formatCurrency(setValue);
  const setValueMetricLabel = `${activeSetValueContract.current.label || getSetValueScopeLabel(CANONICAL_SET_VALUE_SCOPE)} Set Value`;
  const setValueDeltaAmount = standardSetValueScope?.delta30dAmount ?? canonicalSetValueMetrics.deltaAmount;
  const setValueDeltaPercent = standardSetValueScope?.delta30dPercent ?? canonicalSetValueMetrics.deltaPercent;
  const setValueSparklineTone =
    setValueDeltaAmount === null
      ? "neutral"
      : setValueDeltaAmount < 0
      ? "negative"
      : setValueDeltaAmount > 0
      ? "positive"
      : "neutral";
  const setValueSparklinePoints = standardSetValueScope?.history?.length > 0 ? standardSetValueScope.history : canonicalSetValueMetrics.visiblePoints || [];

  // Set Header Summary Contract: the title/header card sources every headline
  // field from here so it renders the same way regardless of setDetailTab.
  // See buildSetHeaderSummary for the explorePayload > shellPayload >
  // marketDashboardPayload > already-loaded client state > fallback order.
  const setHeaderSummary = useMemo(
    () =>
      buildSetHeaderSummary({
        explorePayload,
        shellPayload,
        marketDashboardPayload: initialMarketDashboardPayload,
        marketDashboardState: activeMarketDashboardDerivedState,
        setValueContract: activeSetValueContract,
        selectedTarget,
        resolvedSetResourceId,
        explorePayloadIsFresh: isPrimarySnapshotReady,
        shellPayloadIsForActiveSet,
        previousSameSetSummary: setHeaderSummaryCacheRef.current,
      }),
    [
      explorePayload,
      shellPayload,
      shellPayloadIsForActiveSet,
      initialMarketDashboardPayload,
      activeMarketDashboardDerivedState,
      activeSetValueContract,
      selectedTarget,
      resolvedSetResourceId,
      isPrimarySnapshotReady,
    ]
  );
  if (setDetailMode && setHeaderSummary.setId) {
    setHeaderSummaryCacheRef.current = setHeaderSummary;
  }
  // Title-card metrics are pending (mid-switch, not genuinely empty) when the
  // active set has no matching data source yet: no fresh explore payload, no
  // identity-matched shell, and the header summary came out empty (the
  // same-set cache didn't fill it, so this is a different set whose shell
  // hasn't committed). In that window the metric displays show a pending
  // indicator instead of the misleading "Coming soon"/"—" placeholders that
  // otherwise read as "this set has no data".
  const titleCardMetricsPending =
    setDetailMode &&
    Boolean(resolvedSetResourceId) &&
    !isPrimarySnapshotReady &&
    !shellPayloadIsForActiveSet &&
    setHeaderSummary.score === null &&
    setHeaderSummary.setValue.current === null;
  const titleMetricPendingPlaceholder = "Loading…";

  const activeChartSetValueMetrics = useMemo(
    () =>
      selectSetValueTrendFromContract({
        contract: activeSetValueContract,
        selectedScope: setValueTrendScope,
        selectedWindowKey: "30D",
      }),
    [activeSetValueContract, setValueTrendScope]
  );
  const snapshotIdentityForDebug = getSetSnapshotIdentity(explorePayload);
  const activeSetSlug =
    toStableIdentifier(selectedTarget?.slug ?? selectedTarget?.canonical_key) ||
    toStableIdentifier(snapshotIdentityForDebug?.slug ?? snapshotIdentityForDebug?.canonical_key) ||
    null;

  useEffect(() => {
    if (!setDetailMode) {
      return;
    }
    debugSetPagePerf("set_value.consistency", {
      headerSetValue: canonicalSetValueMetrics.value,
      chartCurrentSetValue: activeChartSetValueMetrics.currentValue,
      headerSource: canonicalSetValueMetrics.source,
      chartSource: `market_dashboard.setValueHistoriesByScope.${setValueTrendScope}`,
      headerSourcePayloadKey: canonicalSetValueMetrics.sourcePayloadKey,
      chartSourcePayloadKey: `setValueHistoriesByScope.${setValueTrendScope}`,
      headerAsOf: canonicalSetValueMetrics.asOf,
      chartAsOf: activeChartSetValueMetrics.asOf,
      activeSetId: resolvedSetResourceId,
      activeSetSlug,
      activeValueScope: setValueTrendScope,
      activeValueScopeLabel: getSetValueScopeLabel(setValueTrendScope),
    });
  }, [
    activeChartSetValueMetrics.asOf,
    activeChartSetValueMetrics.currentValue,
    activeSetSlug,
    canonicalSetValueMetrics.asOf,
    canonicalSetValueMetrics.source,
    canonicalSetValueMetrics.sourcePayloadKey,
    canonicalSetValueMetrics.value,
    resolvedSetResourceId,
    setDetailMode,
    setValueTrendScope,
  ]);

  useEffect(() => {
    if (!setDetailMode || setDetailTab !== "overview") {
      return;
    }
    const standardHistory =
      activeSetValueHistory.historiesByScope?.[CANONICAL_SET_VALUE_SCOPE] ||
      activeSetValueHistory.historiesByScope?.standard ||
      [];
    debugSetPagePerf("set_value_trend.render_state", {
      requestedTargetId,
      selectedTargetId: selectedTarget?.target_id,
      resolvedSetResourceId,
      stateSetId: marketDashboardState.setId,
      activeSetId: activeSetValueHistory.setId,
      status: activeSetValueHistory.status,
      historyLength: Array.isArray(activeSetValueHistory.history) ? activeSetValueHistory.history.length : 0,
      standardHistoryLength: Array.isArray(standardHistory) ? standardHistory.length : 0,
      dashboardSourceWindow: activeMarketDashboardState.sourceWindow,
    });
  }, [
    activeMarketDashboardState.sourceWindow,
    activeSetValueHistory.historiesByScope,
    activeSetValueHistory.history,
    activeSetValueHistory.setId,
    activeSetValueHistory.status,
    marketDashboardState.setId,
    requestedTargetId,
    resolvedSetResourceId,
    selectedTarget?.target_id,
    setDetailMode,
    setDetailTab,
  ]);
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
  // Trend arrows compare against the previous REAL observation — a
  // carried-forward filler row would fake a flat delta.
  const realHistoryTrendPoints = normalizedHistoryTrendPoints.filter((point) => !point.isCarriedForward);
  const previousTrendPoint =
    realHistoryTrendPoints.length >= 2
      ? realHistoryTrendPoints[realHistoryTrendPoints.length - 2]
      : null;
  const currentAverageLossAmount = getLossAmountFromMeanAndCost(summary.mean_value, summary.pack_cost);
  const previousAverageLossAmount = getLossAmountFromMeanAndCost(
    previousTrendPoint?.meanValue,
    previousTrendPoint?.packCost
  );
  const trendByMetricKey = {
    ripScore: getHistoryMetricTrend({
      // Trend tracks the absolute model score against recorded history (which
      // stores the raw formula output), not the cohort-relative public number.
      metricKey: "ripScore",
      currentValue: heroModelScoreRaw,
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
    // Tracks the AUTHORITATIVE desirability score. It used to track the CA7
    // pillar, which is no longer a RIP component and no longer exists on the
    // canonical payload.
    desirabilityScore: getHistoryMetricTrend({
      metricKey: "desirabilityScore",
      currentValue: toNumber(canonicalUniversalSetDesirability?.score),
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
      // Average Loss renders as a signed value (mean − cost, clamped ≤ $0), so
      // its trend is computed on the same signed scale: the arrow tracks the
      // number the user sees, and "up" (toward $0) is the improvement. The
      // magnitude-scale helper values would point the arrow the wrong way.
      currentValue: currentAverageLossAmount === null ? null : -currentAverageLossAmount,
      previousValue: previousAverageLossAmount === null ? null : -previousAverageLossAmount,
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
  const trendScoresSelection = selectTrendScores({
    summary,
    previousPoint: previousTrendPoint,
    setValueMetrics: canonicalSetValueMetrics,
  });
  Object.entries(trendScoresSelection).forEach(([metricKey, selectedTrend]) => {
    if (trendByMetricKey[metricKey]?.trend === "unknown" && selectedTrend?.trend !== "unknown") {
      trendByMetricKey[metricKey] = selectedTrend;
    }
  });
  trendByMetricKey.setValue = canonicalSetValueMetrics.isFallback
    ? trendByMetricKey.setValue
    : canonicalSetValueMetrics.trend;

  const marketReadMetrics = [
    {
      label: setValueMetricLabel,
      rawValue: setValue,
      value: setValueDisplay,
      trend: trendByMetricKey.setValue,
      infoText: "Set value from daily Near Mint card market observations.",
    },
    {
      label: "Pack Market Price",
      rawValue: toNumber(summary.pack_cost),
      value: formatCurrency(summary.pack_cost),
      trend: trendByMetricKey.packCost,
      infoText: "Estimated current pack market price used by the simulation.",
    },
    {
      label: "Expected Value",
      rawValue: toNumber(summary.mean_value),
      value: formatCurrency(summary.mean_value),
      trend: trendByMetricKey.averagePackValue,
      infoText: SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT,
    },
    {
      label: "Expected Value vs Cost",
      rawValue: toNumber(meanValueToCostRatio),
      value: formatNumber(meanValueToCostRatio, 2),
      trend: trendByMetricKey.averageReturnVsCost,
      infoText: "Expected Value divided by the current estimated pack market price.",
    },
  ].filter((metric) => metric.rawValue !== null);
  const topPricedCardsResult = getTopPricedCards({
    topMarketCards: activeTopMarketCardsState.cards,
    checklistCards: checklistState.cards,
  });
  const topPricedCards = topPricedCardsResult.cards;
  const hasTopPricedCards = topPricedCards.length > 0;
  // The Top Chase Cards section container must always render on Overview —
  // TopMarketCardsContent (via topPricedCardsStatus below) already renders a
  // loading skeleton, an error message, or "No priced cards are available
  // yet" on its own; hiding the whole SectionCard here just because the slim
  // /market/top-chase snapshot came back empty (with no checklist fallback
  // available either) silently dropped the section instead of showing that
  // empty state.
  const shouldShowTopMarketCards = true;
  const topPricedCardsStatus =
    activeTopMarketCardsState.status === "error" && !hasTopPricedCards
      ? "error"
      : hasTopPricedCards
      ? "success"
      : activeTopMarketCardsState.status === "loading" || activeTopMarketCardsState.status === "idle"
      ? "loading"
      : "success";
  const topPricedCardsInfo =
    topPricedCardsResult.source === "topMarketCards"
      ? "Highest priced chase-card variants from the current set calculation, sorted by estimated card market price descending."
      : "Highest checklist card market prices in this set, sorted by estimated card market price descending.";
  useEffect(() => {
    if (!setDetailMode || setDetailTab !== "overview") {
      return;
    }
    const topChaseCards = activeTopMarketCardsState.cards || [];
    debugSetPagePerf("top_chase_cards.trend_state", {
      setId: resolvedSetResourceId,
      cardCount: topChaseCards.length,
      cardsWithPriceHistory: topChaseCards.filter((card) => getTopCardPriceHistory(card).length >= 2).length,
      cardsWith30DDelta: topChaseCards.filter((card) =>
        extractDeltaWindows({ deltas: card?.deltas }).some((entry) => entry.key === "30D")
      ).length,
      cardsWithLifetimeDelta: topChaseCards.filter((card) =>
        extractDeltaWindows({ deltas: card?.deltas }).some((entry) => entry.key === "lifetime")
      ).length,
      selectedWindowKey: topMarketCardsWindowKey,
    });
  }, [
    activeTopMarketCardsState.cards,
    resolvedSetResourceId,
    setDetailMode,
    setDetailTab,
    topMarketCardsWindowKey,
  ]);
  const marketMoversByWindow = activeTopMarketCardsState.marketMoversByWindow || null;
  // 7D Movers ticker source: only ever the 7D window. Prefer the live slim fetch when
  // it carries 7D rows; otherwise fall back to the (possibly stale)
  // dashboard-seeded 7D entry until the live 7D fetch lands.
  const moversTickerEntry =
    marketMoversLiveHasRows && marketMoversLive?.window === MOVERS_TICKER_WINDOW
      ? marketMoversLive
      : (marketMoversByWindow && marketMoversByWindow[MOVERS_TICKER_WINDOW]) || null;
  const moversTickerItems = useMemo(() => selectMoversTickerItems(moversTickerEntry), [moversTickerEntry]);
  const moversTickerStatus =
    moversTickerItems.length > 0
      ? "success"
      : activeMarketMoversState.status === "loading" || activeMarketMoversState.status === "idle"
      ? "loading"
      : activeMarketMoversState.status === "error"
      ? "error"
      : "empty";
  // Stable href for the ticker's links — every ticker item and the trailing
  // affordance navigate to the same "View all movers" destination (the Cards
  // tab's dedicated Market Movers view). Real anchors for keyboard/AT
  // semantics and native modified-click/new-tab behavior.
  const moversTickerHref = updateSetDetailQueryParams({
    pathname,
    searchParams,
    tab: "cards",
    section: "market-movers",
    cardSort: "7d-movers",
    movementFilter: "all",
  });
  // Chase rows lead into the Cards tab for this set, sorted by price, so the
  // destination keeps both the set and a sensible browsing context.
  // "current-price" is one of the three keys in ALL_CARDS_SORT_OPTIONS
  // (set-number | name | current-price) — an unrecognised value would silently
  // land the Cards tab on its fallback sort. Sort direction is separate client
  // state (cardSortDirection) and is not part of this URL builder, so the Cards
  // tab applies its own default direction for that sort.
  const topChaseRowHref = updateSetDetailQueryParams({
    pathname,
    searchParams,
    tab: "cards",
    section: "all-cards",
    cardSort: "current-price",
    movementFilter: "all",
  });
  // Progressive rendering (replaces the old Phase 9B whole-tab cohesive
  // skeleton): each Overview section gates independently on its own fetch's
  // status instead of waiting for every critical asset to settle together.
  // Set Value and Performance vs Cost already receive status/error props and
  // self-render their own loading/error states (SetValueTrendCard,
  // MarketMoversModule, TopMarketCardsContent); Performance vs Cost's
  // PackValueHistoryChart does not, so it gets an explicit SectionBoundary
  // below keyed to overviewPerformanceVsCostStatus.
  // Core rule: renderable OPvC history beats loading/error presentation.
  // The section-level selector handles empty-seed vs live-loading distinctions
  // so first-load can never show settled unavailability before /overview
  // settles.
  const overviewPerformanceVsCostStatus = overviewPerformanceHistoryState.status;
  // Section-level timing (see components/ui/SectionBoundary.jsx and
  // hooks/useSectionTiming.js): one metric per Overview priority section.
  // Market Signals has no async gate (see comment above), so it's reported
  // as "success" the moment the tab mounts — an honest ~0ms.
  const overviewTimingSetId = setDetailMode && setDetailTab === "overview" ? resolvedSetResourceId : null;
  useSectionTiming("setValue", overviewTimingSetId ? activeSetValueHistory.status : "idle", {
    setId: overviewTimingSetId,
    tab: "overview",
  });
  useSectionTiming("performanceVsCost", overviewTimingSetId ? overviewPerformanceVsCostStatus : "idle", {
    setId: overviewTimingSetId,
    tab: "overview",
  });
  // "marketMovers" on Overview now measures the 7D Movers ticker (the
  // Market Movers card's replacement) — same metric name so dashboards keep
  // one continuous series. "empty" counts as settled, mirroring the old
  // card's success-with-no-rows presentation.
  useSectionTiming("marketMovers", overviewTimingSetId ? (moversTickerStatus === "empty" ? "success" : moversTickerStatus) : "idle", {
    setId: overviewTimingSetId,
    tab: "overview",
  });
  useSectionTiming("topChase", overviewTimingSetId ? topPricedCardsStatus : "idle", {
    setId: overviewTimingSetId,
    tab: "overview",
  });
  useSectionTiming("marketSignals", overviewTimingSetId ? "success" : "idle", {
    setId: overviewTimingSetId,
    tab: "overview",
  });
  // Insights loading cohesion, split by priority tier (progressive-rendering
  // refactor): critical (RIP Score hero + pillar cards, priorities 1-3) and
  // secondary (Opening Outcomes charts + Desirability Evidence, priorities
  // 4-5) each gate independently on their own fetch's status now, instead of
  // one shared whole-tab hold keyed to a single combined fetch.
  const activeInsightsCriticalStatus =
    insightsCriticalFetchState.setId === resolvedSetResourceId ? insightsCriticalFetchState.status : "idle";
  const activeInsightsSecondaryStatus =
    insightsSecondaryFetchState.setId === resolvedSetResourceId ? insightsSecondaryFetchState.status : "idle";
  const insightsCriticalLoadFailed =
    setDetailMode && setDetailTab === "insights" && activeInsightsCriticalStatus === "error";
  const insightsCriticalPending =
    setDetailMode &&
    setDetailTab === "insights" &&
    Boolean(resolvedSetResourceId) &&
    (activeInsightsCriticalStatus === "idle" || activeInsightsCriticalStatus === "loading");
  const insightsCriticalPendingTimedOut =
    insightsCriticalPendingTimeoutState.setId === resolvedSetResourceId && insightsCriticalPendingTimeoutState.timedOut;
  // RIP Score hero/pillar cards hold their own branded panel (see
  // showInsightsCohesiveLoading's new render usage below, scoped to just
  // that section now — not the whole tab) until the critical fetch settles
  // or times out.
  const showInsightsCohesiveLoading = insightsCriticalPending && !insightsCriticalPendingTimedOut;
  // criticalHeroMs is shared by Insights' RIP Score hero and Pull Rates' hit
  // rate summary (both are each tab's priority-1 content), disambiguated by
  // the tab field — see hooks/useSectionTiming.js.
  useSectionTiming("criticalHero", setDetailMode && setDetailTab === "insights" ? activeInsightsCriticalStatus : "idle", {
    setId: resolvedSetResourceId,
    tab: "insights",
  });
  const insightsLoadFailed =
    setDetailMode && setDetailTab === "insights" && !hasActiveInsightsPayload && activeInsightsSecondaryStatus === "error";
  const insightsSecondaryPending =
    setDetailMode &&
    setDetailTab === "insights" &&
    Boolean(resolvedSetResourceId) &&
    !hasActiveInsightsPayload &&
    !insightsLoadFailed;
  // "Secondary data exists" in renderable terms — any secondary-owned field
  // the Insights sections can actually draw. Used to retire the pending
  // timeout the moment data lands (renderable data beats loading status);
  // the timeout copy must never linger over sections that now have content.
  const insightsSecondaryHasRenderableData =
    hasNonEmptyArray(explorePayload?.top_hits || explorePayload?.topHits) ||
    hasNonEmptyArray(explorePayload?.distribution_bins || explorePayload?.distributionBins) ||
    hasNonEmptyArray(explorePayload?.percentiles) ||
    hasNonEmptyArray(explorePayload?.rankings) ||
    hasNonEmptyArray(explorePayload?.history_trend || explorePayload?.historyTrend) ||
    hasMeaningfulObjectFields(explorePayload?.rip_statistics || explorePayload?.ripStatistics) ||
    hasMeaningfulObjectFields(explorePayload?.openingDesirability || explorePayload?.opening_desirability);
  useEffect(() => {
    if (!insightsSecondaryHasRenderableData) {
      return;
    }
    // Secondary data arrived (fresh fetch, re-merge after a navigation reset,
    // or a late response) — a previously-fired "taking longer than expected"
    // timeout no longer describes reality and must clear immediately.
    setInsightsPendingTimeoutState((previous) =>
      previous.setId !== null || previous.timedOut ? { setId: null, timedOut: false } : previous
    );
  }, [insightsSecondaryHasRenderableData]);
  const insightsPendingTimedOut =
    !insightsSecondaryHasRenderableData &&
    insightsPendingTimeoutState.setId === resolvedSetResourceId &&
    insightsPendingTimeoutState.timedOut;
  // Opening Outcomes + Desirability Evidence (secondary tier) stay in their
  // loading/fallback presentation while blocked; the fallback copy takes
  // over once loading is no longer expected to resolve on its own (fetch
  // error or timeout).
  const insightsSectionsBlocked = insightsSecondaryPending || insightsLoadFailed;
  const insightsSectionsShowFallbackCopy = insightsLoadFailed || insightsPendingTimedOut;
  // "Simulation Drivers unavailable: no top_hits rows" is only evidence once
  // it is settled truth: on the set-detail page the secondary insights fetch
  // must have SUCCEEDED for this set and still produced no rows. While it is
  // idle/loading — or a navigation reset momentarily dropped the merge — an
  // empty explorePayload says nothing about the DB (Paradox Rift has 10
  // top_hits rows), so surfacing the warning then is a false alarm. Explore
  // mode keeps the old behavior: its payload is loaded up front, so missing
  // rows there are already settled truth.
  const simulationDriversWarningVisible =
    Boolean(simulationDrivers.diagnostics?.warning) &&
    topHits.length === 0 &&
    (!setDetailMode || activeInsightsSecondaryStatus === "success");
  const visibleSetPageWarnings = simulationDriversWarningVisible
    ? [...warnings, simulationDrivers.diagnostics.warning]
    : warnings;
  // Opening Outcomes settled-state audit (Phase 9C): once the payload is in,
  // each sub-view either has rows to render or gets a compact empty state —
  // never a chart-sized blank panel. The card's large min-height is also only
  // applied when the active view actually renders chart-sized content.
  const historicalTrendHasRenderablePoints = hasNonEmptyArray(historyTrend) && historyTrend.length >= 2;
  const openingOutcomesViewHasData =
    activeInsightsGraphMode === "simulation-drivers"
      ? topHits.length > 0
      : activeInsightsGraphMode === "value-contribution"
      ? rankings.length > 0
      : activeInsightsGraphMode === "pack-breakdown"
      ? hasRenderablePackPathRows(ripStatistics?.pack_paths, normalStateRows)
      : activeInsightsGraphMode === "historical-trend"
      // PackValueHistoryChart owns its own compact empty state, so always
      // render its branch and let the chart decide.
      ? true
      : activeInsightsGraphMode === "simulation-metrics"
      // SimulationMetricsContent renders honest per-metric "not available"
      // states, so it is never blocked by a missing-data verdict.
      ? true
      : hasRenderableOutcomeDistributionRows(distributionBins, thresholdBins);
  const openingOutcomesEmptyViewCopy =
    activeInsightsGraphMode === "simulation-drivers"
      ? "Simulation driver data isn't available for this set yet."
      : activeInsightsGraphMode === "value-contribution"
      ? "Value structure data isn't available for this set yet."
      : activeInsightsGraphMode === "pack-breakdown"
      ? "Pack path data isn't available for this set yet."
      : "Outcome distribution data isn't available for this set yet.";
  // Chart-sized min-heights apply only to views that render chart-sized
  // content with data. Metrics sizes itself; Opening P vs C only expands once
  // it has enough points to plot (otherwise its compact empty state shows).
  const openingOutcomesUsesExpandedLayout =
    !insightsSectionsBlocked &&
    openingOutcomesViewHasData &&
    activeInsightsGraphMode !== "simulation-metrics" &&
    (activeInsightsGraphMode !== "historical-trend" || historicalTrendHasRenderablePoints);
  useEffect(() => {
    if (!setDetailMode || setDetailTab !== "insights" || !resolvedSetResourceId || hasActiveInsightsPayload) {
      return undefined;
    }
    const setId = resolvedSetResourceId;
    // A fresh pending episode (e.g. retrying after navigation reset the
    // payload) must start from the skeleton again, not from stale timeout
    // copy left over from an earlier episode for the same set.
    setInsightsPendingTimeoutState((previous) =>
      previous.setId === setId && previous.timedOut ? { setId: null, timedOut: false } : previous
    );
    const timer = window.setTimeout(() => {
      setInsightsPendingTimeoutState({ setId, timedOut: true });
    }, INSIGHTS_PENDING_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [setDetailMode, setDetailTab, resolvedSetResourceId, hasActiveInsightsPayload]);
  // Mirrors the timeout effect above, for the critical (RIP Score hero/pillar
  // cards) tier specifically, keyed off insightsCriticalPending rather than
  // hasActiveInsightsPayload (which only reflects secondary-owned fields).
  useEffect(() => {
    if (!insightsCriticalPending) {
      return undefined;
    }
    const setId = resolvedSetResourceId;
    setInsightsCriticalPendingTimeoutState((previous) =>
      previous.setId === setId && previous.timedOut ? { setId: null, timedOut: false } : previous
    );
    const timer = window.setTimeout(() => {
      setInsightsCriticalPendingTimeoutState({ setId, timedOut: true });
    }, INSIGHTS_PENDING_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [insightsCriticalPending, resolvedSetResourceId]);
  // Pull Rates loading shell (Phase 9B): pullRatesState only resets to this
  // set's shape once its fetch effect fires post-paint, so guard by set id
  // the same way the other per-tab states do, and treat idle/loading with no
  // usable assumptions as "show the loading shell" instead of the misleading
  // "coming soon" copy.
  const activePullRatesState =
    pullRatesState.setId === resolvedSetResourceId
      ? pullRatesState
      : { status: "idle", setId: resolvedSetResourceId, pullRateAssumptions: null, error: null };
  const pullRatesTabPending =
    setDetailMode &&
    setDetailTab === "pull-rates" &&
    !pullRateAssumptions &&
    (activePullRatesState.status === "idle" || activePullRatesState.status === "loading");
  // Phase 9D.1: the loading shell may never settle if the fetch hangs (no
  // request timeout) or an upstream gate keeps the state parked on "idle" —
  // same escape hatch as Insights, so Pull Rates can never shimmer
  // indefinitely: after the timeout the shell switches to explicit
  // "taking longer than expected" copy.
  const pullRatesPendingTimedOut =
    pullRatesPendingTimeoutState.setId === resolvedSetResourceId && pullRatesPendingTimeoutState.timedOut;
  useEffect(() => {
    if (!setDetailMode || setDetailTab !== "pull-rates" || !resolvedSetResourceId || pullRateAssumptions) {
      return undefined;
    }
    const setId = resolvedSetResourceId;
    // A fresh pending episode must start from the skeleton again, not from
    // stale timeout copy left over from an earlier episode for the same set.
    setPullRatesPendingTimeoutState((previous) =>
      previous.setId === setId && previous.timedOut ? { setId: null, timedOut: false } : previous
    );
    const timer = window.setTimeout(() => {
      setPullRatesPendingTimeoutState({ setId, timedOut: true });
    }, INSIGHTS_PENDING_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [setDetailMode, setDetailTab, resolvedSetResourceId, pullRateAssumptions]);
  // Temporary fallback: if a full cards payload is already seeded (e.g. the
  // user visited Insights first, or an old SSR seed is still present), show
  // it until the paginated fetch for this set lands, instead of an empty
  // grid. Once cardsPageState has real data for this set it always wins.
  const cardsPageFallbackCards =
    checklistState.setId === resolvedSetResourceId && checklistState.cards.length > 0 ? checklistState.cards : [];
  // cardsPageState only resets to this set's "idle"/empty shape once its
  // fetch effect fires post-paint (setDetailTab === "cards"), so a set
  // switch can otherwise render the previous set's cards grid/pagination for
  // one commit under the new set's title — guard it the same way
  // activeMarketDashboardState/activeDirectSetValueState already do.
  const activeCardsPageState =
    cardsPageState.setId === resolvedSetResourceId
      ? cardsPageState
      : { status: "idle", setId: resolvedSetResourceId, scopeKey: null, page: 1, cards: [], pagination: null, filters: null, meta: null, error: null };
  const authoritativeSetCardCount =
    toNumber(activeCardsPageState.pagination?.totalCards) > 0
      ? toNumber(activeCardsPageState.pagination?.totalCards)
      : toNumber(
          selectedTarget?.card_count ??
            selectedTarget?.cardCount ??
            selectedTarget?.checklist_set_value_total_card_count ??
            selectedTarget?.checklistSetValueTotalCardCount ??
            summary?.simulated_set_value_card_count
        );
  const effectiveCardsPageCards = activeCardsPageState.cards.length > 0 ? activeCardsPageState.cards : cardsPageFallbackCards;
  const effectiveCardsPageStatus =
    activeCardsPageState.cards.length > 0
      ? activeCardsPageState.status
      : cardsPageFallbackCards.length > 0
      ? "success_stale"
      : activeCardsPageState.status;
  // Capability comes from the completed endpoint contract. It deliberately
  // defaults true while page one is cold so a route-selected 7D sort cannot
  // be replaced before the first request is made.
  const hasCardMovementData = activeCardsPageState.filters?.availableSorts?.includes("7d-movers") ?? true;
  const cardsRequest = resolveCardsRequest({
    selectedSubTab: cardsSection,
    selectedTimeframe,
    activeSortMode: cardSortMode,
    activeSortDirection: cardSortDirection,
    activeMovementMetric: cardMovementMetric,
  });
  const effectiveCardSortMode = cardsRequest.sort;
  const effectiveCardMovementFilter = cardsRequest.movementFilter;
  const effectiveCardMovementSort = cardsRequest.movementSort;
  const effectiveCardMovementMetric = cardsRequest.movementMetric;
  const availableCardRarities = activeCardsPageState.filters?.availableRarities || [];
  const effectiveCardRarityFilter = getEffectiveRarityFilter(cardsSection, cardRarityFilter);
  useEffect(() => {
    setCardsPage(1);
  }, [
    effectiveCardSortMode,
    cardsRequest.sortDirection,
    effectiveCardMovementSort,
    effectiveCardMovementMetric,
    effectiveCardMovementFilter,
    cardSearchQuery,
    effectiveCardRarityFilter,
    cardsSection,
    resolvedSetResourceId,
  ]);
  // Preserve endpoint order verbatim. Sorting only the accumulated browser
  // pages would corrupt the global 7D ranking as infinite-scroll chunks append.
  const displayedChecklistCards = effectiveCardsPageCards;
  // Development-only market diagnostics: one object per set-page load
  // summarizing marketAsOfDate, every surface's end date, canonical mover
  // totals, and banner↔Cards parity — with warnings on any disagreement.
  // Slim values only; never logs card payloads or price histories.
  const activeCardsPageStateForDiagnostics = activeCardsPageState;
  useEffect(() => {
    if (process.env.NODE_ENV === "production" || !setDetailMode || !resolvedSetResourceId) {
      return;
    }
    const moversMeta = marketMoversLive?.meta || null;
    const moversTotals = moversMeta?.movementTotals || null;
    const cardsTotals = cardsPageMetaForMarketDate?.movementTotals || null;
    const openingProfitRawEnd = (Array.isArray(historyTrend) ? historyTrend : []).reduce((latest, row) => {
      const date = getHistoryDateKey(row?.snapshotDate ?? row?.snapshot_date ?? row?.date);
      return date && (!latest || date > latest) ? date : latest;
    }, null);
    const openingProfitHasPointInRange =
      !marketAsOfDate ||
      (Array.isArray(historyTrend) &&
        historyTrend.some((row) => {
          const date = getHistoryDateKey(row?.snapshotDate ?? row?.snapshot_date ?? row?.date);
          return date && date <= marketAsOfDate;
        }));
    const topChaseEndDate = (Array.isArray(topPricedCards) ? topPricedCards : []).reduce((latest, card) => {
      const date = getHistoryPointsEndDate(getTopCardPriceHistory(card, topMarketCardsWindowKey, marketAsOfDate));
      return date && (!latest || date > latest) ? date : latest;
    }, null);
    const loadedMoversViewCards = activeCardsPageStateForDiagnostics.cards;
    const isCanonicalMoversCardsView =
      cardsSection === "market-movers" &&
      effectiveCardMovementSort === "7d-movers" &&
      effectiveCardMovementFilter === "all" &&
      loadedMoversViewCards.length > 0;
    const usedLegacyMoverList =
      moversMeta?.snapshot?.usedLegacyMoverList === true ||
      (Boolean(moversTickerEntry) && !marketMoversLiveHasRows);
    const report = buildSetPageMarketDiagnostics({
      setId: resolvedSetResourceId,
      generationId: marketDateResolution.sources.find((source) => source.generationId)?.generationId || null,
      marketAsOfDate,
      titleCardEndDate: getHistoryPointsEndDate(setValueSparklinePoints),
      setValueEndDate: activeChartSetValueMetrics.lastPoint?.date || null,
      // The rendered chart clamps to marketAsOfDate and forward-fills up to
      // it, so its visible end is the cutoff whenever any point is in range.
      openingProfitEndDate:
        marketAsOfDate && openingProfitHasPointInRange && openingProfitRawEnd
          ? marketAsOfDate
          : openingProfitRawEnd,
      topChaseEndDate,
      cardsSnapshotEndDate:
        cardsPageMetaForMarketDate?.snapshot?.marketAsOfDate ||
        cardsPageMetaForMarketDate?.snapshot?.movementAsOfDate ||
        null,
      totalCards: moversTotals?.checklistCardCount ?? cardsTotals?.checklistCardCount ?? null,
      cardsWith7dMovement: moversTotals?.cardsWithCalculableMovement ?? cardsTotals?.cardsWithCalculableMovement ?? null,
      nonzero7dMovers: moversTotals?.nonzeroMovementCount ?? cardsTotals?.nonzeroMovementCount ?? null,
      marketMoversFilteredTotal: moversTotals?.filteredTotal ?? null,
      bannerCount: moversTickerItems.length,
      bannerFirstTenIds: moversTickerItems.map(
        (item) => item?.card?.canonicalCardId || item?.card?.cardId || item?.card?.id || null
      ),
      cardsFirstTenIds: isCanonicalMoversCardsView
        ? loadedMoversViewCards.slice(0, 10).map((card) => card?.canonicalCardId || card?.id || null)
        : null,
      usedLegacyMoverList,
      isMixedGenerations: marketDateResolution.isMixedGenerations || marketDateResolution.isMixedDates,
      moversMovementFilter: "all",
    });
    reportSetPageMarketDiagnostics(report);
  }, [
    setDetailMode,
    resolvedSetResourceId,
    marketAsOfDate,
    marketDateResolution,
    marketMoversLive,
    marketMoversLiveHasRows,
    moversTickerEntry,
    moversTickerItems,
    setValueSparklinePoints,
    activeChartSetValueMetrics.lastPoint,
    historyTrend,
    topPricedCards,
    topMarketCardsWindowKey,
    cardsPageMetaForMarketDate,
    cardsSection,
    effectiveCardMovementSort,
    effectiveCardMovementFilter,
    activeCardsPageStateForDiagnostics,
  ]);
  // Infinite scroll (Phase 10): a sentinel below the grid advances cardsPage
  // instead of Previous/Next buttons. `loading_more` keeps every rendered
  // card in place and shows only the bottom brand loader.
  const cardsPageIsLoadingMore = activeCardsPageState.status === "loading_more";
  const cardsPageIsFetching = activeCardsPageState.status === "loading" || cardsPageIsLoadingMore;
  // A failed load-more lands in success_stale + error with the loaded cards
  // kept; surface a bottom retry affordance instead of silently stalling the
  // list (the sentinel is disabled while an error is pending so it cannot
  // hammer a failing endpoint).
  const cardsPageLoadMoreError = Boolean(
    activeCardsPageState.error && activeCardsPageState.cards.length > 0 && activeCardsPageState.pagination?.hasNextPage
  );
  const cardsPageFullyLoaded = Boolean(
    activeCardsPageState.pagination &&
      !activeCardsPageState.pagination.hasNextPage &&
      activeCardsPageState.pagination.totalPages > 1
  );
  // Latest-value ref so the IntersectionObserver callback (created once per
  // grid growth) always reads the current gate without re-subscribing on
  // every state change. Duplicate fires are harmless: the next page is
  // computed from the last *merged* page, so repeated calls set the same
  // value, and the fetch effect's request-key dedupe drops repeats anyway.
  const cardsLoadMoreGateRef = useRef({ canLoadMore: false, nextPage: 1, stateScopeKey: null });
  cardsLoadMoreGateRef.current = {
    canLoadMore: Boolean(
      setDetailMode &&
        setDetailTab === "cards" &&
        cardsSubTab === "checklist" &&
        activeCardsPageState.pagination?.hasNextPage &&
        !cardsPageIsFetching &&
        !activeCardsPageState.error &&
        cardsPage === activeCardsPageState.page
    ),
    nextPage: (activeCardsPageState.pagination?.page || activeCardsPageState.page || 1) + 1,
    // Scope of the cards currently in state — lets the fetch effect skip a
    // doomed page-N request when sort/search/filter changed in the same
    // commit that the page counter is about to be rewound to 1.
    stateScopeKey: activeCardsPageState.scopeKey,
  };
  useEffect(() => {
    if (!setDetailMode || setDetailTab !== "cards" || cardsSubTab !== "checklist") {
      return undefined;
    }
    if (typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    // One sentinel now that PublicProfileLocalScaffold mounts the page content
    // once (it used to render a desktop `hidden xl:block` copy alongside a
    // mobile `xl:hidden` copy, so a single element ref landed on the
    // last-mounted, display:none one). querySelectorAll still handles the list
    // because the gate ref and the idempotent page advance make duplicate fires
    // harmless either way, and this needs no change if a future layout
    // re-splits.
    const sentinels = Array.from(document.querySelectorAll("[data-cards-load-more-sentinel]"));
    if (sentinels.length === 0) {
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) {
          return;
        }
        const { canLoadMore, nextPage } = cardsLoadMoreGateRef.current;
        if (!canLoadMore) {
          return;
        }
        debugSetPagePerf("cards_page.load_more", { resolvedSetId: resolvedSetResourceId, nextPage });
        setCardsPage((page) => (page >= nextPage ? page : nextPage));
      },
      // Generous prefetch margin: start loading the next chunk well before
      // the user reaches the bottom of the grid.
      { rootMargin: "1000px 0px" }
    );
    for (const sentinel of sentinels) {
      observer.observe(sentinel);
    }
    return () => observer.disconnect();
    // effectiveCardsPageCards.length: re-observe after each append so the
    // initial-intersection callback re-fires if the sentinel is still within
    // the prefetch margin (IntersectionObserver only reports crossings, so a
    // fast scroller would otherwise stall after one chunk).
  }, [setDetailMode, setDetailTab, cardsSubTab, resolvedSetResourceId, effectiveCardsPageCards.length]);
  const decisionMetrics = [
    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatCurrency(summary.pack_cost), trend: trendByMetricKey.packCost },
    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatCurrency(summary.mean_value), trend: trendByMetricKey.averagePackValue },
    { label: RIP_COPY.simpleMetrics.averageHitValue, value: averageHitValueDisplay, trend: trendByMetricKey.averageHitValue },
    { label: RIP_COPY.simpleMetrics.averageLoss, value: formatSignedCurrency(simpleAverageLossValue), trend: trendByMetricKey.averageLoss },
    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatPercent(summary.prob_profit, { probability: true }), trend: trendByMetricKey.chanceToBeatPackCost },
    { label: RIP_COPY.simpleMetrics.chanceAtBigPull, value: formatPercent(summary.prob_big_hit, { probability: true }), trend: trendByMetricKey.chanceAtBigPull },
  ];
  // Header/title-card variant of decisionMetrics — sourced from
  // setHeaderSummary (the stable header contract) instead of `summary`
  // directly, so these tiles stay populated regardless of setDetailTab.
  // A null metric renders the pending placeholder mid-switch (matching shell
  // not ready yet) and only the settled "Coming soon" once we know this set
  // genuinely has no value — never the previous set's leaked number.
  const formatHeaderMetric = (value, formatter) =>
    value === null || value === undefined
      ? titleCardMetricsPending
        ? titleMetricPendingPlaceholder
        : "Coming soon"
      : formatter(value);
  const headerDecisionMetrics = [
    { label: RIP_COPY.simpleMetrics.currentPackCost, value: formatHeaderMetric(setHeaderSummary.packCost, formatCurrency), trend: trendByMetricKey.packCost },
    { label: RIP_COPY.simpleMetrics.averagePackValue, value: formatHeaderMetric(setHeaderSummary.expectedValue, formatCurrency), trend: trendByMetricKey.averagePackValue },
    { label: RIP_COPY.simpleMetrics.chanceToBeatPackCost, value: formatHeaderMetric(setHeaderSummary.chanceToBeatPackCost, (v) => formatPercent(v, { probability: true })), trend: trendByMetricKey.chanceToBeatPackCost },
  ];
  const headerExpectedLossText =
    setHeaderSummary.averageLoss === null || setHeaderSummary.averageLoss === undefined
      ? null
      : `${formatSignedCurrency(setHeaderSummary.averageLoss)} versus pack price`;
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
    { label: "Expected Value vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
    { label: "Typical Opening (P50) vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
    { label: "Strong Upside (P95) vs Cost", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
    { label: "Jackpot Upside (Top 1% / P99)", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
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
    { label: "Expected Value vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
    { label: "Typical Opening (P50) vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
    { label: "Strong Upside (P95) vs Cost", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
    { label: "Jackpot Upside (Top 1% / P99)", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
  ];
  const safetyPillarMetrics = [
    { label: "Typical Opening", value: formatCurrency(percentileP50 ?? summary.median_value), trend: trendByMetricKey.typicalPackValue, infoText: getMetricTooltip("Typical Opening") },
    { label: "Bad Pack Floor Value", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.badPackFloorValue, infoText: getMetricTooltip("Bad Pack Floor Value") },
    { label: "Chance to Miss Pack Cost", value: formatPercent(chanceToMissPackCostValue, { probability: true }), trend: trendByMetricKey.chanceToMissPackCost, infoText: getMetricTooltip("Chance to Miss Pack Cost") },
    { label: "Average Loss When You Miss", value: formatLossCurrency(summary.expected_loss_when_losing), trend: trendByMetricKey.averageLossWhenYouMiss, infoText: getMetricTooltip("Average Loss When You Miss") },
    { label: "Typical Loss When You Miss", value: formatLossCurrency(summary.median_loss_when_losing), trend: trendByMetricKey.typicalLossWhenYouMiss, infoText: getMetricTooltip("Typical Loss When You Miss") },
    { label: "Worst 5% Outcome", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.worstFivePercentShortfall?.trend === "unknown" ? trendByMetricKey.badPackFloorValue : trendByMetricKey.worstFivePercentShortfall, infoText: getMetricTooltip("Worst 5% Outcome") },
  ];
  const desirabilityPillarMetrics = [
    ...desirabilityOverviewMetrics,
    {
      label: "Top Desirability Drivers",
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
  // The backend scoring config's pillar weights were read here and printed
  // into the section tooltip. They are Financial RIP V2's 60/25/15 split, and
  // no weight is shown on a public surface any more.
  // Stated as the two-level model the backend actually computes. The old copy
  // listed the three pillars and desirability in one flat sentence, which
  // invited the 60+25+15+10 = 110% reading; these are not four peers.
  // Neutral and factual: what the two canonical inputs MEASURE, with no
  // weights, no formula and no contribution arithmetic. They are NOT halves —
  // the canonical blend is 0.90 Financial RIP + 0.10 Collector Appeal, and
  // "halves" both misstated that and invited an even-split reading.
  // The previous copy stated an 80/20
  // split (the canonical model is not 80/20) and then expanded it into
  // Profit/Safety/Stability percentages, which are Financial RIP V2's pillars.
  const ripBreakdownInfo =
    "RIP Score combines Financial RIP with Collector Appeal. Financial RIP is the monetary opening profile built from the simulated pack-value distribution and the pack price; Collector Appeal is how desirable the modeled cards are and how often the pack can deliver them.";
  // The Explore expert view's three pillar-lens cards, and nothing else. These
  // are Financial RIP V2 pillars, presented as their own named lenses on a
  // diagnostic surface - never as the components of Financial RIP, which has
  // its own six V3 components in FinancialRipV3Breakdown.
  const legacyExpertPillarRows = useMemo(
    () => selectRipScoreBreakdown(legacyExpertRip, trendByMetricKey, { requestTimeout: isTimeoutFallbackPayload }),
    [legacyExpertRip, trendByMetricKey, isTimeoutFallbackPayload]
  );
  const ripBreakdownRowByTitle = new Map(legacyExpertPillarRows.rows.map((row) => [row.title, row]));
  // The legacy Profit/Safety/Stability pillar tiles, the Overall RIP v4
  // composition (`selectRipDesirabilityBreakdown`) and the CA7 "10% term" view
  // model were all built here. Every one of them described a superseded model:
  // the pillars are Financial RIP V2, the composition is Overall RIP v4, and
  // the term carried a weight label and a contribution in model points. The
  // canonical presentation is FinancialRipV3Breakdown plus
  // CollectorAppealBreakdown, which read the V7 contract directly.
  // `requestedCollectorProfileView` selected the Roster Appeal / Opening Paths
  // view of the removed Collector Profile from a legacy `?section=`. There is no
  // view to select any more: those sections are now plain scroll aliases onto
  // the canonical Collector Appeal block (SET_DETAIL_SECTION_TARGETS), so no
  // local state is derived from them.
  // `overviewPillarSignals` and `overviewDecisionTrackedSignals` were built
  // here to feed the Overview Decision Signals card. That card is gone (it
  // scored Profit, Safety, Stability, Opening Experience and Chase Potential),
  // so the two feeds have no consumer and are not built.
  const initialModuleSetValueHistories =
    initialMarketDashboardPayload?.setValueHistoriesByScope ||
    initialMarketDashboardPayload?.set_value_histories_by_scope ||
    {};
  const initialTopChaseCards = Array.isArray(initialMarketDashboardPayload?.topChaseCards)
    ? initialMarketDashboardPayload.topChaseCards
    : Array.isArray(initialMarketDashboardPayload?.top_chase_cards)
    ? initialMarketDashboardPayload.top_chase_cards
    : [];
  const initialCorrelationForDiagnostics = resolvePreferredCardAppealCorrelation({
    explorePayload,
    cardsPayload: initialCardsPayload,
    checklistState,
  });
  const initialCorrelationRowsForDiagnostics = Array.isArray(initialCorrelationForDiagnostics?.plotRows)
    ? initialCorrelationForDiagnostics.plotRows
    : Array.isArray(initialCorrelationForDiagnostics?.plot_rows)
    ? initialCorrelationForDiagnostics.plot_rows
    : Array.isArray(initialCorrelationForDiagnostics?.rows)
    ? initialCorrelationForDiagnostics.rows
    : [];
  const debugWarnings = [
    ...Object.entries(initialModuleSnapshots?.errors || {}).map(
      ([key, value]) => `${key}: ${value?.message || "module snapshot unavailable"}`
    ),
  ];
  const initialModuleDiagnosticRows = [
    ["initial cards payload", initialCardsPayload ? "present" : "missing"],
    ["initial cards count", Array.isArray(initialCardsPayload?.cards) ? initialCardsPayload.cards.length : 0],
    ["initial market dashboard", initialMarketDashboardPayload ? "present" : "missing"],
    [
      "initial set value scopes",
      SET_VALUE_SCOPE_OPTIONS.map((scope) => `${scope.key}:${initialModuleSetValueHistories?.[scope.key]?.length || 0}`).join(", "),
    ],
    ["initial top chase count", initialTopChaseCards.length],
    [
      "initial correlation",
      `n=${toNumber(initialCorrelationForDiagnostics?.n) ?? 0}, plotted=${initialCorrelationRowsForDiagnostics.length}`,
    ],
    ["explore warnings", (explorePayload?.meta?.warnings || []).length],
    ["suppressed warnings", suppressedWarnings.length],
    ["debug warnings", debugWarnings.length],
  ];
  const setPageDiagnosticRows = [
    ["shell payload ready", setShellContract?.contractVersion ? "yes" : "no"],
    ["cards fetch state", checklistState.status],
    ["market dashboard state", activeMarketDashboardState.status],
    ["set value history state", activeDirectSetValueState.status],
    ["simulation drivers", `${simulationDrivers.rows.length} rows`],
    ["top hits source", simulationDrivers.diagnostics?.source || "missing"],
    ["stale cards cache", getCachedPokemonSetCards(resolvedSetResourceId) ? "available" : "none"],
    // Diagnostics only. Names WHICH canonical V7 shape answered, so a stale
    // snapshot (neither shape present) is visible here as "none" rather than
    // being inferred from an unavailable card.
    ["canonical rip source", heroScoreSelection.sourceShape || "none"],
  ];

  const handleTargetIdChange = (nextTargetId, options = {}) => {
    if (!nextTargetId) {
      return;
    }
    if (String(nextTargetId) === String(requestedTargetId || "")) {
      return;
    }

    if (typeof options.closeToolsPanel === "function") {
      options.closeToolsPanel();
    }

    const nextHref = setDetailMode
      ? appendSetDetailIntentToHref(targetHrefById?.[nextTargetId] || null, { tab: setDetailTab })
      : targetHrefById?.[nextTargetId] || null;

    setPendingTargetId(nextTargetId);
    warmSetDetailResources(nextTargetId, { reason: "selection" });
    announceNavigationStart({
      href: nextHref,
      source: setDetailMode ? "set-to-set" : "target-select",
    });
    debugLoadingTiming("set_to_set_transition_start", {
      targetId: nextTargetId,
      href: nextHref,
    });

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

  const handleHeroSetSelect = (target) => {
    revealMobileSetContext();
    handleTargetIdChange(String(target?.target_id || ""));
    setHeroSetPickerOpen(false);
  };

  const handleSetPickerKeyDown = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      return;
    }
    const options = Array.from(event.currentTarget.querySelectorAll('[role="option"]:not(:disabled)'));
    if (options.length === 0) {
      return;
    }
    event.preventDefault();
    const currentIndex = options.indexOf(document.activeElement);
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? options.length - 1
          : event.key === "ArrowDown"
            ? (currentIndex + 1 + options.length) % options.length
            : (currentIndex - 1 + options.length) % options.length;
    options[nextIndex]?.focus();
  };

  const handleTargetChange = (event, options = {}) => {
    const nextTargetId = String(event.target.value || "").trim();
    handleTargetIdChange(nextTargetId, options);
  };

  const handleTargetPrefetch = (targetId, options = {}) => {
    warmSetDetailResources(targetId, options);
    const prefetchHref = targetHrefById?.[String(targetId || "")] || null;
    if (prefetchHref) {
      router.prefetch(prefetchHref);
    }
  };

  useEffect(() => {
    setPendingTargetId(null);
    debugLoadingTiming("critical_data_ready", {
      label: setDetailMode ? "set-route-shell" : "rip-statistics-route-shell",
      targetId: requestedTargetId,
    });
  }, [requestedTargetId, setDetailMode]);

  useEffect(() => {
    if (!heroSetPickerOpen || typeof document === "undefined") {
      return undefined;
    }

    // The control that opened the menu, so Escape hands focus back to it
    // instead of dropping the user at the top of the document. Captured at open
    // time rather than looked up on dismiss, because arrow-key navigation moves
    // focus into the listbox and more than one picker trigger exists in the DOM
    // (desktop and mobile compositions are both mounted).
    const opener =
      document.activeElement instanceof HTMLElement &&
      document.activeElement.matches?.('[aria-haspopup="listbox"]')
        ? document.activeElement
        : null;

    const handleOutsideClick = (event) => {
      if (!event.target.closest?.("[data-set-picker]")) {
        setHeroSetPickerOpen(false);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setHeroSetPickerOpen(false);
        const fallback = document.querySelector(
          '[aria-haspopup="listbox"][aria-expanded="true"]:not([aria-hidden="true"])'
        );
        (opener || fallback)?.focus?.();
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
    if (!setDetailMode) {
      return undefined;
    }
    const setId = resolvedSetResourceId;
    if (!setId) {
      return undefined;
    }
    debugSetPagePerf("set.bootstrap_ready", {
      routeSetId: requestedTargetId,
      selectedTargetId: selectedTarget?.target_id,
      resolvedSetId: setId,
    });
    markSetPagePerformance("set_shell_ready", {
      routeSetId: requestedTargetId,
      selectedTargetId: selectedTarget?.target_id,
      resolvedSetId: setId,
    });
    return schedulePostShellWarmup(() => {
      warmSetDetailResources(setId, { includeAdjacent: false, reason: "bootstrap" });
    });
  }, [setDetailMode, requestedTargetId, selectedTarget?.target_id, resolvedSetResourceId, warmSetDetailResources]);

  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    if (!setId) {
      setChecklistState((previous) => ({
        status: "empty",
        setId: null,
        cards: previous?.cards || [],
        cardAppealMarketPriceCorrelation: previous?.cardAppealMarketPriceCorrelation || null,
        error: null,
      }));
      return undefined;
    }
    const snapshotCards = initialSetPageDataSeed.cards;
    const seededCorrelation = resolvePreferredCardAppealCorrelation({
      explorePayload,
      cardsPayload: initialCardsPayload,
      previous: initialCardAppealMarketPriceCorrelation,
    });
    if (!canFetchSetDetailModules) {
      setChecklistState((previous) => ({
        status:
          (previous.status === "success" || previous.status === "success_stale") && previous.setId === setId
            ? previous.status
            : "empty",
        setId,
        cards:
          (previous.status === "success" || previous.status === "success_stale") && previous.setId === setId
            ? previous.cards
            : snapshotCards,
        cardAppealMarketPriceCorrelation: resolvePreferredCardAppealCorrelation({
          explorePayload,
          cardsPayload: initialCardsPayload,
          previous: previous?.cardAppealMarketPriceCorrelation,
        }),
        error: null,
      }));
      return undefined;
    }

    // Cards tab no longer triggers this live fetch (it uses
    // getPokemonSetCardsPage instead, see the cardsPageState effect below) —
    // only Insights needs card validation rows + correlation, sourced from
    // the slim getPokemonSetCardsValidation contract (Phase 3C) rather than
    // the full legacy /cards payload. The cache/snapshot seeding above this
    // line still runs unconditionally, so an already-seeded/cached payload
    // (e.g. from a prior Insights visit, or a legacy full cardsPayload if
    // one happens to be present) still seeds checklistState for free.
    const shouldRenderChecklist = setDetailTab === "insights";
    const cachedPayload = checklistCacheRef.current.get(setId) || getCachedPokemonSetCards(setId) || null;
    const cachedCards = Array.isArray(cachedPayload) ? cachedPayload : Array.isArray(cachedPayload?.cards) ? cachedPayload.cards : [];
    const cachedCorrelation = resolvePreferredCardAppealCorrelation({
      explorePayload,
      cardsPayload: Array.isArray(cachedPayload) ? null : cachedPayload,
      previous: checklistState.cardAppealMarketPriceCorrelation,
    });
    const seededCards = cachedCards.length > 0 ? cachedCards : snapshotCards;
    if (seededCards.length > 0) {
      setChecklistState((previous) => ({
        status: previous?.setId === setId && previous?.status === "success_stale" ? "success_stale" : "success",
        setId,
        cards: seededCards,
        cardAppealMarketPriceCorrelation: cachedCorrelation,
        error: previous?.setId === setId && previous?.status === "success_stale" ? previous.error : null,
      }));
      if (!shouldRenderChecklist) {
        return undefined;
      }
    }

    if (!shouldRenderChecklist && seededCards.length > 0) {
      return undefined;
    }
    if (!shouldRenderChecklist) {
      warmSetDetailResources(setId, { reason: "cards-background" });
      return undefined;
    }

    const cardsValidationRequestKey = String(setId);
    if (lastCardsValidationRequestKeyRef.current === cardsValidationRequestKey) {
      debugSetPagePerf("cards.tab_fetch_skipped_duplicate", { resolvedSetId: setId });
      return undefined;
    }
    lastCardsValidationRequestKeyRef.current = cardsValidationRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    const clickStartedAt = performance.now();
    debugSetPagePerf("cards.tab_fetch_start", {
      routeSetId: requestedTargetId,
      selectedTargetId: selectedTarget?.target_id,
      resolvedSetId: setId,
    });
    setChecklistState((previous) => ({
      status: previous.setId === setId && previous.cards.length > 0 ? "success_stale" : "loading",
      setId,
      cards:
        previous.setId === setId && previous.cards.length > 0
          ? previous.cards
          : seededCards,
      cardAppealMarketPriceCorrelation: resolvePreferredCardAppealCorrelation({
        explorePayload,
        cardsPayload: Array.isArray(cachedPayload) ? null : cachedPayload,
        previous: previous?.cardAppealMarketPriceCorrelation || seededCorrelation,
      }),
      error: null,
    }));

    getPokemonSetCardsValidation(setId)
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          debugSetPagePerf("cards.tab_fetch_stale", { setId, activeSetResourceId: activeSetResourceIdRef.current });
          return;
        }
        const cards = Array.isArray(payload?.cards) ? payload.cards : [];
        checklistCacheRef.current.set(setId, payload);
        setChecklistState((previous) => {
          const correlation = resolvePreferredCardAppealCorrelation({
            explorePayload,
            cardsPayload: payload,
            previous: previous?.cardAppealMarketPriceCorrelation,
          });
          if (cards.length > 0) {
            return {
              status: "success",
              setId,
              cards,
              cardAppealMarketPriceCorrelation: correlation,
              error: null,
            };
          }
          const previousCards = previous?.setId === setId ? previous.cards : [];
          const preserveCards = previousCards.length > 0 ? previousCards : seededCards;
          if (preserveCards.length > 0) {
            return {
              status: "success_stale",
              setId,
              cards: preserveCards,
              cardAppealMarketPriceCorrelation: correlation,
              error: "Cards refresh returned empty; showing snapshot-backed cards.",
            };
          }
          return {
            status: isExplicitNoCardsPayload(payload) ? "empty" : "success_stale",
            setId,
            cards: [],
            cardAppealMarketPriceCorrelation: correlation,
            error: isExplicitNoCardsPayload(payload)
              ? null
              : "Cards refresh returned no rows; retrying with snapshot-first state.",
          };
        });
        debugSetPagePerf("cards.tab_ready", {
          setId,
          elapsedMs: Math.round(performance.now() - clickStartedAt),
          count: cards.length,
        });
        debugLoadingTiming("critical_data_ready", {
          label: "cards-tab",
          setId,
          elapsedMs: Math.round(performance.now() - clickStartedAt),
          count: cards.length,
        });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastCardsValidationRequestKeyRef.current === cardsValidationRequestKey) {
          lastCardsValidationRequestKeyRef.current = null;
        }
        if (isCancelled) {
          return;
        }
        setChecklistState((previous) => ({
          status:
            previous.setId === setId && previous.cards.length > 0
              ? "success_stale"
              : "error",
          setId,
          cards: previous.setId === setId && previous.cards.length > 0 ? previous.cards : seededCards,
          cardAppealMarketPriceCorrelation: resolvePreferredCardAppealCorrelation({
            explorePayload,
            cardsPayload: initialCardsPayload,
            previous: previous?.cardAppealMarketPriceCorrelation,
          }),
          error: error?.message || "Unable to load cards for this set.",
        }));
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again.
      if (!requestSettled && lastCardsValidationRequestKeyRef.current === cardsValidationRequestKey) {
        lastCardsValidationRequestKeyRef.current = null;
      }
    };
  }, [
    setDetailMode,
    setDetailTab,
    cardsSubTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    warmSetDetailResources,
    canFetchSetDetailModules,
    explorePayload,
    initialCardsPayload,
    initialSetPageDataSeed,
    initialCardAppealMarketPriceCorrelation,
  ]);

  // Cards tab: slim, paginated fetch (getPokemonSetCardsPage) instead of the
  // full /cards payload above. Refetches whenever the set, page, sort,
  // movement filter, or search query changes. Pages beyond the first are
  // appended to the accumulated list (infinite scroll) as long as they belong
  // to the same scope (set + sort + search + movement filter); a scope change
  // rewinds cardsPage to 1 and the page-1 response replaces the list.
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    if (!setId) {
      setCardsPageState({ status: "empty", setId: null, scopeKey: null, page: 1, cards: [], pagination: null, filters: null, meta: null, error: null });
      return undefined;
    }
    if (!canFetchSetDetailModules) {
      setCardsPageState((previous) => ({
        status: previous.setId === setId && previous.cards.length > 0 ? previous.status : "empty",
        setId,
        scopeKey: previous.setId === setId ? previous.scopeKey : null,
        page: cardsPage,
        cards: previous.setId === setId ? previous.cards : [],
        pagination: previous.setId === setId ? previous.pagination : null,
        filters: previous.setId === setId ? previous.filters : null,
        meta: previous.setId === setId ? previous.meta : null,
        error: null,
      }));
      return undefined;
    }

    const shouldRenderCardsPage = setDetailTab === "cards" && cardsSubTab === "checklist";
    if (!shouldRenderCardsPage) {
      return undefined;
    }

    const requestedPage = cardsPage;
    const movementSortValue = effectiveCardMovementSort;
    // Percent vs dollar ranking is resolved server-side, so it is part of the
    // request scope: switching metric must restart the list at page one rather
    // than append a differently-ranked chunk onto the loaded pages.
    const movementMetricValue = effectiveCardMovementMetric;
    // Market Movers is the SAME canonical Cards dataset with mover-membership
    // filtering applied server-side (section=market-movers); All Cards keeps
    // the complete checklist. Same snapshot, same normalization, same
    // movement values — only the query mode differs.
    const cardsSectionValue = cardsSection === "market-movers" ? "market-movers" : "all-cards";

    // Everything except the page number — `cardsPageState.scopeKey` records
    // which scope the accumulated cards belong to, so a late response can
    // never append into a different set/sort/search/filter view (stale-scope
    // guard on top of the effect-cleanup cancellation below).
    const cardsPageScopeKey = [
      setId,
      PRICING_SNAPSHOT_CONTRACT_VERSION,
      cardsSectionValue,
      effectiveCardSortMode,
      cardsRequest.sortDirection,
      cardSearchQuery.trim(),
      effectiveCardRarityFilter || "",
      effectiveCardMovementFilter,
      movementSortValue,
      movementMetricValue || "",
    ].join("|");
    // Leaving Cards and coming back (or any other re-render that re-triggers
    // this effect, e.g. a sibling tab's payload updating explorePayload)
    // re-evaluates this effect even though the set/page/sort/filter/query
    // haven't actually changed. Skip re-issuing the exact same request —
    // getPokemonSetCardsPage's own in-flight join only catches concurrent
    // duplicates, not these later, non-overlapping repeats. (A failed request
    // clears the key, so the Retry nonce can re-enter with the same key.)
    const cardsPageRequestKey = `${cardsPageScopeKey}|page:${requestedPage}`;
    if (requestedPage > 1 && cardsLoadMoreGateRef.current.stateScopeKey !== cardsPageScopeKey) {
      // Sort/search/filter just changed while the page counter still points
      // into the previous scope — the scope-reset effect rewinds cardsPage to
      // 1 in this same commit, so don't issue a page-N fetch of the new scope
      // that would only be cancelled (or worse, render a mid-list chunk).
      debugSetPagePerf("cards_page.tab_fetch_skipped_scope_change", { resolvedSetId: setId, requestKey: cardsPageRequestKey });
      return undefined;
    }
    if (lastCardsPageRequestKeyRef.current === cardsPageRequestKey) {
      debugSetPagePerf("cards_page.tab_fetch_skipped_duplicate", { resolvedSetId: setId, requestKey: cardsPageRequestKey });
      return undefined;
    }
    lastCardsPageRequestKeyRef.current = cardsPageRequestKey;
    activeCardsPageRequestKeyRef.current = cardsPageRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    debugSetPagePerf("cards_page.tab_fetch_start", {
      resolvedSetId: setId,
      page: requestedPage,
      sort: effectiveCardSortMode,
      sortDirection: cardsRequest.sortDirection,
      movementFilter: effectiveCardMovementFilter,
    });
    setCardsPageState((previous) => {
      const sameScope = previous.setId === setId && previous.scopeKey === cardsPageScopeKey;
      if (requestedPage > 1 && sameScope && previous.cards.length > 0) {
        // Loading a further chunk of the list already on screen — keep every
        // rendered card in place and only surface the bottom loader.
        return { ...previous, status: "loading_more", error: null };
      }
      return {
        // Page one owns a complete request identity. Clear every page from
        // the previous set/sort/search/rarity/movement scope immediately so
        // stale prices or deltas cannot remain visible under fresh controls.
        status: "loading",
        setId,
        scopeKey: cardsPageScopeKey,
        page: requestedPage,
        cards: [],
        pagination: null,
        filters: null,
        meta: null,
        error: null,
      };
    });

    const cardsFetchStartedAt = typeof performance !== "undefined" ? performance.now() : Date.now();

    getPokemonSetCardsPage(setId, {
      page: requestedPage,
      pageSize: CARDS_PAGE_SIZE,
      sort: effectiveCardSortMode,
      sortDirection: cardsRequest.sortDirection,
      query: cardSearchQuery.trim() || null,
      rarity: effectiveCardRarityFilter,
      movementFilter: effectiveCardMovementFilter,
      movementSort: movementSortValue,
      movementMetric: movementMetricValue,
      section: cardsSectionValue,
    })
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          return;
        }
        if (activeCardsPageRequestKeyRef.current !== cardsPageRequestKey) {
          debugSetPagePerf("cards_page.tab_fetch_stale_identity", { setId, requestKey: cardsPageRequestKey });
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          debugSetPagePerf("cards_page.tab_fetch_stale", { setId, activeSetResourceId: activeSetResourceIdRef.current });
          return;
        }
        setCardsPageState((previous) => {
          if (activeCardsPageRequestKeyRef.current !== cardsPageRequestKey) {
            return previous;
          }
          const shouldAppend =
            requestedPage > 1 &&
            previous.setId === setId &&
            previous.scopeKey === cardsPageScopeKey &&
            previous.cards.length > 0;
          const mergedCards = shouldAppend
            ? dedupeChecklistCards([...previous.cards, ...payload.cards])
            : payload.cards;
          return {
            status: mergedCards.length > 0 ? "success" : "empty",
            setId,
            scopeKey: cardsPageScopeKey,
            page: payload.pagination?.page ?? requestedPage,
            cards: mergedCards,
            pagination: payload.pagination,
            filters: payload.filters,
            meta: payload.meta || null,
            error: null,
          };
        });
        // Section-level timing (see lib/perf/sectionTiming.js): the first
        // page load reports cardsFirstBatchMs (grid becomes usable), every
        // subsequent IntersectionObserver-triggered page reports
        // cardsNextBatchMs — a repeatable per-batch event, so this is logged
        // directly here rather than through useSectionTiming (which reports
        // a single-shot loading->settled transition per section).
        const cardsBatchElapsedMs = Math.round(
          (typeof performance !== "undefined" ? performance.now() : Date.now()) - cardsFetchStartedAt
        );
        const cardsBatchMetricName = requestedPage > 1 ? "cardsNextBatch" : "cardsFirstBatch";
        markSectionTiming(`${cardsBatchMetricName}_success`, {
          setId,
          tab: "cards",
          page: requestedPage,
          elapsedMs: cardsBatchElapsedMs,
        });
        debugSectionTiming("[section-timing]", `${cardsBatchMetricName}Ms`, {
          setId,
          tab: "cards",
          page: requestedPage,
          elapsedMs: cardsBatchElapsedMs,
        });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastCardsPageRequestKeyRef.current === cardsPageRequestKey) {
          lastCardsPageRequestKeyRef.current = null;
        }
        if (isCancelled) {
          return;
        }
        if (activeCardsPageRequestKeyRef.current !== cardsPageRequestKey) {
          return;
        }
        setCardsPageState((previous) => ({
          status: previous.setId === setId && previous.cards.length > 0 ? "success_stale" : "error",
          setId,
          scopeKey: previous.setId === setId ? previous.scopeKey : null,
          page: requestedPage,
          cards: previous.setId === setId ? previous.cards : [],
          pagination: previous.setId === setId ? previous.pagination : null,
          filters: previous.setId === setId ? previous.filters : null,
          meta: previous.setId === setId ? previous.meta : null,
          error: error?.message || "Unable to load cards for this set.",
        }));
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again — otherwise the tab could sit
      // on its loading state forever with the key still claimed.
      if (!requestSettled && lastCardsPageRequestKeyRef.current === cardsPageRequestKey) {
        lastCardsPageRequestKeyRef.current = null;
      }
    };
  }, [
    setDetailMode,
    setDetailTab,
    cardsSubTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSetDetailModules,
    cardsPage,
    cardsPageRetryNonce,
    cardsSection,
    effectiveCardSortMode,
    cardsRequest.sortDirection,
    effectiveCardMovementSort,
    effectiveCardMovementMetric,
    effectiveCardMovementFilter,
    cardSearchQuery,
    effectiveCardRarityFilter,
  ]);

  // Pull Rates tab fetch effect (Phase 4A): slim, dedicated fetch
  // (getPokemonSetPullRates) instead of the full /page payload — see the
  // pullRateAssumptions derivation above for the fallback-to-explorePayload
  // behavior.
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    if (!setId) {
      setPullRatesState({ status: "idle", setId: null, pullRateAssumptions: null, error: null });
      return undefined;
    }
    if (!canFetchSetDetailModules) {
      setPullRatesState((previous) => ({
        status: previous.setId === setId ? previous.status : "idle",
        setId,
        pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
        error: null,
      }));
      return undefined;
    }
    if (setDetailTab !== "pull-rates" && setDetailTab !== "overview") {
      return undefined;
    }

    const pullRatesRequestKey = String(setId);
    if (lastPullRatesRequestKeyRef.current === pullRatesRequestKey) {
      debugSetPagePerf("pull_rates.tab_fetch_skipped_duplicate", { resolvedSetId: setId });
      return undefined;
    }
    lastPullRatesRequestKeyRef.current = pullRatesRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    setPullRatesState((previous) => ({
      status: previous.setId === setId && previous.pullRateAssumptions ? "success_stale" : "loading",
      setId,
      pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
      error: null,
    }));

    getPokemonSetPullRates(setId)
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          return;
        }
        setPullRatesState({
          status: payload?.pullRateAssumptions ? "success" : "empty",
          setId,
          pullRateAssumptions: payload?.pullRateAssumptions || null,
          error: null,
        });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastPullRatesRequestKeyRef.current === pullRatesRequestKey) {
          lastPullRatesRequestKeyRef.current = null;
        }
        if (isCancelled) {
          return;
        }
        setPullRatesState((previous) => ({
          status: previous.setId === setId && previous.pullRateAssumptions ? "success_stale" : "error",
          setId,
          pullRateAssumptions: previous.setId === setId ? previous.pullRateAssumptions : null,
          error: error?.message || "Unable to load pull rate assumptions for this set.",
        }));
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again — otherwise the tab could sit
      // on its loading state forever with the key still claimed.
      if (!requestSettled && lastPullRatesRequestKeyRef.current === pullRatesRequestKey) {
        lastPullRatesRequestKeyRef.current = null;
      }
    };
  }, [setDetailMode, setDetailTab, requestedTargetId, selectedTarget, resolvedSetResourceId, canFetchSetDetailModules]);

  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    if (!setId) {
      setSetValueHistoryState(createSetValueHistoryState({ status: "empty" }));
      return undefined;
    }
    if (!canFetchSetDetailModules) {
      setSetValueHistoryState((previous) =>
        previous?.setId === setId && previous.status === "success"
          ? previous
          : createSetValueHistoryState({ status: "empty", setId })
      );
      return undefined;
    }

    // Prefer the already-loaded market dashboard state for this set (live
    // reducer state, then a raw cache read) over issuing a brand-new
    // /market/value-history request for scopes that live data already has.
    const cachedDashboardPayload = getCachedPokemonSetMarketDashboard(setId, {
      window: DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW,
    });
    const liveMarketDashboardHistoriesByScope =
      activeMarketDashboardState.setId === setId
        ? activeMarketDashboardDerivedState.setValue.historiesByScope
        : {};
    const marketDashboardSetValue = hasAnySetValueHistory(liveMarketDashboardHistoriesByScope)
      ? { historiesByScope: liveMarketDashboardHistoriesByScope, availableScopes: activeMarketDashboardDerivedState.setValue.availableScopes }
      : adaptSetValueHistoriesFromSources({
          explorePayload,
          marketSnapshotPayload: cachedDashboardPayload,
        });
    const seededSetValueFromSnapshot = {
      historiesByScope: initialSetPageDataSeed.setValueHistoriesByScope,
      availableScopes: SET_VALUE_SCOPE_OPTIONS,
    };
    const seededSetValue = hasAnySetValueHistory(seededSetValueFromSnapshot.historiesByScope)
      ? seededSetValueFromSnapshot
      : marketDashboardSetValue;
    const seededHistoriesByScope = seededSetValue?.historiesByScope || {};
    const seededLoadedScopes = SET_VALUE_SCOPE_OPTIONS.map((scope) => scope.key).filter(
      (scope) => Array.isArray(seededHistoriesByScope?.[scope]) && seededHistoriesByScope[scope].length > 0
    );

    if (seededLoadedScopes.length > 0) {
      setSetValueHistoryState((previous) => {
        const mergedHistoriesByScope = {
          ...(previous?.setId === setId ? previous.historiesByScope || {} : {}),
          ...seededHistoriesByScope,
        };
        const mergedLoadedScopes = Array.from(new Set([...(previous?.loadedScopes || []), ...seededLoadedScopes]));
        return createSetValueHistoryState({
          status: hasAnySetValueHistory(mergedHistoriesByScope) ? "success" : "idle",
          setId,
          historiesByScope: mergedHistoriesByScope,
          loadedScopes: mergedLoadedScopes,
          availableScopes: seededSetValue?.availableScopes || SET_VALUE_SCOPE_OPTIONS,
          meta: previous?.meta || null,
        });
      });
    }

    if (hasCompleteSetValueScopes(seededHistoriesByScope)) {
      debugSetPagePerf("set_value.direct_fetch_skipped", {
        setId,
        reason: "snapshot_has_all_scopes",
      });
      return undefined;
    }

    // The header/title set value always needs the canonical "standard" scope.
    // "hits"/"top10" are only needed once the overview Set Value Trend card is
    // actually visible (or the user has picked that scope there) — not on
    // every set switch regardless of which tab is active.
    const desiredScopes = Array.from(
      new Set([
        CANONICAL_SET_VALUE_SCOPE,
        ...(setDetailTab === "overview" ? [setValueTrendScope || CANONICAL_SET_VALUE_SCOPE] : []),
      ])
    );
    // This effect re-runs on every tab switch (setDetailTab is a dependency,
    // since Overview also needs setValueTrendScope), but seededLoadedScopes
    // above only reflects server-seeded/dashboard-cached data — it never
    // reflects a scope this very effect already fetched on an earlier run.
    // Without also checking the live setValueHistoryState here, switching
    // Cards -> Pull Rates -> Insights -> Overview re-issues an identical
    // /market/value-history?scope=standard request at every stop even though
    // nothing about the request key changed.
    const alreadyLoadedScopes =
      setValueHistoryState.setId === setId ? setValueHistoryState.loadedScopes || [] : [];
    const requestedScopes = desiredScopes.filter(
      (scope) => !seededLoadedScopes.includes(scope) && !alreadyLoadedScopes.includes(scope)
    );
    if (requestedScopes.length === 0) {
      return undefined;
    }
    let isCancelled = false;
    const clickStartedAt = performance.now();

    setSetValueHistoryState((previous) =>
      previous.setId === setId
        ? createSetValueHistoryState({
            ...previous,
            status:
              previous.status === "success" || previous.status === "success_stale" || previous.status === "empty"
                ? previous.status
                : "loading",
            error: null,
          })
        : createSetValueHistoryState({ status: "loading", setId })
    );

    debugSetPagePerf("set_value.direct_fetch_start", {
      resolvedSetId: setId,
      scopes: requestedScopes,
    });

    Promise.all(
      requestedScopes.map((scope) =>
        getPokemonSetValueHistory(setId, { days: 365, scope }).then((payload) => ({
          scope,
          payload,
        }))
      )
    )
      .then((results) => {
        if (isCancelled) {
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          debugSetPagePerf("set_value.direct_fetch_stale", { setId, activeSetResourceId: activeSetResourceIdRef.current });
          return;
        }

        const historiesByScope = {};
        const loadedScopes = [];
        const availableScopeLookup = new Map();
        let selectedMeta = null;
        results.forEach(({ scope, payload }) => {
          const payloadSetId = toStableIdentifier(payload?.set?.id ?? payload?.set_id);
          const payloadScope = String((payload?.meta?.valueScope ?? payload?.meta?.value_scope ?? scope) || "").trim() || scope;
          if (payloadSetId && payloadSetId !== setId) {
            debugSetPagePerf("set_value.direct_fetch_ignored", {
              requestedSetId: setId,
              payloadSetId,
              scope,
              reason: "set_mismatch",
            });
            return;
          }
          if (payloadScope !== scope) {
            debugSetPagePerf("set_value.direct_fetch_ignored", {
              setId,
              scope,
              payloadScope,
              reason: "scope_mismatch",
            });
            return;
          }
          historiesByScope[scope] = Array.isArray(payload?.history) ? payload.history : [];
          loadedScopes.push(scope);
          if (!selectedMeta || scope === CANONICAL_SET_VALUE_SCOPE) {
            selectedMeta = payload?.meta || null;
          }
          (payload?.meta?.availableScopes || []).forEach((entry) => {
            if (entry?.key) {
              availableScopeLookup.set(entry.key, entry);
            }
          });
        });
        const availableScopes = SET_VALUE_SCOPE_OPTIONS.map((entry) => availableScopeLookup.get(entry.key) || entry);
        setSetValueHistoryState((previous) => {
          const shouldMergePrevious = previous?.setId === setId;
          const mergedHistoriesByScope = shouldMergePrevious
            ? {
                ...(previous.historiesByScope || {}),
                ...historiesByScope,
              }
            : historiesByScope;
          const mergedLoadedScopes = shouldMergePrevious
            ? Array.from(new Set([...(previous.loadedScopes || []), ...loadedScopes]))
            : loadedScopes;
          const mergedHasHistory = Object.values(mergedHistoriesByScope).some((history) => history.length > 0);

          return createSetValueHistoryState({
            status: mergedHasHistory ? "success" : "empty",
            setId,
            historiesByScope: mergedHistoriesByScope,
            loadedScopes: mergedLoadedScopes,
            availableScopes,
            meta: selectedMeta || previous?.meta || null,
          });
        });
        debugSetPagePerf("set_value.direct_fetch_ready", {
          setId,
          scopes: loadedScopes,
          elapsedMs: Math.round(performance.now() - clickStartedAt),
          standardPoints: historiesByScope[CANONICAL_SET_VALUE_SCOPE]?.length || 0,
        });
      })
      .catch((error) => {
        if (isCancelled) {
          return;
        }
        setSetValueHistoryState((previous) =>
          previous?.setId === setId && Object.values(previous.historiesByScope || {}).some((history) => history.length > 0)
            ? createSetValueHistoryState({
                ...previous,
                status: "success_stale",
                error: error?.message || "Unable to load set value history for this set.",
              })
            :
          createSetValueHistoryState({
            status: "error",
            setId,
            error: error?.message || "Unable to load set value history for this set.",
          })
        );
      });

    return () => {
      isCancelled = true;
    };
  }, [
    setDetailMode,
    setDetailTab,
    setValueTrendScope,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSetDetailModules,
    explorePayload,
    initialSetPageDataSeed,
    activeMarketDashboardState.setId,
    activeMarketDashboardDerivedState,
  ]);

  // Top Chase Cards and Market Movers now fetch their own slim
  // /market/top-chase and /market/movers endpoints (see the two effects
  // below). This effect no longer issues a live /market/dashboard fetch — it
  // only hydrates marketDashboardState from an already-seeded/cached payload,
  // which both modules read as a temporary safety-net fallback until their
  // own fetches land (see activeTopMarketCardsState above).
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    const dashboardSourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW;
    if (!setId) {
      dispatchMarketDashboard({ type: "reset", status: "empty", sourceWindow: dashboardSourceWindow });
      return undefined;
    }
    if (!canFetchSetDetailModules) {
      dispatchMarketDashboard({
        type: "reset",
        status: "empty",
        setId,
        sourceWindow: dashboardSourceWindow,
      });
      return undefined;
    }

    const shouldRenderMarketData = setDetailTab === "overview";
    if (!shouldRenderMarketData) {
      // No background hydration for a tab the user isn't on — overview's own
      // render (or a future switch back to it) triggers this effect again.
      return undefined;
    }

    const seededDashboardPayload = initialSetPageDataSeed.marketDashboard;
    const cachedDashboard = getCachedPokemonSetMarketDashboard(setId, { window: dashboardSourceWindow });
    const mergedCachedDashboard = cachedDashboard || seededDashboardPayload;
    const cachedMarketDashboardState = hydrateMarketDashboardStateFromCachedPayload({
      setId,
      cachedPayload: mergedCachedDashboard,
      sourceWindow: dashboardSourceWindow,
    });

    if (cachedMarketDashboardState) {
      if (isDevPerfLoggingEnabled) {
        // Dev-only signal that a legacy /market/dashboard payload (SSR seed or
        // a cache entry from some other legacy caller of
        // getPokemonSetMarketDashboard) is still backing the temporary
        // fallback path for Top Chase Cards/Market Movers. Expected to fire
        // rarely now that both modules fetch their own slim endpoints; if it
        // fires often, something is still populating the legacy cache.
        console.warn(
          "[pokemon-set-perf] Overview is using a legacy /market/dashboard payload as a fallback for Top Chase Cards/Market Movers — this should only happen briefly before /market/top-chase and /market/movers finish loading.",
          { setId }
        );
      }
      dispatchMarketDashboard({
        type: "success",
        setId,
        payload: cachedMarketDashboardState.payload,
        sourceWindow: dashboardSourceWindow,
      });
    }
    return undefined;
  }, [
    setDetailMode,
    setDetailTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSetDetailModules,
    explorePayload,
    initialSetPageDataSeed,
  ]);

  // Slim /market/top-chase fetch — Top Chase Cards no longer depends on the
  // monolithic /market/dashboard fetch.
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    const topChaseSourceWindow = DEFAULT_TOP_CHASE_MARKET_WINDOW;
    if (!setId) {
      dispatchTopChase({ type: "reset", status: "empty", sourceWindow: topChaseSourceWindow });
      return undefined;
    }
    if (!canFetchSlimMarketModules) {
      dispatchTopChase({
        type: "reset",
        status: "empty",
        setId,
        sourceWindow: topChaseSourceWindow,
      });
      return undefined;
    }

    const shouldRenderOverviewData = setDetailTab === "overview";
    if (!shouldRenderOverviewData) {
      return undefined;
    }

    const topChaseRequestKey = `${setId}|${topChaseSourceWindow}`;
    const topChaseStateIsRenderable =
      activeTopChaseState.status === "loading" ||
      activeTopChaseState.status === "success" ||
      activeTopChaseState.status === "success_stale";
    if (lastTopChaseRequestKeyRef.current === topChaseRequestKey && topChaseStateIsRenderable) {
      debugSetPagePerf("top_chase.tab_fetch_skipped_duplicate", { resolvedSetId: setId });
      return undefined;
    }
    if (lastTopChaseRequestKeyRef.current === topChaseRequestKey && !topChaseStateIsRenderable) {
      lastTopChaseRequestKeyRef.current = null;
    }
    lastTopChaseRequestKeyRef.current = topChaseRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    dispatchTopChase({ type: "loading", setId, sourceWindow: topChaseSourceWindow });

    getPokemonSetTopChase(setId, { window: topChaseSourceWindow, limit: 10 })
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          if (lastTopChaseRequestKeyRef.current === topChaseRequestKey) {
            lastTopChaseRequestKeyRef.current = null;
          }
          dispatchTopChase({ type: "reset", status: "empty", setId, sourceWindow: topChaseSourceWindow });
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          debugSetPagePerf("top_chase.tab_fetch_stale", { setId, activeSetResourceId: activeSetResourceIdRef.current });
          if (lastTopChaseRequestKeyRef.current === topChaseRequestKey) {
            lastTopChaseRequestKeyRef.current = null;
          }
          dispatchTopChase({ type: "reset", status: "empty", setId, sourceWindow: topChaseSourceWindow });
          return;
        }
        dispatchTopChase({ type: "success", setId, payload, sourceWindow: topChaseSourceWindow });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastTopChaseRequestKeyRef.current === topChaseRequestKey) {
          lastTopChaseRequestKeyRef.current = null;
        }
        if (isCancelled) {
          dispatchTopChase({ type: "reset", status: "empty", setId, sourceWindow: topChaseSourceWindow });
          return;
        }
        dispatchTopChase({
          type: "error",
          setId,
          error: error?.message || "Unable to load top chase cards for this set.",
          sourceWindow: topChaseSourceWindow,
        });
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again.
      if (!requestSettled && lastTopChaseRequestKeyRef.current === topChaseRequestKey) {
        lastTopChaseRequestKeyRef.current = null;
      }
    };
  }, [
    setDetailMode,
    setDetailTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSlimMarketModules,
    // Section-local Retry: re-runs this effect only (see retryTopChaseModule).
    topChaseRetryNonce,
  ]);

  // Slim /market/movers fetch for the selected 1D/7D/30D window — Market
  // Movers no longer depends on the monolithic /market/dashboard fetch
  // either, and refetches whenever the selected window changes.
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    // The slim movers fetch serves the fixed Overview ticker only. The Cards
    // preset uses the paginated cards endpoint instead.
    const isOverviewMoversConsumer = setDetailTab === "overview";
    const moversSourceWindow = MOVERS_TICKER_WINDOW;
    const moversFetchLimit = MOVERS_TICKER_FETCH_LIMIT;
    if (!setId) {
      dispatchMarketMovers({ type: "reset", status: "empty", sourceWindow: moversSourceWindow });
      return undefined;
    }
    if (!canFetchSlimMarketModules) {
      dispatchMarketMovers({
        type: "reset",
        status: "empty",
        setId,
        sourceWindow: moversSourceWindow,
      });
      return undefined;
    }

    if (!isOverviewMoversConsumer) {
      return undefined;
    }

    const marketMoversRequestKey = `${setId}|${moversSourceWindow}|${moversFetchLimit}`;
    const marketMoversStateIsRenderable =
      activeMarketMoversState.status === "loading" ||
      activeMarketMoversState.status === "success" ||
      activeMarketMoversState.status === "success_stale";
    if (lastMarketMoversRequestKeyRef.current === marketMoversRequestKey && marketMoversStateIsRenderable) {
      debugSetPagePerf("market_movers.tab_fetch_skipped_duplicate", { resolvedSetId: setId });
      return undefined;
    }
    if (lastMarketMoversRequestKeyRef.current === marketMoversRequestKey && !marketMoversStateIsRenderable) {
      lastMarketMoversRequestKeyRef.current = null;
    }
    lastMarketMoversRequestKeyRef.current = marketMoversRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    dispatchMarketMovers({ type: "loading", setId, sourceWindow: moversSourceWindow });

    getPokemonSetMarketMovers(setId, { window: moversSourceWindow, limit: moversFetchLimit })
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          if (lastMarketMoversRequestKeyRef.current === marketMoversRequestKey) {
            lastMarketMoversRequestKeyRef.current = null;
          }
          dispatchMarketMovers({ type: "reset", status: "empty", setId, sourceWindow: moversSourceWindow });
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          debugSetPagePerf("market_movers.tab_fetch_stale", { setId, activeSetResourceId: activeSetResourceIdRef.current });
          if (lastMarketMoversRequestKeyRef.current === marketMoversRequestKey) {
            lastMarketMoversRequestKeyRef.current = null;
          }
          dispatchMarketMovers({ type: "reset", status: "empty", setId, sourceWindow: moversSourceWindow });
          return;
        }
        dispatchMarketMovers({ type: "success", setId, payload, sourceWindow: moversSourceWindow });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastMarketMoversRequestKeyRef.current === marketMoversRequestKey) {
          lastMarketMoversRequestKeyRef.current = null;
        }
        if (isCancelled) {
          dispatchMarketMovers({ type: "reset", status: "empty", setId, sourceWindow: moversSourceWindow });
          return;
        }
        dispatchMarketMovers({
          type: "error",
          setId,
          error: error?.message || "Unable to load market movers for this set.",
          sourceWindow: moversSourceWindow,
        });
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again.
      if (!requestSettled && lastMarketMoversRequestKeyRef.current === marketMoversRequestKey) {
        lastMarketMoversRequestKeyRef.current = null;
      }
    };
  }, [
    setDetailMode,
    setDetailTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSlimMarketModules,
    // Section-local Retry: re-runs this effect only (see retryMarketMoversModule).
    marketMoversRetryNonce,
  ]);

  // Slim /overview fetch for Set Value Trend/Performance vs Cost only.
  // When the route seeded an /overview snapshot (see seededOverviewPayload),
  // this effect still runs but refreshes quietly: the reducer's "loading"
  // case keeps the same-set seeded payload as success_stale, so seeded
  // sections never regress to a loading panel while the refresh is in
  // flight, and the request-key guard below keeps tab revisits from
  // re-fetching the identical set/window.
  useEffect(() => {
    if (!setDetailMode) {
      return undefined;
    }

    const setId = resolvedSetResourceId;
    const overviewSourceWindow = DEFAULT_MARKET_DASHBOARD_SOURCE_WINDOW;
    if (!setId) {
      dispatchOverview({ type: "reset", status: "empty", sourceWindow: overviewSourceWindow });
      return undefined;
    }
    if (!canFetchSlimMarketModules) {
      dispatchOverview({
        type: "reset",
        status: "empty",
        setId,
        sourceWindow: overviewSourceWindow,
      });
      return undefined;
    }

    // Insights needs the slim /overview payload too: its Opening Profit vs
    // Cost / Metrics views merge performanceVsCostHistory with the set-page
    // history_trend (see mergePerformanceHistories), and a direct Insights
    // entry must not depend on the user visiting Overview first to see fresh
    // history. The request-key guard below still makes overview<->insights
    // switches share one fetch per set/window.
    const shouldRenderOverviewData = setDetailTab === "overview" || setDetailTab === "insights";
    if (!shouldRenderOverviewData) {
      // No background fetch for a tab the user isn't on — a tab that needs
      // this data (or a future switch back to one) triggers this effect again.
      return undefined;
    }

    const overviewRequestKey = `${setId}|${overviewSourceWindow}`;
    const overviewStateIsRenderable =
      activeOverviewState.status === "loading" ||
      activeOverviewState.status === "success" ||
      activeOverviewState.status === "success_stale";
    if (lastOverviewRequestKeyRef.current === overviewRequestKey && overviewStateIsRenderable) {
      debugSetPagePerf("overview.tab_fetch_skipped_duplicate", { resolvedSetId: setId });
      return undefined;
    }
    if (lastOverviewRequestKeyRef.current === overviewRequestKey && !overviewStateIsRenderable) {
      lastOverviewRequestKeyRef.current = null;
    }
    lastOverviewRequestKeyRef.current = overviewRequestKey;

    let isCancelled = false;
    let requestSettled = false;
    dispatchOverview({ type: "loading", setId, sourceWindow: overviewSourceWindow });

    getPokemonSetOverview(setId, { window: overviewSourceWindow })
      .then((payload) => {
        requestSettled = true;
        if (isCancelled) {
          if (lastOverviewRequestKeyRef.current === overviewRequestKey) {
            lastOverviewRequestKeyRef.current = null;
          }
          dispatchOverview({ type: "reset", status: "empty", setId, sourceWindow: overviewSourceWindow });
          return;
        }
        if (!isSetStateForActiveSet(setId, { requestedTargetId, selectedTarget, resolvedSetResourceId: activeSetResourceIdRef.current })) {
          if (lastOverviewRequestKeyRef.current === overviewRequestKey) {
            lastOverviewRequestKeyRef.current = null;
          }
          dispatchOverview({ type: "reset", status: "empty", setId, sourceWindow: overviewSourceWindow });
          return;
        }
        dispatchOverview({ type: "success", setId, payload, sourceWindow: overviewSourceWindow });
      })
      .catch((error) => {
        requestSettled = true;
        if (lastOverviewRequestKeyRef.current === overviewRequestKey) {
          lastOverviewRequestKeyRef.current = null;
        }
        if (isCancelled) {
          dispatchOverview({ type: "reset", status: "empty", setId, sourceWindow: overviewSourceWindow });
          return;
        }
        dispatchOverview({
          type: "error",
          setId,
          error: error?.message || "Unable to load set overview for this set.",
          sourceWindow: overviewSourceWindow,
        });
      });

    return () => {
      isCancelled = true;
      // An unsettled request's response will be ignored (isCancelled), so a
      // revisit must be allowed to fetch again.
      if (!requestSettled && lastOverviewRequestKeyRef.current === overviewRequestKey) {
        lastOverviewRequestKeyRef.current = null;
      }
    };
  }, [
    setDetailMode,
    setDetailTab,
    requestedTargetId,
    selectedTarget,
    resolvedSetResourceId,
    canFetchSlimMarketModules,
    // Section-local Retry: re-runs this effect only (see retryOverviewModule).
    overviewRetryNonce,
  ]);

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
              value={displayedTargetId || ""}
              onChange={handleTargetChange}
              onFocus={() => handleTargetPrefetch(requestedTargetId, { includeAdjacent: true, reason: "sidebar-focus" })}
              disabled={isPending || switcherTargets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {switcherTargets.map((target) => (
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
              value={displayedTargetId || ""}
              onChange={(event) => handleTargetChange(event, { closeToolsPanel })}
              onFocus={() => handleTargetPrefetch(requestedTargetId, { includeAdjacent: true, reason: "mobile-focus" })}
              disabled={isPending || switcherTargets.length === 0}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            >
              {switcherTargets.map((target) => (
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
    <main className={setDetailMode ? "w-full max-w-full pb-[calc(5.25rem+env(safe-area-inset-bottom)+0.875rem)] pt-0 desk:pb-8 desk:pt-8" : "w-full max-w-full pb-8 pt-0 lg:py-8"}>
      {/* The set page's desktop boundary is 1200px, not Tailwind's 1280px xl,
          so it opts the shared scaffold into the `desk` recipe. Both strings are
          written out statically. The non-set Explore page renders through this
          same component and keeps `xl`, so nothing else is retuned. */}
      <PublicProfileLocalScaffold
        profileBaseHref={profileBaseHref}
        mode="public"
        sectionItems={[]}
        mobileNavItems={[]}
        desktopSidebarContent={setDetailMode ? null : desktopSidebarContent}
        mobileToolsPanelContent={setDetailMode ? null : renderMobileToolsPanelContent}
        mobileToolsTitle="Explore Filters & Navigation"
        mobileToolsDescription="Switch TCG and set filters."
        mobileToolsPanelAriaLabel="Explore filters and navigation"
        mobileToolsTriggerLabel="Filters & Tools"
        mobileToolsTriggerTitle="Open filters and navigation"
        useFloatingToolsOnTablet={!setDetailMode}
        forceCompactToolsBelow2xl={!setDetailMode}
        centerContentIgnoringSidebar
        desktopSidebarClassName=""
        desktopBreakpoint={setDetailMode ? "desk" : "xl"}
        desktopContentOffsetClassName={setDetailMode ? "desk:flex desk:justify-center" : "xl:flex xl:justify-center"}
        contentShellClassName={
          setDetailMode
            ? "mx-auto w-full max-w-[960px] desk:max-w-[1440px] desk:px-4 2xl:px-5"
            : undefined
        }
        wrapDesktopContentInFrame={false}
        mobileBottomNavVariant="flat"
        hideDesktopSidebar={setDetailMode}
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
          className={`dashboard-container relative isolate w-full max-w-full min-w-0 !p-0 !bg-transparent !border-0 !rounded-none ${
            setDetailMode
              ? "set-detail-glass-scope mx-auto max-w-[1400px] space-y-4 xl:!p-0 xl:!bg-transparent xl:!rounded-none xl:!border-0"
              : "space-y-8 xl:!p-6 xl:!bg-[rgba(255,255,255,0.02)] xl:!rounded-2xl xl:!border"
          }`}
        >
        {setDetailMode && ambientSetArtworkUrl ? (
          <div
            data-set-ambient-artwork
            aria-hidden="true"
            className="set-page-atmosphere pointer-events-none fixed inset-0 -z-10 hidden select-none overflow-hidden bg-no-repeat sm:block"
          >
            {/* Two passes over one cached image URL — the browser fetches it
                once. The bloom copy sits underneath and supplies the glow;
                every opacity/filter/mask value comes from the --set-artwork-*
                tokens in globals.css, never from this markup. */}
            <img
              src={ambientSetArtworkUrl}
              alt=""
              className="set-page-atmosphere-bloom absolute inset-0 h-full w-full object-contain object-center"
              loading="eager"
              decoding="async"
            />
            <img
              src={ambientSetArtworkUrl}
              alt=""
              className="set-page-atmosphere-artwork absolute inset-0 h-full w-full object-contain object-center"
              loading="eager"
              decoding="async"
            />
          </div>
        ) : null}
        {pageError ? (
          <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6">
            <p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p>
            <p className="mt-2 text-sm text-red-300">{pageError}</p>
          </section>
        ) : null}

        {canRenderPrimaryContent ? (
          <>
            {setDetailMode ? (
              <>
                {/* DOM order is tabs -> identity so that below 1200px, where the
                    shell becomes `display: contents`, the tabs land first and
                    their containing block becomes the full-height page
                    container (so they stay pinned for the whole page rather
                    than for the shell's own height). Desktop restores the
                    hero-above-tabs reading order with `desk:order-*` inside the
                    shell's flex column. */}
                <div data-set-context-shell className="set-detail-context-shell overflow-visible rounded-xl desk:flex desk:flex-col md:rounded-2xl">
                <div
                  id="set-detail-content"
                  data-set-detail-sticky-tabs
                  data-mobile-set-context-hidden={isMobileSetContextHidden ? "true" : "false"}
                  ref={mobileSetContextRef}
                  // Below 1200px this block is pinned, and a pinned control has
                  // to read as a solid surface: at 96% opacity plus a blur, the
                  // bright chart strokes underneath stayed clearly legible
                  // through it as the page scrolled. The opacity and the blur
                  // are therefore desktop-only utilities rather than a CSS
                  // override — `important: true` in tailwind.config.js makes
                  // every utility !important, so a plain rule in globals.css
                  // could never win against them. Desktop keeps the glass.
                  className="set-detail-sticky-tabs max-desk:mt-2 min-h-10 desk:order-2 scroll-mt-24 rounded-b-xl border border-t-0 border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1 shadow-[0_8px_24px_rgba(2,6,23,0.24)] desk:bg-[color:color-mix(in_srgb,var(--surface-panel)_96%,transparent)] desk:backdrop-blur-md md:min-h-11 md:scroll-mt-28 md:rounded-b-2xl"
                  aria-busy={isTabNavPending}
                >
                  {/* Below 1200px the set picker is the top row of this same
                      sticky block, so the current set can be switched at any
                      scroll position without returning to the top. It renders
                      flat here (no border/radius of its own) so the picker and
                      the tabs read as one control, not two stacked cards.
                      Desktop is unaffected: this subtree is desk:hidden and the
                      desktop context header's own picker still owns selection
                      there. */}
                  {/* `data-set-picker` is what the document-level dismiss
                      handler treats as "inside the picker". Without it, a
                      mousedown/touchstart on an OPTION counted as an outside
                      click, so the listbox unmounted before the option's click
                      could fire and selection silently did nothing.

                      `relative z-30` is what lifts the open menu over the tab
                      strip. A z-index on the listbox itself cannot do it: the
                      hero section carries `backdrop-filter` (from
                      .set-context-premium), which creates a stacking context
                      the listbox's own z-50 is sealed inside, and the tab
                      strip's `backdrop-blur-md` creates a second one that
                      paints later in DOM order. Raising this wrapper — an
                      ancestor of the menu and an earlier sibling of the tabs —
                      moves the whole trapped context above them. It stays
                      inside the sticky block's own context (z-40, itself inside
                      an `isolation: isolate` container), so the global header
                      is unaffected. */}
                  <div data-set-sticky-picker data-set-picker className="relative z-30 desk:hidden">
                    <PokemonSetMobileHero
                      model={mobileHeroModel}
                      pickerOpen={heroSetPickerOpen}
                      onTogglePicker={() => setHeroSetPickerOpen((open) => !open)}
                      onSelectTarget={handleHeroSetSelect}
                      onPickerKeyDown={handleSetPickerKeyDown}
                      targets={switcherTargets}
                      selectedTargetId={requestedTargetId}
                      pickerDisabled={isPending || switcherTargets.length === 0}
                      listboxId="set-mobile-picker-list"
                      isPickerOwner={!isDesktopHeroComposition}
                      surfaceClassName="rounded-none border-0 bg-transparent px-0 py-0"
                    />
                    <span
                      aria-hidden="true"
                      className="mb-0.5 mt-0.5 block h-px bg-[var(--border-subtle)]"
                    />
                  </div>
                  <SectionViewTabs
                    className={`transition-opacity duration-150 ${isTabNavPending ? "opacity-60" : ""}`}
                    value={setDetailTab}
                    onChange={handleSetDetailTabChange}
                    variant="primary"
                    /* Scoped, mobile-only emphasis for the active Insights
                       segment. Desktop tabs, tab order, routing and
                       accessibility are untouched. */
                    options={[
                      { value: "overview", label: "RIP", icon: "trend" },
                      { value: "cards", label: "Cards & Products", icon: "cards" },
                      { value: "pull-rates", label: "Pull Rates", icon: "target" },
                      { value: "insights", label: "Analysis", icon: "analysis" },
                    ]}
                  />
                </div>
                <section
                  data-set-context-header
                  data-set-picker-open={isDesktopHeroComposition && heroSetPickerOpen ? "true" : "false"}
                  className="set-context-premium page-hero-panel relative min-h-[88px] overflow-visible rounded-t-xl border max-desk:hidden desk:order-1 md:rounded-t-2xl"
                >
                  <div className="mx-auto grid min-h-[88px] w-full max-w-[1400px] items-stretch md:grid-cols-[minmax(20rem,1.7fr)_repeat(4,minmax(8.5rem,1fr))]">
                    <div ref={heroSetPickerRef} data-set-picker data-compact-set-picker className="relative z-20 flex min-w-0 items-center gap-4 px-4 py-2.5 sm:gap-6 md:gap-7 md:px-5">
                      {heroLogoUrl ? (
                        <span className="flex h-14 w-24 flex-none items-center justify-center sm:h-16 sm:w-28">
                          <img
                            src={heroLogoUrl}
                            alt=""
                            aria-hidden="true"
                            className="max-h-14 w-auto max-w-24 object-contain opacity-95 sm:max-h-16 sm:max-w-28"
                            loading="lazy"
                            decoding="async"
                          />
                        </span>
                      ) : null}
                      <div className="flex min-w-0 flex-1 items-center">
                        <button
                          type="button"
                          onClick={() => setHeroSetPickerOpen((open) => !open)}
                          disabled={isPending || switcherTargets.length === 0}
                          aria-expanded={isDesktopHeroComposition && heroSetPickerOpen}
                          aria-haspopup="listbox"
                          aria-controls="compact-set-picker-list"
                          /* Correction 2: this hero is display:none below 1200px
                             but still mounted, so it hands picker ownership to
                             the mobile composition rather than staying a second
                             focusable, operable trigger. */
                          aria-hidden={isDesktopHeroComposition ? undefined : true}
                          tabIndex={isDesktopHeroComposition ? 0 : -1}
                          className="set-context-identity flex min-h-12 max-w-full items-center gap-2.5 rounded-lg text-left text-lg font-semibold text-[var(--text-primary)] transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-90 md:text-xl"
                          title={switcherTargets.length > 0 ? "Switch set" : "No sets available"}
                        >
                          <span className="min-w-0 py-0.5">
                            <span className="block truncate leading-tight">{selectedName}</span>
                            {selectedTarget?.era ? (
                            <span className="mt-1.5 block truncate text-xs font-medium leading-tight tracking-[0.01em] text-[var(--text-secondary)]">{selectedTarget.era}</span>
                            ) : null}
                          </span>
                          <span aria-hidden="true" className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)]/70">
                            <svg
                              viewBox="0 0 20 20"
                              className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${isDesktopHeroComposition && heroSetPickerOpen ? "rotate-180" : ""}`}
                              fill="currentColor"
                            >
                              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                            </svg>
                          </span>
                        </button>
                        {isDesktopHeroComposition && heroSetPickerOpen ? (
                          <div
                            id="compact-set-picker-list"
                            role="listbox"
                            aria-label="Available sets"
                            onKeyDown={handleSetPickerKeyDown}
                            className="index-scrollbar set-dropdown-glass absolute left-0 top-[calc(100%+0.5rem)] z-50 max-h-56 w-full min-w-[16rem] overflow-y-auto rounded-xl p-1.5"
                          >
                            {switcherTargets.map((target) => {
                              const isSelected = String(target.target_id) === String(requestedTargetId || "");
                              return (
                                <button
                                  key={`compact-set-option:${target.target_type}:${target.target_id}`}
                                  type="button"
                                  role="option"
                                  aria-selected={isSelected}
                                  onMouseEnter={() => handleTargetPrefetch(target.target_id, { reason: "hero-hover" })}
                                  onFocus={() => handleTargetPrefetch(target.target_id, { reason: "hero-focus" })}
                                  onClick={() => handleHeroSetSelect(target)}
                                  className={`set-dropdown-option flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm leading-5 transition-colors ${
                                    isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                                  }`}
                                >
                                  <span className="min-w-0 flex-1 truncate whitespace-nowrap">{target.name}</span>
                                  {isSelected ? <span className="shrink-0 text-xs font-medium text-[var(--accent)]">Current</span> : null}
                                </button>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    </div>

                    <div data-set-context-release-date className="min-w-0 border-t border-[var(--border-subtle)] px-4 py-2.5 md:border-l md:border-t-0">
                      <p className="set-context-eyebrow flex items-center gap-1.5"><SetPageIcon name="calendar" />Release Date</p>
                      <p className="mt-2 text-sm font-semibold tabular-nums text-[var(--text-primary)]">{selectedTarget?.release_date || selectedTarget?.releaseDate ? formatLongDate(selectedTarget?.release_date ?? selectedTarget?.releaseDate) : "—"}</p>
                    </div>
                    <div data-set-context-total-cards className="min-w-0 border-t border-[var(--border-subtle)] px-4 py-2.5 md:border-l md:border-t-0">
                      <p className="set-context-eyebrow flex items-center gap-1.5"><SetPageIcon name="cards" />Total Cards</p>
                      <p className="mt-2 text-sm font-semibold tabular-nums text-[var(--text-primary)]">{authoritativeSetCardCount > 0 ? Math.round(authoritativeSetCardCount).toLocaleString("en-US") : "—"}</p>
                    </div>
                    <div data-set-context-set-value className="min-w-0 border-t border-[var(--border-subtle)] px-4 py-2.5 md:border-l md:border-t-0">
                        <p className="set-context-eyebrow flex items-center gap-1.5"><SetPageIcon name="value" />Set Value</p>
                        <MarketValueChange
                          className="mt-1"
                          value={setHeaderSummary.setValue.current}
                          changeAmount={setHeaderSummary.setValue.delta30dAmount}
                          changePercent={setHeaderSummary.setValue.delta30dPercent}
                          windowLabel="30D"
                          loading={titleCardMetricsPending && setHeaderSummary.setValue.current === null}
                          variant="table-row"
                          accessibleLabel="Current set value"
                        />
                    </div>
                    <div className="min-w-0 border-t border-[var(--border-subtle)] px-4 py-2.5 md:border-l md:border-t-0">
                        <p className="set-context-eyebrow flex items-center gap-1.5"><SetPageIcon name="trophy" />RIP Rank</p>
                        {/* Score stays the focal point and stays neutral; the tier
                            takes the outlined pill and the verdict a lighter
                            relative of the breakdown's interpretation pill, both
                            from one shared tier presentation. The rank is plain
                            inline text — it is a position, not a judgement, and a
                            third chip on this row made the compact card read as
                            three competing badges. */}
                        <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                          {setContextRipTier ? (
                            <span
                              data-set-context-rip-tier
                              className="inline-flex flex-none items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-tight"
                              style={setContextRipPresentation.tierPill}
                            >
                              {setContextRipTier} Tier
                            </span>
                          ) : null}
                          {setContextRipRank !== null ? (
                            <span
                              data-set-context-rip-rank
                              className="flex-none text-[11px] font-medium leading-tight tabular-nums text-[var(--text-secondary)]"
                              title={
                                setContextRipCohort === null
                                  ? `Rank #${Math.round(setContextRipRank)}`
                                  : `Rank #${Math.round(setContextRipRank)} of ${Math.round(setContextRipCohort)} ranked sets`
                              }
                            >
                              #{Math.round(setContextRipRank)}{setContextRipCohort === null ? "" : ` of ${Math.round(setContextRipCohort)}`}
                            </span>
                          ) : null}
                        </div>
                        {/* The interpretation verdict pill was here. It rendered
                            the retired interpretation engine's label, which
                            describes a model the site no longer publishes. A
                            neutral line naming the two canonical inputs takes
                            the slot so the card keeps its shape. */}
                    </div>
                  </div>
                </section>

                </div>

                {setDetailTab === "overview" ? (
                  <RipDecisionPage
                    canonical={canonicalRip}
                    summary={summary}
                    chaseCards={topPricedCards}
                    cardCount={authoritativeSetCardCount}
                    pullRateAssumptions={pullRateAssumptions}
                    cardsHref={updateSetDetailQueryParams({ pathname, searchParams, tab: "cards" })}
                    pullRatesHref={updateSetDetailQueryParams({ pathname, searchParams, tab: "pull-rates" })}
                  />
                ) : null}

                {false && setDetailTab === "overview" ? (
                  // Progressive rendering: each section below gates
                  // independently on its own fetch status instead of one
                  // shared whole-tab skeleton (removed — see
                  // overviewPerformanceVsCostStatus above). Set Value renders
                  // as soon as its history settles even if Market Movers/Top
                  // Chase are still loading, and vice versa.
                  <section id="set-detail-overview" data-mobile-feed className="scroll-mt-24 space-y-5 max-desk:space-y-0 md:scroll-mt-28">
                    <div id="set-detail-movers-ticker" className="min-w-0">
                      {/* 7D Movers ticker — full-width strip directly under the tab
                          bar, replacing the retired Market Movers card on Overview.
                          Always renders; loading/error/empty states live inside the
                          same fixed-height strip (no layout shift). */}
                      <SectionErrorBoundary sectionName="overview-movers-ticker" resetKeys={[resolvedSetResourceId]} title="7D Movers" minHeightClassName="min-h-[3rem]">
                        <SevenDayMarketMoversTicker
                          entry={moversTickerEntry}
                          maxItems={10}
                          scope="set"
                          status={moversTickerStatus}
                          error={activeMarketMoversState.error}
                          viewAllHref={moversTickerHref}
                          onRetry={retryMarketMoversModule}
                        />
                      </SectionErrorBoundary>
                    </div>

                    {/* The compact canonical answer to "how does this set
                        score", in the position the retired Decision Signals
                        card used to hold: after the movers strip, before the
                        charts it introduces. It reads the page's ONE resolved
                        canonical bundle, so Overview and Insights can never
                        show different numbers for the same set. It is one
                        grouped surface rather than three cards, so it does not
                        take the viewport the way Decision Signals did. */}
                    {/* First ordinary section under the set-level 7D Movers
                        ticker, so it takes the quiet 1px divider variant. That
                        variant moved here from Set Value Trend, which is no
                        longer the module directly under the ticker; Set Value
                        now takes the ordinary luminous divider like every other
                        later analytical section. */}
                    <div data-mobile-section data-mobile-section-variant="after-movers" className="min-w-0">
                      <SectionErrorBoundary sectionName="overview-rip-summary" resetKeys={[resolvedSetResourceId]} title="RIP Summary" minHeightClassName="min-h-[7rem]">
                        <OverviewRipSummary
                          canonical={canonicalRip}
                          onViewAnalysis={() =>
                            handleSetDetailNavSelect({
                              tab: "insights",
                              section: "rip-score",
                              targetId: "set-detail-rip-score",
                            })
                          }
                        />
                      </SectionErrorBoundary>
                    </div>

                    <div id="set-detail-overview-performance" className="scroll-mt-24 grid gap-5 lg:grid-cols-2 lg:items-stretch md:scroll-mt-28">
                      <div id="set-detail-set-value-trend" data-mobile-section className="min-w-0 scroll-mt-24 lg:h-full md:scroll-mt-28">
                        {/* Priority 2: Set Value. SetValueTrendCard already
                            self-renders loading/error from status/error, so
                            it only needs render-exception isolation here. */}
                        <SectionErrorBoundary sectionName="overview-set-value" resetKeys={[resolvedSetResourceId]} title="Set Value" minHeightClassName="min-h-[16rem]">
                          <SetValueTrendCard
                            setId={resolvedSetResourceId}
                            setValueContract={activeSetValueContract}
                            history={activeSetValueHistory.history}
                            historiesByScope={activeSetValueHistory.historiesByScope}
                            availableScopes={activeSetValueHistory.availableScopes}
                            status={activeSetValueHistory.status}
                            error={activeSetValueHistory.error}
                            selectedScope={setValueTrendScope}
                            onSelectedScopeChange={setSetValueTrendScope}
                            marketAsOfDate={marketAsOfDate}
                          />
                        </SectionErrorBoundary>
                      </div>
                      <div data-mobile-section className="min-w-0 lg:h-full">
                        {/* Priority 3: Performance vs Cost. PackValueHistoryChart
                            has no internal status handling, so it gets an
                            explicit SectionBoundary keyed to the /overview
                            payload's own status. */}
                        <SectionErrorBoundary sectionName="overview-performance-vs-cost" resetKeys={[resolvedSetResourceId]} title="Opening Profit vs Cost" minHeightClassName="min-h-[16rem]">
                          <SectionCard
                            title="Opening Profit vs Cost"
                            titleInfoText={PERFORMANCE_VS_COST_INFO_TEXT}
                            className="flex h-full flex-col"
                            bodyClassName="flex min-h-0 flex-1 flex-col"
                          >
                            <SectionBoundary
                              status={overviewPerformanceVsCostStatus}
                              error={activeOverviewState.error ? new Error(activeOverviewState.error) : null}
                              onRetry={retryOverviewModule}
                              title="Loading opening profit vs cost…"
                              minHeightClassName="min-h-[14rem]"
                              className="h-full"
                            >
                              <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} summary={summary} marketAsOfDate={marketAsOfDate} flush />
                            </SectionBoundary>
                            {openingSimulationFreshness.label ? (
                              <p
                                data-opening-simulation-freshness
                                data-stale={openingSimulationFreshness.isStale ? "true" : "false"}
                                className={`mt-2 text-[11px] leading-snug ${
                                  openingSimulationFreshness.isStale
                                    ? "text-[var(--text-secondary)]"
                                    : "text-[var(--text-secondary)] opacity-80"
                                }`}
                              >
                                <span className="sr-only">{openingSimulationFreshness.accessibleLabel}</span>
                                <span aria-hidden="true">{openingSimulationFreshness.label}</span>
                              </p>
                            ) : null}
                            {/* Below 1200px these become compact label/value
                                rows separated by thin dividers instead of a
                                bordered multi-column grid: same metrics, same
                                values, same trend indicators, same info
                                tooltips, a fraction of the height. Desktop
                                keeps the three-column subgrid exactly. */}
                            <div data-overview-opening-economics className="mt-3 border-t border-[var(--border-subtle)] pt-2.5 max-desk:mt-2.5 max-desk:pt-2">
                              <dl className="grid grid-cols-1 desk:grid-cols-3 desk:grid-rows-[auto_auto_auto]">
                                {headerDecisionMetrics.map((metric, metricIndex) => (
                                  <div
                                    key={`overview-opening-${metric.label}`}
                                    data-opening-metric-row
                                    className={`grid min-w-0 grid-cols-[minmax(0,1fr)_auto] grid-rows-1 items-center gap-x-3 px-0 py-2 max-desk:min-h-14 desk:grid-cols-1 desk:grid-rows-[minmax(3rem,auto)_minmax(1.5rem,auto)_minmax(0.875rem,auto)] desk:items-stretch desk:px-3 desk:py-2 desk:first:pl-0 desk:row-span-3 desk:grid-rows-subgrid desk:last:pr-0 ${
                                      metricIndex > 0
                                        ? "border-t border-[var(--border-subtle)] desk:border-l desk:border-t-0 desk:border-[var(--border-subtle)]"
                                        : ""
                                    }`}
                                  >
                                    <dt className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium leading-tight text-[var(--text-secondary)] desk:items-start md:whitespace-nowrap">
                                      <span>{getFriendlyMetricLabel(metric.label)}</span>
                                      {getMetricTooltip(metric.label) ? <InfoPopover text={getMetricTooltip(metric.label)} /> : null}
                                    </dt>
                                    {/* One right column for every value. The trend
                                        arrow renders only for some metrics, so
                                        with the arrow trailing the number each
                                        row ended at a different x and the column
                                        read as ragged. Reversing the pair below
                                        desktop puts the arrow on the inside and
                                        pins every value — arrow or not — to the
                                        same right edge, which the helper line
                                        below then shares. Desktop keeps the
                                        original number-then-arrow order. */}
                                    <dd className="justify-self-end whitespace-nowrap text-sm font-semibold tabular-nums text-[var(--text-primary)] desk:justify-self-auto desk:whitespace-normal">
                                      <span className="inline-flex items-center gap-1.5 max-desk:flex-row-reverse">
                                        {metric.value}
                                        <OpeningMetricTrendIndicator
                                          trend={metric.trend}
                                          neutral={metric.label === RIP_COPY.simpleMetrics.currentPackCost}
                                        />
                                      </span>
                                    </dd>
                                    <dd className="col-span-2 text-[11px] font-normal leading-tight text-[var(--text-secondary)] max-desk:text-right desk:col-span-1">
                                      {metric.label === RIP_COPY.simpleMetrics.averagePackValue && headerExpectedLossText
                                        ? (
                                        <span>
                                          {headerExpectedLossText.replace("versus", "vs")}
                                        </span>
                                        )
                                        : <span aria-hidden="true" className="hidden desk:inline">&nbsp;</span>}
                                    </dd>
                                  </div>
                                ))}
                              </dl>
                            </div>
                          </SectionCard>
                        </SectionErrorBoundary>
                      </div>
                    </div>

                    {/* Top Chase Cards at 2/3 width, Sealed Market at 1/3.
                        Below lg they stack, Top Chase first. The Decision
                        Signals card shared this right-hand column and was
                        removed: it scored Profit, Safety, Stability, Opening
                        Experience and Chase Potential, none of which are terms
                        of the current model. The grid keeps its shape - Sealed
                        Market simply owns the 1/3 column alone. */}
                    <div className="grid gap-5 lg:grid-cols-3 lg:items-start">
                      {shouldShowTopMarketCards ? (
                        <div id="set-detail-top-market-cards" data-mobile-section className="min-w-0 scroll-mt-24 md:scroll-mt-28 lg:col-span-2">
                          {/* Top Chase Cards — self-renders loading/error. */}
                          <SectionErrorBoundary sectionName="overview-top-chase" resetKeys={[resolvedSetResourceId]} title="Top Chase Cards" minHeightClassName="min-h-[14rem]">
                            <TopChaseCardsModule
                              cards={topPricedCards}
                              status={topPricedCardsStatus}
                              error={activeTopMarketCardsState.error}
                              infoText={topPricedCardsInfo}
                              selectedWindowKey={topMarketCardsWindowKey}
                              onWindowChange={setTopMarketCardsWindowKey}
                              marketAsOfDate={marketAsOfDate}
                              rowHref={topChaseRowHref}
                              onRetry={retryTopChaseModule}
                            />
                          </SectionErrorBoundary>
                        </div>
                      ) : null}
                      <div className="min-w-0 space-y-5">
                        <div data-mobile-section>
                          {/* Sealed Market owns an independent prepared-snapshot request. */}
                          <SectionErrorBoundary sectionName="overview-sealed-market" resetKeys={[resolvedSetResourceId]} title="Sealed Market" minHeightClassName="min-h-[11rem]">
                            <SealedMarketTrendCard setId={resolvedSetResourceId} />
                          </SectionErrorBoundary>
                        </div>
                      </div>
                    </div>
                  </section>
                ) : null}

                {setDetailMode && !isDesktopHeroComposition && showReturnToTop ? (
                  <button
                    type="button"
                    onClick={() => {
                      revealMobileSetContext();
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    className="fixed bottom-[calc(5.25rem+env(safe-area-inset-bottom)+0.75rem)] right-4 z-[60] inline-flex h-12 w-12 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 text-[var(--text-primary)] shadow-[0_12px_30px_rgba(2,6,23,0.32)] backdrop-blur transition-transform hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] desk:bottom-6 desk:right-6"
                    aria-label="Return to top"
                  >
                    <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                      <path d="M10 4.25a.75.75 0 0 1 .53.22l4.5 4.5a.75.75 0 1 1-1.06 1.06L10.75 6.56v8.19a.75.75 0 0 1-1.5 0V6.56L6.03 9.98a.75.75 0 0 1-1.06-1.06l4.5-4.5A.75.75 0 0 1 10 4.25Z" />
                    </svg>
                  </button>
                ) : null}

                {setDetailTab === "cards" ? (
                  // Transparency stack (Cards): this section is a transparent
                  // layout region — the same shape #set-detail-overview already
                  // uses — because a panel here was the first ancestor blocking
                  // the ambient set artwork. Only the controls carry a surface;
                  // nothing paints a background behind the card grid.
                  <section id="set-detail-cards" data-cards-section className="scroll-mt-24 space-y-4 md:scroll-mt-28">
                    {/* One compact controls panel: sub-tabs, search, sort/rarity
                        or direction, timeframe, movement metric, and the count. */}
                    <div data-cards-toolbar className="set-glass-surface space-y-3 rounded-2xl border p-3 md:p-4">
                      <SectionViewTabs
                        value={cardsSection}
                        onChange={(nextSection) =>
                          handleSetDetailNavSelect({
                            tab: "cards",
                            section: nextSection,
                            cardsSubTab: "checklist",
                            targetId: "set-detail-cards",
                          })
                        }
                        variant="secondary"
                        options={[
                          { value: "all-cards", label: "All Cards" },
                          { value: "market-movers", label: "Market Movers" },
                        ]}
                      />

                      {cardsSubTab === "checklist" ? (
                        <label className="block min-w-0 max-w-sm text-xs font-semibold text-[var(--text-secondary)]">
                          <span className="mb-1 block uppercase tracking-[0.08em]">Search</span>
                          <input
                            type="text"
                            value={cardSearchQuery}
                            onChange={(event) => setCardSearchQuery(event.target.value)}
                            placeholder="Search cards by name"
                            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                          />
                        </label>
                      ) : null}

                      {cardsSubTab === "checklist" && effectiveCardsPageCards.length > 0 && hasCardMovementData ? (
                        <div className="flex flex-wrap items-end gap-3">
                          {cardsSection === "all-cards" ? (
                            <>
                            <div className="min-w-0 text-xs font-semibold text-[var(--text-secondary)]">
                              <span className="mb-1 block uppercase tracking-[0.08em]">Sort</span>
                              <div className="flex flex-wrap gap-2">
                                <select
                                  aria-label="Sort cards by"
                                  value={cardSortMode}
                                  onChange={(event) => setCardSortMode(event.target.value)}
                                  className="min-w-[10rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                                >
                                  {ALL_CARDS_SORT_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                  ))}
                                </select>
                                <button
                                  type="button"
                                  onClick={() => setCardSortDirection((direction) => direction === "asc" ? "desc" : "asc")}
                                  aria-label={`Sort ${ALL_CARDS_SORT_OPTIONS.find((option) => option.value === cardSortMode)?.label || "cards"} ${cardSortDirection === "asc" ? "ascending" : "descending"}. Activate to reverse order.`}
                                  aria-pressed={cardSortDirection === "desc"}
                                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                                >
                                  {getAllCardsDirectionLabel(cardSortMode, cardSortDirection)}
                                </button>
                              </div>
                            </div>
                            <label className="min-w-0 text-xs font-semibold text-[var(--text-secondary)]">
                              <span className="mb-1 block uppercase tracking-[0.08em]">Rarity</span>
                              <select
                                value={cardRarityFilter}
                                onChange={(event) => setCardRarityFilter(event.target.value)}
                                className="min-w-[10rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                              >
                                <option value="">All Rarities</option>
                                {availableCardRarities.map((rarityOption) => (
                                  <option key={rarityOption} value={rarityOption}>{rarityOption}</option>
                                ))}
                              </select>
                            </label>
                            </>
                          ) : (
                            <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Movement direction">
                              {["gainers", "losers"].map((direction) => (
                                <button
                                  key={direction}
                                  type="button"
                                  onClick={() => setCardSortDirection(direction)}
                                  aria-pressed={cardSortDirection === direction}
                                  aria-label={direction === "gainers" ? "Gainers" : "Losers"}
                                  className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                                    cardSortDirection === direction ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                                  }`}
                                >
                                  {/* Button padding and label size are unchanged — only the
                                      triangle shrinks, via the shared DeltaTrendIcon's own
                                      "sm" size (em-relative, so it stays proportional) inside
                                      a fixed, identical box for both directions. The buttons'
                                      own aria-labels keep the icon's internal label out of the
                                      accessible name. Per-card movement triangles are a
                                      separate surface and stay as they are. */}
                                  <span className="inline-flex items-center gap-1.5">
                                    <DeltaTrendIcon
                                      direction={direction === "gainers" ? "up" : "down"}
                                      size="sm"
                                      className="h-3 w-3 justify-center"
                                    />
                                    <span>{direction === "gainers" ? "Gainers" : "Losers"}</span>
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}
                          <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Movement timeframe">
                            {CARD_TIMEFRAMES.map((timeframe) => (
                              <button
                                key={timeframe}
                                type="button"
                                onClick={() => setSelectedTimeframe(timeframe)}
                                aria-pressed={selectedTimeframe === timeframe}
                                className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                                  selectedTimeframe === timeframe ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                                }`}
                              >
                                {timeframe}
                              </button>
                            ))}
                          </div>
                          {cardsSection === "market-movers" ? (
                            // Third independent Market Movers control: which
                            // magnitude the ranking compares. Direction and
                            // timeframe are untouched by it. The visible labels are
                            // symbol-led for compactness, so each button carries a
                            // spelled-out accessible name.
                            <div className="flex rounded-lg border border-[var(--border-subtle)] p-0.5" role="group" aria-label="Rank movement by">
                              {MARKET_MOVER_METRIC_OPTIONS.map((option) => (
                                <button
                                  key={option.value}
                                  type="button"
                                  onClick={() => setCardMovementMetric(option.value)}
                                  aria-pressed={cardMovementMetric === option.value}
                                  title={option.accessibleLabel}
                                  className={`rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                                    cardMovementMetric === option.value ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                                  }`}
                                >
                                  <span aria-hidden="true">{option.label}</span>
                                  <span className="sr-only">{option.accessibleLabel}</span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                          <p className="ml-auto text-xs text-[var(--text-secondary)]">
                            {displayedChecklistCards.length.toLocaleString("en-US")} of {(activeCardsPageState.pagination?.totalCards ?? effectiveCardsPageCards.length).toLocaleString("en-US")} cards
                          </p>
                        </div>
                      ) : null}
                    </div>

                    {cardsSubTab === "checklist" ? (
                      <div className="min-w-0">
                        {(effectiveCardsPageStatus === "idle" || effectiveCardsPageStatus === "loading") &&
                        effectiveCardsPageCards.length === 0 ? (
                          // Branded tab loader only while the card page
                          // payload itself is loading and no card rows exist
                          // yet. Once rows render, lazy card images keep
                          // their card-shaped placeholders (ChecklistCardTile
                          // → CardImagePlaceholder) — individual image loads
                          // must never re-block the whole tab.
                          <SetTabLoadingPanel
                            title="Loading cards…"
                            helper="Pulling the checklist page and card market fields for this set."
                          />
                        ) : null}

                        {effectiveCardsPageStatus === "error" ? (
                          <p className="text-sm text-red-300">{activeCardsPageState.error || "Unable to load cards for this set."}</p>
                        ) : null}

                        {effectiveCardsPageStatus === "empty" ? (
                          <p className="text-sm text-[var(--text-secondary)]">No cards found for this set.</p>
                        ) : null}

                        {effectiveCardsPageCards.length > 0 ? (
                          <>
                            {displayedChecklistCards.length > 0 ? (
                              // Never dim or overlay the grid while more
                              // cards load — appended chunks render below and
                              // the already-visible cards must stay stable.
                              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
                                {displayedChecklistCards.map((card) => (
                                  <ChecklistCardTile
                                    key={`${card.id || card.cardNumber || card.name}`}
                                    card={card}
                                    movementWindow={selectedTimeframe}
                                  />
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-[var(--text-secondary)]">No cards match this movement filter yet.</p>
                            )}

                            {/* Infinite scroll: the sentinel sits below the
                                grid and advances cardsPage via
                                IntersectionObserver (generous rootMargin) —
                                no user-facing Previous/Next buttons. Located
                                by data attribute because the scaffold mounts
                                this tree twice (desktop + mobile copies). */}
                            <div data-cards-load-more-sentinel="true" aria-hidden="true" className="h-px w-full" />

                            {cardsPageIsLoadingMore ? (
                              <div aria-live="polite" className="pt-1">
                                <InDexLogoLoader
                                  fullScreen={false}
                                  label="Loading more cards"
                                  shouldDelay={false}
                                  isLoading={true}
                                  className="index-loader-shell--compact"
                                />
                              </div>
                            ) : null}

                            {cardsPageLoadMoreError ? (
                              <div className="mt-3 flex flex-col items-center gap-2 text-center">
                                <p className="text-xs text-[var(--text-secondary)]">Couldn&apos;t load more cards.</p>
                                <button
                                  type="button"
                                  onClick={() => setCardsPageRetryNonce((nonce) => nonce + 1)}
                                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/50 px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
                                >
                                  Retry
                                </button>
                              </div>
                            ) : null}

                            {cardsPageFullyLoaded && !cardsPageIsLoadingMore ? (
                              <p className="mt-4 text-center text-xs text-[var(--text-secondary)]/80">
                                All {(activeCardsPageState.pagination?.totalCards ?? activeCardsPageState.cards.length).toLocaleString("en-US")} cards loaded
                              </p>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {setDetailTab === "pull-rates" ? (
                  <PullRatesTab
                    pullRateAssumptions={pullRateAssumptions}
                    pullRatesTabPending={pullRatesTabPending}
                    pullRatesPendingTimedOut={pullRatesPendingTimedOut}
                    activePullRatesState={activePullRatesState}
                    resolvedSetResourceId={resolvedSetResourceId}
                  />
                ) : null}
              </>
            ) : null}

            {showInsightsCohesiveLoading ? (
              // Branded loader for just the critical tier (RIP Score hero +
              // pillar cards, priorities 1-3) — only engages in set detail
              // mode (insightsCriticalPending is false on /Explore). Once the
              // critical fetch settles this whole region reveals; Opening
              // Outcomes and Desirability Evidence below then show their own
              // secondary-tier loading/fallback state independently
              // (insightsSectionsBlocked/insightsSectionsShowFallbackCopy)
              // while priorities 4-5 catch up — this is the actual
              // progressive-rendering seam for Insights.
              <SetTabLoadingPanel
                title="Loading RIP score…"
                helper="Pulling your set's RIP score and pillar breakdown."
                compactMobile
              />
            ) : null}

            {(!setDetailMode || setDetailTab === "insights") && !showInsightsCohesiveLoading ? (
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
                <div ref={heroSetPickerRef} data-set-picker data-hero-picker className="relative w-full">
                  <CenteredSuffixInline
                    as="button"
                    type="button"
                    onClick={() => setHeroSetPickerOpen((open) => !open)}
                    disabled={isPending || switcherTargets.length === 0}
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
                    title={switcherTargets.length > 0 ? "Switch set" : "No sets available"}
                  >
                    <span>{selectedName}</span>
                  </CenteredSuffixInline>

                  {heroSetPickerOpen ? (
                    <div
                      id="hero-set-picker-list"
                      role="listbox"
                      aria-label="Available sets"
                      onKeyDown={handleSetPickerKeyDown}
                      className="index-scrollbar set-dropdown-glass absolute left-1/2 top-full z-30 mt-2 max-h-72 w-[min(36rem,92vw)] -translate-x-1/2 overflow-y-auto rounded-xl p-1.5 text-left"
                    >
                      {switcherTargets.map((target) => {
                        const isSelected = String(target.target_id) === String(requestedTargetId || "");
                        return (
                          <button
                            key={`hero-set-option:${target.target_type}:${target.target_id}`}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            onMouseEnter={() => handleTargetPrefetch(target.target_id, { reason: "hero-hover" })}
                            onFocus={() => handleTargetPrefetch(target.target_id, { reason: "hero-focus" })}
                            onClick={() => handleHeroSetSelect(target)}
                            className={`set-dropdown-option flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                              isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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
                      {/* The RIP Score / RIP Core toggle stood here. RIP Core is
                          Financial RIP V2 and is not a current alternative to
                          the RIP Score, so there is one headline and no mode. */}
                      <div className="mt-1 flex w-full justify-center">
                        <div className="inline-flex items-center gap-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                            {heroScoreSelection.label}
                          </p>
                          <InfoPopover text={heroScoreSelection.helper} />
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
                        <ScoreMeter score={topScoreRaw} rankTier={heroScoreSelection.tier} />
                      </div>
                      {displayedHeroModelScore !== null ? (
                        <p className="mt-2 text-xs leading-snug text-[var(--text-secondary)]">
                          Underlying model score: {displayedHeroModelScore}
                        </p>
                      ) : null}
                      <div className="mt-4 flex w-full justify-center self-center">
                        <HeroScoreBadges rank={heroScoreSelection.rank} tier={heroScoreSelection.tier} cohortSize={heroScoreSelection.cohortSize} size="hero" />
                      </div>
                    </div>

                    {/* The interpretation-engine recommendation callout stood
                        here. Its badge and summary came from the retired
                        Profit/Safety/Stability model, so it described neither
                        Financial RIP V3 nor Collector Appeal V3. One neutral
                        line naming the canonical inputs replaces it. */}
                    <p data-rip-hero-helper className="mx-auto mt-5 w-full max-w-2xl text-center text-xs leading-relaxed text-[var(--text-secondary)] sm:text-left">
                      {RIP_SCORE_HELPER}
                    </p>

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
                              rankTier={ripBreakdownRowByTitle.get("Profit")?.rankTier ?? null}
                              infoText={`${SIMPLE_PILLAR_INFO_COPY.Profit}${decisionSignalFreshnessInfo}`}
                              sectionMeta={profitMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Profit]}
                              fallbackSummary={interpretation?.profit}
                            />
                            <SimplePillarSummaryCard
                              title="Safety"
                              rankTier={ripBreakdownRowByTitle.get("Safety")?.rankTier ?? null}
                              infoText={`${SIMPLE_PILLAR_INFO_COPY.Safety}${decisionSignalFreshnessInfo}`}
                              sectionMeta={safetyMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Safety]}
                              fallbackSummary={interpretation?.safety}
                            />
                            <SimplePillarSummaryCard
                              title="Stability"
                              rankTier={ripBreakdownRowByTitle.get("Stability")?.rankTier ?? null}
                              infoText={`${SIMPLE_PILLAR_INFO_COPY.Stability}${decisionSignalFreshnessInfo}`}
                              sectionMeta={stabilityMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Stability]}
                              fallbackSummary={interpretation?.stability}
                            />
                            <SimplePillarSummaryCard
                              title="Collector Appeal"
                              rankTier={ripBreakdownRowByTitle.get("Collector Appeal")?.rankTier ?? null}
                              infoText={`${SIMPLE_PILLAR_INFO_COPY["Collector Appeal"]}${decisionSignalFreshnessInfo}`}
                              sectionMeta={desirabilityMeta}
                              backendPillar={pillarMetaByKey[PILLAR_TITLE_TO_KEY.Desirability]}
                              fallbackSummary={desirabilitySummary}
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
              // Below 1200px Insights is the same continuous analytical feed
              // Overview already is: the three sections drop their outer cards
              // and are separated by a divider plus breathing room instead. The
              // `max-desk:space-y-0` is required, not decorative — `space-y-4`
              // is an !important utility, so without it the feed's own
              // margin-top would lose and the two spacings would stack.
              <section id="set-detail-insights" data-mobile-feed className="scroll-mt-24 space-y-4 pt-0 max-desk:space-y-0 md:scroll-mt-28">
                {/* Priorities 1-2: RIP Score hero + pillar cards. Gated above
                    via showInsightsCohesiveLoading (critical-only now), so
                    only render-exception isolation is needed here. */}
                <div data-mobile-section>
                <SectionErrorBoundary sectionName="insights-rip-score" resetKeys={[resolvedSetResourceId]} title="RIP Score" minHeightClassName="min-h-[14rem]">
                  <RipScoreBreakdownModule
                    score={topScoreRaw}
                    rankTier={heroScoreSelection.tier}
                    rankValue={heroScoreSelection.rank}
                    cohortSize={heroScoreSelection.cohortSize}
                    titleInfoText={`${ripBreakdownInfo}${decisionSignalFreshnessInfo}`}
                    canonical={canonicalRip}
                    requestTimeout={isTimeoutFallbackPayload}
                  />
                </SectionErrorBoundary>
                </div>

                {/* The public Collector Profile section stood here. It is
                    removed, not relocated: Collector Appeal is presented once,
                    by CollectorAppealBreakdown inside the RIP Score section
                    above, and no empty wrapper or placeholder card is left
                    behind in its place. Its deep links resolve to that block. */}

                {/* Priority 4: the Simulation Results deep-dive (formerly
                    "Opening Outcomes"). Already internally gated on the
                    secondary tier via insightsSectionsBlocked. */}
                <div data-mobile-section>
                <SectionErrorBoundary sectionName="insights-opening-outcomes" resetKeys={[resolvedSetResourceId]} title="Simulation Results" minHeightClassName="min-h-[24rem]">
                <section id={ANALYSIS_SECTION_ID} className="scroll-mt-24 md:scroll-mt-28">
                  {/* Always-expanded card (same card treatment as SectionCard): the
                      Insights page is the deep-dive destination, so the full
                      sub-tab explorer renders on load. Deep links and left-nav
                      clicks only pick the sub-tab and scroll — there is no
                      collapse state to reveal. */}
                  {/* Shell cleanup only. Below 1200px the outer context card is
                      gone and the section joins the continuous mobile feed. The
                      title, the supporting description, the view tabs and every
                      simulation view (Outcome Distribution, Opening Profit vs
                      Cost, Simulation Drivers, Value Structure, Pack Paths,
                      Metrics) are unchanged at every width — the sub-tab strip
                      still needs its own pass. Desktop keeps the card. */}
                  <article
                    className={[
                      // `desk:p-5`, not `sm:p-5` — see SectionCard's insetClass:
                      // an sm-scoped inset outranks max-desk: and would leave
                      // the card inset across the whole 640-1199px tablet band.
                      // Identical p-5 at 1200px+.
                      "set-glass-surface w-full max-w-full min-w-0 rounded-2xl border p-4 desk:p-5",
                      SECTION_CARD_MOBILE_FLUSH_CLASS,
                      openingOutcomesUsesExpandedLayout ? "min-h-[38rem]" : "",
                    ].filter(Boolean).join(" ")}
                  >
                    <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <SectionEyebrow>03 · Raw evidence</SectionEyebrow>
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          <h2 className="min-w-0 max-w-full text-lg font-semibold text-[var(--text-primary)]">Simulation Results</h2>
                          <InfoPopover text={SIMULATION_RESULTS_INFO_TEXT} />
                        </div>
                        {/* Below 1200px this line restates the eyebrow directly
                            above it ("03 · Raw evidence") and costs a whole
                            line of a phone screen before the sub-tabs. Hidden,
                            not deleted: the copy is unchanged and 1200px+
                            renders it exactly as before. */}
                        <p className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)] max-desk:hidden">The raw evidence — full simulation outputs behind the score.</p>
                      </div>
                    </div>

                    <div
                      className={["mt-4 min-w-0 max-w-full", openingOutcomesUsesExpandedLayout ? "min-h-[32rem]" : ""].filter(Boolean).join(" ")}
                    >
                    <SimulationSectionSelector
                      className="mb-4"
                      selectedValue={activeInsightsGraphMode}
                      onValueChange={(nextView) => {
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
                      options={[
                        { value: "outcome-distribution", label: "Outcome Distribution", shortLabel: "Outcomes" },
                        { value: "historical-trend", label: "Opening Profit vs Cost", shortLabel: "OPvC" },
                        { value: "simulation-drivers", label: "Simulation Drivers", shortLabel: "Drivers" },
                        { value: "value-contribution", label: "Value Structure", shortLabel: "Value" },
                        { value: "pack-breakdown", label: "Pack Paths", shortLabel: "Paths" },
                        { value: "simulation-metrics", label: "Metrics", shortLabel: "Metrics" },
                      ]}
                    />

                    <SimulationSectionHeader
                      title={
                        activeInsightsGraphMode === "historical-trend"
                          ? "Opening Profit vs Cost"
                          : activeInsightsGraphMode === "simulation-drivers"
                          ? "Simulation Drivers"
                          : activeInsightsGraphMode === "value-contribution"
                          ? "Value Structure"
                          : activeInsightsGraphMode === "pack-breakdown"
                          ? "Pack Paths"
                          : activeInsightsGraphMode === "simulation-metrics"
                          ? "Metrics"
                          : "Outcome Distribution"
                      }
                      infoText={
                        activeInsightsGraphMode === "historical-trend"
                          ? OPENING_PERFORMANCE_VS_COST_INFO_TEXT
                          : activeInsightsGraphMode === "simulation-drivers"
                          ? SIMULATION_DRIVERS_INFO_TEXT
                          : activeInsightsGraphMode === "value-contribution"
                          ? rarityContributionInfo
                          : activeInsightsGraphMode === "pack-breakdown"
                          ? PACK_PATHS_INFO_TEXT
                          : activeInsightsGraphMode === "simulation-metrics"
                          ? SIMULATION_METRICS_INFO_TEXT
                          : outcomeDistributionInfo
                      }
                      className={activeInsightsGraphMode === "simulation-drivers" ? "mb-1.5" : "mb-3"}
                    />

                    {insightsSectionsBlocked ? (
                      // The /insights payload feeds every Simulation Results
                      // view (distribution bins, drivers, rankings, pack
                      // paths) — hold one stable in-card loading state
                      // instead of each view's misleading "no data" empty
                      // state while the fetch is in flight, and switch to
                      // compact fallback copy if it fails or stalls.
                      insightsSectionsShowFallbackCopy ? (
                        <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">
                          Set insights are taking longer than expected to load. Refresh the page to retry.
                        </p>
                      ) : (
                        <InlinePanelSkeleton rows={6} className="min-h-[24rem]" />
                      )
                    ) : !openingOutcomesViewHasData ? (
                      activeInsightsSecondaryStatus === "loading" ? (
                        // Another sub-view's data unblocked the card, but the
                        // secondary fetch that owns THIS sub-view's rows is
                        // still in flight — a quiet placeholder, never a
                        // premature "isn't available" verdict (Paradox Rift
                        // has real top_hits rows that arrive with it).
                        <InlinePanelSkeleton rows={4} className="min-h-[12rem]" />
                      ) : (
                        // Settled, but this sub-view genuinely has no rows for
                        // this set — a compact note, not a chart-sized blank
                        // panel, and only for the affected sub-tab.
                        <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 px-4 py-3 text-sm text-[var(--text-secondary)]">
                          {openingOutcomesEmptyViewCopy}
                        </p>
                      )
                    ) : activeInsightsGraphMode === "simulation-drivers" ? (
                      <SimulationResultsPanel id="set-detail-simulation-drivers">
                        {/* Below desktop the intro loses vertical air and the
                            interpretation drops a type step, so the panel opens
                            on the ranked drivers rather than on a paragraph.
                            The copy itself is unchanged and still complete —
                            only its size and the gap around it move. */}
                        <div className="mb-2 grid min-w-0 gap-2 max-desk:mb-1.5 max-desk:gap-1 max-desk:text-[11px] lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                          {/* The callout's own padding and body size step down
                              below 1200px so the panel opens on the drivers
                              rather than on a paragraph. The badge, the accent
                              rail and every word of the copy are untouched, and
                              the shared component's defaults are not edited —
                              so no other caller of InterpretationInsight
                              moves. */}
                          <InterpretationInsight
                            sectionMeta={topEvDriversMeta}
                            fallbackSummary={collectorFriendlyText(interpretation?.topEvDrivers)}
                            compact
                            showEvidence={false}
                            className="min-w-0 max-desk:py-0.5 max-desk:[&>div]:mb-1 max-desk:[&>p]:text-xs max-desk:[&>p]:leading-snug"
                          />
                          <div className="flex min-w-0 flex-col gap-0.5 max-desk:flex-row max-desk:items-baseline max-desk:justify-between max-desk:gap-2 lg:min-w-[12rem] lg:text-right">
                            <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] lg:justify-end">
                              Simulated Expected Value
                              <InfoPopover text={`${SIMULATED_AVERAGE_PACK_VALUE_INFO_TEXT}${formatSectionFreshnessInfo(simulationDrivers.diagnostics?.freshness)}`} />
                            </span>
                            <span className="text-base font-semibold tabular-nums text-[var(--text-primary)] max-desk:text-sm">{formatCurrency(simulationDriversSummaryValue)}</span>
                          </div>
                        </div>
                        <TopEVDriversContent
                          topHits={topHits}
                          meanValue={summary.mean_value}
                          condensed
                          compactImage
                          maxRows={10}
                          diagnostics={simulationDrivers.diagnostics}
                          showSummary={false}
                          showHiddenCountFooter={false}
                        />
                      </SimulationResultsPanel>
                    ) : activeInsightsGraphMode === "value-contribution" ? (
                      <SimulationResultsPanel id="set-detail-value-structure">
                        <RarityContributionContent rankings={rankings} condensed />
                      </SimulationResultsPanel>
                    ) : activeInsightsGraphMode === "pack-breakdown" ? (
                      <SimulationResultsPanel id="set-detail-pack-breakdown">
                        <PackBreakdownContent
                          packPaths={ripStatistics?.pack_paths}
                          normalStateRows={normalStateRows}
                          evidenceRows={packBreakdownEvidenceRows}
                          condensed
                        />
                      </SimulationResultsPanel>
                    ) : activeInsightsGraphMode === "historical-trend" ? (
                      // Opening Performance vs Cost: the SAME performance history as
                      // Overview, but rendered in the technical "simulation"
                      // variant so the series are named by raw percentile-vs-cost
                      // ratios. This is the flush visual reference for the card.
                      <SimulationResultsPanel id="set-detail-opening-performance-cost">
                        <PackValueHistoryChart
                          historyTrend={historyTrend}
                          packCost={summary.pack_cost}
                          summary={summary}
                          variant="simulation"
                          marketAsOfDate={marketAsOfDate}
                          flush
                        />
                      </SimulationResultsPanel>
                    ) : activeInsightsGraphMode === "simulation-metrics" ? (
                      // Metrics intentionally keeps its own internal scroll — it
                      // is allowed to overflow the fixed card height.
                      <div id="set-detail-simulation-metrics" className="max-h-[36rem] scroll-mt-24 overflow-y-auto pr-1 md:scroll-mt-28">
                        <SimulationMetricsContent
                          summary={summary}
                          percentiles={percentiles}
                          ripStatistics={ripStatistics}
                          historyTrend={historyTrend}
                          asOfDate={fallbackSetValueAsOf}
                          performanceHistoryLatestDate={latestRealPerformanceDate}
                        />
                      </div>
                    ) : (
                      // Outcome Distribution renders flush — no inner chart card,
                      // matching Opening Performance vs Cost. The section header above
                      // already shows the "Outcome Distribution" title.
                      <SimulationResultsPanel id="set-detail-outcome-distribution">
                        <RipDistributionChart bins={distributionBins} thresholdBins={thresholdBins} markers={chartMarkers} showTitle={false} flush />
                      </SimulationResultsPanel>
                    )}
                    </div>
                  </article>
                </section>
                </SectionErrorBoundary>
                </div>
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
                  rankValue={ripBreakdownRowByTitle.get("Profit")?.rankValue ?? null}
                  rankTier={ripBreakdownRowByTitle.get("Profit")?.rankTier ?? null}
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
                    { label: "Expected Value vs Cost", value: formatNumber(meanValueToCostRatio, 2), trend: trendByMetricKey.averageReturnVsCost },
                    { label: "Typical Opening (P50) vs Cost", value: formatNumber(medianValueToCostRatio, 2), trend: trendByMetricKey.typicalReturnVsCost },
                    { label: "Strong Upside (P95) vs Cost", value: formatNumber(summary.p95_value_to_cost_ratio, 2), trend: trendByMetricKey.bigHitUpside },
                    { label: "Jackpot Upside (Top 1% / P99)", value: formatNumber(summary.p99_value_to_cost_ratio, 2), trend: trendByMetricKey.godPullUpside },
                  ]}
                />
                <ScorePillarCard
                  title="Safety"
                  score={displayedSafetyScore}
                  scoreTrend={trendByMetricKey.safetyScore}
                  rankValue={ripBreakdownRowByTitle.get("Safety")?.rankValue ?? null}
                  rankTier={ripBreakdownRowByTitle.get("Safety")?.rankTier ?? null}
                  rankLabel="Safety Rank"
                  sectionMeta={safetyMeta}
                  fallbackSummary={null}
                  infoText={getFormattedTooltip("Safety")}
                  simpleMetrics={[
                    { label: "Typical Opening", value: formatCurrency(percentileP50 ?? summary.median_value), trend: trendByMetricKey.typicalPackValue, infoText: getMetricTooltip("Typical Opening") },
                    { label: "Bad Pack Floor Value", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.badPackFloorValue, infoText: getMetricTooltip("Bad Pack Floor Value") },
                    { label: "Chance to Miss Pack Cost", value: formatPercent(1 - (toNumber(summary.prob_profit) > 1 ? toNumber(summary.prob_profit) / 100 : toNumber(summary.prob_profit)), { probability: true }), trend: trendByMetricKey.chanceToMissPackCost, infoText: getMetricTooltip("Chance to Miss Pack Cost") },
                  ]}
                  advancedMetrics={[
                    { label: "Average Loss When You Miss", value: formatLossCurrency(summary.expected_loss_when_losing), trend: trendByMetricKey.averageLossWhenYouMiss, infoText: getMetricTooltip("Average Loss When You Miss") },
                    { label: "Typical Loss When You Miss", value: formatLossCurrency(summary.median_loss_when_losing), trend: trendByMetricKey.typicalLossWhenYouMiss, infoText: getMetricTooltip("Typical Loss When You Miss") },
                    { label: "Worst 5% Outcome", value: formatCurrency(percentileP5 ?? summary.tail_value_p05), trend: trendByMetricKey.worstFivePercentShortfall?.trend === "unknown" ? trendByMetricKey.badPackFloorValue : trendByMetricKey.worstFivePercentShortfall, infoText: getMetricTooltip("Worst 5% Outcome") },
                  ]}
                />
                <ScorePillarCard
                  title="Stability"
                  score={displayedStabilityScore}
                  scoreTrend={trendByMetricKey.stabilityScore}
                  rankValue={ripBreakdownRowByTitle.get("Stability")?.rankValue ?? null}
                  rankTier={ripBreakdownRowByTitle.get("Stability")?.rankTier ?? null}
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
                <div id="set-detail-desirability" className="h-full scroll-mt-24 md:scroll-mt-28">
                  {/* The authoritative desirability score, from
                      `universalSetDesirability`. It carries its own ALL-SET rank
                      (of 135), not the 21-set simulated cohort rank the retired
                      CA7 pillar used. */}
                  <ScorePillarCard
                    title="Set Desirability"
                    score={toNumber(canonicalUniversalSetDesirability?.score)}
                    scoreTrend={trendByMetricKey.desirabilityScore}
                    rankValue={toNumber(canonicalUniversalSetDesirability?.rank)}
                    rankTier={null}
                    cohortSize={toNumber(canonicalUniversalSetDesirability?.rankedSetCount)}
                    rankLabel="Set Desirability Rank"
                    sectionMeta={desirabilityMeta}
                    fallbackSummary={desirabilitySummary}
                    infoText={SIMPLE_PILLAR_INFO_COPY["Set Desirability"]}
                    simpleMetrics={desirabilityOverviewMetrics}
                    advancedMetrics={[
                      {
                        label: "Top Desirability Drivers",
                        value: null,
                        content: <TopDesirabilityDrivers drivers={topDesirabilityCards} />,
                        trend: null,
                      },
                    ]}
                  />
                </div>
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
                    <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} diagnostics={simulationDrivers.diagnostics} />
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
                    : activeInsightsGraphMode === "historical-trend"
                    ? PERFORMANCE_VS_COST_INFO_TEXT
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
                  <PackValueHistoryChart historyTrend={historyTrend} packCost={summary.pack_cost} summary={summary} marketAsOfDate={marketAsOfDate} />
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

                    <TopEVDriversContent topHits={topHits} meanValue={summary.mean_value} diagnostics={simulationDrivers.diagnostics} />
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

            {visibleSetPageWarnings.length > 0 ? (
              <section className="set-glass-surface-dense rounded-2xl border p-4 sm:p-5">
                <p className="text-sm font-semibold text-[var(--text-primary)]">Warnings</p>
                <div className="mt-2 space-y-1">
                  {visibleSetPageWarnings.map((warning, index) => (
                    <p key={`${warning}:${index}`} className="text-sm text-[var(--text-secondary)]">{warning}</p>
                  ))}
                </div>
              </section>
            ) : null}

            {showDebugTimings || showSetPageDiagnostics ? (
              <section className="set-glass-surface-dense rounded-2xl border p-4 sm:p-5">
                {showDebugTimings ? (
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
                ) : null}
                {showSetPageDiagnostics ? (
                  <div className={["flex flex-wrap items-center gap-2", showDebugTimings ? "mt-3" : ""].join(" ").trim()}>
                    <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Set Page Diagnostics</span>
                    {[...setPageDiagnosticRows, ...initialModuleDiagnosticRows].map(([key, value]) => (
                      <span
                        key={key}
                        className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-1 text-xs text-[var(--text-secondary)]"
                      >
                        {key}: {value}
                      </span>
                    ))}
                  </div>
                ) : null}
                {showSetPageDiagnostics && (suppressedWarnings.length > 0 || debugWarnings.length > 0) ? (
                  <div className="mt-3 space-y-1">
                    {[...suppressedWarnings, ...debugWarnings].map((warning, index) => (
                      <p key={`${warning}:${index}`} className="text-xs text-[var(--text-secondary)]">
                        {warning}
                      </p>
                    ))}
                  </div>
                ) : null}
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
