import { MARKET_CHART_VIEW_ACTIVITY, MARKET_CHART_VIEW_INDEX } from "../../components/explore/marketPerformanceDomain.mjs";

export const ACTIVITY_WINDOW_BY_TIMEFRAME = Object.freeze({ "7D": 7, "30D": 30, "3M": 90, "6M": 180 });
export const DEFAULT_ACTIVITY_TIMEFRAME = "30D";

export const activityWindowForTimeframe = (timeframe) => ACTIVITY_WINDOW_BY_TIMEFRAME[timeframe] ?? null;
export const activityTimeframeAvailable = (timeframe) => activityWindowForTimeframe(timeframe) !== null;

export function enterActivityView(timeframe) {
  return {
    chartViewMode: MARKET_CHART_VIEW_ACTIVITY,
    timeframe: activityTimeframeAvailable(timeframe) ? timeframe : DEFAULT_ACTIVITY_TIMEFRAME,
  };
}

export function reconcileActivityView(chartViewMode, focusedSeries, capability) {
  if (chartViewMode !== MARKET_CHART_VIEW_ACTIVITY) return chartViewMode;
  return focusedSeries?.asset === "cards" && capability?.available === true
    ? chartViewMode
    : MARKET_CHART_VIEW_INDEX;
}
