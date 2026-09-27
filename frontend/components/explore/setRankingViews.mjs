import { INDEX_PLAN_PLUS } from "../../lib/access/indexPlanAccess.mjs";

export const SET_RANKING_VIEWS = Object.freeze([
  { value: "ripScore", label: "RIP Score", requiredPlan: null },
  { value: "financial", label: "Financial", requiredPlan: INDEX_PLAN_PLUS },
  { value: "collectorAppeal", label: "Collector", requiredPlan: INDEX_PLAN_PLUS },
  { value: "chaseAccessibility", label: "Chase", requiredPlan: INDEX_PLAN_PLUS },
  { value: "packEconomics", label: "Pack Economics", requiredPlan: null },
  { value: "compareMetrics", label: "Compare Metrics", requiredPlan: INDEX_PLAN_PLUS },
]);

export function findSetRankingView(value) {
  return SET_RANKING_VIEWS.find((view) => view.value === value) || SET_RANKING_VIEWS[0];
}
