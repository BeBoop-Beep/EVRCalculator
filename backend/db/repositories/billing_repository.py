"""Persistence boundary for server-owned billing records."""

from datetime import datetime, timedelta, timezone

from backend.db.clients.supabase_client import supabase


class BillingRepository:
    def find_customer(self, user_id: str, provider: str = "stripe") -> dict | None:
        response = (supabase.table("billing_customers").select("*")
                    .eq("user_id", user_id).eq("provider", provider).limit(1).execute())
        return (response.data or [None])[0]

    def find_subscriptions(self, user_id: str) -> list[dict]:
        response = (supabase.table("billing_subscriptions").select("*")
                    .eq("user_id", user_id).execute())
        return list(response.data or [])

    def list_customers(self) -> list[dict]:
        response = supabase.table("billing_customers").select("*").eq("provider", "stripe").execute()
        return list(response.data or [])

    def find_customer_by_provider_id(self, provider_customer_id: str, provider: str = "stripe") -> dict | None:
        response = (supabase.table("billing_customers").select("*")
                    .eq("provider", provider).eq("provider_customer_id", provider_customer_id).limit(1).execute())
        return (response.data or [None])[0]

    def create_customer_mapping(self, *, user_id: str, provider_customer_id: str, provider: str = "stripe") -> dict:
        try:
            response = supabase.table("billing_customers").insert({
                "user_id": user_id, "provider": provider, "provider_customer_id": provider_customer_id,
            }).execute()
            return response.data[0]
        except Exception:
            existing = self.find_customer(user_id, provider)
            if existing and existing.get("provider_customer_id") == provider_customer_id:
                return existing
            raise

    def upsert_subscription(self, row: dict) -> dict:
        response = supabase.table("billing_subscriptions").upsert(
            row, on_conflict="provider,provider_subscription_id").execute()
        return response.data[0]

    def persist_subscription_and_recompute(self, row: dict) -> dict:
        response = supabase.rpc("persist_billing_subscription_and_recompute", {"p_subscription": row}).execute()
        return response.data

    def mark_missing_subscriptions_and_recompute(self, user_id: str, current_ids: list[str]) -> int:
        response = supabase.rpc("mark_missing_billing_subscriptions_and_recompute", {
            "p_user_id": user_id, "p_current_provider_subscription_ids": current_ids,
        }).execute()
        return int(response.data or 0)

    def manual_plan(self, user_id: str) -> str | None:
        response = (supabase.table("billing_manual_entitlements").select("plan")
                    .eq("user_id", user_id).limit(1).execute())
        return ((response.data or [{}])[0]).get("plan")

    def recompute_effective_plan(self, user_id: str) -> str | None:
        return supabase.rpc("recompute_effective_index_plan", {"target_user_id": user_id}).execute().data

    def get_profile(self, user_id: str) -> dict | None:
        response = supabase.table("users").select("id,email,index_plan").eq("id", user_id).limit(1).execute()
        return (response.data or [None])[0]

    def claim_webhook_event(self, *, event_id: str, event_type: str, stale_after_seconds: int = 300) -> str:
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        response = supabase.rpc("claim_billing_webhook_event", {
            "p_provider_event_id": event_id,
            "p_event_type": event_type,
            "p_stale_before": stale_before.isoformat(),
        }).execute()
        return response.data

    def webhook_diagnostics(self, *, stale_after_seconds: int = 300) -> dict:
        stale_before = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
        failed = (supabase.table("billing_webhook_events").select(
            "provider_event_id,event_type,processing_attempts,error_code,error_summary,updated_at"
        ).eq("processing_status", "failed").order("updated_at", desc=True).limit(100).execute())
        stale = (supabase.table("billing_webhook_events").select("provider_event_id", count="exact")
                 .eq("processing_status", "processing").lt("processing_started_at", stale_before).execute())
        return {"failed": list(failed.data or []), "failedCount": failed.count or len(failed.data or []),
                "staleProcessingCount": stale.count or 0}

    def finish_webhook_event(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("billing_webhook_events").update({"processing_status": "processed",
            "processed_at": now, "updated_at": now}).eq("provider", "stripe").eq("provider_event_id", event_id).execute()

    def fail_webhook_event(self, event_id: str, code: str, summary: str) -> None:
        supabase.table("billing_webhook_events").update({"processing_status": "failed",
            "error_code": code, "error_summary": summary[:500], "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("provider", "stripe").eq("provider_event_id", event_id).execute()
