from pathlib import Path


SQL = (Path(__file__).parents[4] / "supabase/migrations/20260901000002_billing_effort4_atomic_reliability.sql").read_text().lower()


def test_atomic_billing_rpcs_are_service_only_and_search_path_pinned():
    assert SQL.count("security definer") == 3
    assert SQL.count("set search_path = pg_catalog, public") == 3
    for signature in ["claim_billing_webhook_event(text, text, timestamptz)",
                      "persist_billing_subscription_and_recompute(jsonb)",
                      "mark_missing_billing_subscriptions_and_recompute(uuid, text[])"]:
        assert f"revoke all on function public.{signature} from public, anon, authenticated" in SQL
        assert f"grant execute on function public.{signature} to service_role" in SQL


def test_subscription_persistence_and_entitlement_recompute_share_transaction():
    assert "on conflict (provider, provider_subscription_id) do update" in SQL
    assert "perform public.recompute_effective_index_plan(persisted.user_id)" in SQL
    assert "on conflict (provider, provider_event_id) do update" in SQL
