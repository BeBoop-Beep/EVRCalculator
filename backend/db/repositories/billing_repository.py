"""Persistence boundary for server-owned billing records."""

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

