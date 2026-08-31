"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPokemonSetRipBootstrap, preloadPokemonSetRipBootstrap, seedPokemonSetRipBootstrap } from "@/lib/pokemon/pokemonSetRipBootstrapClient.mjs";

const setIdentity = (payload) => String(payload?.set?.id || payload?.set?.target_id || payload?.set?.targetId || "");

export default function useSetRipBootstrapController({ setId, initialPayload, enabled }) {
  const validSeed = initialPayload?.available && setIdentity(initialPayload) === String(setId || "") ? initialPayload : null;
  const [state, setState] = useState(() => ({ status: validSeed ? "success" : "idle", setId: validSeed ? setId : null, payload: validSeed, error: null }));
  const activeSetIdRef = useRef(String(setId || ""));
  activeSetIdRef.current = String(setId || "");

  useEffect(() => {
    if (!validSeed) return;
    seedPokemonSetRipBootstrap(setId, validSeed);
    setState({ status: "success", setId, payload: validSeed, error: null });
  }, [setId, validSeed]);

  const load = useCallback(({ force = false, speculative = false } = {}) => {
    if (!setId) return Promise.resolve(null);
    const requestedSetId = String(setId);
    if (!speculative) setState((current) => current.setId === setId && current.status === "success" && !force ? current : { status: "loading", setId, payload: null, error: null });
    const request = speculative ? preloadPokemonSetRipBootstrap(setId, { force }) : getPokemonSetRipBootstrap(setId, { force });
    return request.then((payload) => {
      if (activeSetIdRef.current !== requestedSetId) return null;
      setState({ status: "success", setId, payload, error: null });
      return payload;
    }).catch((error) => {
      if (activeSetIdRef.current !== requestedSetId) return null;
      if (!speculative) setState({ status: "error", setId, payload: null, error: error?.message || "RIP bootstrap unavailable." });
      return null;
    });
  }, [setId]);

  useEffect(() => { if (enabled && !(state.setId === setId && state.status === "success")) load(); }, [enabled, load, setId, state.setId, state.status]);
  const payload = state.setId === setId ? state.payload : null;
  return { state, payload, load, preload: () => load({ speculative: true }), retry: () => load({ force: true }) };
}
