// The exact target fields `/Market`'s Top Rankings ladder renders — and nothing
// else.
//
// WHY THIS EXISTS
// ---------------
// `ExploreTopRankings` is a "use client" component, so every property of every
// object handed to it is serialized into the RSC flight payload and shipped to
// the browser. It was being handed whole Rankings targets, which made the
// /Market document 1,415,318 bytes (194,229 gzipped) — carrying
// `publicRipContractV8`, `financialRipV3`, `openingExperience`,
// `universalSetDesirability`, `overallRipV5/V6`, `rip`, `ripCore` and the rest
// of the canonical Rankings document into a client bundle that reads NONE of
// them. Measured: the ladder consumes 16,877 of 1,407,091 target bytes (1.2%).
//
// WHAT THIS IS NOT
// ----------------
// This is NOT the fix for the DB->backend transfer. `getRipStatisticsTargets`
// still fetches the complete canonical document, deliberately: it is the SAME
// shared cohort read Rankings and set detail depend on, and giving /Market its
// own narrower backend request would fracture that canonical cache identity and
// buy a second cold cohort read. Removing the server-side transfer is a
// separate, publication-level question.
//
// What this DOES remove is the server->browser copy, which is pure waste at any
// payload size: the ladder cannot render a field it never reads.
//
// EVERY KEY BELOW IS READ SOMEWHERE
// ---------------------------------
// Both casings are kept because the consumers read camelCase with a snake_case
// fallback (`target?.checklistSetValue ?? target?.checklist_set_value`), and a
// projection that dropped either half would silently blank a column on whichever
// casing the publication happens to carry.
//
//   target_type, target_id  ExploreTopRankings rows, buildTcgSetHrefFromTarget,
//                           mobilePreviewResetKey
//   set_id, id              rankingMovement.getStableSetId
//   name                    row label, href slug, ladder tie-break, initials
//   logo_image_url          LadderLogo
//   symbol_image_url        LadderLogo fallback
//   checklistSetValue*      readSetValue — the value the ladder sorts by
//   checklistSetValueAsOf*  readSetValueAsOf / latestAsOf
//   ...PricedCardCount*     readPricedCoverage
//   ...TotalCardCount*      readPricedCoverage
//   previousChecklistSetValue7d*  buildPreviousSetValueRanks / getSetValueMovement
//   setValueComparisonStatus7d*   movement availability gate — "no comparable
//                                 snapshot" must stay distinguishable from zero
const MARKET_RANKING_FIELDS = Object.freeze([
  "target_type",
  "target_id",
  "set_id",
  "id",
  "name",
  "logo_image_url",
  "symbol_image_url",
  "checklistSetValue",
  "checklist_set_value",
  "checklistSetValueAsOf",
  "checklist_set_value_as_of",
  "checklistSetValuePricedCardCount",
  "checklist_set_value_priced_card_count",
  "checklistSetValueTotalCardCount",
  "checklist_set_value_total_card_count",
  "previousChecklistSetValue7d",
  "previous_checklist_set_value_7d",
  "setValueComparisonStatus7d",
  "set_value_comparison_status_7d",
]);

/**
 * One target -> the ladder's view of it.
 *
 * A key the target does not carry is OMITTED rather than written as `undefined`,
 * so the projection cannot turn "the publication has no value here" into a
 * present-but-empty field, and cannot add weight back to the flight payload.
 */
function projectTarget(target) {
  if (!target || typeof target !== "object") {
    return target;
  }
  const projected = {};
  for (const field of MARKET_RANKING_FIELDS) {
    if (target[field] !== undefined) {
      projected[field] = target[field];
    }
  }
  return projected;
}

/**
 * Project the Market ladder's targets. Order is preserved exactly — the ladder
 * does its own set-value sort, but the incoming cohort order is still the
 * canonical rank order and nothing here may reorder it.
 */
export function projectMarketRankingTargets(targets) {
  return Array.isArray(targets) ? targets.map(projectTarget) : [];
}

export { MARKET_RANKING_FIELDS };
