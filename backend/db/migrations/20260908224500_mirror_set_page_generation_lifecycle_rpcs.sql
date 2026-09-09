-- 20260908224500: source-repo mirror of the three production set-page
-- generation lifecycle functions, authored for review/contract-testing only.
--
-- WHY THIS EXISTS
-- ----------------
-- validate_pokemon_set_page_snapshot_generation, activate_pokemon_set_page_
-- snapshot_generation (with its live-membership-loss guard, applied in prod
-- as migration 20260908222038), and the wrapper
-- publish_pokemon_public_rip_leaderboard_with_set_pages exist and are ALREADY
-- LIVE in production, applied directly by a separate party with DB access.
-- No repo migration previously mirrored any of the three -- a repo-wide grep
-- for all three function names turned up zero matches under
-- backend/db/migrations before this file was added. This migration exists so
-- the repo carries a reviewable, testable source-of-truth copy alongside the
-- production reality, NOT to be applied by this effort. Do not run this file
-- against any database from this branch; it is authored for structural
-- contract tests only (see backend/tests/unit/db/test_set_page_generation_
-- lifecycle_rpc_mirror_sql.py).
--
-- PROVENANCE
-- ----------
-- The three CREATE OR REPLACE bodies below were transcribed verbatim from
-- `pg_get_functiondef` output supplied out-of-band by the party who owns
-- production DB access. This effort has NO live DB credentials and could NOT
-- independently verify the MD5/text against the running database -- treat
-- this file as an as-given transcription, not an independently verified
-- mirror. Flag any future drift for a maintainer to re-diff against
-- `pg_get_functiondef` before trusting this file as canonical.
--
-- GRANTS ARE INTENTIONALLY OMITTED. The supplied function bodies did not
-- include REVOKE/GRANT statements, and fabricating a grants block not
-- actually confirmed against prod would misrepresent the mirror as more
-- complete than the evidence supports. If prod grants differ from this
-- repo's usual REVOKE-ALL-then-GRANT-service_role convention, that is a
-- separate, real gap to close with real evidence, not to guess at here.
--
-- WHAT IS MIRRORED
-- -----------------
-- 1. validate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
--    RETURNS jsonb -- computes actual_set_count/actual_ids/collector_count/bad
--    from pokemon_set_page_snapshot_generation_rows, compares against the
--    generation row's expected_set_count/expected_set_ids/
--    expected_collector_row_count, and writes status='validated'|'failed'
--    plus the validation_json report back onto the generation row.
--
-- 2. activate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
--    RETURNS uuid -- the live-membership-loss guard (missing_live_count):
--    refuses to activate a generation that would silently drop any
--    currently-live public.pokemon_set_page_snapshot_latest.set_id that is
--    NOT present in the candidate generation's rows. This guard runs AFTER
--    the `n <> g.expected_set_count` completeness check and BEFORE the
--    destructive `DELETE FROM pokemon_set_page_snapshot_latest`.
--
-- 3. publish_pokemon_public_rip_leaderboard_with_set_pages(p_snapshot jsonb,
--    p_rows jsonb, p_latest jsonb, p_generation_id uuid) RETURNS uuid -- a
--    thin wrapper that calls publish_pokemon_public_rip_leaderboard(...) and
--    then activate_pokemon_set_page_snapshot_generation(p_generation_id),
--    asserting the returned generation id matches. NEITHER call is wrapped in
--    an EXCEPTION block anywhere in this chain (verified by inspection of all
--    three bodies below, plus the previously-mirrored
--    publish_pokemon_public_rip_leaderboard body): a RAISE EXCEPTION from
--    either call propagates out of this outer function call uncaught, so
--    Postgres rolls back the ENTIRE implicit transaction the RPC call opened
--    -- both the Rankings snapshot writes AND any partial activation effects.
--    There is no dblink/autonomous-transaction extension in use anywhere in
--    this chain, so there is no way for the Rankings-writer half to survive
--    an activation failure, or vice versa.

BEGIN;

CREATE OR REPLACE FUNCTION public.validate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $function$
declare
  g public.pokemon_set_page_snapshot_generations%rowtype;
  actual_ids uuid[];
  actual_count int;
  collector_count int;
  bad int;
  passed boolean;
  report jsonb;
begin
  select * into g
  from public.pokemon_set_page_snapshot_generations
  where id=p_generation_id
  for update;

  if not found or g.status<>'building' then
    raise exception 'generation % is not building',p_generation_id;
  end if;

  select coalesce(array_agg(set_id order by set_id),'{}'::uuid[]),count(*)
  into actual_ids,actual_count
  from public.pokemon_set_page_snapshot_generation_rows
  where generation_id=p_generation_id;

  select
    count(*) filter(where payload_json?'publicCollectorAppealContractV1'),
    count(*) filter(
      where payload_json is null
         or jsonb_typeof(payload_json)<>'object'
         or (
           payload_json?'publicCollectorAppealContractV1'
           and (
             payload_json#>>'{publicCollectorAppealContractV1,contractVersion}'
               is distinct from g.collector_contract_version
             or
             payload_json#>>'{publicCollectorAppealContractV1,collectorAppeal,modelRunId}'
               is distinct from g.collector_model_run_id::text
           )
         )
    )
  into collector_count,bad
  from public.pokemon_set_page_snapshot_generation_rows
  where generation_id=p_generation_id;

  passed :=
    actual_count=g.expected_set_count
    and actual_ids=g.expected_set_ids
    and collector_count=g.expected_collector_row_count
    and bad=0;

  report := jsonb_build_object(
    'passed',passed,
    'expectedSetCount',g.expected_set_count,
    'actualSetCount',actual_count,
    'expectedCollectorRows',g.expected_collector_row_count,
    'actualCollectorRows',collector_count,
    'invalidRows',bad,
    'collectorModelRunId',g.collector_model_run_id,
    'collectorContractVersion',g.collector_contract_version
  );

  update public.pokemon_set_page_snapshot_generations
  set status=case when passed then 'validated' else 'failed' end,
      completed_set_count=actual_count,
      validation_passed=passed,
      validation_json=report,
      validated_at=timezone('utc',now())
  where id=p_generation_id;

  return report;
end
$function$;

CREATE OR REPLACE FUNCTION public.activate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '180s'
AS $function$
declare
  g public.pokemon_set_page_snapshot_generations%rowtype;
  prior uuid;
  n int;
  missing_live_count int;
begin
  select * into g
  from public.pokemon_set_page_snapshot_generations
  where id=p_generation_id
  for update;

  if not found
     or g.status not in ('validated','published')
     or not g.validation_passed
     or coalesce((g.validation_json->>'passed')::boolean,false)=false
  then
    raise exception 'generation % is not validated', p_generation_id;
  end if;

  select generation_id into prior
  from public.pokemon_set_page_snapshot_current_generation
  where scope='pokemon'
  for update;

  select count(*) into n
  from public.pokemon_set_page_snapshot_generation_rows
  where generation_id=p_generation_id;

  if n<>g.expected_set_count then
    raise exception 'generation % became incomplete', p_generation_id;
  end if;

  select count(*) into missing_live_count
  from public.pokemon_set_page_snapshot_latest live
  where live.set_id is not null
    and not exists (
      select 1
      from public.pokemon_set_page_snapshot_generation_rows candidate
      where candidate.generation_id=p_generation_id
        and candidate.set_id=live.set_id
    );

  if missing_live_count > 0 then
    raise exception
      'generation % omits % currently live set page(s); refusing destructive activation',
      p_generation_id, missing_live_count;
  end if;

  delete from public.pokemon_set_page_snapshot_latest
  where set_id is not null;

  insert into public.pokemon_set_page_snapshot_latest
  select set_id,set_identity_json,title_card_json,rip_summary_json,market_summary_json,
         risk_summary_json,concentration_json,desirability_summary_json,
         set_intelligence_json,payload_json,as_of,source_updated_at,created_at,updated_at,
         rip_bootstrap_json,rip_simulation_evidence_json,rip_advanced_json
  from public.pokemon_set_page_snapshot_generation_rows
  where generation_id=p_generation_id;

  insert into public.pokemon_set_page_snapshot_current_generation(scope,generation_id,activated_at)
  values('pokemon',p_generation_id,timezone('utc',now()))
  on conflict(scope) do update
  set generation_id=excluded.generation_id,
      activated_at=excluded.activated_at;

  update public.pokemon_set_page_snapshot_generations
  set status='published',
      previous_generation_id=case when prior is distinct from p_generation_id then prior else previous_generation_id end,
      published_at=coalesce(published_at,timezone('utc',now()))
  where id=p_generation_id;

  return p_generation_id;
end
$function$;

CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard_with_set_pages(
  p_snapshot jsonb,
  p_rows jsonb,
  p_latest jsonb,
  p_generation_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '240s'
AS $function$
declare
  v_publication_id uuid;
  v_generation_id uuid;
begin
  v_publication_id :=
    public.publish_pokemon_public_rip_leaderboard(
      p_snapshot,
      p_rows,
      p_latest
    );

  v_generation_id :=
    public.activate_pokemon_set_page_snapshot_generation(
      p_generation_id
    );

  if v_generation_id is distinct from p_generation_id then
    raise exception
      'set-page activation returned unexpected generation %',
      v_generation_id;
  end if;

  return v_publication_id;
end
$function$;

COMMIT;
