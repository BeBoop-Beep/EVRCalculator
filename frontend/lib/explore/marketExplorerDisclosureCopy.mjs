// ---------------------------------------------------------------------------
// Market Explorer — group disclosure copy.
//
// The reconciliation facts (how much of a parent market its published
// submarkets cover, what sits in the residual, why some segments do not exist)
// are genuinely useful and were previously printed as standing paragraphs
// inside the filter list. That is the wrong place: the rail is a set of
// controls, and two paragraphs of methodology between the checkboxes cost more
// height than the checkboxes themselves.
//
// Same facts, folded into the group header's ⓘ. Nothing here invents a number:
// every value is the published reconciliation, and when the snapshot carries no
// reconciliation the sentence about it is simply not written.
// ---------------------------------------------------------------------------

import { formatBasketValue } from "./marketOverviewPresentation.mjs";

const sentences = (parts) => parts.filter(Boolean).join(" ");

/**
 * Card Rarities ⓘ — coverage, residual, and where the authority lives.
 *
 * `topChaseStatus` is folded in here rather than shown as a separate standing
 * note: "there are no chase rarity submarkets, and here is the reason" is part
 * of what this group's option list means.
 */
export function buildCardRaritiesInfo(cardReconciliation, topChaseStatus = null) {
  const published = cardReconciliation?.publishedSegmentBasketValue;
  const residual = cardReconciliation?.residualBasketValue;
  const residualLabel = cardReconciliation?.residualLabel || "Other Cards";
  return sentences([
    published
      ? `Published rarity submarkets represent ${formatBasketValue(published)} of the Raw Card Market.`
      : "Each option is a rarity submarket built from its own canonical card constituents.",
    residual
      ? `${formatBasketValue(residual)} sits in ${residualLabel} and is not published as its own submarket.`
      : null,
    "A rarity gets its own market only when it is broad enough to be one — enough priced cards, across enough sets — so base and single-set rarities stay in the residual rather than becoming an index over a handful of cards.",
    "The taxonomy is backend-defined: a rarity the backend does not publish cannot appear here.",
    topChaseStatus && topChaseStatus.available !== true && topChaseStatus.reason
      ? `Chase rarity segments are not published. ${topChaseStatus.reason}`
      : null,
  ]);
}

/** Sealed Product Families ⓘ — tracked total, coverage, residual. */
export function buildSealedFamiliesInfo(reconciliation) {
  const parent = reconciliation?.parentBasketValue;
  const published = reconciliation?.publishedSegmentBasketValue;
  const residual = reconciliation?.residualBasketValue;
  const residualLabel = reconciliation?.residualLabel || "Other Sealed";
  return sentences([
    parent ? `Total tracked Sealed value is ${formatBasketValue(parent)}.` : null,
    published ? `Published product families represent ${formatBasketValue(published)} of it.` : null,
    residual
      ? `${formatBasketValue(residual)} sits in ${residualLabel} — tracked sealed products whose family is not published as its own submarket, such as tins, collection boxes and bundles the classifier does not resolve to a family with enough history to index.`
      : null,
    "Families are backend-classified: a family the classifier does not publish cannot appear here.",
  ]);
}

/** Asset Market ⓘ — what the group is, and what it deliberately excludes. */
export const ASSET_MARKET_INFO =
  "Asset classes: the same collectible held in a different form, each with its own market. Raw singles, sealed product, and graded slabs once canonical graded analytics exist. Chase is not an asset class — it is a ranking mode applied to a filtered universe, so the published per-set chase basket lives under Benchmarks and custom chase markets are built in Build a Market.";

/** Benchmarks ⓘ — what a benchmark is here. */
export const BENCHMARKS_INFO =
  "Canonical reference markets to read another series against. They are not asset classes, and selecting one adds only that line.";

/** Era & Sets ⓘ — the scope semantics, stated plainly. */
export const ERA_SETS_INFO =
  "Canonical eras and the tracked sets inside them. Selecting one sets a research scope; it does not add a line, because no standalone era or set index is published and filtering an already-aggregated global index in the browser would be a different number from a market built over that scope's own constituents. Hand a scope to Build a Market to chart it for real.";
