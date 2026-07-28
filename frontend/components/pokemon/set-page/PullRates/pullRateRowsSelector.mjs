// Flattens the grouped pull-rate payload (pack_structure / hit_rarity_model /
// special_pack_rules, or the flat `rows` fallback) into ONE ordered row list
// for the condensed Pull Rate Assumptions table.
//
// This is shaping only — it never recomputes a pull rate. Every numeric field
// is passed through untouched so the table keeps formatting the same canonical
// values with the same helpers (see pullRateFormatting.mjs).
//
// Ordering: the payload's own order is preserved wherever two rows share a
// tier, so a set whose rows already arrive canonically ordered renders in that
// order. A tier rank is applied on top because the frontend merges several
// arrays and the backend emits hit_rarity_model rows alphabetically
// (`for rarity_key in sorted(hit_rarity_keys)` in explore_page_service.py) —
// which would otherwise interleave Hyper Rare between Double Rare and
// Illustration Rare.
import { buildGroupsForRender } from "./pullRateFormatting.mjs";

const SPECIAL_PACK_GROUP_KEY = "special_pack_rules";

// Tier numbering matches the canonical presentation order:
//   1 standard pack slots, 2 reverse/parallel slots, 3 Double Rare + other
//   standard hits, 4 Illustration Rare, 5 Ultra Rare, 6 Special Illustration
//   Rare, 7 Hyper Rare, 8 other set-specific/special slots.
const OTHER_STANDARD_HIT_TIER = 3;
const OTHER_SPECIAL_SLOT_TIER = 8;

const RARITY_TIER_RANKS = new Map([
  ["common", 1],
  ["uncommon", 1],
  ["rare", 1],
  ["regular reverse", 2],
  ["reverse", 2],
  ["reverse holo", 2],
  ["reverse holofoil", 2],
  ["parallel", 2],
  ["parallel foil", 2],
  ["double rare", 3],
  ["illustration rare", 4],
  ["ultra rare", 5],
  ["special illustration rare", 6],
  ["hyper rare", 7],
]);

export function normalizeRarityKey(rarity) {
  return String(rarity || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\s+/g, " ");
}

function normalizeGroupKey(groupKey) {
  return String(groupKey || "").trim().toLowerCase();
}

// Unknown rarities stay grouped with their own kind rather than being invented
// into a tier: an unrecognised special-pack slot sorts last, an unrecognised
// hit rarity sorts with the other standard hits.
export function selectRarityTier(rarity, groupKey) {
  const knownTier = RARITY_TIER_RANKS.get(normalizeRarityKey(rarity));
  if (knownTier !== undefined) {
    return knownTier;
  }
  if (normalizeGroupKey(groupKey) === SPECIAL_PACK_GROUP_KEY) {
    return OTHER_SPECIAL_SLOT_TIER;
  }
  return OTHER_STANDARD_HIT_TIER;
}

export function selectPullRateRows(pullRateAssumptions) {
  const groups = buildGroupsForRender(pullRateAssumptions);

  const entries = [];
  groups.forEach((group, groupIndex) => {
    const groupKey = group?.key || null;
    const rows = Array.isArray(group?.rows) ? group.rows : [];
    rows.forEach((row, rowIndex) => {
      if (!row || typeof row !== "object") {
        return;
      }
      // formatPullFrequency branches on the row's group, so the enclosing
      // group key is carried onto rows that don't already declare one — the
      // flattened row must format exactly as it did inside its group table.
      const resolvedGroup = row.group || groupKey;
      entries.push({
        key: `${groupKey || group?.label || "group"}:${row.rarity || "unknown"}:${row.slotLabel || ""}:${rowIndex}`,
        row: { ...row, group: resolvedGroup },
        groupKey: resolvedGroup,
        tier: selectRarityTier(row.rarity, resolvedGroup),
        groupIndex,
        rowIndex,
      });
    });
  });

  entries.sort(
    (left, right) =>
      left.tier - right.tier ||
      left.groupIndex - right.groupIndex ||
      left.rowIndex - right.rowIndex
  );

  return entries.map(({ key, row, groupKey }) => ({ key, row, groupKey }));
}
