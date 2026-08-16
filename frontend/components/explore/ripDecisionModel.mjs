import { readCanonicalBlock } from "./canonicalRipV7.mjs";
import { buildRipDrivers } from "./ripDrivers.mjs";
import { getRipQualitativeLabel } from "./ripQualitativeLabel.mjs";
import { normalizeRarityKey, selectPullRateRows } from "../pokemon/set-page/PullRates/pullRateRowsSelector.mjs";

function number(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstNumber(...values) {
  for (const value of values) {
    const parsed = number(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return null;
}

/**
 * NOTE ON SCOPE
 * -------------
 * A broad decision-contract reader used to live here. It searched invented
 * canonical/summary shapes and invented snake_case chase keys that the backend
 * has never emitted, which was the root cause of the broken decision pass:
 * every field resolved to null while the page claimed the odds were
 * unavailable. A regression test asserts those names never come back, so this
 * note deliberately describes them rather than spelling them out.
 *
 * It is gone. Canonical decision information — the canonical chase, break-even,
 * product economics, probability thresholds — flows ONLY through
 * `ripDecisionContract.mjs`. Nothing in this file parses the decision contract.
 *
 * What remains below is deliberately narrow: market-context cards for "Other
 * Major Value Chases", which come from the pre-existing chase-card array and
 * carry no modeled odds.
 */

/** Case/spacing-insensitive name, the last-resort identity for a market card. */
function normalizedName(value) {
  const name = firstText(value);
  return name ? name.toLowerCase().replace(/\s+/g, " ") : null;
}

function variantIdOf(card) {
  return firstText(card.cardVariantId, card.card_variant_id, card.variantId, card.variant_id);
}

function cardIdOf(card) {
  return firstText(card.cardId, card.card_id, card.id);
}

/**
 * Whether two chase cards are the same card for deduplication purposes.
 *
 * A TRUE fallback ladder, evaluated between the two objects rather than by
 * reducing each to a single identity first. Reducing each side independently
 * meant a card that had a variant id and one that only had a card id were
 * compared as different "kinds" and never matched — so a market row missing
 * variant identity survived alongside the Top Chase it duplicates.
 *
 * 1. BOTH have a variant id  -> variant ids decide, and that is final.
 *    Two known-different variants of one Pokemon are different chases, so this
 *    must NOT fall through to card id or name when the variants disagree.
 * 2. Otherwise BOTH have a card id -> card ids decide.
 * 3. Otherwise -> normalized names, the last resort for data with no stable ids.
 */
export function isSameChaseCard(left, right) {
  if (!left || typeof left !== "object" || !right || typeof right !== "object") return false;

  const leftVariant = variantIdOf(left);
  const rightVariant = variantIdOf(right);
  if (leftVariant && rightVariant) return leftVariant === rightVariant;

  const leftCard = cardIdOf(left);
  const rightCard = cardIdOf(right);
  if (leftCard && rightCard) return leftCard === rightCard;

  const leftName = normalizedName(left.name ?? left.cardName ?? left.card_name);
  const rightName = normalizedName(right.name ?? right.cardName ?? right.card_name);
  return Boolean(leftName) && leftName === rightName;
}

/**
 * Market-context cards for "Other Major Value Chases".
 *
 * This helper normalizes and filters market cards ONLY. It does not read Top
 * Chase, break-even, probability thresholds, product economics or
 * `payload.ripDecision` — those belong to `ripDecisionContract.mjs`.
 *
 * `excludeCard` is the canonical Top Chase, which the page already shows above
 * with exact modeled odds. Repeating it here as the #1 "other" chase is pure
 * duplication that adds no information.
 *
 * Matching walks the variant -> card -> name ladder in `isSameChaseCard`, so two
 * known-different variants never collapse while a row missing variant identity
 * can still be matched on the canonical card id both sides carry.
 *
 * The Top Chase is removed BEFORE the limit is applied, so the section always
 * renders the intended number of genuinely secondary cards.
 */
export function selectMarketChaseCards(chaseCards = [], { excludeCard = null, limit = 4 } = {}) {
  return (Array.isArray(chaseCards) ? chaseCards : [])
    .filter((card) => card?.name || card?.cardName || card?.card_name)
    .filter((card) => !excludeCard || !isSameChaseCard(card, excludeCard))
    .slice(0, limit);
}

export function buildRipDecisionModel({ canonical, summary = {}, pullRateAssumptions = null } = {}) {
  const overall = readCanonicalBlock(canonical?.overall);
  const financial = readCanonicalBlock(canonical?.financialRip);
  const collector = readCanonicalBlock(canonical?.collectorAppeal);
  const packCost = number(summary.pack_cost);
  const expectedValue = number(summary.mean_value);
  const typicalOpening = number(summary.median_value);
  const recoverCostProbability = number(summary.prob_profit);
  const expectedLoss = firstNumber(summary.expected_loss_per_pack, summary.expectedLossPerPack);

  let verdict = "Canonical RIP ranking is unavailable for this set.";
  if (overall.rank !== null && overall.cohortSize !== null) {
    const leading = overall.rank <= Math.max(3, Math.ceil(overall.cohortSize * 0.2));
    const economicsBelowCost = packCost !== null && expectedValue !== null && expectedValue < packCost;
    if (leading && economicsBelowCost) verdict = "One of the strongest relative opening options, though expected returns remain below pack cost.";
    else if (leading) verdict = "One of the strongest relative opening options in the currently tracked set cohort.";
    else if (economicsBelowCost) verdict = "A middle-of-the-pack opening option with expected returns below today's pack cost.";
    else verdict = "Its combined opening economics and collector appeal place it in the middle of the tracked cohort.";
  }

  // HELPS / HURTS / RESULT and the takeaway are one deterministic decision, so
  // the sentence can never contradict the labels shown above it.
  const drivers = buildRipDrivers({ financial, collector, overall });
  const takeaway = drivers.takeaway;
  const qualitativeLabel = getRipQualitativeLabel({
    tier: overall.tier,
    rank: overall.rank,
    cohortSize: overall.cohortSize,
  });

  const consumerPriority = new Map([
    ["illustration rare", 1],
    ["ultra rare", 2],
    ["special illustration rare", 3],
    ["hyper rare", 4],
    ["double rare", 5],
  ]);
  const openingOdds = selectPullRateRows(pullRateAssumptions)
    .map(({ row, groupKey }) => ({
      label: String(row?.rarity || "").trim(),
      rarityKey: normalizeRarityKey(row?.rarity),
      denominator: number(row?.rarityOddsDenominator),
      groupKey,
    }))
    .filter((row) => row.label && row.denominator > 0 && (row.groupKey === "hit_rarity_model" || consumerPriority.has(row.rarityKey)))
    .sort((left, right) => (consumerPriority.get(left.rarityKey) ?? 20) - (consumerPriority.get(right.rarityKey) ?? 20))
    .slice(0, 3)
    .map(({ label, denominator }) => ({
      label: label.replace(/\b\w/g, (letter) => letter.toUpperCase()),
      denominator,
    }));

  return {
    overall,
    financial,
    collector,
    packCost,
    expectedValue,
    typicalOpening,
    recoverCostProbability,
    expectedLoss,
    verdict,
    qualitativeLabel,
    drivers,
    takeaway,
    openingOdds,
  };
}
