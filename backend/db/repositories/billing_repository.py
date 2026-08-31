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
        now = datetime.now(timezone.utc)
        try:
            supabase.table("billing_webhook_events").insert({
                "provider": "stripe", "provider_event_id": event_id, "event_type": event_type,
                "processing_status": "processing", "processing_attempts": 1,
                "processing_started_at": now.isoformat(), "updated_at": now.isoformat(),
            }).execute()
            return "claimed"
        except Exception:
            response = (supabase.table("billing_webhook_events").select("*")
                        .eq("provider", "stripe").eq("provider_event_id", event_id).limit(1).execute())
            row = (response.data or [None])[0]
            if not row: raise
            if row.get("processing_status") == "processed": return "duplicate"
            started = row.get("processing_started_at")
            stale = not started or datetime.fromisoformat(started.replace("Z", "+00:00")) < now - timedelta(seconds=stale_after_seconds)
            if row.get("processing_status") == "failed" or stale:
                supabase.table("billing_webhook_events").update({
                    "processing_status": "processing", "processing_started_at": now.isoformat(),
                    "processing_attempts": int(row.get("processing_attempts") or 0) + 1,
                    "updated_at": now.isoformat(), "error_code": None, "error_summary": None,
                }).eq("id", row["id"]).execute()
                return "claimed"
            return "busy"

    def finish_webhook_event(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("billing_webhook_events").update({"processing_status": "processed",
            "processed_at": now, "updated_at": now}).eq("provider", "stripe").eq("provider_event_id", event_id).execute()

    def fail_webhook_event(self, event_id: str, code: str, summary: str) -> None:
        supabase.table("billing_webhook_events").update({"processing_status": "failed",
            "error_code": code, "error_summary": summary[:500], "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("provider", "stripe").eq("provider_event_id", event_id).execute()
