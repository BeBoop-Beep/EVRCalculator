-- Treatment Direct Preference V1 research collection.
-- Additive and isolated. No pricing, Collector Appeal, Overall RIP, Rankings,
-- or Set-page authority is mutated by this migration.

begin;

create table if not exists public.pokemon_treatment_preference_v1_block_claims (
    study_version text not null,
    schedule_fingerprint text not null,
    block_index integer not null check (block_index >= 0 and block_index < 450),
    session_hash text,
    claim_token uuid,
    claimed_at timestamptz,
    expires_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (study_version, schedule_fingerprint, block_index),
    check ((session_hash is null) = (claim_token is null)),
    check ((session_hash is null) = (claimed_at is null)),
    check (
        session_hash is null
        or expires_at is not null
        or completed_at is not null
    )
);

create unique index if not exists uq_pokemon_treatment_preference_v1_session
on public.pokemon_treatment_preference_v1_block_claims (
    study_version, schedule_fingerprint, session_hash
)
where session_hash is not null;

create table if not exists public.pokemon_treatment_preference_v1_responses (
    id uuid primary key default gen_random_uuid(),
    study_version text not null,
    schedule_fingerprint text not null,
    session_hash text not null check (session_hash ~ '^[0-9a-f]{64}$'),
    block_index integer not null check (block_index >= 0 and block_index < 450),
    underlying_pair_id text not null check (length(underlying_pair_id) = 24),
    set_id uuid not null references public.sets(id),
    subject_key text not null,
    left_card_id uuid not null references public.pokemon_canonical_cards(id),
    right_card_id uuid not null references public.pokemon_canonical_cards(id),
    left_treatment text not null check (
        left_treatment in ('Double Rare', 'Ultra Rare', 'Special Illustration Rare')
    ),
    right_treatment text not null check (
        right_treatment in ('Double Rare', 'Ultra Rare', 'Special Illustration Rare')
    ),
    randomized_orientation_receipt text not null check (
        randomized_orientation_receipt in ('A_LEFT', 'B_LEFT')
    ),
    response text not null check (response in ('LEFT', 'RIGHT', 'TIE')),
    submitted_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (study_version, schedule_fingerprint, session_hash, underlying_pair_id)
);

create index if not exists idx_pokemon_treatment_preference_v1_pair
on public.pokemon_treatment_preference_v1_responses (
    study_version, schedule_fingerprint, underlying_pair_id
);

create index if not exists idx_pokemon_treatment_preference_v1_block
on public.pokemon_treatment_preference_v1_responses (
    study_version, schedule_fingerprint, block_index
);

alter table public.pokemon_treatment_preference_v1_block_claims enable row level security;
alter table public.pokemon_treatment_preference_v1_responses enable row level security;

revoke all on table public.pokemon_treatment_preference_v1_block_claims from public, anon, authenticated;
revoke all on table public.pokemon_treatment_preference_v1_responses from public, anon, authenticated;
grant select, insert, update, delete on table public.pokemon_treatment_preference_v1_block_claims to service_role;
grant select, insert, update, delete on table public.pokemon_treatment_preference_v1_responses to service_role;

insert into public.pokemon_treatment_preference_v1_block_claims (
    study_version, schedule_fingerprint, block_index
)
select
    'treatment_direct_preference_v1',
    '4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055',
    gs
from generate_series(0, 449) as gs
on conflict do nothing;

create or replace function public.claim_pokemon_treatment_preference_v1_block(
    p_session_hash text
)
returns table (
    block_index integer,
    claim_token uuid,
    already_completed boolean
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_study constant text := 'treatment_direct_preference_v1';
    v_schedule constant text := '4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055';
    v_index integer;
    v_token uuid;
    v_completed timestamptz;
begin
    if p_session_hash is null or p_session_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'TREATMENT_PREFERENCE_SESSION_HASH_INVALID';
    end if;

    perform pg_advisory_xact_lock(hashtext(v_study || ':' || v_schedule));

    select c.block_index, c.claim_token, c.completed_at
      into v_index, v_token, v_completed
    from public.pokemon_treatment_preference_v1_block_claims c
    where c.study_version = v_study
      and c.schedule_fingerprint = v_schedule
      and c.session_hash = p_session_hash
    limit 1;

    if found then
        return query select v_index, v_token, (v_completed is not null);
        return;
    end if;

    select c.block_index
      into v_index
    from public.pokemon_treatment_preference_v1_block_claims c
    where c.study_version = v_study
      and c.schedule_fingerprint = v_schedule
      and c.completed_at is null
      and (
          c.session_hash is null
          or c.expires_at < now()
      )
    order by md5(p_session_hash || ':' || c.block_index::text)
    limit 1
    for update skip locked;

    if not found then
        return;
    end if;

    v_token := gen_random_uuid();

    update public.pokemon_treatment_preference_v1_block_claims c
       set session_hash = p_session_hash,
           claim_token = v_token,
           claimed_at = now(),
           expires_at = now() + interval '6 hours',
           completed_at = null,
           updated_at = now()
     where c.study_version = v_study
       and c.schedule_fingerprint = v_schedule
       and c.block_index = v_index;

    return query select v_index, v_token, false;
end;
$$;

create or replace function public.submit_pokemon_treatment_preference_v1_block(
    p_session_hash text,
    p_claim_token uuid,
    p_block_index integer,
    p_responses jsonb
)
returns table (
    accepted_responses integer,
    already_completed boolean
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_study constant text := 'treatment_direct_preference_v1';
    v_schedule constant text := '4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055';
    v_claim public.pokemon_treatment_preference_v1_block_claims%rowtype;
    v_count integer;
    v_distinct integer;
begin
    if p_session_hash is null or p_session_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'TREATMENT_PREFERENCE_SESSION_HASH_INVALID';
    end if;
    if p_claim_token is null then
        raise exception 'TREATMENT_PREFERENCE_CLAIM_TOKEN_INVALID';
    end if;
    if p_block_index < 0 or p_block_index >= 450 then
        raise exception 'TREATMENT_PREFERENCE_BLOCK_INDEX_INVALID';
    end if;
    if jsonb_typeof(p_responses) <> 'array' or jsonb_array_length(p_responses) <> 12 then
        raise exception 'TREATMENT_PREFERENCE_RESPONSE_COUNT_INVALID';
    end if;

    perform pg_advisory_xact_lock(hashtext(v_study || ':' || v_schedule));

    select *
      into v_claim
    from public.pokemon_treatment_preference_v1_block_claims c
    where c.study_version = v_study
      and c.schedule_fingerprint = v_schedule
      and c.block_index = p_block_index
    for update;

    if not found
       or v_claim.session_hash is distinct from p_session_hash
       or v_claim.claim_token is distinct from p_claim_token then
        raise exception 'TREATMENT_PREFERENCE_CLAIM_MISMATCH';
    end if;

    if v_claim.completed_at is not null then
        select count(*)
          into v_count
        from public.pokemon_treatment_preference_v1_responses r
        where r.study_version = v_study
          and r.schedule_fingerprint = v_schedule
          and r.session_hash = p_session_hash
          and r.block_index = p_block_index;
        return query select v_count, true;
        return;
    end if;

    select count(*), count(distinct x.underlying_pair_id)
      into v_count, v_distinct
    from jsonb_to_recordset(p_responses) as x(
        underlying_pair_id text,
        set_id uuid,
        subject_key text,
        left_card_id uuid,
        right_card_id uuid,
        left_treatment text,
        right_treatment text,
        randomized_orientation_receipt text,
        response text
    );

    if v_count <> 12 or v_distinct <> 12 then
        raise exception 'TREATMENT_PREFERENCE_RESPONSE_SET_INVALID';
    end if;

    insert into public.pokemon_treatment_preference_v1_responses (
        study_version,
        schedule_fingerprint,
        session_hash,
        block_index,
        underlying_pair_id,
        set_id,
        subject_key,
        left_card_id,
        right_card_id,
        left_treatment,
        right_treatment,
        randomized_orientation_receipt,
        response
    )
    select
        v_study,
        v_schedule,
        p_session_hash,
        p_block_index,
        x.underlying_pair_id,
        x.set_id,
        x.subject_key,
        x.left_card_id,
        x.right_card_id,
        x.left_treatment,
        x.right_treatment,
        x.randomized_orientation_receipt,
        upper(x.response)
    from jsonb_to_recordset(p_responses) as x(
        underlying_pair_id text,
        set_id uuid,
        subject_key text,
        left_card_id uuid,
        right_card_id uuid,
        left_treatment text,
        right_treatment text,
        randomized_orientation_receipt text,
        response text
    );

    get diagnostics v_count = row_count;
    if v_count <> 12 then
        raise exception 'TREATMENT_PREFERENCE_RESPONSE_INSERT_INCOMPLETE';
    end if;

    update public.pokemon_treatment_preference_v1_block_claims c
       set completed_at = now(),
           expires_at = null,
           updated_at = now()
     where c.study_version = v_study
       and c.schedule_fingerprint = v_schedule
       and c.block_index = p_block_index;

    return query select v_count, false;
end;
$$;

revoke all on function public.claim_pokemon_treatment_preference_v1_block(text)
    from public, anon, authenticated;
revoke all on function public.submit_pokemon_treatment_preference_v1_block(text, uuid, integer, jsonb)
    from public, anon, authenticated;
grant execute on function public.claim_pokemon_treatment_preference_v1_block(text)
    to service_role;
grant execute on function public.submit_pokemon_treatment_preference_v1_block(text, uuid, integer, jsonb)
    to service_role;

comment on table public.pokemon_treatment_preference_v1_block_claims is
    'Research-only blinded Treatment preference V1 assignment claims. Anonymous session hashes only.';
comment on table public.pokemon_treatment_preference_v1_responses is
    'Research-only blinded Treatment preference V1 pairwise responses. No market prices or account identities.';

commit;
