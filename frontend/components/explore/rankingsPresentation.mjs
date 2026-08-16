function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function first(target, paths) {
  for (const path of paths) {
    let value = target;
    for (const key of path.split(".")) value = value && typeof value === "object" ? value[key] : null;
    if (value !== null && value !== undefined && value !== "") return value;
  }
  return null;
}

/** Optional presentation adapter for canonical chase fields as they arrive. */
export function readOptionalRankingsChase(target) {
  const name = first(target, ["ripDecision.topChase.cardName", "rip_decision.top_chase.card_name", "rankingsChase.cardName", "topChase.cardName", "top_chase.card_name", "top_chase_name"]);
  if (!name) return null;
  return {
    name: String(name),
    marketValue: number(first(target, ["ripDecision.topChase.currentMarketPrice", "rip_decision.top_chase.current_market_price", "rankingsChase.currentMarketPrice", "topChase.currentMarketPrice", "top_chase.current_market_price", "top_chase_market_value"])),
    oneInPacks: number(first(target, ["ripDecision.topChase.impliedOddsOneInN", "rip_decision.top_chase.implied_odds_one_in_n", "rankingsChase.impliedOddsOneInN", "topChase.impliedOddsOneInN", "top_chase.implied_odds_one_in_n", "top_chase_one_in_packs"])),
    packsTo50: number(first(target, ["ripDecision.topChase.packsFor50PercentChance", "rip_decision.top_chase.packs_for_50_percent_chance", "rankingsChase.packsFor50PercentChance", "topChase.packsFor50PercentChance", "top_chase.packs_for_50_percent_chance", "modeled_packs_to_50"])),
  };
}
