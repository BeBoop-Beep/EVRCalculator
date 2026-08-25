export const INDEX_PLAN_PLUS = "plus";
export const INDEX_PLAN_PREMIUM = "premium";

export function normalizeIndexPlan(plan) {
  if (typeof plan !== "string") return null;
  const normalized = plan.trim().toLowerCase();
  return normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM
    ? normalized
    : null;
}

export function hasIndexPlusAccess(plan) {
  const normalized = normalizeIndexPlan(plan);
  return normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM;
}

export function hasIndexPremiumAccess(plan) {
  return normalizeIndexPlan(plan) === INDEX_PLAN_PREMIUM;
}

export function resolveRankingsPlanAccess(user) {
  const indexPlan = normalizeIndexPlan(user?.index_plan);
  return {
    canViewRankingsIntelligence: hasIndexPlusAccess(indexPlan),
    accessMode: indexPlan || "basic",
  };
}
