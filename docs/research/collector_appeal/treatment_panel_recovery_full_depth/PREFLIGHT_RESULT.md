# Full-Depth Treatment Panel — Preflight

Status: `PREFLIGHT_COMPLETE_COLLECTION_NOT_AUTHORIZED_TODAY`

Workflow run: `36931570047`

## Frozen universe

- 114 matched identity-group entries
- 7 Sets
- 4 treatment families
- 241 frozen canonical cards
- 240 cards currently resolve to the frozen/current variant authority
- 1 frozen card has a documented stale lineage problem
- 34 cached PkmnPrices identities
- 206 additional provider identities would require bounded exact resolution
- maximum 180-day history-row exposure for resolvable targets: 43,200
- hard research credit cap: 50,000
- active B5 runs at preflight: none
- provider calls in preflight: 0
- database writes: 0

Manifest fingerprint:
`f1d234bdd198a49e0f39f0d27fc9a60292bad2cf2cb55ac33d68abcd4af4dd90`

Sample fingerprint:
`d11d360e219621af241e6de635c816a19c71975afdd0d313f9f27b650852f6e9`

## One unresolved frozen card

Canonical card:
- Escavalier #60, Black Bolt
- canonical ID `60b65429-e628-4157-8b31-f70a68468004`

The frozen Round-23 ladder links its old uncommon variant IDs to a legacy card identity that now resolves as Antique Cover Fossil after the market-history identity stabilization. The current canonical Escavalier card itself is intact, but there is no safe surviving `card_variants` mapping for its canonical ID.

The current simulator still contains legacy Escavalier-named rows on those old variant IDs, which demonstrates the lineage defect rather than providing a safe repair.

Policy:
- do not substitute another card;
- do not infer a canonical variant from name alone;
- leave this frozen card unresolved;
- its matched ladder remains unavailable unless a separate authoritative identity repair is completed.

This does not change the frozen full-depth sample and no outcome-based selection occurs.

## Provider budget

The prior expanded recovery run ended when PkmnPrices returned account-level `429 credit_limit_exceeded`.

Therefore the full-depth run remains in `preflight` mode. No collection retry is authorized in the current exhausted provider-credit window.
