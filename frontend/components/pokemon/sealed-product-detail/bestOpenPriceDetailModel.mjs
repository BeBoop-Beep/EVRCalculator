// A threshold is a modeled price for a fixed-budget whole-unit strategy.
// It is not proof that every cheaper price/quantity also ranks first.
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export function bestOpenThresholdCopy(bestOpen) {
  const price = Number(bestOpen?.bestOpenPrice);
  if (!Number.isFinite(price) || price <= 0) return null;
  return bestOpen.status === "current_number_one_with_headroom"
    ? `At ${money.format(price)} per unit, the published leader still ranks #1 in the same modeled Full Market cohort.`
    : `At ${money.format(price)} per unit, this product's modeled opening strategy would reach #1 in the published Full Market cohort.`;
}
export function bestOpenStrategyCopy(bestOpen) {
  const budget = Number(bestOpen?.sourceFullMarketBudget);
  const quantity = Number(bestOpen?.thresholdQuantity);
  if (!Number.isFinite(budget) || budget <= 0 || !Number.isInteger(quantity) || quantity < 1) return null;
  return `${quantity.toLocaleString("en-US")} whole ${quantity === 1 ? "unit" : "units"} within a ${money.format(budget)} comparison budget. This is not a one-unit ranking.`;
}
export function bestOpenUnavailableCopy(reason) {
  if (reason === "product_not_in_current_full_market") return "This product is not part of the current Full Market Best-Open cohort.";
  if (["stale_source_publication", "no_published_snapshot", "no_live_budget_ranking_source", "incomplete_snapshot_rows"].includes(reason)) {
    return "A current Best-Open Price has not been published for this Full Market ranking yet.";
  }
  return "Best-Open Price is temporarily unavailable for this product.";
}
