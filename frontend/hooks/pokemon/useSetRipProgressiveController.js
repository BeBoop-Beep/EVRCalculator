"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPokemonSetRipRankContext, selectSetRipRankContext } from "@/lib/pokemon/pokemonSetRipRankContextClient.mjs";
import {
  getPokemonSetRipAdvanced,
  getPokemonSetRipSimulationEvidence,
  selectSameRunRipAdvanced,
  selectSameRunRipSimulation,
} from "@/lib/pokemon/pokemonSetRipProgressiveClient.mjs";

const rankIdle = { status: "idle", setId: null, expectedCalculationRunId: null, payload: null, error: null };
const evidenceIdle = { status: "idle", setId: null, calculationRunId: null, payload: null, error: null };

export default function useSetRipProgressiveController({
  setId,
  calculationRunId,
  canonicalSource,
  rankContextEnabled,
  canViewProductRipIntelligence,
}) {
  const [rankContextState, setRankContextState] = useState(rankIdle);
  const [simulationState, setSimulationState] = useState(evidenceIdle);
  const [advancedState, setAdvancedState] = useState(evidenceIdle);
  const activeIdentityRef = useRef(null);
  const rankRequestKeyRef = useRef(null);
  activeIdentityRef.current = setId && calculationRunId ? `${setId}|${calculationRunId}` : null;

  const loadRankContext = useCallback(({ force = false } = {}) => {
    if (!canViewProductRipIntelligence || !setId || !calculationRunId) return;
    const identity = `${setId}|${calculationRunId}`;
    if (!force && rankRequestKeyRef.current === identity) return;
    rankRequestKeyRef.current = identity;
    setRankContextState({ status: "loading", setId, expectedCalculationRunId: calculationRunId, payload: null, error: null });
    getPokemonSetRipRankContext(setId, calculationRunId, { force }).then((payload) => {
      if (activeIdentityRef.current !== identity) return;
      const selected = selectSetRipRankContext(payload, { setId, calculationRunId });
      setRankContextState({ status: selected ? "success" : "error", setId, expectedCalculationRunId: calculationRunId, payload: selected, error: selected ? null : "Rank context response was malformed." });
    }).catch((error) => {
      if (activeIdentityRef.current !== identity) return;
      rankRequestKeyRef.current = null;
      setRankContextState({ status: "error", setId, expectedCalculationRunId: calculationRunId, payload: null, error: error?.message || "Rank context unavailable." });
    });
  }, [calculationRunId, canViewProductRipIntelligence, setId]);

  const loadSimulation = useCallback(({ force = false } = {}) => {
    if (!setId || !calculationRunId) return;
    const identity = `${setId}|${calculationRunId}`;
    setSimulationState((current) => current.status === "loading" && !force ? current : { status: "loading", setId, calculationRunId, payload: null, error: null });
    getPokemonSetRipSimulationEvidence(setId, calculationRunId, { force }).then((payload) => {
      if (activeIdentityRef.current !== identity) return;
      const compatible = selectSameRunRipSimulation(payload, { setId, calculationRunId });
      setSimulationState({ status: compatible ? "success" : "stale", setId, calculationRunId, payload: compatible, error: compatible ? null : "Simulation evidence is awaiting the current RIP publication." });
    }).catch((error) => {
      if (activeIdentityRef.current !== identity) return;
      setSimulationState({ status: "error", setId, calculationRunId, payload: null, error: error?.message || "Simulation evidence is unavailable." });
    });
  }, [calculationRunId, setId]);

  const loadAdvanced = useCallback(({ force = false } = {}) => {
    if (!setId || !calculationRunId) return;
    const identity = `${setId}|${calculationRunId}`;
    setAdvancedState((current) => current.status === "loading" && !force ? current : { status: "loading", setId, calculationRunId, payload: null, error: null });
    getPokemonSetRipAdvanced(setId, calculationRunId, { force }).then((payload) => {
      if (activeIdentityRef.current !== identity) return;
      const compatible = selectSameRunRipAdvanced(payload, { setId, calculationRunId, bootstrapCanonical: canonicalSource });
      setAdvancedState({ status: compatible ? "success" : "stale", setId, calculationRunId, payload: compatible, error: compatible ? null : "Advanced evidence is awaiting the current RIP publication." });
    }).catch((error) => {
      if (activeIdentityRef.current !== identity) return;
      setAdvancedState({ status: "error", setId, calculationRunId, payload: null, error: error?.message || "Advanced evidence is unavailable." });
    });
  }, [calculationRunId, canonicalSource, setId]);

  useEffect(() => {
    if (rankContextEnabled) loadRankContext();
  }, [loadRankContext, rankContextEnabled]);

  const rankContext = rankContextState.setId === setId && rankContextState.expectedCalculationRunId === calculationRunId ? rankContextState.payload : null;
  const simulation = simulationState.setId === setId && simulationState.calculationRunId === calculationRunId ? simulationState.payload : null;
  const advanced = advancedState.setId === setId && advancedState.calculationRunId === calculationRunId ? advancedState.payload : null;
  return { rankContextState, simulationState, advancedState, rankContext, simulation, advanced, loadRankContext, loadSimulation, loadAdvanced };
}
