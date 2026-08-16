import { getRankForMode, getRankedSetCountForMode } from "../../constants/exploreRankingConfig.mjs";
import { readAverageLoss, readCollectorAppealBlock } from "./rankingsSort.mjs";

function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isTopQuartile(rank, cohort) {
  const r = number(rank), n = number(cohort);
  return r !== null && n !== null && n > 0 && r <= Math.max(1, Math.ceil(n / 4));
}

function relativeRank(targets, leader, read) {
  const ranked = [...targets].map((target, index) => ({ target, index, value: number(read(target)) }))
    .filter((entry) => entry.value !== null).sort((a, b) => b.value - a.value || a.index - b.index);
  const index = ranked.findIndex((entry) => entry.target === leader);
  return index < 0 ? null : { rank: index + 1, cohort: ranked.length };
}

/** Presentation-only claims. No values are blended and no score is produced. */
export function explainRankingsLeader(targets) {
  const rows = Array.isArray(targets) ? targets : [], leader = rows[0];
  if (!leader) return null;
  const claims = [];
  if (isTopQuartile(getRankForMode(leader, "financial"), getRankedSetCountForMode(leader, "financial"))) claims.push("Top-tier financial outcomes");
  const appeal = readCollectorAppealBlock(leader);
  if (isTopQuartile(appeal.rank, appeal.cohortSize)) claims.push("elite collector appeal");
  const chance = relativeRank(rows, leader, (target) => target?.prob_profit);
  if (chance && isTopQuartile(chance.rank, chance.cohort)) claims.push("one of the better chances to beat cost");
  const downside = relativeRank(rows, leader, (target) => { const loss = readAverageLoss(target); return loss === null ? null : -loss; });
  if (downside && isTopQuartile(downside.rank, downside.cohort)) claims.push("lower downside than most ranked sets");
  const ev = relativeRank(rows, leader, (target) => target?.mean_value);
  if (ev && isTopQuartile(ev.rank, ev.cohort)) claims.push("strong expected value");
  return claims.length ? `${claims.slice(0, 2).join(" + ")}.` : "The strongest Overall RIP profile in the current ranked cohort.";
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
  const name = first(target, ["rankingsChase.name", "topChase.name", "top_chase.name", "top_chase_name"]);
  if (!name) return null;
  return {
    name: String(name),
    marketValue: number(first(target, ["rankingsChase.marketValue", "topChase.marketValue", "top_chase.market_value", "top_chase_market_value"])),
    oneInPacks: number(first(target, ["rankingsChase.oneInPacks", "topChase.oneInPacks", "top_chase.one_in_packs", "top_chase_one_in_packs"])),
    packsTo50: number(first(target, ["rankingsChase.packsTo50", "topChase.packsTo50", "top_chase.packs_to_50", "modeled_packs_to_50"])),
    spendTo50: number(first(target, ["rankingsChase.spendTo50", "topChase.spendTo50", "top_chase.spend_to_50", "modeled_spend_to_50"])),
  };
}
