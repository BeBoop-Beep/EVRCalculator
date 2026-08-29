# Rankings publication lifecycle

The public `/Rankings` route serves the persisted Explore Rankings publication. It does not
recompute rankings from live simulation views. Freshness therefore means that the persisted
publication agrees with promoted-date authority, not merely that simulations have recently run.

## Coordinated lifecycle

1. Resolve the promoted market date and require an open publication gate.
2. Verify every supported set has a complete simulation for that exact date.
3. Finalize sealed-product Collector Appeal and Overall RIP for those exact calculation runs.
4. Build product-family rankings from the same run map and form the complete Set RIP cohort.
5. Evaluate `evaluate_rankings_publication_readiness` before invoking the canonical RPC.
6. Persist an attempt in `pokemon_rankings_publication_attempts`.
7. Publish atomically through `publish_pokemon_public_rip_leaderboard`.
8. Re-read latest and historical artifacts and assert market date, source-run map, cohort,
   completion state, and canonical scoring versions.

The publisher's existing payload validation remains the final defensive boundary. Readiness is
an orchestration and operations contract; it does not replace or loosen publisher validation.

## Failure behavior

An incomplete promoted-date simulation cohort explicitly defers only Rankings. Independent
market snapshot families may continue under their own contracts. Sealed-product finalization is
never claimed for a partial cohort, and the last complete Rankings snapshot remains active.

If finalization, product-family construction, Set RIP, the publication RPC, or post-publication
parity fails, the attempt row records a machine-readable reason and bounded diagnostics. A daily
coordinated run cannot report fully current success in those states.

## August 2026 incident

August 28 was a correct fail-closed deferral: one supported set retained its August 27 canonical
run, so the August 28 promoted-date cohort was incomplete and Rankings could not safely advance.

August 27 was a distinct V10 wiring defect. The snapshot builder conditionally constructed Set
RIP only when an `overallRipV9` rank existed, while publication had already moved to V10 and
required a complete `setRipV1` contract. A complete V10 cohort could consequently reach final
validation without Set RIP and fail publication. The condition now follows the canonical
`overallRipV10` ranked cohort.

No RIP formula, weight, simulation mathematics, product-family ordering, Set RIP methodology,
or public entitlement behavior is changed by this repair.
