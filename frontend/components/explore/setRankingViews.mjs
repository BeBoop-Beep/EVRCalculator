import { INDEX_PLAN_PLUS } from "../../lib/access/indexPlanAccess.mjs";

export const SET_RANKING_VIEWS = Object.freeze([
  { value: "ripScore", label: "RIP Score", requiredPlan: null },
  { value: "packEconomics", label: "Pack Economics", requiredPlan: INDEX_PLAN_PLUS },
]);

export function findSetRankingView(value) {
  return SET_RANKING_VIEWS.find((view) => view.value === value) || SET_RANKING_VIEWS[0];
}
