"use client";

import { useCallback, useEffect, useMemo, useReducer } from "react";
import {
  EXPLORER_SELECTION_ACTIONS,
  reconcileAssetUniverse,
  reconcileCardSegmentIds,
  reconcileSealedFamilyIds,
  reduceExplorerSelection,
  resolveAvailableAssetKeys,
  resolveAvailableCardSegmentIds,
  resolveAvailableSealedFamilyIds,
  resolveSelectedSeriesIds,
} from "@/lib/explore/marketExplorerState.mjs";
import {
  isCardSegmentSeriesId,
  isSealedSegmentSeriesId,
} from "@/lib/explore/marketExplorerSeries.mjs";

// ---------------------------------------------------------------------------
// The prepared-market selection, owned by ONE reducer.
//
// WHY A REDUCER AND NOT THREE SETTERS: reduceExplorerSelection documents it in
// full. The short version is that the whole selection moves in one pure step,
// so React replaying an update — StrictMode double-invocation, or re-running
// the queue from a base state — can never apply half of it. The previous
// nested-setter version cancelled every quick-segment click silently.
//
// The published id lists travel WITH each dispatch rather than being closed
// over, so a re-published snapshot cannot leave the reducer reconciling against
// an availability list that no longer exists.
// ---------------------------------------------------------------------------
export default function useMarketExplorerSelection({
  overview, sealedSegments, cardSegments, initialState,
}) {
  const availableKeys = useMemo(() => resolveAvailableAssetKeys(overview), [overview]);
  const availableSealedIds = useMemo(
    () => resolveAvailableSealedFamilyIds(sealedSegments), [sealedSegments]);
  const availableCardIds = useMemo(
    () => resolveAvailableCardSegmentIds(cardSegments), [cardSegments]);

  const [selection, dispatch] = useReducer(reduceExplorerSelection, initialState, (initial) => {
    const sealedFamilyIds = reconcileSealedFamilyIds(initial?.sealedFamilyIds, availableSealedIds);
    const segmentIds = reconcileCardSegmentIds(initial?.segmentIds, availableCardIds);
    return {
      // An empty parent selection is legitimate — a link asking only for SIR
      // charts only SIR — so reconciliation is told there is other content
      // rather than resurrecting every market to avoid a blank chart.
      assetUniverse: reconcileAssetUniverse(initial?.assetUniverse, availableKeys, {
        hasOtherSeries: sealedFamilyIds.length > 0 || segmentIds.length > 0,
      }),
      sealedFamilyIds,
      segmentIds,
    };
  });

  const available = useMemo(() => ({
    assetKeys: availableKeys,
    sealedFamilyIds: availableSealedIds,
    cardSegmentIds: availableCardIds,
  }), [availableKeys, availableSealedIds, availableCardIds]);

  // A re-published snapshot can add or drop a market or a submarket. Selection
  // follows it rather than pointing at a series that no longer exists. The
  // reducer makes this idempotent, so re-running it changes nothing.
  useEffect(() => {
    dispatch({ type: EXPLORER_SELECTION_ACTIONS.reconcile, available });
  }, [available]);

  const toggleMarket = useCallback((seriesId) => {
    dispatch({ type: EXPLORER_SELECTION_ACTIONS.toggleMarket, seriesId, available });
  }, [available]);
  const toggleSealed = useCallback((seriesId) => {
    dispatch({ type: EXPLORER_SELECTION_ACTIONS.toggleSealedFamily, seriesId, available });
  }, [available]);
  const toggleCardSegment = useCallback((seriesId) => {
    dispatch({ type: EXPLORER_SELECTION_ACTIONS.toggleCardSegment, seriesId, available });
  }, [available]);

  const selectedSeriesIds = useMemo(() => resolveSelectedSeriesIds(selection), [selection]);

  return {
    selection,
    selectedSeriesIds,
    toggleMarket,
    toggleSealed,
    toggleCardSegment,
    /** One entry point for the legend and the Active Markets chips, neither of
     *  which cares which axis a series came from. */
    toggleAny: (seriesId, removeQuery) => {
      if (String(seriesId).startsWith("query:")) removeQuery?.(seriesId);
      else if (isSealedSegmentSeriesId(seriesId)) toggleSealed(seriesId);
      else if (isCardSegmentSeriesId(seriesId)) toggleCardSegment(seriesId);
      else toggleMarket(seriesId);
    },
  };
}
