import { QUERY_ASSET_CARDS, QUERY_MODE_ALL } from "./marketExplorerQuery.mjs";

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
});

export function marketExplorerBuilderDraftReducer(state, action) {
  if (action.type === "clear") return { ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT };
  if (action.type === "asset") return { ...state, asset: action.asset, setIds: action.setIds, segmentIds: [], pokemonIds: [] };
  if (action.type === "replace") return { ...INITIAL_MARKET_EXPLORER_BUILDER_DRAFT, ...action.draft };
  if (action.type === "field") return { ...state, [action.field]: action.value };
  return state;
}
