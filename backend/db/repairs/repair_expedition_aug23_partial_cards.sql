-- DO NOT run as part of deployment.  One-off, fail-closed production repair
-- for the isolated card-only partial write from scrape job 146025.

BEGIN;

CREATE TEMP TABLE expedition_aug23_partial_cards ON COMMIT DROP AS
SELECT c.id
FROM public.cards c
JOIN public.sets s ON s.id = c.set_id
WHERE s.canonical_key = 'expeditionBaseSet'
  AND split_part(coalesce(c.card_number, ''), '/', 2) = '102'
  AND c.created_at = TIMESTAMPTZ '2026-08-24 04:27:14.165795+00';

DO $$
DECLARE
    candidate_count bigint;
    legitimate_raw_count bigint;
    canonical_count bigint;
    variant_count bigint;
    observation_count bigint;
    identity_count bigint;
    dependency_count bigint;
    fk record;
BEGIN
    SELECT count(*) INTO candidate_count FROM expedition_aug23_partial_cards;
    IF candidate_count <> 101 THEN
        RAISE EXCEPTION 'expected 101 isolated Expedition incident cards, found %', candidate_count;
    END IF;

    SELECT count(*) INTO legitimate_raw_count
    FROM public.cards c JOIN public.sets s ON s.id = c.set_id
    WHERE s.canonical_key = 'expeditionBaseSet'
      AND split_part(coalesce(c.card_number, ''), '/', 2) = '165';
    IF legitimate_raw_count <> 165 THEN
        RAISE EXCEPTION 'expected 165 legitimate raw Expedition /165 cards, found %', legitimate_raw_count;
    END IF;

    SELECT count(*) INTO canonical_count
    FROM public.pokemon_canonical_cards pc
    JOIN public.sets s ON s.id = pc.set_id
    WHERE s.canonical_key = 'expeditionBaseSet';
    IF canonical_count <> 165 THEN
        RAISE EXCEPTION 'expected 165 canonical Expedition cards, found %', canonical_count;
    END IF;

    SELECT count(*) INTO variant_count
    FROM public.card_variants v
    JOIN expedition_aug23_partial_cards c ON c.id = v.card_id;
    IF variant_count <> 0 THEN
        RAISE EXCEPTION 'incident cards have % card variants; refusing repair', variant_count;
    END IF;

    SELECT count(*) INTO observation_count
    FROM public.card_variant_price_observations o
    JOIN public.card_variants v ON v.id = o.card_variant_id
    JOIN expedition_aug23_partial_cards c ON c.id = v.card_id;
    IF observation_count <> 0 THEN
        RAISE EXCEPTION 'incident cards have % observations; refusing repair', observation_count;
    END IF;

    SELECT count(*) INTO identity_count
    FROM public.card_variant_external_identities e
    JOIN public.card_variants v ON v.id = e.card_variant_id
    JOIN expedition_aug23_partial_cards c ON c.id = v.card_id;
    IF identity_count <> 0 THEN
        RAISE EXCEPTION 'incident cards have % external identities; refusing repair', identity_count;
    END IF;

    -- Discover every current single-column FK that targets cards(id).  This
    -- prevents a later schema addition from silently escaping the repair gate.
    FOR fk IN
        SELECT
            con.conrelid::regclass AS dependent_table,
            child_att.attname AS dependent_column
        FROM pg_constraint con
        JOIN pg_attribute parent_att
          ON parent_att.attrelid = con.confrelid
         AND parent_att.attnum = con.confkey[1]
        JOIN pg_attribute child_att
          ON child_att.attrelid = con.conrelid
         AND child_att.attnum = con.conkey[1]
        WHERE con.contype = 'f'
          AND con.confrelid = 'public.cards'::regclass
          AND array_length(con.conkey, 1) = 1
          AND parent_att.attname = 'id'
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM %s d JOIN expedition_aug23_partial_cards c ON c.id = d.%I',
            fk.dependent_table,
            fk.dependent_column
        ) INTO dependency_count;
        IF dependency_count <> 0 THEN
            RAISE EXCEPTION 'incident cards have % dependent rows in %.%; refusing repair',
                dependency_count, fk.dependent_table, fk.dependent_column;
        END IF;
    END LOOP;

    -- Also discover every FK targeting variants belonging to the candidate
    -- cards.  The expected variant cohort is empty, but retaining this gate
    -- makes the repair fail closed if the schema or live state changes.
    FOR fk IN
        SELECT
            con.conrelid::regclass AS dependent_table,
            child_att.attname AS dependent_column
        FROM pg_constraint con
        JOIN pg_attribute parent_att
          ON parent_att.attrelid = con.confrelid
         AND parent_att.attnum = con.confkey[1]
        JOIN pg_attribute child_att
          ON child_att.attrelid = con.conrelid
         AND child_att.attnum = con.conkey[1]
        WHERE con.contype = 'f'
          AND con.confrelid = 'public.card_variants'::regclass
          AND array_length(con.conkey, 1) = 1
          AND parent_att.attname = 'id'
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM %s d JOIN public.card_variants v ON v.id = d.%I '
            'JOIN expedition_aug23_partial_cards c ON c.id = v.card_id',
            fk.dependent_table,
            fk.dependent_column
        ) INTO dependency_count;
        IF dependency_count <> 0 THEN
            RAISE EXCEPTION 'incident variants have % dependent rows in %.%; refusing repair',
                dependency_count, fk.dependent_table, fk.dependent_column;
        END IF;
    END LOOP;
END $$;

-- Snapshot Base counts before the narrowly scoped delete.
CREATE TEMP TABLE expedition_repair_base_invariants ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM public.cards c JOIN public.sets s ON s.id = c.set_id
     WHERE s.canonical_key = 'base') AS cards,
    (SELECT count(*) FROM public.card_variants v JOIN public.cards c ON c.id = v.card_id
     JOIN public.sets s ON s.id = c.set_id WHERE s.canonical_key = 'base') AS variants,
    (SELECT count(*) FROM public.card_variant_price_observations o
     JOIN public.card_variants v ON v.id = o.card_variant_id
     JOIN public.cards c ON c.id = v.card_id JOIN public.sets s ON s.id = c.set_id
     WHERE s.canonical_key = 'base') AS observations,
    (SELECT count(*) FROM public.card_variant_external_identities e
     JOIN public.card_variants v ON v.id = e.card_variant_id
     JOIN public.cards c ON c.id = v.card_id JOIN public.sets s ON s.id = c.set_id
     WHERE s.canonical_key = 'base') AS identities;

DELETE FROM public.cards c
USING expedition_aug23_partial_cards doomed
WHERE c.id = doomed.id;

DO $$
DECLARE
    remaining_102 bigint;
    remaining_165 bigint;
    canonical_count bigint;
    base_before expedition_repair_base_invariants%ROWTYPE;
    base_after expedition_repair_base_invariants%ROWTYPE;
BEGIN
    SELECT count(*) INTO remaining_102
    FROM public.cards c JOIN public.sets s ON s.id = c.set_id
    WHERE s.canonical_key = 'expeditionBaseSet'
      AND split_part(coalesce(c.card_number, ''), '/', 2) = '102';
    SELECT count(*) INTO remaining_165
    FROM public.cards c JOIN public.sets s ON s.id = c.set_id
    WHERE s.canonical_key = 'expeditionBaseSet'
      AND split_part(coalesce(c.card_number, ''), '/', 2) = '165';
    SELECT count(*) INTO canonical_count
    FROM public.pokemon_canonical_cards pc JOIN public.sets s ON s.id = pc.set_id
    WHERE s.canonical_key = 'expeditionBaseSet';

    IF remaining_102 <> 0 OR remaining_165 <> 165 OR canonical_count <> 165 THEN
        RAISE EXCEPTION 'Expedition postcondition failed: /102=%, /165=%, canonical=%',
            remaining_102, remaining_165, canonical_count;
    END IF;

    SELECT * INTO base_before FROM expedition_repair_base_invariants;
    SELECT
        (SELECT count(*) FROM public.cards c JOIN public.sets s ON s.id = c.set_id
         WHERE s.canonical_key = 'base'),
        (SELECT count(*) FROM public.card_variants v JOIN public.cards c ON c.id = v.card_id
         JOIN public.sets s ON s.id = c.set_id WHERE s.canonical_key = 'base'),
        (SELECT count(*) FROM public.card_variant_price_observations o
         JOIN public.card_variants v ON v.id = o.card_variant_id
         JOIN public.cards c ON c.id = v.card_id JOIN public.sets s ON s.id = c.set_id
         WHERE s.canonical_key = 'base'),
        (SELECT count(*) FROM public.card_variant_external_identities e
         JOIN public.card_variants v ON v.id = e.card_variant_id
         JOIN public.cards c ON c.id = v.card_id JOIN public.sets s ON s.id = c.set_id
         WHERE s.canonical_key = 'base')
    INTO base_after;
    IF base_after IS DISTINCT FROM base_before THEN
        RAISE EXCEPTION 'Base counts changed: before=%, after=%', base_before, base_after;
    END IF;
END $$;

COMMIT;
