BEGIN;

-- Explicit, stable Market membership authority — Sep 10/11 2026 106-root recovery.
--
-- EVIDENCE TRAIL (read-only, live prod queries against zwxzxuuawalvwioadhmf):
--   * No pre-existing stable table/view holds the approved root set independent
--     of certification. Every candidate ("pokemon_market_rollout_root_sets_v1",
--     "pokemon_market_public_rollout_root_sets_v1",
--     "pokemon_market_root_set_market_ready_v1", the
--     "..._publication_cohort_v1"/"..._current_certification_v1" views) is a VIEW
--     computed from live certification/freshness state, not a fixed table.
--   * `pokemon_market_set_value_publication_cohort_v1` currently returns exactly
--     106 rows. Per repo memory (project_top_chase_stale_window_row /
--     project_sept8_rankings_zero_attempt_bug lineage) and the Sep-10
--     investigation, this 106 is the business-approved count, but the view
--     derives it by filtering out 5 structurally-certified roots that are
--     merely PRICE_FRESHNESS_STALE today (Black Bolt, Chaos Rising, Journey
--     Together, Paldean Fates, Scarlet and Violet Base Set). That filtering
--     mechanism is certification-sensitive and violates the documented
--     membership-vs-certification invariant in
--     backend/db/services/pokemon_market_rollout_cohort.py.
--   * No migration, table, or code comment enumerates a pre-existing explicit
--     106-id list independent of that filtering. There is therefore no
--     rediscovered pre-existing authority to reuse.
--
-- DECISION (forward-only, NOT a rediscovered list): this migration snapshots
-- the CURRENT 106 root set_ids returned by
-- pokemon_market_set_value_publication_cohort_v1 at authoring time
-- (2026-09-11) into an explicit, certification-independent table. This
-- matches the approved 106 count exactly. The 5 currently-stale-but-
-- structurally-certified roots are deliberately NOT unioned in, because doing
-- so would yield 111 and contradict the final "exactly 106" business
-- decision stated for this task; no evidence was found that those 5 were
-- ever intended as members of the approved 106. If that evidence later
-- surfaces, add them via a new forward-only migration/INSERT — never by
-- editing this snapshot in place.
--
-- From this point forward, membership is READ from this table only.
-- Certification/freshness must annotate members, never gate membership.

CREATE TABLE IF NOT EXISTS public.pokemon_market_root_authority (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id),
    added_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL DEFAULT 'reconstructed_snapshot_2026_09_11',
    notes text
);

COMMENT ON TABLE public.pokemon_market_root_authority IS
'Explicit, stable Market root-set membership authority (approved 106-root cohort). Independent of certification/price-freshness state. Certification/coverage/freshness must be joined as annotation only and must never add or drop rows here. Any future membership change must be a new forward-only migration, never an UPDATE of the snapshot semantics of existing rows.';

INSERT INTO public.pokemon_market_root_authority (set_id, source, notes)
SELECT v.set_id,
       'reconstructed_snapshot_2026_09_11',
       'Seeded from pokemon_market_set_value_publication_cohort_v1 (106 rows) at migration authoring time. See migration header for full evidence trail.'
FROM public.pokemon_market_set_value_publication_cohort_v1 v
ON CONFLICT (set_id) DO NOTHING;

REVOKE ALL ON public.pokemon_market_root_authority FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_authority TO service_role;

COMMIT;
