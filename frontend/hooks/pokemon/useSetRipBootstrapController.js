"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPokemonSetRipBootstrap, preloadPokemonSetRipBootstrap, seedPokemonSetRipBootstrap } from "@/lib/pokemon/pokemonSetRipBootstrapClient.mjs";

const setIdentity = (payload) => String(payload?.set?.id || payload?.set?.target_id || payload?.set?.targetId || "");

const hasReadyPillar = (pillar) => Boolean(pillar && typeof pillar === "object" && Object.keys(pillar).length > 0);
const isChaseReady = (payload) => payload?.canonical?.chaseAccessibility?.status === "ready";

// A seed is "core-ready-but-chase-missing" when the SSR/initial payload has fully
// populated Overall/Financial/Collector pillars but the Chase Accessibility pillar
// is empty/not-ready. Per Task 6's diagnosis (STALE_INITIAL_BOOTSTRAP_CACHE), this
// specific shape is the signature of a stale Next.js Data Cache entry served on a
// cold SSR hit, not a genuine backend gap.
const needsChaseReconciliation = (payload) => {
  const canonical = payload?.canonical || {};
  return (
    hasReadyPillar(canonical.overall) &&
    hasReadyPillar(canonical.financial) &&
    hasReadyPillar(canonical.collector) &&
    !isChaseReady(payload)
  );
};

export default function useSetRipBootstrapController({ setId, initialPayload, enabled }) {
  const validSeed = initialPayload?.available && setIdentity(initialPayload) === String(setId || "") ? initialPayload : null;
  const [state, setState] = useState(() => ({ status: validSeed ? "success" : "idle", setId: validSeed ? setId : null, payload: validSeed, error: null }));
  const activeSetIdRef = useRef(String(setId || ""));
  activeSetIdRef.current = String(setId || "");
  // Tracks whether the one-shot Chase reconciliation fetch has already been
  // attempted for the current setId, so it can never run more than once per
  // set view (no retry loop, no polling).
  const chaseReconciliationAttemptedRef = useRef(null);

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

  // ONE no-store client reconciliation: if the accepted seed for this set has
  // ready Overall/Financial/Collector but Chase Accessibility is missing,
  // fetch once (bypassing the client cache) to check whether fresher backend
  // data has Chase. This intentionally calls getPokemonSetRipBootstrap
  // directly instead of `load()`: `load()` drives the controller's general
  // loading/error state machine, and the pre-existing "enabled" effect above
  // re-invokes `load()` whenever status isn't "success" — routing the
  // reconciliation through that path would risk an unbounded retry loop if
  // the reconciliation fetch itself fails. Calling the bootstrap client
  // directly keeps this a true one-shot: on success with Chase ready, the
  // seed is replaced; on success without Chase, or on any failure, the
  // existing accepted seed (and its truthful Chase "Unavailable") is left
  // exactly as-is and the gap is reported as a publication-data blocker.
  //
  // NOT gated on entitlement: RipDecisionPage renders
  // <ChaseAccessibilitySnapshotCard> inside the public data-three-pillar-summary
  // row, outside any canViewProductRipIntelligence gate — Chase Accessibility
  // is actually a public pillar on this page, visible to anonymous/non-entitled
  // viewers too. Gating this one-shot repair fetch on entitlement (as an
  // earlier fix round mistakenly did, based on a literal reading of "entitled
  // user" in the plan text rather than the page's actual rendering) would
  // leave the exact viewers who can see the card stuck on a stale "Unavailable"
  // indefinitely. The fetch is still one-shot and bounded by the other 3
  // conditions below (valid seed, Overall/Financial/Collector ready, Chase
  // missing), so this does not reintroduce a retry loop or broad backend load.
  useEffect(() => {
    if (!enabled || !validSeed) return;
    if (state.setId !== setId || state.status !== "success") return;
    if (state.payload !== validSeed) return;
    if (!needsChaseReconciliation(validSeed)) return;
    if (chaseReconciliationAttemptedRef.current === setId) return;
    chaseReconciliationAttemptedRef.current = setId;
    const requestedSetId = String(setId);
    getPokemonSetRipBootstrap(setId, { force: true })
      .then((fresh) => {
        if (activeSetIdRef.current !== requestedSetId) return;
        if (isChaseReady(fresh)) {
          setState({ status: "success", setId, payload: fresh, error: null });
          return;
        }
        // eslint-disable-next-line no-console
        console.warn(
          "[pokemon-set-rip] Chase Accessibility publication-data blocker: fresh no-store reconciliation still reports Chase Accessibility as unavailable for set",
          setId,
        );
      })
      .catch((error) => {
        // eslint-disable-next-line no-console
        console.warn(
          "[pokemon-set-rip] Chase Accessibility reconciliation fetch failed; preserving the already-accepted seed for set",
          setId,
          error?.message || error,
        );
      });
  }, [enabled, validSeed, setId, state.setId, state.status, state.payload]);

  const payload = state.setId === setId ? state.payload : null;
  return { state, payload, load, preload: () => load({ speculative: true }), retry: () => load({ force: true }) };
}
