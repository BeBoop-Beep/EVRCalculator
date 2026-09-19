begin;

-- P5A_ZERO_DIFF_START
CREATE TEMP TABLE p5a_canonical_before ON COMMIT DROP AS
WITH targets(canonical_card_id,set_id) AS (VALUES
  ('00afbaf5-46cc-4b2d-b1ee-c9839b7d6d8f'::uuid,'4099fc11-a3f6-4034-8208-fbf82bd89de5'::uuid),
  ('02768af4-334c-4eb8-a6f3-71b84e54f9f5'::uuid,'1b3250bb-f123-47d8-b090-499e5879eda7'::uuid),
  ('037e131a-63bb-41b1-9a46-d215487eb412'::uuid,'3c459327-59d0-41d5-b21e-aae36361cc77'::uuid),
  ('038cd0c3-e33f-4a96-9999-81608939b119'::uuid,'a69e4091-5b33-499d-85a5-a8f0b7ecaddc'::uuid),
  ('0ac8d1e3-dc0a-4cca-9df8-04291875dffe'::uuid,'1c6a8735-af2a-475b-b230-5bd18f827b06'::uuid),
  ('145c3df2-bafd-4fe8-820e-2226b51454d2'::uuid,'30396643-190c-416d-92a4-e8414c8b4980'::uuid),
  ('214a20d8-6ae0-46de-9047-082b506c4b1e'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('310cafff-701e-4213-a59b-938d2f5f794e'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('3695a310-0980-4cba-b790-ab7d827b3b44'::uuid,'5bdbfae1-3f2e-44e7-b8c9-1035ad45b896'::uuid),
  ('3ef680dc-9c3a-4d0f-af5d-f7b8b3c35695'::uuid,'b5172ada-e0d5-4c3f-a4c7-06b4ac3391de'::uuid),
  ('4540ac5a-4e22-40d0-a0f1-2dbb14c99243'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('4f7b4614-fcf3-4f15-b596-dd4be57849d1'::uuid,'cb1dc8ed-925b-443d-ba23-d6ffa8f7084c'::uuid),
  ('57f1882b-11e5-4fa6-98a8-b4e323392911'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('621b038b-e832-47a2-8bdd-1160945d6d44'::uuid,'89e710d1-c378-4b4e-aaea-5994d8441f45'::uuid),
  ('7781f22e-0d90-4a51-87d8-d56fcbc34dd7'::uuid,'70a8d8f3-9aee-4ac8-88e4-dfbca50652f4'::uuid),
  ('8de57c6e-93ca-4f8e-a9b8-98ee422d4761'::uuid,'77bde285-03f8-4a48-b6a5-2f548225c3eb'::uuid),
  ('a6a3e0ec-9e63-4ee3-9cb8-c3981a495e5d'::uuid,'77bde285-03f8-4a48-b6a5-2f548225c3eb'::uuid),
  ('ab8f7a71-f1e8-41e8-89cb-b01bea223bf2'::uuid,'ca0ad9de-678b-4734-9e91-93a1d7201e51'::uuid),
  ('b38102f7-42b0-49bc-a2b1-a16bda58a581'::uuid,'4f84d317-e15d-4598-bc8d-52baa04b3485'::uuid),
  ('b815a131-d4f1-43da-b8b2-fb521ffbab10'::uuid,'aac3de95-9f92-44af-966d-70b1d201c01e'::uuid),
  ('c10d44b1-f2c9-4110-9753-61c23275b218'::uuid,'1b3250bb-f123-47d8-b090-499e5879eda7'::uuid),
  ('c3040b5f-0d8e-4f11-b426-a96624ca7d5e'::uuid,'126093d8-50e7-4a7c-891d-8cffd5733eeb'::uuid),
  ('cae71539-cdde-41e1-aa61-cf1f67f43d69'::uuid,'aac3de95-9f92-44af-966d-70b1d201c01e'::uuid),
  ('dd970fea-4ec2-4870-b258-141c9a5563b2'::uuid,'92575c0d-fac2-42ff-86f3-fb81f7452188'::uuid),
  ('e0e90f28-075e-4eda-a5c0-a017adf2760c'::uuid,'a69e4091-5b33-499d-85a5-a8f0b7ecaddc'::uuid),
  ('e4b73b72-2882-436f-9d27-90b229185520'::uuid,'4de777b3-396e-4f19-9d78-c054b296bedb'::uuid),
  ('e4ca99f2-796b-447a-af18-224eb290297b'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('ec21dd75-f0d8-4cd7-ad31-50bec1a687b3'::uuid,'ffc6b635-fe16-4416-b4fc-0f727e4c81d4'::uuid),
  ('f13e4255-67dd-48ce-af76-69abda61c8d9'::uuid,'8938c853-2282-46d8-ba44-87584fa2c168'::uuid),
  ('f940db65-6995-4dbf-bd92-817aececb2ec'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('58a01e34-87f7-4693-a763-c40f8c8cabc1'::uuid,'0b8ebcec-2b4e-4a77-9923-ffc4be6514c5'::uuid),
  ('8b48e631-400b-42d7-86f4-b7000b139ad4'::uuid,'bbea2ee9-6be2-44bd-b14e-b4a8b9c858de'::uuid),
  ('bd0fc6f2-31de-4ca3-9459-0b4753baa2b7'::uuid,'78c7f000-9a9e-45ca-8233-8f36030f6019'::uuid)
)
SELECT t.canonical_card_id,t.set_id,r.card_variant_id,r.condition_id,r.market_price,r.source,r.captured_at,r.price_selection_reason
FROM targets t LEFT JOIN LATERAL (
  SELECT * FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(t.set_id) x
  WHERE x.canonical_card_id=t.canonical_card_id
) r ON true;

CREATE TEMP TABLE p5a_latest_before ON COMMIT DROP AS
WITH targets(variant_id) AS (VALUES
  ('09c602d4-6c85-4f6d-b1b3-a12e5155f5de'::uuid),
  ('2e825dec-1a8a-46dd-9e47-4cb7d55ee42a'::uuid),
  ('33aae8ca-8e63-406e-a672-c067a8dd27ca'::uuid),
  ('3dd0f4fa-16ac-4263-b9bc-817b48a3074c'::uuid),
  ('5a9d23cc-e13a-4c29-a761-d602f87ca950'::uuid),
  ('5c4c7dc2-9636-4544-8f24-b20c5df54127'::uuid),
  ('5ed848c2-fc64-4528-aff0-279b89c46b8c'::uuid),
  ('63191dd8-35a2-411d-89c9-af8e1de3e181'::uuid),
  ('7b646415-6c67-4910-8ae4-18a65c88f514'::uuid),
  ('8a4b2acc-eee4-45bb-96b2-1130d9c3ad8b'::uuid),
  ('9543c2f9-1ffe-4d2f-b1c5-beed15f1ed15'::uuid),
  ('96a68097-9308-481e-b57d-acd23f5c6bef'::uuid),
  ('b432b3a4-19b0-4598-94c8-9bc2f206ee82'::uuid),
  ('b46702d4-a9db-44fa-8bfc-1c46839581f3'::uuid),
  ('b6e430da-2e44-40e3-9263-d3a9a037d0c3'::uuid),
  ('f68cb094-0a0d-423f-8a76-b013ac5b86a6'::uuid)
)
SELECT t.variant_id,v.condition_id,v.market_price,v.source,v.captured_at,v.created_at
FROM targets t LEFT JOIN public.card_market_usd_latest_by_condition v ON v.variant_id=t.variant_id;
-- P5A_ZERO_DIFF_END


CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shad(target_set_id uuid)
RETURNS TABLE(canonical_card_id uuid, set_id uuid, pokemon_tcg_api_card_id text, legacy_card_id uuid, card_variant_id uuid, condition_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
WITH near_mint_condition AS (
    SELECT id
    FROM public.conditions
    WHERE name = 'Near Mint'
      AND abbreviation = 'NM'
    ORDER BY id
    LIMIT 1
), manual_identity AS (
    SELECT pcc.*, link.legacy_card_id, -1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = pcc.id
    WHERE pcc.set_id = target_set_id
), parent_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 0 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    WHERE pcc.set_id = target_set_id
), variant_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.card_variants matched_variant
      ON matched_variant.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    JOIN public.cards c
      ON c.id = matched_variant.card_id
     AND c.set_id = pcc.set_id
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
), name_number_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 2 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND lower(regexp_replace(trim(c.name), '\\s+', ' ', 'g')) = lower(regexp_replace(trim(pcc.name), '\\s+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', '')
     )
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
      AND NOT EXISTS (SELECT 1 FROM variant_api_identity variant_match WHERE variant_match.id = pcc.id)
), resolved_cards AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), identity_candidates AS (
    SELECT resolved.id AS canonical_card_id, resolved.set_id, resolved.pokemon_tcg_api_card_id,
           resolved.rarity, resolved.legacy_card_id, cv.id AS card_variant_id,
           cv.printing_type, cv.special_type, resolved.identity_rank
    FROM resolved_cards resolved
    JOIN public.card_variants cv ON cv.card_id = resolved.legacy_card_id
), candidates AS (
    SELECT ic.canonical_card_id, ic.set_id, ic.pokemon_tcg_api_card_id, ic.legacy_card_id,
           ic.card_variant_id, latest.condition_id, ic.printing_type, latest.market_price,
           latest.captured_at, latest.source,
           CASE
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_non_holo_base_print'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_holo_fallback'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
             WHEN ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_holo_base_print'
             WHEN ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_non_holo_fallback'
             WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
             ELSE 'latest_nm_special_or_other_fallback'
           END AS price_selection_reason,
           row_number() OVER (
             PARTITION BY ic.canonical_card_id
             ORDER BY ic.identity_rank,
                      latest.captured_at DESC NULLS LAST,
                      CASE WHEN ic.special_type IS NULL THEN 0 ELSE 1 END,
                      CASE
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' THEN 0
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' THEN 1
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        WHEN ic.printing_type='holo' THEN 0
                        WHEN ic.printing_type='non-holo' THEN 1
                        WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        ELSE 9
                      END,
                      CASE WHEN pref.preferred_card_variant_id = ic.card_variant_id THEN 0 ELSE 1 END,
                      latest.created_at DESC NULLS LAST,
                      ic.card_variant_id
           ) AS selection_rank
    FROM identity_candidates ic
    LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
      ON pref.canonical_card_id = ic.canonical_card_id
    CROSS JOIN near_mint_condition nmc
    JOIN LATERAL (
      SELECT current_row.condition_id,
             current_row.market_price,
             current_row.last_observed_date AS captured_at,
             current_row.source,
             current_row.last_observation_created_at AS created_at,
             current_row.last_observation_id AS id
      FROM public.card_variant_price_current_v2 current_row
      WHERE current_row.card_variant_id = ic.card_variant_id
        AND current_row.condition_id = nmc.id
        AND current_row.market_price > 0
        AND current_row.currency = 'USD'
        AND current_row.source = 'TCGPlayer'
      ORDER BY current_row.last_observed_date DESC NULLS LAST,
               current_row.last_observation_created_at DESC NULLS LAST,
               current_row.last_observation_id DESC NULLS LAST
      LIMIT 1
    ) latest ON true
)
SELECT candidates.canonical_card_id, candidates.set_id, candidates.pokemon_tcg_api_card_id,
       candidates.legacy_card_id, candidates.card_variant_id, candidates.condition_id,
       candidates.printing_type, candidates.market_price, candidates.captured_at,
       candidates.source, candidates.price_selection_reason
FROM candidates
WHERE candidates.selection_rank = 1;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid) TO service_role;

CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition
WITH (security_invoker=true) AS
SELECT
    c.id AS card_id,
    c.set_id,
    s.name AS set_name,
    c.name AS card_name,
    c.card_number,
    c.rarity,
    cv.id AS variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.condition_id,
    cond.name AS condition,
    latest.market_price,
    latest.high_price,
    latest.low_price,
    latest.currency,
    latest.source,
    latest.last_observed_date AS captured_at,
    latest.last_observation_created_at AS created_at
FROM public.card_variants cv
JOIN public.cards c ON c.id = cv.card_id
LEFT JOIN public.sets s ON s.id = c.set_id
CROSS JOIN LATERAL (
    SELECT DISTINCT ON (current_row.condition_id)
        current_row.condition_id,
        current_row.market_price,
        current_row.high_price,
        current_row.low_price,
        current_row.currency,
        current_row.source,
        current_row.last_observed_date,
        current_row.last_observation_created_at,
        current_row.last_observation_id
    FROM public.card_variant_price_current_v2 current_row
    WHERE current_row.card_variant_id = cv.id
      AND current_row.currency = 'USD'
      AND current_row.source = 'TCGPlayer'
    ORDER BY current_row.condition_id,
             current_row.last_observed_date DESC NULLS LAST,
             current_row.last_observation_created_at DESC NULLS LAST,
             current_row.last_observation_id DESC NULLS LAST
) latest
LEFT JOIN public.conditions cond ON cond.id = latest.condition_id;

COMMENT ON VIEW public.card_market_usd_latest_by_condition IS 'Latest TCGPlayer USD Price Storage V2 current row per variant and condition. LATERAL selection preserves variant filter pushdown.';
-- CREATE OR REPLACE VIEW preserves the existing view ACL. Do not change API grants here.

-- Preserve existing function shape and selection rules; lock only the source.
CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(p_root_set_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(root_set_id uuid, root_set_name text, member_set_id uuid, member_set_name text, member_type text, market_scope text, canonical_card_id uuid, card_name text, card_number text, rarity text, canonical_review_status text, card_variant_id uuid, edition text, printing_type text, special_type text, identity_basis text, market_price numeric, captured_at date, source text, price_selection_reason text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH near_mint AS (
    SELECT c.id
    FROM public.conditions c
    WHERE lower(c.name) = 'near mint'
    ORDER BY c.id
    LIMIT 1
),
roots AS (
    SELECT s.id AS root_set_id,
           s.name AS root_set_name
    FROM public.sets s
    WHERE s.parent_opening_set_id IS NULL
      AND s.catalog_only = false
      AND (p_root_set_id IS NULL OR s.id = p_root_set_id)
),
members AS (
    SELECT r.root_set_id,
           r.root_set_name,
           r.root_set_id AS member_set_id,
           r.root_set_name AS member_set_name,
           'main'::text AS member_type
    FROM roots r
    UNION ALL
    SELECT r.root_set_id,
           r.root_set_name,
           child.id,
           child.name,
           coalesce(child.subset_type, 'subset')::text
    FROM roots r
    JOIN public.sets child
      ON child.parent_opening_set_id = r.root_set_id
     AND child.counts_toward_parent_set_value = true
),
eligible_cards AS (
    SELECT m.root_set_id,
           m.root_set_name,
           m.member_set_id,
           m.member_set_name,
           m.member_type,
           pcc.id AS canonical_card_id,
           pcc.name AS card_name,
           coalesce(pcc.number, pcc.printed_number) AS card_number,
           pcc.rarity,
           pcc.canonical_review_status
    FROM members m
    JOIN public.pokemon_canonical_cards pcc
      ON pcc.set_id = m.member_set_id
     AND pcc.set_value_eligible = true
),
edition_evidence AS (
    SELECT ec.root_set_id,
           count(DISTINCT ec.canonical_card_id)::integer AS eligible_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = '1st-edition')::integer AS first_edition_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = 'unlimited')::integer AS unlimited_card_count
    FROM eligible_cards ec
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
    GROUP BY ec.root_set_id
),
root_profiles AS (
    SELECT r.root_set_id,
           r.root_set_name,
           coalesce(ev.eligible_card_count, 0) AS eligible_card_count,
           coalesce(ev.first_edition_card_count, 0) AS first_edition_card_count,
           coalesce(ev.unlimited_card_count, 0) AS unlimited_card_count,
           CASE
             WHEN lower(r.root_set_name) = 'base' THEN 'base_three_printings'
             WHEN coalesce(ev.eligible_card_count, 0) > 0
              AND coalesce(ev.first_edition_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
              AND coalesce(ev.unlimited_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
               THEN 'edition_split'
             ELSE 'standard'
           END AS profile
    FROM roots r
    LEFT JOIN edition_evidence ev ON ev.root_set_id = r.root_set_id
),
root_scopes AS (
    SELECT rp.root_set_id, rp.root_set_name, 'standard'::text AS market_scope
    FROM root_profiles rp
    WHERE rp.profile = 'standard'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'edition_split'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('shadowless'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'base_three_printings'
),
standard_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           'standard'::text AS market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           price.card_variant_id,
           cv.edition,
           cv.printing_type,
           cv.special_type,
           meta.identity_basis,
           price.market_price,
           price.captured_at,
           price.source,
           price.price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope = 'standard'
    LEFT JOIN public.pokemon_canonical_card_market_prices_latest price
      ON price.canonical_card_id = ec.canonical_card_id
     AND price.set_id = ec.member_set_id
    LEFT JOIN public.card_variants cv ON cv.id = price.card_variant_id
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.card_variant_id = price.card_variant_id
     AND meta.canonical_card_id = ec.canonical_card_id
),
edition_variant_latest AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           meta.card_variant_id,
           meta.edition,
           meta.printing_type,
           meta.special_type,
           meta.identity_basis,
           latest.market_price,
           latest.captured_at,
           latest.source,
           row_number() OVER (
             PARTITION BY ec.root_set_id, rs.market_scope, ec.canonical_card_id
             ORDER BY
               CASE meta.identity_basis
                 WHEN 'explicit_legacy_identity_link' THEN 0
                 WHEN 'parent_pokemon_tcg_api_id' THEN 1
                 WHEN 'normalized_name_number_fallback' THEN 2
                 ELSE 9
               END,
               CASE WHEN meta.special_type IS NULL OR meta.special_type = '' THEN 0 ELSE 1 END,
               CASE
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'non-holo' THEN 0
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'holo' THEN 1
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'reverse-holo' THEN 2
                 WHEN meta.printing_type = 'holo' THEN 0
                 WHEN meta.printing_type = 'non-holo' THEN 1
                 WHEN meta.printing_type = 'reverse-holo' THEN 2
                 ELSE 9
               END,
               latest.captured_at DESC NULLS LAST,
               meta.card_variant_id
           ) AS selection_rank
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
     AND (
       (rs.market_scope = 'first_edition' AND meta.edition = '1st-edition')
       OR (rs.market_scope = 'unlimited' AND meta.edition = 'unlimited')
       OR (rs.market_scope = 'shadowless' AND meta.edition = 'shadowless')
     )
    CROSS JOIN near_mint nm
    LEFT JOIN LATERAL (
      SELECT o.market_price, o.last_observed_date AS captured_at, o.source
      FROM public.card_variant_price_current_v2 o
      WHERE o.card_variant_id = meta.card_variant_id
        AND o.condition_id = nm.id
        AND o.market_price IS NOT NULL
        AND o.market_price > 0
        AND trim(both '"' from upper(coalesce(o.currency,''))) = 'USD'
        AND o.source = 'TCGPlayer'
      ORDER BY o.last_observed_date DESC NULLS LAST, o.last_observation_created_at DESC NULLS LAST, o.last_observation_id DESC
      LIMIT 1
    ) latest ON true
),
edition_selected AS (
    SELECT *
    FROM edition_variant_latest
    WHERE selection_rank = 1
),
edition_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           sel.card_variant_id,
           sel.edition,
           sel.printing_type,
           sel.special_type,
           sel.identity_basis,
           sel.market_price,
           sel.captured_at,
           sel.source,
           CASE
             WHEN sel.card_variant_id IS NULL THEN 'missing_required_edition_variant'
             WHEN sel.market_price IS NULL THEN 'required_edition_variant_missing_nm_price'
             ELSE 'edition_exact_latest_nm_preferred_printing'
           END AS price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    LEFT JOIN edition_selected sel
      ON sel.root_set_id = ec.root_set_id
     AND sel.market_scope = rs.market_scope
     AND sel.canonical_card_id = ec.canonical_card_id
)
SELECT * FROM standard_rows
UNION ALL
SELECT root_set_id, root_set_name, member_set_id, member_set_name, member_type,
       market_scope, canonical_card_id, card_name, card_number, rarity,
       canonical_review_status, card_variant_id, edition, printing_type,
       special_type, identity_basis, market_price, captured_at, source,
       price_selection_reason
FROM edition_rows;
$function$;


-- Preserve existing function shape and selection rules; lock only the source.
CREATE OR REPLACE FUNCTION public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(target_set_id uuid, target_date date)
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, card_variant_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
with near_mint_condition as (
    select id
    from public.conditions
    where name='Near Mint' and abbreviation='NM'
    order by id
    limit 1
), base_cards as (
    select pcc.*
    from public.pokemon_canonical_cards pcc
    where pcc.set_id=target_set_id
      and pcc.set_value_eligible=true
), manual_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 as identity_rank
    from base_cards pcc
    join public.pokemon_canonical_card_legacy_identity_links link on link.canonical_card_id=pcc.id
), parent_api_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,0 as identity_rank
    from base_cards pcc
    join public.cards c on c.set_id=pcc.set_id and c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,1 as identity_rank
    from base_cards pcc
    join public.card_variants matched_variant on matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    join public.cards c on c.id=matched_variant.card_id and c.set_id=pcc.set_id
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
), name_number_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,2 as identity_rank
    from base_cards pcc
    join public.cards c
      on c.set_id=pcc.set_id
     and lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
     and regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') in (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
     )
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
      and not exists(select 1 from variant_api_identity v where v.canonical_card_id=pcc.id)
), resolved_cards as (
    select * from manual_identity
    union all select * from parent_api_identity
    union all select * from variant_api_identity
    union all select * from name_number_identity
), identity_candidates as (
    select resolved.canonical_card_id,resolved.set_id,resolved.rarity,resolved.identity_rank,
           cv.id as card_variant_id,cv.printing_type,cv.special_type
    from resolved_cards resolved
    join public.card_variants cv on cv.card_id=resolved.legacy_card_id
), candidates as (
    select ic.canonical_card_id,ic.set_id,ic.card_variant_id,ic.printing_type,
           state.market_price,state.latest_observed_date as captured_at,state.source,
           case
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_common_uncommon_non_holo_base_print'
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' and ic.special_type is null then 'latest_nm_common_uncommon_holo_fallback'
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_common_uncommon_regular_reverse_fallback'
             when ic.printing_type='holo' and ic.special_type is null then 'latest_nm_rare_or_hit_holo_base_print'
             when ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_non_holo_fallback'
             when ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_regular_reverse_fallback'
             else 'latest_nm_special_or_other_fallback'
           end as price_selection_reason,
           row_number() over(
             partition by ic.canonical_card_id
             order by ic.identity_rank,
                      state.latest_observed_date desc nulls last,
                      case when ic.special_type is null then 0 else 1 end,
                      case
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' then 0
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' then 1
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 2
                        when ic.printing_type='holo' then 0
                        when ic.printing_type='non-holo' then 1
                        when ic.printing_type='reverse-holo' and ic.special_type is null then 2
                        else 9
                      end,
                      case when pref.preferred_card_variant_id=ic.card_variant_id then 0 else 1 end,
                      ic.card_variant_id
           ) as selection_rank
    from identity_candidates ic
    left join public.pokemon_canonical_card_variant_preferences_v2 pref
      on pref.canonical_card_id=ic.canonical_card_id
    cross join near_mint_condition nmc
    join lateral (
      select priced_source.market_price,priced_source.latest_observed_date,priced_source.source
      from (
        select rr.source,rr.latest_observed_date,ev.market_price
        from (
          select r.source,max(least(r.observed_through,target_date)) as latest_observed_date
          from public.card_variant_price_observation_ranges_v2 r
          where r.card_variant_id=ic.card_variant_id
            and r.condition_id=nmc.id
            and r.currency='USD'
            and r.source='TCGPlayer'
            and r.observed_from<=target_date
          group by r.source
        ) rr
        join lateral (
          select e.market_price
          from public.card_variant_price_events_v2 e
          where e.card_variant_id=ic.card_variant_id
            and e.condition_id=nmc.id
            and e.currency='USD'
            and e.source=rr.source
            and e.effective_date<=target_date
            and e.market_price>0
          order by e.effective_date desc,e.id desc
          limit 1
        ) ev on true
      ) priced_source
      order by priced_source.latest_observed_date desc,priced_source.source desc
      limit 1
    ) state on true
)
select canonical_card_id,set_id,card_variant_id,printing_type,market_price,captured_at,source,price_selection_reason
from candidates
where selection_rank=1;
$function$;


-- Preserve existing function shape and selection rules; lock only the source.
CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v4_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
 SET work_mem TO '64MB'
AS $function$
with requested_roots as materialized (
  select distinct x.set_id
  from unnest(coalesce(p_set_ids,array[]::uuid[])) as x(set_id)
  where x.set_id is not null
), dates as materialized (
  select gs::date as market_date
  from generate_series(p_start_date,p_end_date,interval '1 day') gs
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
), member_map as materialized (
  select r.set_id as root_set_id,r.set_id as member_set_id
  from requested_roots r
  union
  select r.set_id,child.id
  from requested_roots r
  join public.sets child
    on child.parent_opening_set_id=r.set_id
   and child.counts_toward_parent_set_value=true
), expanded_set_ids as materialized (
  select coalesce(array_agg(distinct m.member_set_id order by m.member_set_id),array[]::uuid[]) as ids
  from member_map m
), canonical_root_days as materialized (
  select r.set_id as root_set_id,d.market_date
  from requested_roots r
  cross join dates d
  join public.pokemon_set_value_daily_history h
    on h.set_id=r.set_id
   and h.snapshot_date=d.market_date
   and h.value_scope='standard'
  where h.source in (
    'canonical_root_set_public_rollout_v1',
    'canonical_root_set_public_rollout_candidate_v1',
    'canonical_root_standard_backfill_v1',
    'canonical_root_set_rollout_v1',
    'price_storage_v2_transition_anchor_v1',
    'price_storage_v2_serving_compatibility_v1'
  )
), canonical_member_days as materialized (
  select c.root_set_id,m.member_set_id,c.market_date
  from canonical_root_days c
  join member_map m on m.root_set_id=c.root_set_id
), legacy_chunks as materialized (
  select r.set_id as root_set_id,
         (p_start_date + (g.n*3))::date as from_date,
         least(p_end_date,(p_start_date + (g.n*3) + 2))::date as through_date
  from requested_roots r
  cross join lateral generate_series(
    0,
    greatest(0,((p_end_date-p_start_date)/3))
  ) as g(n)
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
    and exists (
      select 1
      from dates d
      where d.market_date between (p_start_date + (g.n*3))::date
                              and least(p_end_date,(p_start_date + (g.n*3) + 2))::date
        and not exists (
          select 1
          from canonical_root_days c
          where c.root_set_id=r.set_id
            and c.market_date=d.market_date
        )
    )
), legacy_member_chunks as materialized (
  select lc.root_set_id,lc.from_date,lc.through_date,
         array_agg(m.member_set_id order by m.member_set_id) as member_ids
  from legacy_chunks lc
  join member_map m on m.root_set_id=lc.root_set_id
  group by lc.root_set_id,lc.from_date,lc.through_date
), legacy_base as materialized (
  select b.*
  from legacy_member_chunks lc
  cross join lateral public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    lc.member_ids,lc.from_date,lc.through_date,p_card_ids
  ) b
), near_mint as materialized (
  select c.id
  from public.conditions c
  where c.name='Near Mint'
  order by c.id
  limit 1
), exception_variants as materialized (
  select e.canonical_card_id,e.set_id,e.card_variant_id
  from public.pokemon_cards_daily_constituent_variant_exceptions_v1 e
  cross join expanded_set_ids a
  where e.enabled
    and e.set_id=any(a.ids)
    and (p_card_ids is null or e.canonical_card_id=any(p_card_ids))
), exception_intervals as materialized (
  select ev.canonical_card_id,ev.set_id,price.card_variant_id,
         price.condition_id,price.source,price.currency,price.market_price,
         price.effective_date as valid_from,
         lead(price.effective_date) over(
           partition by price.card_variant_id,price.condition_id,price.source,price.currency
           order by price.effective_date,price.id
         ) as valid_to
  from exception_variants ev
  join public.card_variant_price_events_v2 price
    on price.card_variant_id=ev.card_variant_id
  cross join near_mint nm
  where price.condition_id=nm.id
    and price.currency='USD'
     and price.source='TCGPlayer'
), exception_source_daily as materialized (
  select d.market_date,ei.canonical_card_id,ei.set_id,ei.card_variant_id,
         ei.source,ei.market_price,observed.latest_observed_date,
         row_number() over(
           partition by d.market_date,ei.canonical_card_id
           order by observed.latest_observed_date desc nulls last,
                    ei.source desc,ei.card_variant_id
         ) as source_rank
  from dates d
  join exception_intervals ei
    on ei.valid_from<=d.market_date
   and (ei.valid_to is null or d.market_date<ei.valid_to)
   and ei.market_price>0
  cross join near_mint nm
  join lateral (
    select max(least(r.observed_through,d.market_date)) as latest_observed_date
    from public.card_variant_price_observation_ranges_v2 r
    where r.card_variant_id=ei.card_variant_id
      and r.condition_id=nm.id
      and r.source=ei.source
      and r.currency='USD'
      and r.observed_from<=d.market_date
  ) observed on observed.latest_observed_date is not null
), exception_overlay as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.latest_observed_date as captured_at
  from exception_source_daily x
  where x.source_rank=1
), legacy_compatible as materialized (
  select b.canonical_card_id,b.set_id,b.market_date,b.market_price,
         b.card_variant_id,b.source,b.captured_at
  from legacy_base b
  union all
  select o.canonical_card_id,o.set_id,o.market_date,o.market_price,
         o.card_variant_id,o.source,o.captured_at
  from exception_overlay o
  where not exists (
    select 1
    from legacy_base b
    where b.canonical_card_id=o.canonical_card_id
      and b.market_date=o.market_date
  )
), canonical_raw as materialized (
  select cmd.root_set_id,
         p.canonical_card_id,p.set_id,cmd.market_date,
         p.market_price,p.card_variant_id,p.source,p.captured_at
  from canonical_member_days cmd
  cross join lateral public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(
    cmd.member_set_id,cmd.market_date
  ) p
  where p_card_ids is null or p.canonical_card_id=any(p_card_ids)
), canonical_rows as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.captured_at
  from (
    select c.*,
           row_number() over(
             partition by c.canonical_card_id,c.market_date
             order by c.root_set_id,c.set_id,c.card_variant_id
           ) as rn
    from canonical_raw c
  ) x
  where x.rn=1
)
select l.canonical_card_id,l.set_id,l.market_date,l.market_price,
       l.card_variant_id,l.source,l.captured_at
from legacy_compatible l
where not exists (
  select 1
  from canonical_member_days c
  where c.member_set_id=l.set_id
    and c.market_date=l.market_date
)
union all
select c.canonical_card_id,c.set_id,c.market_date,c.market_price,
       c.card_variant_id,c.source,c.captured_at
from canonical_rows c
order by market_date,canonical_card_id,set_id;
$function$;


-- Preserve existing function shape and selection rules; lock only the source.
CREATE OR REPLACE FUNCTION public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(p_set_id uuid, p_start_date date DEFAULT NULL::date, p_end_date date DEFAULT NULL::date)
 RETURNS TABLE(set_id uuid, snapshot_date date, value_scope text, set_value numeric, priced_card_count integer, total_card_count integer, canonical_card_count integer, linked_card_count integer, included_card_count integer, coverage_pct numeric, source text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH near_mint AS MATERIALIZED (
    SELECT id
    FROM public.conditions
    WHERE lower(name)='near mint'
    ORDER BY id
    LIMIT 1
), canonical_checklist AS MATERIALIZED (
    SELECT pcc.set_id,
           pcc.id AS canonical_card_id,
           pcc.pokemon_tcg_api_card_id,
           pcc.name,
           pcc.number,
           pcc.printed_number
    FROM public.pokemon_canonical_cards pcc
    WHERE pcc.set_id=p_set_id
      AND pcc.set_value_eligible=true
), canonical_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS canonical_card_count
    FROM canonical_checklist
    GROUP BY set_id
), canonical_card_links AS MATERIALIZED (
    SELECT DISTINCT cc.set_id,cc.canonical_card_id,c.id AS card_id
    FROM canonical_checklist cc
    JOIN public.cards c
      ON c.set_id=cc.set_id
     AND (
       c.pokemon_tcg_api_id=cc.pokemon_tcg_api_card_id
       OR (
         lower(regexp_replace(coalesce(cc.name,''),'[[:space:]]+',' ','g'))=
           lower(regexp_replace(coalesce(c.name,''),'[[:space:]]+',' ','g'))
         AND (
           coalesce(cc.number,'')=coalesce(c.card_number,'')
           OR coalesce(cc.printed_number,'')=coalesce(c.card_number,'')
           OR ltrim(split_part(coalesce(cc.number,''),'/',1),'0')=ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
           OR ltrim(split_part(coalesce(cc.printed_number,''),'/',1),'0')=ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
         )
       )
     )
    UNION
    SELECT DISTINCT cc.set_id,cc.canonical_card_id,link.legacy_card_id
    FROM canonical_checklist cc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id=cc.canonical_card_id
), canonical_variant_links AS MATERIALIZED (
    SELECT DISTINCT ccl.set_id,ccl.canonical_card_id,ccl.card_id,cv.id AS card_variant_id
    FROM canonical_card_links ccl
    JOIN public.card_variants cv ON cv.card_id=ccl.card_id
    WHERE (
      cv.special_type IS NULL OR cv.special_type=''
      OR EXISTS (
        SELECT 1 FROM public.cards c_name
        WHERE c_name.id=ccl.card_id
          AND lower(regexp_replace(coalesce(c_name.name,''),'[^a-zA-Z0-9]+','','g'))='pokeball'
      )
    )
      AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo','non-holo'))
), linked_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS linked_card_count
    FROM canonical_variant_links
    GROUP BY set_id
), scope_flags AS MATERIALIZED (
    SELECT cc.set_id,cc.canonical_card_id,
           EXISTS (
             SELECT 1
             FROM public.pokemon_card_desirability_links l
             WHERE l.pokemon_canonical_card_id=cc.canonical_card_id
               AND l.is_hit_eligible=true
           ) AS is_hit_eligible
    FROM canonical_checklist cc
), hit_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS hit_card_count
    FROM scope_flags
    WHERE is_hit_eligible=true
    GROUP BY set_id
), observed_bounds AS (
    SELECT cvl.set_id,
           min(r.observed_from) AS first_observation_date,
           max(r.observed_through) AS latest_observation_date
    FROM canonical_variant_links cvl
    JOIN near_mint nm ON true
    JOIN public.card_variant_price_observation_ranges_v2 r
      ON r.card_variant_id=cvl.card_variant_id
     AND r.condition_id=nm.id
     AND r.currency='USD'
     AND r.source='TCGPlayer'
    WHERE EXISTS (
      SELECT 1
      FROM public.card_variant_price_events_v2 e
      WHERE e.card_variant_id=r.card_variant_id
        AND e.condition_id=r.condition_id
        AND e.source=r.source
        AND e.currency=r.currency
        AND e.market_price>0
    )
    GROUP BY cvl.set_id
), requested_bounds AS (
    SELECT b.set_id,
           greatest(b.first_observation_date,coalesce(p_start_date,b.first_observation_date)) AS start_date,
           least(
             CASE WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                  THEN p_end_date ELSE b.latest_observation_date END,
             timezone('America/Phoenix',now())::date
           ) AS end_date
    FROM observed_bounds b
), constituents AS MATERIALIZED (
    SELECT c.canonical_card_id,c.set_id,c.market_date,c.market_price,c.card_variant_id,c.source,c.captured_at,
           sf.is_hit_eligible
    FROM requested_bounds b
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
      ARRAY[b.set_id],b.start_date,b.end_date,NULL::uuid[]
    ) c
    JOIN scope_flags sf
      ON sf.set_id=c.set_id
     AND sf.canonical_card_id=c.canonical_card_id
    WHERE b.start_date<=b.end_date
), standard_aggregated AS (
    SELECT c.set_id,c.market_date AS snapshot_date,'standard'::text AS value_scope,
           round(sum(c.market_price)::numeric,2) AS set_value,
           count(DISTINCT c.canonical_card_id)::integer AS priced_card_count,
           max(cc.canonical_card_count)::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT c.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT c.canonical_card_id)::numeric/nullif(max(cc.canonical_card_count),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:standard:canonical_checklist'::text AS source
    FROM constituents c
    JOIN canonical_counts cc ON cc.set_id=c.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=c.set_id
    GROUP BY c.set_id,c.market_date
), hits_aggregated AS (
    SELECT c.set_id,c.market_date AS snapshot_date,'hits'::text AS value_scope,
           round(sum(c.market_price)::numeric,2) AS set_value,
           count(DISTINCT c.canonical_card_id)::integer AS priced_card_count,
           max(hc.hit_card_count)::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT c.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT c.canonical_card_id)::numeric/nullif(max(hc.hit_card_count),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:hits:canonical_checklist'::text AS source
    FROM constituents c
    JOIN canonical_counts cc ON cc.set_id=c.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=c.set_id
    LEFT JOIN hit_counts hc ON hc.set_id=c.set_id
    WHERE c.is_hit_eligible=true
    GROUP BY c.set_id,c.market_date
), ranked AS MATERIALIZED (
    SELECT c.*,
           row_number() OVER (
             PARTITION BY c.set_id,c.market_date
             ORDER BY c.market_price DESC,c.canonical_card_id
           ) AS price_rank
    FROM constituents c
), top10_aggregated AS (
    SELECT r.set_id,r.market_date AS snapshot_date,'top10'::text AS value_scope,
           round(sum(r.market_price)::numeric,2) AS set_value,
           count(DISTINCT r.canonical_card_id)::integer AS priced_card_count,
           least(10,max(cc.canonical_card_count))::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT r.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT r.canonical_card_id)::numeric/nullif(least(10,max(cc.canonical_card_count)),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:top10:canonical_checklist'::text AS source
    FROM ranked r
    JOIN canonical_counts cc ON cc.set_id=r.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=r.set_id
    WHERE r.price_rank<=10
    GROUP BY r.set_id,r.market_date
)
SELECT * FROM standard_aggregated
UNION ALL SELECT * FROM hits_aggregated
UNION ALL SELECT * FROM top10_aggregated
ORDER BY snapshot_date,value_scope;
$function$;


CREATE OR REPLACE VIEW public.card_market_usd_latest WITH (security_invoker=true) AS
SELECT c.id AS card_id,
    c.name,
    c.set_id,
    c.rarity,
    cv.id AS variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.market_price,
    latest.currency,
    latest.source,
    latest.last_observed_date AS captured_at,
    latest.last_observation_created_at AS created_at
   FROM ((card_variants cv
     JOIN cards c ON ((c.id = cv.card_id)))
     CROSS JOIN LATERAL ( SELECT current_row.card_variant_id,
            current_row.condition_id,
            current_row.source,
            current_row.currency,
            current_row.event_id,
            current_row.effective_date,
            current_row.state,
            current_row.market_price,
            current_row.high_price,
            current_row.low_price,
            current_row.source_observation_id,
            current_row.updated_at,
            current_row.last_observed_date,
            current_row.last_observation_id,
            current_row.last_observation_created_at
           FROM card_variant_price_current_v2 current_row
          WHERE ((current_row.card_variant_id = cv.id) AND (current_row.currency = 'USD'::text AND current_row.source = 'TCGPlayer'::text))
          ORDER BY current_row.last_observed_date DESC NULLS LAST, current_row.last_observation_created_at DESC NULLS LAST, current_row.last_observation_id DESC NULLS LAST
         LIMIT 1) latest);

CREATE OR REPLACE VIEW public.simulation_input_cards_with_near_mint_price WITH (security_invoker=true) AS
SELECT sic.id,
    sic.calculation_run_id,
    sic.card_id,
    sic.card_variant_id,
    sic.condition_id,
    sic.card_name,
    sic.rarity_bucket,
    sic.price_source,
    sic.price_used,
    sic.captured_at,
    sic.effective_pull_rate,
    sic.ev_contribution,
    sic.created_at,
    current_nm.market_price AS current_near_mint_price,
    current_nm.last_observed_date AS current_near_mint_price_captured_at,
    current_nm.source AS current_near_mint_price_source
   FROM (simulation_input_cards sic
     LEFT JOIN LATERAL ( SELECT current_row.market_price,
            current_row.last_observed_date,
            current_row.source,
            current_row.last_observation_created_at,
            current_row.last_observation_id
           FROM card_variant_price_current_v2 current_row
          WHERE ((current_row.card_variant_id = sic.card_variant_id) AND (current_row.condition_id = sic.condition_id) AND (current_row.market_price > (0)::numeric) AND (current_row.currency = 'USD'::text AND current_row.source = 'TCGPlayer'::text))
          ORDER BY current_row.last_observed_date DESC NULLS LAST, current_row.last_observation_created_at DESC NULLS LAST, current_row.last_observation_id DESC NULLS LAST
         LIMIT 1) current_nm ON (true));

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
 SET work_mem TO '64MB'
AS $function$
WITH near_mint AS MATERIALIZED (
    SELECT id FROM public.conditions
    WHERE name='Near Mint' AND abbreviation='NM'
    ORDER BY id LIMIT 1
), base_cards AS MATERIALIZED (
    SELECT pcc.*
    FROM public.pokemon_canonical_cards pcc
    WHERE p_set_ids IS NOT NULL
      AND cardinality(p_set_ids)>0
      AND pcc.set_id=ANY(p_set_ids)
      AND pcc.set_value_eligible=true
      AND (p_card_ids IS NULL OR cardinality(p_card_ids)=0 OR pcc.id=ANY(p_card_ids))
), manual_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 identity_rank
    FROM base_cards pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link ON link.canonical_card_id=pcc.id
), parent_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
    FROM base_cards pcc
    JOIN public.cards c ON c.set_id=pcc.set_id AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
    FROM base_cards pcc
    JOIN public.card_variants matched_variant ON matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    JOIN public.cards c ON c.id=matched_variant.card_id AND c.set_id=pcc.set_id
    WHERE NOT EXISTS (SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id)
), name_number_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,2 identity_rank
    FROM base_cards pcc
    JOIN public.cards c
      ON c.set_id=pcc.set_id
     AND lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
     )
    WHERE NOT EXISTS (SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id)
      AND NOT EXISTS (SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.id)
), resolved AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), variants AS MATERIALIZED (
    SELECT DISTINCT r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,r.legacy_card_id,
           cv.id card_variant_id,cv.printing_type,cv.special_type
    FROM resolved r
    JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
    WHERE (cv.special_type IS NULL OR cv.special_type=''
           OR EXISTS (
               SELECT 1 FROM public.cards c_name
               WHERE c_name.id=r.legacy_card_id
                 AND lower(regexp_replace(coalesce(c_name.name,''),'[^a-zA-Z0-9]+','','g'))='pokeball'
           ))
      AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo','non-holo'))
), event_intervals AS MATERIALIZED (
    SELECT e.card_variant_id,e.condition_id,e.source,e.currency,e.market_price,
           e.effective_date valid_from,
           lead(e.effective_date) OVER (
             PARTITION BY e.card_variant_id,e.condition_id,e.source,e.currency
             ORDER BY e.effective_date,e.id
           ) valid_to
    FROM public.card_variant_price_events_v2 e
    JOIN variants v ON v.card_variant_id=e.card_variant_id
    CROSS JOIN near_mint nm
    WHERE e.condition_id=nm.id AND e.currency='USD' AND e.source='TCGPlayer'
), dates AS MATERIALIZED (
    SELECT gs::date market_date
    FROM generate_series(p_start_date,p_end_date,interval '1 day') gs
    WHERE p_start_date IS NOT NULL AND p_end_date IS NOT NULL AND p_end_date>=p_start_date
), source_daily AS MATERIALIZED (
    SELECT d.market_date,v.canonical_card_id,v.set_id,v.rarity,v.identity_rank,
           v.card_variant_id,v.printing_type,v.special_type,
           ei.source,ei.market_price,obs.latest_observed_date,
           row_number() OVER (
             PARTITION BY d.market_date,v.card_variant_id
             ORDER BY obs.latest_observed_date DESC NULLS LAST,ei.source DESC
           ) source_rank
    FROM dates d
    JOIN variants v ON true
    JOIN event_intervals ei
      ON ei.card_variant_id=v.card_variant_id
     AND ei.valid_from<=d.market_date
     AND (ei.valid_to IS NULL OR d.market_date<ei.valid_to)
     AND ei.market_price>0
    CROSS JOIN near_mint nm
    JOIN LATERAL (
      SELECT max(least(r.observed_through,d.market_date)) latest_observed_date
      FROM public.card_variant_price_observation_ranges_v2 r
      WHERE r.card_variant_id=v.card_variant_id
        AND r.condition_id=nm.id
        AND r.source=ei.source
        AND r.currency='USD'
        AND r.observed_from<=d.market_date
    ) obs ON obs.latest_observed_date IS NOT NULL
), candidate_daily AS MATERIALIZED (
    SELECT s.*,
           row_number() OVER (
             PARTITION BY s.market_date,s.canonical_card_id
             ORDER BY s.identity_rank,
                      s.latest_observed_date DESC NULLS LAST,
                      CASE WHEN s.special_type IS NULL OR s.special_type='' THEN 0 ELSE 1 END,
                      CASE
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='non-holo' THEN 0
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='holo' THEN 1
                        WHEN s.printing_type='holo' THEN 0
                        WHEN s.printing_type='non-holo' THEN 1
                        ELSE 9
                      END,
                      CASE WHEN pref.preferred_card_variant_id=s.card_variant_id THEN 0 ELSE 1 END,
                      s.card_variant_id
           ) selection_rank
    FROM source_daily s
    LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
      ON pref.canonical_card_id=s.canonical_card_id
    WHERE s.source_rank=1
)
SELECT c.canonical_card_id,c.set_id,c.market_date,c.market_price,
       c.card_variant_id,c.source,c.latest_observed_date AS captured_at
FROM candidate_daily c
WHERE c.selection_rank=1
ORDER BY c.market_date,c.canonical_card_id;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_resolved_universe(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE plpgsql
 STABLE
 SET "TimeZone" TO 'America/Phoenix'
 SET plan_cache_mode TO 'force_custom_plan'
 SET search_path TO ''
AS $function$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
BEGIN
    IF p_set_ids IS NULL OR array_length(p_set_ids, 1) IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a bounded p_start_date/p_end_date';
    END IF;
    IF p_start_date > p_end_date THEN
        RAISE EXCEPTION 'p_start_date (%) must not be after p_end_date (%)', p_start_date, p_end_date;
    END IF;

    SELECT id INTO v_near_mint_condition_id
    FROM public.conditions WHERE lower(name) = 'near mint' ORDER BY id LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH canonical_checklist AS (
        SELECT pcc.id AS pokemon_canonical_card_id, pcc.set_id AS pokemon_set_id,
               pcc.pokemon_tcg_api_card_id, pcc.name, pcc.number, pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = ANY(p_set_ids)
          AND (p_card_ids IS NULL OR pcc.id = ANY(p_card_ids))
    ),
    canonical_card_links AS (
        SELECT DISTINCT cc.pokemon_canonical_card_id, cc.pokemon_set_id, c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c ON c.set_id = cc.pokemon_set_id
         AND (c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
              OR (lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) =
                      lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                  AND (coalesce(cc.number, '') = coalesce(c.card_number, '')
                       OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                       OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                       OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0'))))
        UNION
        SELECT DISTINCT cc.pokemon_canonical_card_id, cc.pokemon_set_id, link.legacy_card_id AS card_id
        FROM canonical_checklist cc
        JOIN public.pokemon_canonical_card_legacy_identity_links link
          ON link.canonical_card_id = cc.pokemon_canonical_card_id
    ),
    canonical_variant_links AS (
        SELECT DISTINCT ccl.pokemon_canonical_card_id, ccl.pokemon_set_id, ccl.card_id, cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = ''
               OR EXISTS (
                   SELECT 1 FROM public.cards c_name
                   WHERE c_name.id = ccl.card_id
                     AND lower(regexp_replace(coalesce(c_name.name, ''), '[^a-zA-Z0-9]+', '', 'g')) = 'pokeball'
               ))
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id, pokemon_set_id FROM canonical_variant_links
    ),
    -- Observations that fall INSIDE the requested window.
    in_range AS (
        SELECT cvl.pokemon_canonical_card_id, cvl.pokemon_set_id, cvl.card_variant_id,
               o.id AS observation_id, o.market_price, o.source, o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
              AND o.source = 'TCGPlayer'
          AND o.market_price IS NOT NULL AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at >= p_start_date AND o.captured_at <= p_end_date
    ),
    -- The single observation still in force ON p_start_date. Exactly ONE
    -- lookup per card, where the old implementation did one per card per DAY.
    -- Without it a window opening mid-history would lose every card whose last
    -- price predates it.
    carry_in AS (
        SELECT lc.pokemon_canonical_card_id, lc.pokemon_set_id, prior.card_variant_id,
               prior.observation_id, prior.market_price, prior.source, prior.captured_at
        FROM linked_cards lc
        JOIN LATERAL (
            SELECT cvl.card_variant_id, o.id AS observation_id, o.market_price, o.source, o.captured_at
            FROM canonical_variant_links cvl
            JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
            WHERE cvl.pokemon_canonical_card_id = lc.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.source = 'TCGPlayer'
              AND o.market_price IS NOT NULL AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < p_start_date
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) prior ON true
    ),
    observations AS (
        SELECT * FROM in_range
        UNION ALL
        SELECT * FROM carry_in
    ),
    validity AS (
        SELECT ob.*,
               lead(ob.captured_at) OVER (
                   PARTITION BY ob.pokemon_canonical_card_id
                   ORDER BY ob.captured_at, ob.observation_id
               ) AS superseded_from
        FROM observations ob
    )
    SELECT v.pokemon_canonical_card_id AS canonical_card_id,
           v.pokemon_set_id AS set_id,
           d.market_date, v.market_price, v.card_variant_id, v.source, v.captured_at
    FROM validity v
    JOIN LATERAL (
        SELECT generate_series(
            greatest(v.captured_at, p_start_date),
            least(coalesce(v.superseded_from - 1, p_end_date), p_end_date),
            interval '1 day'
        )::date AS market_date
    ) d ON true
    WHERE coalesce(v.superseded_from - 1, p_end_date) >= p_start_date
    ORDER BY d.market_date, v.pokemon_canonical_card_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
AS $function$
DECLARE
  v_reader_verified boolean;
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
  END IF;
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;

  -- NULL means unrestricted. An explicitly empty filter means no cards,
  -- matching the original public constituent contract.
  IF p_card_ids IS NOT NULL AND cardinality(p_card_ids)=0 THEN
    RETURN;
  END IF;

  -- Acceptance is tied to the actual tested implementation, not its name.
  -- A subsequent reader change falls back to raw until independently accepted.
  v_reader_verified := md5(pg_get_functiondef(
    'public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure
  )) = '756f4d28ea3710f59bb23f254ecd3580';

  RETURN QUERY
  WITH requested AS MATERIALIZED (
    SELECT DISTINCT u.requested_set_id
    FROM unnest(p_set_ids) AS u(requested_set_id)
    WHERE u.requested_set_id IS NOT NULL
  ), approved AS MATERIALIZED (
    SELECT r.requested_set_id, a.start_date, a.end_date
    FROM requested r
    JOIN public.pokemon_set_market_constituent_v2_acceptance a
      ON a.set_id=r.requested_set_id
    WHERE v_reader_verified
      AND a.status='complete'
      AND a.missing_side=0
      AND a.mismatches=0
      AND a.old_rows=a.v2_rows
      AND a.start_date IS NOT NULL
      AND a.end_date IS NOT NULL
      AND a.start_date<=a.end_date
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_set_market_constituent_legacy_exceptions_v2 e
        WHERE e.set_id=r.requested_set_id
      )
  ), v2_segments AS MATERIALIZED (
    SELECT a.requested_set_id,
           greatest(p_start_date,a.start_date) AS from_date,
           least(p_end_date,a.end_date) AS through_date
    FROM approved a
    WHERE a.start_date<=p_end_date AND a.end_date>=p_start_date
  ), legacy_segments AS MATERIALIZED (
    -- Unaccepted sets retain their existing reader in full.
    SELECT r.requested_set_id, p_start_date AS from_date, p_end_date AS through_date
    FROM requested r
    WHERE NOT EXISTS(SELECT 1 FROM approved a WHERE a.requested_set_id=r.requested_set_id)
    UNION ALL
    -- Before and after the tested range, use legacy, with no overlap.
    SELECT a.requested_set_id,p_start_date,least(p_end_date,a.start_date-1)
    FROM approved a WHERE p_start_date<a.start_date
    UNION ALL
    SELECT a.requested_set_id,greatest(p_start_date,a.end_date+1),p_end_date
    FROM approved a WHERE p_end_date>a.end_date
  ), result_rows AS (
    -- Bounded per-set calls avoid the pathological all-set expansion observed
    -- when feeding the V2 SQL function a large multi-set array.
    SELECT v.*
    FROM v2_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) v
    UNION ALL
    SELECT l.*
    FROM legacy_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_legacy_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) l
  )
  SELECT r.canonical_card_id,r.set_id,r.market_date,r.market_price,
         r.card_variant_id,r.source,r.captured_at
  FROM result_rows r
  ORDER BY r.market_date,r.canonical_card_id,r.set_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_card_market_top_hits_latest()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
begin
  truncate table public.card_market_top_hits_latest;

  insert into public.card_market_top_hits_latest (
    set_id,
    card_id,
    card_variant_id,
    condition_id,
    rank,
    card_name,
    card_number,
    rarity,
    market_price,
    currency,
    source,
    captured_at
  )
  with near_mint_condition as (
    select id
    from public.conditions
    where lower(name) in ('near mint', 'nm')
    limit 1
  ),
  latest_observations as (
    select
      o.card_variant_id,
      o.condition_id,
      o.market_price,
      o.currency,
      o.source,
      o.captured_at,
      o.created_at,
      row_number() over (
        partition by o.card_variant_id, o.source
        order by o.captured_at desc nulls last, o.created_at desc
      ) as rn
    from public.card_variant_price_observations o
    join near_mint_condition nmc
      on nmc.id = o.condition_id
    where o.market_price is not null
      and o.currency = 'USD'
      and o.source = 'TCGPlayer'
  ),
  latest_nm_per_variant as (
    select
      lo.card_variant_id,
      lo.condition_id,
      lo.market_price,
      lo.currency,
      lo.source,
      lo.captured_at
    from latest_observations lo
    where lo.rn = 1
  ),
  best_nm_latest_per_card as (
    select
      c.set_id,
      c.id as card_id,
      cv.id as card_variant_id,
      lnv.condition_id,
      c.name as card_name,
      c.card_number,
      c.rarity,
      lnv.market_price,
      lnv.currency,
      lnv.source,
      lnv.captured_at,
      row_number() over (
        partition by c.id
        order by lnv.market_price desc nulls last,
                 lnv.captured_at desc nulls last,
                 cv.created_at desc,
                 cv.id
      ) as card_choice_rank
    from latest_nm_per_variant lnv
    join public.card_variants cv
      on cv.id = lnv.card_variant_id
    join public.cards c
      on c.id = cv.card_id
  ),
  ranked_set_hits as (
    select
      bnlpc.set_id,
      bnlpc.card_id,
      bnlpc.card_variant_id,
      bnlpc.condition_id,
      bnlpc.card_name,
      bnlpc.card_number,
      bnlpc.rarity,
      bnlpc.market_price,
      bnlpc.currency,
      bnlpc.source,
      bnlpc.captured_at,
      row_number() over (
        partition by bnlpc.set_id
        order by bnlpc.market_price desc nulls last,
                 bnlpc.card_name asc,
                 bnlpc.card_id
      ) as set_rank
    from best_nm_latest_per_card bnlpc
    where bnlpc.card_choice_rank = 1
  )
  select
    rsh.set_id,
    rsh.card_id,
    rsh.card_variant_id,
    rsh.condition_id,
    rsh.set_rank as rank,
    rsh.card_name,
    rsh.card_number,
    rsh.rarity,
    rsh.market_price,
    rsh.currency,
    rsh.source,
    rsh.captured_at
  from ranked_set_hits rsh
  where rsh.set_rank <= 10;
end;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_card_market_top_hits_by_edition_latest()
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
declare
  v_rows integer := 0;
begin
  truncate table public.card_market_top_hits_by_edition_latest;

  insert into public.card_market_top_hits_by_edition_latest (
    set_id,
    edition,
    card_id,
    card_variant_id,
    condition_id,
    rank,
    card_name,
    card_number,
    rarity,
    market_price,
    currency,
    source,
    captured_at
  )
  with latest_observations as (
    select
      o.card_variant_id,
      o.condition_id,
      o.market_price,
      o.currency,
      o.source,
      o.captured_at,
      o.created_at,
      row_number() over (
        partition by o.card_variant_id, o.condition_id
        order by o.captured_at desc nulls last, o.created_at desc
      ) as rn
    from public.card_variant_price_observations o
    where o.market_price is not null
      and o.currency = 'USD'
      and o.source = 'TCGPlayer'
  ),
  latest_per_variant_condition as (
    select
      lo.card_variant_id,
      lo.condition_id,
      lo.market_price,
      lo.currency,
      lo.source,
      lo.captured_at
    from latest_observations lo
    where lo.rn = 1
  ),
  joined as (
    select
      c.set_id,
      coalesce(cv.edition, '') as edition,
      c.id as card_id,
      cv.id as card_variant_id,
      lpvc.condition_id,
      c.name as card_name,
      c.card_number,
      c.rarity,
      lpvc.market_price,
      lpvc.currency,
      lpvc.source,
      lpvc.captured_at
    from latest_per_variant_condition lpvc
    join public.card_variants cv
      on cv.id = lpvc.card_variant_id
    join public.cards c
      on c.id = cv.card_id
  ),
  best_available_per_card_identity as (
    select
      j.*,
      row_number() over (
        partition by
          j.set_id,
          j.edition,
          j.card_name,
          j.card_number,
          j.rarity
        order by
          j.market_price desc nulls last,
          j.captured_at desc nulls last,
          j.card_variant_id
      ) as identity_rank
    from joined j
  ),
  ranked as (
    select
      b.set_id,
      b.edition,
      b.card_id,
      b.card_variant_id,
      b.condition_id,
      b.card_name,
      b.card_number,
      b.rarity,
      b.market_price,
      b.currency,
      b.source,
      b.captured_at,
      row_number() over (
        partition by b.set_id, b.edition
        order by
          b.market_price desc nulls last,
          b.card_name asc,
          b.card_number asc
      ) as set_edition_rank
    from best_available_per_card_identity b
    where b.identity_rank = 1
  )
  select
    r.set_id,
    r.edition,
    r.card_id,
    r.card_variant_id,
    r.condition_id,
    r.set_edition_rank as rank,
    r.card_name,
    r.card_number,
    r.rarity,
    r.market_price,
    r.currency,
    r.source,
    r.captured_at
  from ranked r
  where r.set_edition_rank <= 10;

  get diagnostics v_rows = row_count;

  return jsonb_build_object(
    'refreshed_rows', v_rows,
    'table_name', 'card_market_top_hits_by_edition_latest'
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_card_variant_market_metrics_latest()
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
declare
  v_rows integer := 0;
begin
  truncate table public.card_variant_market_metrics_latest;

  insert into public.card_variant_market_metrics_latest (
    card_variant_id,
    card_id,
    set_id,
    condition_id,
    current_market_price,
    current_captured_at,
    delta_1d,
    delta_7d,
    delta_30d,
    delta_3m,
    delta_6m,
    delta_1y,
    delta_lifetime,
    delta_pct_1d,
    delta_pct_7d,
    delta_pct_30d,
    delta_pct_3m,
    delta_pct_6m,
    delta_pct_1y,
    delta_pct_lifetime,
    base_price_1d,
    base_price_7d,
    base_price_30d,
    base_price_3m,
    base_price_6m,
    base_price_1y,
    base_price_lifetime,
    refreshed_at
  )
  with near_mint_condition as (
    select id
    from public.conditions
    where id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'
    limit 1
  ),
  current_rows as (
    select distinct on (h.card_variant_id, h.condition_id)
      h.card_variant_id,
      h.condition_id,
      h.market_price as current_market_price,
      h.captured_at as current_captured_at
    from public.card_variant_price_observations h
    join near_mint_condition nmc
      on nmc.id = h.condition_id
    where h.currency = 'USD'
      and h.source = 'TCGPlayer'
      and h.market_price is not null
    order by
      h.card_variant_id,
      h.condition_id,
      h.captured_at desc,
      h.created_at desc
  ),
  enriched as (
    select
      cr.card_variant_id,
      cv.card_id,
      c.set_id,
      cr.condition_id,
      cr.current_market_price,
      cr.current_captured_at,

      b1d.market_price as base_price_1d,
      b7d.market_price as base_price_7d,
      b30d.market_price as base_price_30d,
      b3m.market_price as base_price_3m,
      b6m.market_price as base_price_6m,
      b1y.market_price as base_price_1y,
      blife.market_price as base_price_lifetime

    from current_rows cr
    join public.card_variants cv
      on cv.id = cr.card_variant_id
    join public.cards c
      on c.id = cv.card_id

    -- 1D: latest price strictly before current observation date
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at < cr.current_captured_at
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b1d on true

    -- 7D: latest price at or before current observation date minus 7 days
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= (cr.current_captured_at - 7)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b7d on true

    -- 30D
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= (cr.current_captured_at - 30)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b30d on true

    -- 3M
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '3 months')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b3m on true

    -- 6M
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '6 months')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b6m on true

    -- 1Y
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '1 year')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b1y on true

    -- lifetime earliest known price
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
      order by h.captured_at asc, h.created_at asc
      limit 1
    ) blife on true
  )
  select
    e.card_variant_id,
    e.card_id,
    e.set_id,
    e.condition_id,
    e.current_market_price,
    e.current_captured_at,

    case when e.base_price_1d is null then null else round((e.current_market_price - e.base_price_1d)::numeric, 2) end,
    case when e.base_price_7d is null then null else round((e.current_market_price - e.base_price_7d)::numeric, 2) end,
    case when e.base_price_30d is null then null else round((e.current_market_price - e.base_price_30d)::numeric, 2) end,
    case when e.base_price_3m is null then null else round((e.current_market_price - e.base_price_3m)::numeric, 2) end,
    case when e.base_price_6m is null then null else round((e.current_market_price - e.base_price_6m)::numeric, 2) end,
    case when e.base_price_1y is null then null else round((e.current_market_price - e.base_price_1y)::numeric, 2) end,
    case when e.base_price_lifetime is null then null else round((e.current_market_price - e.base_price_lifetime)::numeric, 2) end,

    case when e.base_price_1d is null or e.base_price_1d = 0 then null else round((((e.current_market_price - e.base_price_1d) / e.base_price_1d) * 100)::numeric, 4) end,
    case when e.base_price_7d is null or e.base_price_7d = 0 then null else round((((e.current_market_price - e.base_price_7d) / e.base_price_7d) * 100)::numeric, 4) end,
    case when e.base_price_30d is null or e.base_price_30d = 0 then null else round((((e.current_market_price - e.base_price_30d) / e.base_price_30d) * 100)::numeric, 4) end,
    case when e.base_price_3m is null or e.base_price_3m = 0 then null else round((((e.current_market_price - e.base_price_3m) / e.base_price_3m) * 100)::numeric, 4) end,
    case when e.base_price_6m is null or e.base_price_6m = 0 then null else round((((e.current_market_price - e.base_price_6m) / e.base_price_6m) * 100)::numeric, 4) end,
    case when e.base_price_1y is null or e.base_price_1y = 0 then null else round((((e.current_market_price - e.base_price_1y) / e.base_price_1y) * 100)::numeric, 4) end,
    case when e.base_price_lifetime is null or e.base_price_lifetime = 0 then null else round((((e.current_market_price - e.base_price_lifetime) / e.base_price_lifetime) * 100)::numeric, 4) end,

    e.base_price_1d,
    e.base_price_7d,
    e.base_price_30d,
    e.base_price_3m,
    e.base_price_6m,
    e.base_price_1y,
    e.base_price_lifetime,
    now()
  from enriched e;

  get diagnostics v_rows = row_count;

  return jsonb_build_object(
    'refreshed_rows', v_rows,
    'table_name', 'card_variant_market_metrics_latest'
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history(p_set_id uuid DEFAULT NULL::uuid, p_start_date date DEFAULT NULL::date, p_end_date date DEFAULT NULL::date)
 RETURNS integer
 LANGUAGE plpgsql
 SET "TimeZone" TO 'America/Phoenix'
 SET search_path TO ''
AS $function$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_rows_upserted INTEGER := 0;
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RAISE NOTICE 'Near Mint condition not found; pokemon_set_value_daily_history refresh skipped.';
        RETURN 0;
    END IF;

    WITH requested_sets AS (
        SELECT id
        FROM public.sets
        WHERE p_set_id IS NULL OR id = p_set_id
    ),
    canonical_checklist AS (
        SELECT
            pcc.set_id,
            pcc.id AS pokemon_canonical_card_id,
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        JOIN requested_sets s ON s.id = pcc.set_id
        WHERE pcc.set_value_eligible = true
    ),
    canonical_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS canonical_card_count
        FROM canonical_checklist
        GROUP BY set_id
    ),
    canonical_card_links AS (
        SELECT DISTINCT cc.set_id, cc.pokemon_canonical_card_id, c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = cc.set_id
         AND (
             c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
             OR (
                 lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) = lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                 AND (
                     coalesce(cc.number, '') = coalesce(c.card_number, '')
                     OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                     OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') = ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                     OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') = ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                 )
             )
         )
        UNION
        SELECT DISTINCT cc.set_id, cc.pokemon_canonical_card_id, link.legacy_card_id AS card_id
        FROM canonical_checklist cc
        JOIN public.pokemon_canonical_card_legacy_identity_links link
          ON link.canonical_card_id = cc.pokemon_canonical_card_id
    ),
    canonical_variant_links AS (
        SELECT DISTINCT ccl.set_id, ccl.pokemon_canonical_card_id, ccl.card_id, cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = ''
               OR EXISTS (
                   SELECT 1 FROM public.cards c_name
                   WHERE c_name.id = ccl.card_id
                     AND lower(regexp_replace(coalesce(c_name.name, ''), '[^a-zA-Z0-9]+', '', 'g')) = 'pokeball'
               ))
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS linked_card_count
        FROM canonical_variant_links
        GROUP BY set_id
    ),
    canonical_scope_flags AS (
        SELECT
            cc.set_id,
            cc.pokemon_canonical_card_id,
            EXISTS (
                SELECT 1
                FROM public.pokemon_card_desirability_links link
                WHERE link.pokemon_canonical_card_id = cc.pokemon_canonical_card_id
                  AND link.is_hit_eligible = true
            ) AS is_hit_eligible
        FROM canonical_checklist cc
    ),
    hit_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS hit_card_count
        FROM canonical_scope_flags
        WHERE is_hit_eligible = true
        GROUP BY set_id
    ),
    observed_bounds AS (
        SELECT
            cvl.set_id,
            min(o.captured_at) AS first_observation_date,
            max(o.captured_at) AS latest_observation_date
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
          AND o.source = 'TCGPlayer'
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
        GROUP BY cvl.set_id
    ),
    set_dates AS (
        SELECT b.set_id, generated_day::date AS snapshot_date
        FROM observed_bounds b
        CROSS JOIN LATERAL generate_series(
            greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date)),
            
least(
                CASE
                    WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                        THEN p_end_date
                    ELSE b.latest_observation_date
                END,
                timezone(v_set_value_market_day_timezone, now())::date
            )
,
            interval '1 day'
        ) AS generated_day
        WHERE greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date))
              <= 
least(
                CASE
                    WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                        THEN p_end_date
                    ELSE b.latest_observation_date
                END,
                timezone(v_set_value_market_day_timezone, now())::date
            )

    ),
    latest_priced_cards AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            cvl.pokemon_canonical_card_id,
            csf.is_hit_eligible,
            latest_price.market_price,
            latest_price.captured_at
        FROM set_dates sd
        JOIN (SELECT DISTINCT set_id, pokemon_canonical_card_id FROM canonical_variant_links) linked_cards
          ON linked_cards.set_id = sd.set_id
        JOIN canonical_scope_flags csf
          ON csf.set_id = linked_cards.set_id
         AND csf.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        JOIN LATERAL (
            SELECT o.market_price, o.captured_at
            FROM canonical_variant_links cvl_inner
            JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl_inner.card_variant_id
              AND o.source = 'TCGPlayer'
            WHERE cvl_inner.set_id = linked_cards.set_id
              AND cvl_inner.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL
              AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at <= sd.snapshot_date
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) latest_price ON true
        JOIN canonical_variant_links cvl
          ON cvl.set_id = linked_cards.set_id
         AND cvl.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        GROUP BY sd.set_id, sd.snapshot_date, cvl.pokemon_canonical_card_id, csf.is_hit_eligible, latest_price.market_price, latest_price.captured_at
    ),
    standard_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'standard'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(cc.canonical_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT lpc.pokemon_canonical_card_id)::numeric / nullif(max(cc.canonical_card_count), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = lpc.set_id
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    hits_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'hits'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(hc.hit_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT lpc.pokemon_canonical_card_id)::numeric / nullif(max(hc.hit_card_count), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:hits:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = lpc.set_id
        LEFT JOIN hit_counts hc ON hc.set_id = lpc.set_id
        WHERE lpc.is_hit_eligible = true
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    ranked_priced_cards AS (
        SELECT lpc.*, row_number() OVER (PARTITION BY lpc.set_id, lpc.snapshot_date ORDER BY lpc.market_price DESC, lpc.pokemon_canonical_card_id) AS price_rank
        FROM latest_priced_cards lpc
    ),
    top10_aggregated AS (
        SELECT
            rpc.set_id,
            rpc.snapshot_date,
            'top10'::text AS value_scope,
            round(sum(rpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            least(10, max(cc.canonical_card_count))::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT rpc.pokemon_canonical_card_id)::numeric / nullif(least(10, max(cc.canonical_card_count)), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist' AS source
        FROM ranked_priced_cards rpc
        JOIN canonical_counts cc ON cc.set_id = rpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = rpc.set_id
        WHERE rpc.price_rank <= 10
        GROUP BY rpc.set_id, rpc.snapshot_date
    ),
    aggregated AS (
        SELECT * FROM standard_aggregated
        UNION ALL SELECT * FROM hits_aggregated
        UNION ALL SELECT * FROM top10_aggregated
    ),
    scope_candidates AS (
        SELECT sd.set_id, sd.snapshot_date, scope.value_scope
        FROM set_dates sd
        CROSS JOIN (VALUES ('standard'::text), ('hits'::text), ('top10'::text)) AS scope(value_scope)
    ),
    stale_deleted AS (
        DELETE FROM public.pokemon_set_value_daily_history h
        USING scope_candidates sc
        WHERE h.set_id = sc.set_id
          AND h.snapshot_date = sc.snapshot_date
          AND h.value_scope = sc.value_scope
          AND NOT EXISTS (
              SELECT 1
              FROM aggregated a
              WHERE a.set_id = h.set_id
                AND a.snapshot_date = h.snapshot_date
                AND a.value_scope = h.value_scope
          )
        RETURNING 1
    ),
    upserted AS (
        INSERT INTO public.pokemon_set_value_daily_history (
            set_id, snapshot_date, value_scope, set_value, priced_card_count, total_card_count,
            canonical_card_count, linked_card_count, included_card_count, coverage_pct, source
        )
        SELECT
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            coalesce(total_card_count, 0),
            coalesce(canonical_card_count, total_card_count, 0),
            coalesce(linked_card_count, 0),
            coalesce(included_card_count, priced_card_count, 0),
            coverage_pct,
            source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            canonical_card_count = EXCLUDED.canonical_card_count,
            linked_card_count = EXCLUDED.linked_card_count,
            included_card_count = EXCLUDED.included_card_count,
            coverage_pct = EXCLUDED.coverage_pct,
            source = EXCLUDED.source,
            updated_at = timezone('utc', now())
        RETURNING 1
    )
    SELECT count(*) INTO v_rows_upserted FROM upserted;

    RETURN coalesce(v_rows_upserted, 0);
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_nightly_snapshot_pricing_freshness(p_snapshot_date date DEFAULT NULL::date, p_sample_limit integer DEFAULT 25)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_snapshot_date date := COALESCE(p_snapshot_date, timezone('utc', now())::date);
    v_sample_limit integer := GREATEST(COALESCE(p_sample_limit, 25), 0);
    v_day_start timestamptz := (v_snapshot_date::text || ' 00:00:00+00')::timestamptz;
    v_day_end timestamptz := ((v_snapshot_date + 1)::text || ' 00:00:00+00')::timestamptz;
    v_total_started timestamptz := clock_timestamp();
    v_step_started timestamptz;
    v_held_asset_load_ms numeric := 0;
    v_card_freshness_check_ms numeric := 0;
    v_sealed_freshness_check_ms numeric := 0;
    v_graded_freshness_check_ms numeric := 0;
    v_total_ms numeric := 0;
    v_card_held_count integer := 0;
    v_sealed_held_count integer := 0;
    v_graded_held_count integer := 0;
    v_invalid_card_count integer := 0;
    v_invalid_sealed_count integer := 0;
    v_invalid_graded_count integer := 0;
    v_fresh_card_count integer := 0;
    v_fresh_sealed_count integer := 0;
    v_fresh_graded_count integer := 0;
    v_missing_card_count integer := 0;
    v_missing_sealed_count integer := 0;
    v_missing_graded_count integer := 0;
    v_missing_total integer := 0;
    v_missing_assets_sample jsonb := '[]'::jsonb;
BEGIN
    v_step_started := clock_timestamp();

    WITH held_cards AS (
        SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
        FROM public.user_card_holdings
        WHERE COALESCE(user_card_holdings.quantity, 0) > 0
          AND user_card_holdings.card_variant_id IS NOT NULL
          AND user_card_holdings.condition_id IS NOT NULL
    ), held_sealed AS (
        SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
        FROM public.user_sealed_product_holdings
        WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
          AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
    ), held_graded AS (
        SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
        FROM public.user_graded_card_holdings
        WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
          AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
    )
    SELECT
        (SELECT COUNT(*) FROM held_cards),
        (SELECT COUNT(*) FROM held_sealed),
        (SELECT COUNT(*) FROM held_graded),
        (SELECT COUNT(*) FROM public.user_card_holdings WHERE COALESCE(quantity, 0) > 0 AND (card_variant_id IS NULL OR condition_id IS NULL)),
        (SELECT COUNT(*) FROM public.user_sealed_product_holdings WHERE COALESCE(quantity, 0) > 0 AND sealed_product_id IS NULL),
        (SELECT COUNT(*) FROM public.user_graded_card_holdings WHERE COALESCE(quantity, 0) > 0 AND graded_card_variant_id IS NULL)
    INTO
        v_card_held_count,
        v_sealed_held_count,
        v_graded_held_count,
        v_invalid_card_count,
        v_invalid_sealed_count,
        v_invalid_graded_count;

    v_held_asset_load_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_cards AS (
        SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
        FROM public.user_card_holdings
        WHERE COALESCE(user_card_holdings.quantity, 0) > 0
          AND user_card_holdings.card_variant_id IS NOT NULL
          AND user_card_holdings.condition_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_card_count
    FROM held_cards h
    WHERE EXISTS (
        SELECT 1
        FROM public.card_variant_price_observation_ranges_v2 o
        WHERE o.card_variant_id = h.card_variant_id
          AND o.condition_id = h.condition_id
          AND o.source = 'TCGPlayer'
          AND o.observed_from <= v_snapshot_date
          AND o.observed_through >= v_snapshot_date
    );

    v_card_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_sealed AS (
        SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
        FROM public.user_sealed_product_holdings
        WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
          AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_sealed_count
    FROM held_sealed h
    WHERE EXISTS (
        SELECT 1
        FROM public.sealed_product_price_observations o
        WHERE o.sealed_product_id = h.sealed_product_id
          AND o.captured_at >= v_day_start
          AND o.captured_at < v_day_end
    );

    v_sealed_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_graded AS (
        SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
        FROM public.user_graded_card_holdings
        WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
          AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_graded_count
    FROM held_graded h
    WHERE EXISTS (
        SELECT 1
        FROM public.graded_card_variant_price_observations g
        WHERE g.graded_card_variant_id = h.graded_card_variant_id
          AND g.captured_date = v_snapshot_date
          AND true
    );

    v_graded_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_missing_card_count := v_card_held_count - v_fresh_card_count + v_invalid_card_count;
    v_missing_sealed_count := v_sealed_held_count - v_fresh_sealed_count + v_invalid_sealed_count;
    v_missing_graded_count := v_graded_held_count - v_fresh_graded_count + v_invalid_graded_count;
    v_missing_total := v_missing_card_count + v_missing_sealed_count + v_missing_graded_count;

    IF v_missing_total > 0 AND v_sample_limit > 0 THEN
        WITH invalid_card_sample AS (
            SELECT 0 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'card',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_card_count, v_sample_limit)) AS gs
        ), invalid_sealed_sample AS (
            SELECT 1 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'sealed',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_sealed_count, v_sample_limit)) AS gs
        ), invalid_graded_sample AS (
            SELECT 2 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'graded',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_graded_count, v_sample_limit)) AS gs
        ), missing_card_sample AS (
            SELECT 3 AS ord,
                   row_number() OVER (ORDER BY h.card_variant_id, h.condition_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'card',
                       'card_variant_id', h.card_variant_id,
                       'condition_id', h.condition_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
                FROM public.user_card_holdings
                WHERE COALESCE(user_card_holdings.quantity, 0) > 0
                  AND user_card_holdings.card_variant_id IS NOT NULL
                  AND user_card_holdings.condition_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.card_variant_price_observation_ranges_v2 o
                      WHERE o.card_variant_id = user_card_holdings.card_variant_id
                        AND o.condition_id = user_card_holdings.condition_id
                        AND o.source = 'TCGPlayer'
                        AND o.observed_from <= v_snapshot_date
          AND o.observed_through >= v_snapshot_date
                  )
            ) h
            LEFT JOIN public.card_market_usd_latest_by_condition l
              ON l.variant_id = h.card_variant_id
             AND l.condition_id = h.condition_id
        ), missing_sealed_sample AS (
            SELECT 4 AS ord,
                   row_number() OVER (ORDER BY h.sealed_product_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'sealed',
                       'sealed_product_id', h.sealed_product_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
                FROM public.user_sealed_product_holdings
                WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
                  AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.sealed_product_price_observations o
                      WHERE o.sealed_product_id = user_sealed_product_holdings.sealed_product_id
                        AND o.captured_at >= v_day_start
                        AND o.captured_at < v_day_end
                  )
            ) h
            LEFT JOIN public.sealed_product_market_usd_latest l
              ON l.sealed_product_id = h.sealed_product_id
        ), missing_graded_sample AS (
            SELECT 5 AS ord,
                   row_number() OVER (ORDER BY h.graded_card_variant_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'graded',
                       'graded_card_variant_id', h.graded_card_variant_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
                FROM public.user_graded_card_holdings
                WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
                  AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.graded_card_variant_price_observations g
                      WHERE g.graded_card_variant_id = user_graded_card_holdings.graded_card_variant_id
                        AND g.captured_date = v_snapshot_date
                        AND true
                  )
            ) h
            LEFT JOIN public.graded_card_market_latest l
              ON l.graded_card_variant_id = h.graded_card_variant_id
        ), combined AS (
            SELECT ord, seq, payload FROM invalid_card_sample
            UNION ALL
            SELECT ord, seq, payload FROM invalid_sealed_sample
            UNION ALL
            SELECT ord, seq, payload FROM invalid_graded_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_card_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_sealed_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_graded_sample
        )
        SELECT COALESCE(jsonb_agg(payload ORDER BY ord, seq), '[]'::jsonb)
        INTO v_missing_assets_sample
        FROM (
            SELECT ord, seq, payload
            FROM combined
            ORDER BY ord, seq
            LIMIT v_sample_limit
        ) limited_sample;
    END IF;

    v_total_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_total_started))::numeric * 1000, 3);

    RETURN jsonb_build_object(
        'snapshot_date', v_snapshot_date::text,
        'status', CASE WHEN v_missing_total = 0 THEN 'ok' ELSE 'skipped' END,
        'check_completed', true,
        'is_fresh', v_missing_total = 0,
        'held_asset_counts', jsonb_build_object(
            'cards', v_card_held_count + v_invalid_card_count,
            'sealed', v_sealed_held_count + v_invalid_sealed_count,
            'graded', v_graded_held_count + v_invalid_graded_count
        ),
        'fresh_asset_counts', jsonb_build_object(
            'cards', v_fresh_card_count,
            'sealed', v_fresh_sealed_count,
            'graded', v_fresh_graded_count
        ),
        'missing_asset_counts', jsonb_build_object(
            'cards', v_missing_card_count,
            'sealed', v_missing_sealed_count,
            'graded', v_missing_graded_count,
            'total', v_missing_total
        ),
        'missing_assets_sample', v_missing_assets_sample,
        'warning', CASE
            WHEN v_missing_total = 0 THEN NULL
            ELSE format(
                'Pricing freshness incomplete for snapshot_date=%s; missing_or_stale_assets=%s. Nightly snapshot skipped.',
                v_snapshot_date::text,
                v_missing_total
            )
        END,
        'timings_ms', jsonb_build_object(
            'held_asset_load_ms', v_held_asset_load_ms,
            'card_freshness_check_ms', v_card_freshness_check_ms,
            'sealed_freshness_check_ms', v_sealed_freshness_check_ms,
            'graded_freshness_check_ms', v_graded_freshness_check_ms,
            'total_ms', v_total_ms
        ),
        'query_path', jsonb_build_object(
            'held_asset_source', jsonb_build_array(
                'user_card_holdings(quantity>0)',
                'user_sealed_product_holdings(quantity>0)',
                'user_graded_card_holdings(quantity>0)'
            ),
            'card_check_source', 'card_variant_price_observation_ranges_v2(observed_from/observed_through)',
            'sealed_check_source', 'sealed_product_price_observations(captured_at)',
            'graded_check_source', 'graded_card_variant_price_observations(captured_date)',
            'uses_distinct_held_assets', true,
            'loads_full_holdings_rows', false,
            'loads_full_latest_views', false,
            'notes', jsonb_build_array(
                'Card and sealed freshness use EXISTS against snapshot-date pricing sources.',
                'Graded freshness falls back to graded_card_market_latest because no graded observation table was found in repo migrations.',
                'Missing asset samples are fetched only after freshness is decided and are bounded by sample limit.'
            )
        )
    );
END;
$function$;

-- P5A_ZERO_DIFF_START
CREATE TEMP TABLE p5a_canonical_after ON COMMIT DROP AS
WITH targets(canonical_card_id,set_id) AS (VALUES
  ('00afbaf5-46cc-4b2d-b1ee-c9839b7d6d8f'::uuid,'4099fc11-a3f6-4034-8208-fbf82bd89de5'::uuid),
  ('02768af4-334c-4eb8-a6f3-71b84e54f9f5'::uuid,'1b3250bb-f123-47d8-b090-499e5879eda7'::uuid),
  ('037e131a-63bb-41b1-9a46-d215487eb412'::uuid,'3c459327-59d0-41d5-b21e-aae36361cc77'::uuid),
  ('038cd0c3-e33f-4a96-9999-81608939b119'::uuid,'a69e4091-5b33-499d-85a5-a8f0b7ecaddc'::uuid),
  ('0ac8d1e3-dc0a-4cca-9df8-04291875dffe'::uuid,'1c6a8735-af2a-475b-b230-5bd18f827b06'::uuid),
  ('145c3df2-bafd-4fe8-820e-2226b51454d2'::uuid,'30396643-190c-416d-92a4-e8414c8b4980'::uuid),
  ('214a20d8-6ae0-46de-9047-082b506c4b1e'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('310cafff-701e-4213-a59b-938d2f5f794e'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('3695a310-0980-4cba-b790-ab7d827b3b44'::uuid,'5bdbfae1-3f2e-44e7-b8c9-1035ad45b896'::uuid),
  ('3ef680dc-9c3a-4d0f-af5d-f7b8b3c35695'::uuid,'b5172ada-e0d5-4c3f-a4c7-06b4ac3391de'::uuid),
  ('4540ac5a-4e22-40d0-a0f1-2dbb14c99243'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('4f7b4614-fcf3-4f15-b596-dd4be57849d1'::uuid,'cb1dc8ed-925b-443d-ba23-d6ffa8f7084c'::uuid),
  ('57f1882b-11e5-4fa6-98a8-b4e323392911'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('621b038b-e832-47a2-8bdd-1160945d6d44'::uuid,'89e710d1-c378-4b4e-aaea-5994d8441f45'::uuid),
  ('7781f22e-0d90-4a51-87d8-d56fcbc34dd7'::uuid,'70a8d8f3-9aee-4ac8-88e4-dfbca50652f4'::uuid),
  ('8de57c6e-93ca-4f8e-a9b8-98ee422d4761'::uuid,'77bde285-03f8-4a48-b6a5-2f548225c3eb'::uuid),
  ('a6a3e0ec-9e63-4ee3-9cb8-c3981a495e5d'::uuid,'77bde285-03f8-4a48-b6a5-2f548225c3eb'::uuid),
  ('ab8f7a71-f1e8-41e8-89cb-b01bea223bf2'::uuid,'ca0ad9de-678b-4734-9e91-93a1d7201e51'::uuid),
  ('b38102f7-42b0-49bc-a2b1-a16bda58a581'::uuid,'4f84d317-e15d-4598-bc8d-52baa04b3485'::uuid),
  ('b815a131-d4f1-43da-b8b2-fb521ffbab10'::uuid,'aac3de95-9f92-44af-966d-70b1d201c01e'::uuid),
  ('c10d44b1-f2c9-4110-9753-61c23275b218'::uuid,'1b3250bb-f123-47d8-b090-499e5879eda7'::uuid),
  ('c3040b5f-0d8e-4f11-b426-a96624ca7d5e'::uuid,'126093d8-50e7-4a7c-891d-8cffd5733eeb'::uuid),
  ('cae71539-cdde-41e1-aa61-cf1f67f43d69'::uuid,'aac3de95-9f92-44af-966d-70b1d201c01e'::uuid),
  ('dd970fea-4ec2-4870-b258-141c9a5563b2'::uuid,'92575c0d-fac2-42ff-86f3-fb81f7452188'::uuid),
  ('e0e90f28-075e-4eda-a5c0-a017adf2760c'::uuid,'a69e4091-5b33-499d-85a5-a8f0b7ecaddc'::uuid),
  ('e4b73b72-2882-436f-9d27-90b229185520'::uuid,'4de777b3-396e-4f19-9d78-c054b296bedb'::uuid),
  ('e4ca99f2-796b-447a-af18-224eb290297b'::uuid,'8dbf97f7-b7e8-4ff5-883a-0bb3356291bf'::uuid),
  ('ec21dd75-f0d8-4cd7-ad31-50bec1a687b3'::uuid,'ffc6b635-fe16-4416-b4fc-0f727e4c81d4'::uuid),
  ('f13e4255-67dd-48ce-af76-69abda61c8d9'::uuid,'8938c853-2282-46d8-ba44-87584fa2c168'::uuid),
  ('f940db65-6995-4dbf-bd92-817aececb2ec'::uuid,'a2cc93d2-762d-4dcc-ac17-62f244abce06'::uuid),
  ('58a01e34-87f7-4693-a763-c40f8c8cabc1'::uuid,'0b8ebcec-2b4e-4a77-9923-ffc4be6514c5'::uuid),
  ('8b48e631-400b-42d7-86f4-b7000b139ad4'::uuid,'bbea2ee9-6be2-44bd-b14e-b4a8b9c858de'::uuid),
  ('bd0fc6f2-31de-4ca3-9459-0b4753baa2b7'::uuid,'78c7f000-9a9e-45ca-8233-8f36030f6019'::uuid)
)
SELECT t.canonical_card_id,t.set_id,r.card_variant_id,r.condition_id,r.market_price,r.source,r.captured_at,r.price_selection_reason
FROM targets t LEFT JOIN LATERAL (
  SELECT * FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(t.set_id) x
  WHERE x.canonical_card_id=t.canonical_card_id
) r ON true;

CREATE TEMP TABLE p5a_latest_after ON COMMIT DROP AS
WITH targets(variant_id) AS (VALUES
  ('09c602d4-6c85-4f6d-b1b3-a12e5155f5de'::uuid),
  ('2e825dec-1a8a-46dd-9e47-4cb7d55ee42a'::uuid),
  ('33aae8ca-8e63-406e-a672-c067a8dd27ca'::uuid),
  ('3dd0f4fa-16ac-4263-b9bc-817b48a3074c'::uuid),
  ('5a9d23cc-e13a-4c29-a761-d602f87ca950'::uuid),
  ('5c4c7dc2-9636-4544-8f24-b20c5df54127'::uuid),
  ('5ed848c2-fc64-4528-aff0-279b89c46b8c'::uuid),
  ('63191dd8-35a2-411d-89c9-af8e1de3e181'::uuid),
  ('7b646415-6c67-4910-8ae4-18a65c88f514'::uuid),
  ('8a4b2acc-eee4-45bb-96b2-1130d9c3ad8b'::uuid),
  ('9543c2f9-1ffe-4d2f-b1c5-beed15f1ed15'::uuid),
  ('96a68097-9308-481e-b57d-acd23f5c6bef'::uuid),
  ('b432b3a4-19b0-4598-94c8-9bc2f206ee82'::uuid),
  ('b46702d4-a9db-44fa-8bfc-1c46839581f3'::uuid),
  ('b6e430da-2e44-40e3-9263-d3a9a037d0c3'::uuid),
  ('f68cb094-0a0d-423f-8a76-b013ac5b86a6'::uuid)
)
SELECT t.variant_id,v.condition_id,v.market_price,v.source,v.captured_at,v.created_at
FROM targets t LEFT JOIN public.card_market_usd_latest_by_condition v ON v.variant_id=t.variant_id;

DO $p5a$
BEGIN
  IF EXISTS (
    SELECT 1 FROM (
      (SELECT * FROM p5a_canonical_before EXCEPT ALL SELECT * FROM p5a_canonical_after)
      UNION ALL
      (SELECT * FROM p5a_canonical_after EXCEPT ALL SELECT * FROM p5a_canonical_before)
    ) difference
  ) THEN RAISE EXCEPTION 'P5A canonical zero-diff failed; rolling back'; END IF;
  IF EXISTS (
    SELECT 1 FROM (
      (SELECT * FROM p5a_latest_before EXCEPT ALL SELECT * FROM p5a_latest_after)
      UNION ALL
      (SELECT * FROM p5a_latest_after EXCEPT ALL SELECT * FROM p5a_latest_before)
    ) difference
  ) THEN RAISE EXCEPTION 'P5A latest-view zero-diff failed; rolling back'; END IF;
END
$p5a$;
-- P5A_ZERO_DIFF_END


commit;
