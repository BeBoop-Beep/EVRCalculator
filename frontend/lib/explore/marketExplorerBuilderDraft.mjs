import { QUERY_ASSET_CARDS, QUERY_MODE_ALL, QUERY_MEMBERSHIP_FILTERS } from "./marketExplorerQuery.mjs";

export const INITIAL_MARKET_EXPLORER_BUILDER_DRAFT = Object.freeze({
  asset: QUERY_ASSET_CARDS,
  eraIds: [],
  setIds: [],
  segmentIds: [],
  pokemonIds: [],
  priceSegmentIds: [],
  releaseAgeCohortIds: [],
  mode: QUERY_MODE_ALL,
  topN: null,
  membershipMode: QUERY_MEMBERSHIP_FILTERS,
  instrumentIds: [],
  exactItems: [],
});

const FILTER_DEFINITION_FIELDS = new Set([
  "eraIds", "setIds", "segmentIds", "pokemonIds", "priceSegmentIds",
  "releaseAgeCohortIds", "mode", "topN",
]);

export function compatibleSetIds(axisSelections) {
  const axisUnions = (axisSelections || []).map(({ ids = [], map = {} }) =>
    ids.length ? new Set(ids.flatMap((id) => map?.[id] || [])) : null
  ).filter(Boolean);
  if (!axisUnions.length) return null;
  return new Set([...axisUnions[0]].filter((setId) => axisUnions.every((allowed) => allowed.has(setId))));
}

function enterMembershipMode(state, value) {
  if (value === "explicit") {
    // Exact Basket is a list of physical leaves, not a filtered universe.
    // Keep the local exact draft, but remove every independent narrowing axis
    // before an explicit spec can be normalized or executed.
    return {
      ...state,
      membershipMode: "explicit",
      eraIds: [], setIds: [], segmentIds: [], pokemonIds: [],
      priceSegmentIds: [], releaseAgeCohortIds: [], mode: QUERY_MODE_ALL, topN: null,
    };
  }
  return { ...state, membershipMode: QUERY_MEMBERSHIP_FILTERS };
}

export function marketExplorerBuilderDraftReducer(state, action) {
  if (action.type === "clear") return { ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT };
  if (action.type === "asset") return { ...state, asset: action.asset, setIds: action.setIds, segmentIds: [], pokemonIds: [], instrumentIds: [], exactItems: [], membershipMode: QUERY_MEMBERSHIP_FILTERS };
  if (action.type === "replace") return { ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, ...action.draft };
  if (action.type === "field") {
    if (action.field === "membershipMode") return enterMembershipMode(state, action.value);
    // Touching an ordinary market-definition control is an intentional return
    // to Filtered Market. Exact draft fields may remain locally for reopening,
    // but cannot influence the normalized filtered spec or its execution.
    if (FILTER_DEFINITION_FIELDS.has(action.field)) {
      return { ...state, [action.field]: action.value, membershipMode: QUERY_MEMBERSHIP_FILTERS };
    }
    return { ...state, [action.field]: action.value };
  }
  return state;
}
