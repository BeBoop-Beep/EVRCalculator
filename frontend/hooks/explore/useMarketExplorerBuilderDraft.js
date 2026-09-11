"use client";

import { useCallback, useMemo, useReducer } from "react";
import {
  QUERY_ASSET_CARDS,
  buildQueryKey,
  buildQueryLabel,
  normalizeQuerySpec,
  sortEraOptions,
  sortSetOptions,
} from "@/lib/explore/marketExplorerQuery.mjs";
import { evaluateMarketQueryAccess } from "@/lib/access/indexPlanAccess.mjs";
import { resolvePreparedSeriesForSpec } from "@/lib/explore/marketExplorerPreparedResolution.mjs";
import {
  INITIAL_MARKET_EXPLORER_BUILDER_DRAFT,
  compatibleSetIds,
  marketExplorerBuilderDraftReducer,
} from "@/lib/explore/marketExplorerBuilderDraft.mjs";

export default function useMarketExplorerBuilderDraft({ options, currentPlan, preparedSeries, activeSeries }) {
  const [draft, dispatch] = useReducer(
    marketExplorerBuilderDraftReducer,
    INITIAL_MARKET_EXPLORER_BUILDER_DRAFT,
  );
  const eraOptions = useMemo(() => sortEraOptions(options?.eras), [options]);
  const assetSets = useMemo(() => sortSetOptions(options?.sets).filter((entry) =>
    Array.isArray(entry.assets) ? entry.assets.includes(draft.asset) : draft.asset === QUERY_ASSET_CARDS
  ), [options, draft.asset]);
  const visibleSets = useMemo(() => {
    let rows = draft.eraIds.length ? assetSets.filter((entry) => draft.eraIds.includes(entry.eraId)) : assetSets;
    const compatibility = options?.compatibility || {};
    const segmentMap = draft.asset === QUERY_ASSET_CARDS
      ? (compatibility.cardRaritySetIds || compatibility.cardSegmentSetIds) : compatibility.sealedFamilySetIds;
    const allowed = compatibleSetIds([
      { ids: draft.segmentIds, map: segmentMap },
      { ids: draft.pokemonIds, map: compatibility.pokemonSetIds },
    ]);
    if (allowed) rows = rows.filter((entry) => allowed.has(entry.id));
    return rows;
  }, [assetSets, draft.asset, draft.eraIds, draft.segmentIds, draft.pokemonIds, options]);
  const segments = useMemo(() => {
    if (draft.asset === "sealed") return options?.sealedProductFamilies?.segments || [];
    // cardSegments fallback is read-only compatibility for an already-loaded
    // pre-Phase-3 payload; every newly published snapshot carries cardRarities.
    return options?.cardRarities?.rarities || options?.cardSegments?.segments || [];
  }, [options, draft.asset]);
  const pokemonOptions = useMemo(() => draft.asset === QUERY_ASSET_CARDS ? (options?.pokemon || []) : [], [options, draft.asset]);
  const priceSegments = useMemo(() => options?.priceSegments?.[draft.asset] || [], [options, draft.asset]);
  const releaseAgeCohorts = useMemo(() => options?.releaseAgeCohorts || [], [options]);
  const spec = useMemo(() => {
    try { return normalizeQuerySpec(draft); } catch { return null; }
  }, [draft]);
  const labels = useMemo(() => ({
    eraNames: Object.fromEntries(eraOptions.map((entry) => [entry.id, entry.label])),
    setNames: Object.fromEntries(assetSets.map((entry) => [entry.id, entry.label])),
    segmentNames: Object.fromEntries(segments.map((entry) => [entry.key, entry.label])),
    pokemonNames: Object.fromEntries(pokemonOptions.map((entry) => [entry.id, entry.label])),
    priceSegmentNames: Object.fromEntries(priceSegments.map((entry) => [entry.id, entry.label])),
    releaseAgeNames: Object.fromEntries(releaseAgeCohorts.map((entry) => [entry.id, entry.label])),
  }), [eraOptions, assetSets, segments, pokemonOptions, priceSegments, releaseAgeCohorts]);
  const preview = useMemo(() => spec ? buildQueryLabel(spec, labels) : "Select at least one exact item", [spec, labels]);
  const access = useMemo(() => spec ? evaluateMarketQueryAccess(currentPlan, spec) : { allowed: false, requiredPlan: "premium" }, [currentPlan, spec]);
  const prepared = useMemo(() => spec ? resolvePreparedSeriesForSpec(spec, preparedSeries) : null, [spec, preparedSeries]);
  const queryKey = useMemo(() => spec ? buildQueryKey(spec) : null, [spec]);
  const alreadyActive = useMemo(() => (activeSeries || []).some((series) =>
    (prepared && series.key === prepared.key) ||
    (queryKey && series.spec && buildQueryKey(series.spec) === queryKey)
  ), [activeSeries, prepared, queryKey]);

  const setAsset = useCallback((asset) => {
    const supported = new Set(sortSetOptions(options?.sets).filter((entry) =>
      Array.isArray(entry.assets) ? entry.assets.includes(asset) : asset === QUERY_ASSET_CARDS
    ).map((entry) => entry.id));
    dispatch({ type: "asset", asset, setIds: draft.setIds.filter((id) => supported.has(id)) });
  }, [options, draft.setIds]);
  const setField = useCallback((field, value) => dispatch({ type: "field", field, value }), []);
  const setDimensionWithSetReconciliation = useCallback((field, value) => {
    const next = Array.isArray(value) ? value : [];
    const compatibility = options?.compatibility || {};
    const nextSegments = field === "segmentIds" ? next : draft.segmentIds;
    const nextPokemon = field === "pokemonIds" ? next : draft.pokemonIds;
    const segmentMap = draft.asset === QUERY_ASSET_CARDS
      ? (compatibility.cardRaritySetIds || compatibility.cardSegmentSetIds) : compatibility.sealedFamilySetIds;
    const permitted = compatibleSetIds([
      { ids: nextSegments, map: segmentMap },
      { ids: nextPokemon, map: compatibility.pokemonSetIds },
    ]);
    dispatch({ type: "field", field, value: next });
    if (permitted) dispatch({
      type: "field",
      field: "setIds",
      value: draft.setIds.filter((id) => permitted.has(id)),
    });
  }, [draft.asset, draft.pokemonIds, draft.segmentIds, draft.setIds, options]);
  const setEraIds = useCallback((value) => {
    const next = Array.isArray(value) ? value : [];
    const allowed = new Set(assetSets.filter((entry) => !next.length || next.includes(entry.eraId)).map((entry) => entry.id));
    dispatch({ type: "field", field: "eraIds", value: next });
    dispatch({ type: "field", field: "setIds", value: draft.setIds.filter((id) => allowed.has(id)) });
  }, [assetSets, draft.setIds]);

  return {
    draft, spec, preview, access, prepared, alreadyActive, eraOptions, assetSets, visibleSets, segments,
    pokemonOptions, priceSegments, releaseAgeCohorts,
    setAsset, setEraIds,
    setSetIds: (value) => setField("setIds", value),
    setSegmentIds: (value) => setDimensionWithSetReconciliation("segmentIds", value),
    setPokemonIds: (value) => setDimensionWithSetReconciliation("pokemonIds", value),
    setPriceSegmentIds: (value) => setField("priceSegmentIds", value),
    setReleaseAgeCohortIds: (value) => setField("releaseAgeCohortIds", value),
    setMembershipMode: (value) => setField("membershipMode", value),
    setExactItems: (value) => {
      const items = Array.isArray(value) ? value : [];
      dispatch({ type: "field", field: "exactItems", value: items });
      dispatch({ type: "field", field: "instrumentIds", value: items.map((item) => item.instrumentId) });
    },
    replace: (value) => dispatch({ type: "replace", draft: value }),
    clear: () => dispatch({ type: "clear" }),
  };
}
