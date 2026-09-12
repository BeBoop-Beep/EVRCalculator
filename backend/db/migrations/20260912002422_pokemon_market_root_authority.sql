-- Freeze the Sep 10, 2026 public Market root membership as a durable,
-- temporal identity table, independent of certification state.
--
-- Context (see project notes for full history): membership for the public
-- Market page was being re-derived every day from
-- pokemon_market_set_value_publication_cohort_v1, a view whose row set is
-- sensitive to certification flags (set_value_certified, top10_certified,
-- market_scope_certified, market_publication_ready) and to a rollout-override
-- CTE that force-sets market_publication_ready=true for certain sets. A
-- product decision (FINAL) fixed Sep 10+ public Market root membership at a
-- specific, human-approved set of 106 root sets. Membership must never again
-- be recomputed daily from certification -- certification is annotation only.
--
-- Honesty note: no pre-existing stable "authority" table was found anywhere
-- in the codebase for this decision. The 106 UUIDs below are a RECONSTRUCTED
-- SNAPSHOT, captured 2026-09-11 by a one-time read-only query against the
-- live production database:
--
--   SELECT set_id
--   FROM pokemon_market_set_value_publication_cohort_v1
--   WHERE market_scope = 'standard'
--   ORDER BY set_id;
--
-- (project zwxzxuuawalvwioadhmf; returned exactly 106 rows). This is NOT a
-- rediscovered authoritative record -- it is the best available
-- reconstruction of "what the human-approved Sep 10 root set was", frozen now
-- so it can never again drift with certification. If a more authoritative
-- source for the original approval later surfaces, reconcile against it.
--
-- Superseding a prior, flawed attempt: an earlier LOCAL, uncommitted pass (in
-- a different worktree, never committed) created
-- 20260911000000_add_pokemon_market_root_authority.sql, which seeded this
-- table via a LIVE `INSERT ... SELECT FROM
-- pokemon_market_set_value_publication_cohort_v1` executed at migration-apply
-- time. That is non-deterministic (the view's row set changes as
-- certification changes) and defeats the entire purpose of a frozen
-- authority. This migration replaces that approach with literal, frozen
-- UUID values captured once, in this file, at authoring time.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE IF NOT EXISTS public.pokemon_market_root_authority (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    set_id                 uuid NOT NULL,
    activated_market_date  date NOT NULL,
    deactivated_market_date date NULL,
    enabled                boolean NOT NULL DEFAULT true,
    source                 text NOT NULL,
    notes                  text NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_market_root_authority_range_chk
        CHECK (deactivated_market_date IS NULL OR deactivated_market_date > activated_market_date)
);

COMMENT ON TABLE public.pokemon_market_root_authority IS
    'Frozen, temporal public Market root membership authority. Membership is '
    'a reviewed human decision, never a live re-derivation from certification '
    'state. See migration header for the reconstruction provenance of the '
    'initial 2026-09-10 snapshot.';

-- No two active (enabled, undeactivated-at-a-given-date) rows may overlap for
-- the same set_id. Modeled with a partial unique index keyed on the
-- activation date for the common non-overlapping-insert case; a stronger
-- exclusion constraint (daterange && operator) is deferred -- see notes below
-- -- because it requires the btree_gist extension, which is out of scope for
-- this pass to enable blindly against production. This unique index is
-- sufficient to prevent the one failure mode this migration actually
-- produces (duplicate seed rows for the same set_id/activation date) while
-- leaving room for a future, more complete overlap-exclusion constraint.
CREATE UNIQUE INDEX IF NOT EXISTS pokemon_market_root_authority_set_activation_uq
    ON public.pokemon_market_root_authority (set_id, activated_market_date);

-- Point-in-time membership lookup: "who is active on market date D".
CREATE INDEX IF NOT EXISTS pokemon_market_root_authority_lookup_idx
    ON public.pokemon_market_root_authority (set_id, activated_market_date, deactivated_market_date)
    WHERE enabled;

CREATE INDEX IF NOT EXISTS pokemon_market_root_authority_enabled_activated_idx
    ON public.pokemon_market_root_authority (activated_market_date)
    WHERE enabled;

CREATE OR REPLACE FUNCTION public.set_pokemon_market_root_authority_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS pokemon_market_root_authority_touch_updated_at
    ON public.pokemon_market_root_authority;
CREATE TRIGGER pokemon_market_root_authority_touch_updated_at
    BEFORE UPDATE ON public.pokemon_market_root_authority
    FOR EACH ROW
    EXECUTE FUNCTION public.set_pokemon_market_root_authority_updated_at();

-- Seed the frozen 2026-09-10 snapshot. Idempotent on re-run via the unique
-- index above (ON CONFLICT DO NOTHING) so this migration is safe to re-apply.
INSERT INTO public.pokemon_market_root_authority
    (set_id, activated_market_date, enabled, source, notes)
SELECT v.set_id, v.activated_market_date, true,
       'reconstructed_snapshot_pokemon_market_set_value_publication_cohort_v1_2026-09-11',
       'Reconstructed 2026-09-10 public Market root snapshot; frozen from a '
       'one-time read-only production query on 2026-09-11 because no prior '
       'durable authority table existed. Not a rediscovered original record.'
FROM (VALUES
    ('03764ded-825a-45c0-8b15-ce100cff9552'::uuid, DATE '2026-09-10'),
    ('03bfd551-26be-423f-a4f2-9c4e936f3de3'::uuid, DATE '2026-09-10'),
    ('069f83b6-3028-4a00-ae8e-96ef2083a11d'::uuid, DATE '2026-09-10'),
    ('076aa350-5b36-4ff4-9095-fe4e95c01b79'::uuid, DATE '2026-09-10'),
    ('0cb8a5a6-5b5a-4288-aded-8b03f0fd9ded'::uuid, DATE '2026-09-10'),
    ('0d90b4ed-16a1-456c-81c6-83d2869d3846'::uuid, DATE '2026-09-10'),
    ('0f7e51e2-5a78-4500-9c9c-f690e934a069'::uuid, DATE '2026-09-10'),
    ('15fd93a2-82e3-4a5f-9f11-112cee192c95'::uuid, DATE '2026-09-10'),
    ('1c48d45b-199b-4925-bbfe-168c59faf66a'::uuid, DATE '2026-09-10'),
    ('1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890'::uuid, DATE '2026-09-10'),
    ('1e5eb27b-53bb-490b-9edb-1ce98b3a4341'::uuid, DATE '2026-09-10'),
    ('202518a0-5e86-4949-b1cd-c1c8ad95b616'::uuid, DATE '2026-09-10'),
    ('212383a2-ed84-4a5e-af37-50814247a437'::uuid, DATE '2026-09-10'),
    ('250f0404-e380-42e7-9aec-385ca8290ad4'::uuid, DATE '2026-09-10'),
    ('262dcb31-b7af-423e-8b11-2b7ba469ff72'::uuid, DATE '2026-09-10'),
    ('26db83e5-986f-4b91-82f4-c993ad1a0aaf'::uuid, DATE '2026-09-10'),
    ('26fedb88-87d7-487a-9f01-528d603c682e'::uuid, DATE '2026-09-10'),
    ('27077ea7-cd5d-4ba7-ae66-e905e780f0fd'::uuid, DATE '2026-09-10'),
    ('279f849e-9de7-4ca3-a922-a4f92ba9d89b'::uuid, DATE '2026-09-10'),
    ('27f3eb48-9964-4a3f-9861-a434ae244697'::uuid, DATE '2026-09-10'),
    ('29901e65-a5d2-4e12-8e26-62216ed947ab'::uuid, DATE '2026-09-10'),
    ('29d1d610-11c5-479c-a9ff-dace7bb96f92'::uuid, DATE '2026-09-10'),
    ('2d477c9a-bb2c-42aa-ae25-7cd4ca0f2a4a'::uuid, DATE '2026-09-10'),
    ('2d6ec108-70b2-4698-a21a-1af39828004f'::uuid, DATE '2026-09-10'),
    ('2fed4a27-a176-4d60-a92a-3c8b15f81dfb'::uuid, DATE '2026-09-10'),
    ('332b2885-9354-4a29-ba52-03fca35594d1'::uuid, DATE '2026-09-10'),
    ('34a48f79-1bd3-4f1d-9e3c-758955be70ee'::uuid, DATE '2026-09-10'),
    ('3836457c-77dc-44b0-a72f-779b6dd78884'::uuid, DATE '2026-09-10'),
    ('3b753fb6-a465-4e68-8ad9-4e34e114d4b7'::uuid, DATE '2026-09-10'),
    ('3f3c7677-b876-4353-821e-6bdd610fd683'::uuid, DATE '2026-09-10'),
    ('46ab39a7-dd96-4a2d-af0f-44b868918114'::uuid, DATE '2026-09-10'),
    ('472f851c-2e41-4c80-b6fc-8478d1d92730'::uuid, DATE '2026-09-10'),
    ('476a8f1c-bd50-4ba7-a217-562015fee3d6'::uuid, DATE '2026-09-10'),
    ('488bda22-33b7-40d7-9fe1-b3f87c2d2204'::uuid, DATE '2026-09-10'),
    ('4b15f040-4351-41ea-90e1-c07eb1b2f4d6'::uuid, DATE '2026-09-10'),
    ('4b792f11-635a-4e2f-9f60-09aafe387a4a'::uuid, DATE '2026-09-10'),
    ('4c0902e8-fc57-4e07-82e1-e4bdb9fe9990'::uuid, DATE '2026-09-10'),
    ('4de777b3-396e-4f19-9d78-c054b296bedb'::uuid, DATE '2026-09-10'),
    ('5109f22e-0799-46b5-a4ad-8861d1cfefee'::uuid, DATE '2026-09-10'),
    ('5361a918-eb23-447e-a00e-e21493bc4320'::uuid, DATE '2026-09-10'),
    ('549f2297-a03b-4276-ad96-ad41a8bcef8f'::uuid, DATE '2026-09-10'),
    ('591a2b3e-2dc8-4e80-b42d-aec4f4b786e4'::uuid, DATE '2026-09-10'),
    ('5bb951fd-bb74-40d7-b496-cca5bf959515'::uuid, DATE '2026-09-10'),
    ('5d3d5c23-7098-4393-ad63-6ad9372aee30'::uuid, DATE '2026-09-10'),
    ('5e160c6d-8f0e-4694-bf72-1fc3b7f01e45'::uuid, DATE '2026-09-10'),
    ('5e99f658-39f0-4845-9228-db8db3965f32'::uuid, DATE '2026-09-10'),
    ('5ee1fc9a-a49e-4323-8aa7-43df6d3c8124'::uuid, DATE '2026-09-10'),
    ('65ee8536-af5a-4242-8a1f-9928c81f501b'::uuid, DATE '2026-09-10'),
    ('69d6d1be-f610-421b-b29c-c3348fe19518'::uuid, DATE '2026-09-10'),
    ('6b5aa766-ca92-4ca2-a750-6323bbd97d13'::uuid, DATE '2026-09-10'),
    ('6c5be923-95d0-46ee-86a4-61148fb5152a'::uuid, DATE '2026-09-10'),
    ('6c82fb37-b9b9-4961-a528-12556bd15417'::uuid, DATE '2026-09-10'),
    ('6d813ed0-f263-4294-a099-18f1d5c7bd81'::uuid, DATE '2026-09-10'),
    ('6e18dc34-5d2f-47b2-8595-e350ebd4a630'::uuid, DATE '2026-09-10'),
    ('70a8d8f3-9aee-4ac8-88e4-dfbca50652f4'::uuid, DATE '2026-09-10'),
    ('74043b01-c2d0-49ad-a86e-404b7579aa83'::uuid, DATE '2026-09-10'),
    ('759c09f8-8a1b-4212-be89-66088afa6893'::uuid, DATE '2026-09-10'),
    ('75cc9ef9-1099-4e47-8d09-17f416606865'::uuid, DATE '2026-09-10'),
    ('75cd439d-aaa2-41cb-86f3-2fefa5b26e29'::uuid, DATE '2026-09-10'),
    ('7705c538-c6c1-4846-8efc-4bf4650f92e0'::uuid, DATE '2026-09-10'),
    ('7a1b8de0-331f-4635-8512-b737da431f7d'::uuid, DATE '2026-09-10'),
    ('7a3dd188-4375-41af-94de-c5247fe0b1a6'::uuid, DATE '2026-09-10'),
    ('7c998bc2-6073-4461-8873-64d1b3e78930'::uuid, DATE '2026-09-10'),
    ('7e99a62d-57ab-4ef4-8338-576524fb8d0d'::uuid, DATE '2026-09-10'),
    ('7fed6bc2-a67f-47e1-a453-d8c4ff986947'::uuid, DATE '2026-09-10'),
    ('806b7046-4fd5-4259-be17-54b28381f034'::uuid, DATE '2026-09-10'),
    ('8158d0ae-0255-48f0-b189-d134035b72b0'::uuid, DATE '2026-09-10'),
    ('8938c853-2282-46d8-ba44-87584fa2c168'::uuid, DATE '2026-09-10'),
    ('8a2c6f1f-dff9-45d7-9ae2-61ad05e4cee7'::uuid, DATE '2026-09-10'),
    ('8b5fb7da-391e-477d-b46c-f99ae584e7d3'::uuid, DATE '2026-09-10'),
    ('8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'::uuid, DATE '2026-09-10'),
    ('8f78267f-493b-4d60-a19e-587ae1f60f69'::uuid, DATE '2026-09-10'),
    ('8fe71704-0369-427a-ad32-4d173b43b1e1'::uuid, DATE '2026-09-10'),
    ('91442900-3949-4ba4-8398-9e3dc2db1fa6'::uuid, DATE '2026-09-10'),
    ('93212749-ce0e-498e-975e-7d947a3448ce'::uuid, DATE '2026-09-10'),
    ('950b9e19-eb8d-41bd-995f-01bdf98103b3'::uuid, DATE '2026-09-10'),
    ('965b3000-c483-4110-bb21-ff5ffe120564'::uuid, DATE '2026-09-10'),
    ('98301e8a-8aa3-43d8-a85b-908883264721'::uuid, DATE '2026-09-10'),
    ('9a59b345-59b0-4fc1-a4a3-5f79cb6f2310'::uuid, DATE '2026-09-10'),
    ('9d282514-6b63-48cd-bc25-9ce330632cd3'::uuid, DATE '2026-09-10'),
    ('9e777620-7479-41c4-84fb-17d2aea123bb'::uuid, DATE '2026-09-10'),
    ('a72c75bd-0d61-4643-b603-fef78425dcfa'::uuid, DATE '2026-09-10'),
    ('a8064dc8-57b9-4e6b-87fd-c0aa077fea7a'::uuid, DATE '2026-09-10'),
    ('a91d2dfa-fd33-44ff-ac12-f221b833a2e2'::uuid, DATE '2026-09-10'),
    ('b0d7bd6a-4e57-4495-b975-e132417cc071'::uuid, DATE '2026-09-10'),
    ('b3c96740-a4a9-4c3d-a8f6-81ed4584549d'::uuid, DATE '2026-09-10'),
    ('b4b34b61-ce48-4fc4-bd91-201a350b2600'::uuid, DATE '2026-09-10'),
    ('ba05227c-b7eb-4428-9e8e-ae70b52fe89f'::uuid, DATE '2026-09-10'),
    ('bd6207d5-eeb5-4e67-aceb-29cf9c2bd9b6'::uuid, DATE '2026-09-10'),
    ('be72ec5d-de1a-41db-81e0-89c310ed75ae'::uuid, DATE '2026-09-10'),
    ('be7c981b-c55e-4f60-a1b8-be922531452d'::uuid, DATE '2026-09-10'),
    ('c38df164-ea0d-4e9e-bae6-4c3a517beb8f'::uuid, DATE '2026-09-10'),
    ('c79eb59b-03a4-41c9-891b-de78a8f50d5e'::uuid, DATE '2026-09-10'),
    ('c825e588-8070-4dc7-b2b4-bedaf811ffed'::uuid, DATE '2026-09-10'),
    ('ca43d96a-ad90-4717-a4f6-253fb26a6d53'::uuid, DATE '2026-09-10'),
    ('cb68bfe9-53a6-4345-b0e3-f6cd6c33383b'::uuid, DATE '2026-09-10'),
    ('cbc11b3c-0244-4fca-880f-68ebdd599894'::uuid, DATE '2026-09-10'),
    ('d001d563-988b-4f8e-904f-acb926748e22'::uuid, DATE '2026-09-10'),
    ('d38ee646-382d-45c0-9463-e9302aa2471a'::uuid, DATE '2026-09-10'),
    ('db98ee23-c79a-4bfb-8a50-a5ba8a69120d'::uuid, DATE '2026-09-10'),
    ('de291399-ead5-41dc-bc12-e7c587684f85'::uuid, DATE '2026-09-10'),
    ('dfcf6c98-1bf3-43a8-83a2-7e56b3c65d03'::uuid, DATE '2026-09-10'),
    ('ed036406-26a7-4c68-92d5-dcd04f62556d'::uuid, DATE '2026-09-10'),
    ('f133524e-50e2-4238-91db-393770680c9b'::uuid, DATE '2026-09-10'),
    ('f59f25a2-d3da-4100-a918-901271a99925'::uuid, DATE '2026-09-10'),
    ('fdbc28d8-0b83-455c-b25c-13d2a222365a'::uuid, DATE '2026-09-10');
) AS v(set_id, activated_market_date)
ON CONFLICT (set_id, activated_market_date) DO NOTHING;

DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT count(*) INTO v_count
    FROM public.pokemon_market_root_authority
    WHERE activated_market_date = DATE '2026-09-10' AND enabled;

    IF v_count <> 106 THEN
        RAISE EXCEPTION
            'pokemon_market_root_authority seed count mismatch: expected 106, got %', v_count;
    END IF;
END
$$;

ALTER TABLE public.pokemon_market_root_authority
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.pokemon_market_root_authority FROM PUBLIC;
REVOKE ALL ON TABLE public.pokemon_market_root_authority FROM anon;
REVOKE ALL ON TABLE public.pokemon_market_root_authority FROM authenticated;
REVOKE ALL ON TABLE public.pokemon_market_root_authority FROM service_role;

GRANT SELECT ON TABLE public.pokemon_market_root_authority TO service_role;

REVOKE ALL ON SEQUENCE public.pokemon_market_root_authority_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.pokemon_market_root_authority_id_seq FROM anon;
REVOKE ALL ON SEQUENCE public.pokemon_market_root_authority_id_seq FROM authenticated;
REVOKE ALL ON SEQUENCE public.pokemon_market_root_authority_id_seq FROM service_role;

REVOKE ALL ON FUNCTION public.set_pokemon_market_root_authority_updated_at() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.set_pokemon_market_root_authority_updated_at() FROM anon;
REVOKE ALL ON FUNCTION public.set_pokemon_market_root_authority_updated_at() FROM authenticated;
REVOKE ALL ON FUNCTION public.set_pokemon_market_root_authority_updated_at() FROM service_role;

COMMIT;
