from argparse import Namespace

from backend.db.services.billing_service import BillingService
from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.errors import BillingProviderError, StripeCustomerMissing
from backend.domain.billing.reconciliation import BillingReconciler
from backend.scripts.billing_doctor import diagnose
from backend.scripts.reconcile_stripe_billing import run


OFFERS = {"plus": CommercialOffer("plus", "plus", "month", True, "price_plus"),
          "premium": CommercialOffer("premium", "premium", "month", True, "price_premium")}


def subscription(sid="sub_1", price="price_plus", status="active", items=1):
    return {"id": sid, "customer": "cus_1", "status": status,
            "items": {"data": [{"price": {"id": price, "product": "prod"}} for _ in range(items)]}}


class Repo:
    def __init__(self):
        self.customer = {"id": "bc_1", "user_id": "u1", "provider_customer_id": "cus_1"}
        self.rows = []
        self.plan = None
        self.manual = None
        self.mutations = 0
    def list_customers(self): return [self.customer]
    def find_subscriptions(self, uid): return list(self.rows)
    def manual_plan(self, uid): return self.manual
    def get_profile(self, uid): return {"id": uid, "index_plan": self.plan}
    def persist_subscription_and_recompute(self, row):
        self.mutations += 1
        self.rows = [old for old in self.rows if old["provider_subscription_id"] != row["provider_subscription_id"]] + [row]
        eligible = [x.get("plan") for x in self.rows if x.get("status") in {"trialing", "active", "past_due"} and x.get("commercial_mapping_status") == "mapped"]
        self.plan = "premium" if "premium" in eligible or self.manual == "premium" else "plus" if "plus" in eligible or self.manual == "plus" else None
        return row
    def mark_missing_subscriptions_and_recompute(self, uid, current):
        changed = 0
        for row in self.rows:
            if row["provider_subscription_id"] not in current and row["status"] != "canceled": row["status"]="canceled"; changed += 1
        self.mutations += 1
        eligible = [x.get("plan") for x in self.rows if x.get("status") in {"trialing", "active", "past_due"}]
        self.plan = "premium" if "premium" in eligible or self.manual == "premium" else "plus" if "plus" in eligible or self.manual == "plus" else None
        return changed
    def webhook_diagnostics(self): return {"failed": [], "failedCount": 0, "staleProcessingCount": 0}


class Provider:
    def __init__(self, remote=None): self.remote = remote or []; self.error = None; self.list_calls = 0
    def retrieve_customer(self, cid):
        if self.error: raise self.error
        return {"id": cid}
    def list_customer_subscriptions(self, cid): self.list_calls += 1; return list(self.remote)


def setup(remote=None):
    repo, provider = Repo(), Provider(remote)
    return BillingService(repo, provider, OFFERS), repo, provider


def test_dry_run_detects_missed_webhook_without_mutating():
    svc, repo, provider = setup([subscription(price="price_premium")])
    report = BillingReconciler(svc).reconcile_all(dry_run=True).as_dict()
    assert report["categories"] == {"INDEX_PLAN_MISMATCH": 1, "LOCAL_SUBSCRIPTION_MISSING": 1}
    assert repo.mutations == 0 and provider.list_calls == 1


def test_repair_recovers_upgrade_and_later_missed_cancellation():
    svc, repo, provider = setup([subscription(price="price_premium")])
    first = BillingReconciler(svc).reconcile_all(dry_run=False).as_dict()
    assert repo.plan == "premium" and first["repairs"] == 1
    provider.remote = []
    second = BillingReconciler(svc).reconcile_all(dry_run=False).as_dict()
    assert repo.plan is None and second["categories"]["LOCAL_SUBSCRIPTION_STALE"] == 1


def test_repair_preserves_manual_entitlement_and_corrects_wrong_plan():
    svc, repo, _ = setup([subscription(price="price_plus")])
    repo.manual = "premium"; repo.plan = "premium"
    repo.rows = [{"provider_subscription_id":"sub_1","plan":"premium","status":"active","commercial_mapping_status":"mapped"}]
    BillingReconciler(svc).reconcile_all(dry_run=False)
    assert repo.rows[0]["plan"] == "plus" and repo.plan == "premium"


def test_anomalies_and_provider_failures_are_classified_and_bulk_continues():
    svc, repo, provider = setup([subscription("a", "price_plus"), subscription("b", "price_premium", items=2), subscription("c", "unknown")])
    report = BillingReconciler(svc).reconcile_all(dry_run=True).as_dict()
    assert report["categories"]["UNSUPPORTED_SUBSCRIPTION_SHAPE"] == 1
    assert report["categories"]["UNMAPPED_PRICE"] == 1
    provider.error = StripeCustomerMissing()
    assert BillingReconciler(svc).reconcile_all().as_dict()["categories"]["STRIPE_CUSTOMER_MISSING"] == 1
    provider.error = BillingProviderError()
    assert BillingReconciler(svc).reconcile_all().as_dict()["categories"]["PROVIDER_ERROR"] == 1


def test_cli_is_dry_by_default_and_doctor_never_returns_secret_values():
    svc, repo, _ = setup([subscription()])
    result = run(Namespace(user_id="u1", customer_id=None, subscription_id=None, all=False, repair=False), svc)
    assert result["repairs"] == 0 and repo.mutations == 0
    env = {"STRIPE_SECRET_KEY":"sk_sensitive", "STRIPE_WEBHOOK_SECRET":"whsec_sensitive"}
    output = str(diagnose(repo, env))
    assert "sk_sensitive" not in output and "whsec_sensitive" not in output
