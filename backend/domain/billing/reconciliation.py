"""Authoritative Stripe-to-local drift detection and repair."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from backend.domain.billing.errors import BillingProviderError, StripeCustomerMissing
from backend.domain.billing.policy import effective_plan, has_duplicate_active_subscriptions


DRIFT_CATEGORIES = frozenset({
    "MATCH", "LOCAL_SUBSCRIPTION_MISSING", "LOCAL_SUBSCRIPTION_STALE",
    "LOCAL_STATUS_MISMATCH", "LOCAL_PLAN_MISMATCH", "INDEX_PLAN_MISMATCH",
    "STRIPE_CUSTOMER_MISSING", "UNMAPPED_PRICE", "MULTIPLE_ACTIVE_SUBSCRIPTIONS",
    "UNSUPPORTED_SUBSCRIPTION_SHAPE", "MANUAL_ENTITLEMENT_ONLY", "PROVIDER_ERROR",
})


@dataclass
class ReconciliationReport:
    accounts_scanned: int = 0
    repairs: int = 0
    entitlement_changes: int = 0
    categories: Counter = field(default_factory=Counter)
    errors: list[dict] = field(default_factory=list)

    def record(self, *categories):
        for category in set(categories) or {"MATCH"}:
            self.categories[category] += 1

    def as_dict(self):
        return {
            "accountsScanned": self.accounts_scanned,
            "matches": self.categories["MATCH"],
            "repairs": self.repairs,
            "entitlementChanges": self.entitlement_changes,
            "categories": dict(sorted(self.categories.items())),
            "errors": self.errors,
        }


class BillingReconciler:
    def __init__(self, service):
        self.service = service
        self.repository = service.repository
        self.provider = service.provider

    def reconcile_customer(self, customer, *, dry_run=True, report=None):
        report = report or ReconciliationReport()
        report.accounts_scanned += 1
        user_id, customer_id = customer["user_id"], customer["provider_customer_id"]
        local = self.repository.find_subscriptions(user_id)
        manual = self.repository.manual_plan(user_id)
        profile = self.repository.get_profile(user_id) or {}
        before = profile.get("index_plan")
        try:
            self.provider.retrieve_customer(customer_id)
            remote_objects = self.provider.list_customer_subscriptions(customer_id)
            remote = [self.service.subscription_row(customer, item) for item in remote_objects]
        except StripeCustomerMissing:
            report.record("STRIPE_CUSTOMER_MISSING")
            report.errors.append({"userId": user_id, "category": "STRIPE_CUSTOMER_MISSING"})
            return report
        except BillingProviderError:
            report.record("PROVIDER_ERROR")
            report.errors.append({"userId": user_id, "category": "PROVIDER_ERROR"})
            return report

        categories = []
        local_by_id = {row["provider_subscription_id"]: row for row in local}
        remote_by_id = {row["provider_subscription_id"]: row for row in remote}
        for sid, row in remote_by_id.items():
            old = local_by_id.get(sid)
            if old is None:
                categories.append("LOCAL_SUBSCRIPTION_MISSING")
            else:
                if old.get("status") != row.get("status"): categories.append("LOCAL_STATUS_MISMATCH")
                if old.get("plan") != row.get("plan"): categories.append("LOCAL_PLAN_MISMATCH")
            if row["commercial_mapping_status"] == "unmapped_price": categories.append("UNMAPPED_PRICE")
            if row["commercial_mapping_status"] == "unsupported_shape": categories.append("UNSUPPORTED_SUBSCRIPTION_SHAPE")
        if set(local_by_id) - set(remote_by_id): categories.append("LOCAL_SUBSCRIPTION_STALE")
        if has_duplicate_active_subscriptions(remote): categories.append("MULTIPLE_ACTIVE_SUBSCRIPTIONS")
        expected = effective_plan(remote, manual)
        if before != expected: categories.append("INDEX_PLAN_MISMATCH")
        if manual and not remote: categories.append("MANUAL_ENTITLEMENT_ONLY")
        report.record(*(categories or ["MATCH"]))

        if not dry_run and categories:
            for subscription in remote_objects:
                self.service.reconcile_subscription_snapshot(customer, subscription)
            self.repository.mark_missing_subscriptions_and_recompute(user_id, list(remote_by_id))
            report.repairs += 1
            after = (self.repository.get_profile(user_id) or {}).get("index_plan")
            if before != after: report.entitlement_changes += 1
        return report

    def reconcile_all(self, *, dry_run=True, customers=None):
        report = ReconciliationReport()
        for customer in customers if customers is not None else self.repository.list_customers():
            try:
                self.reconcile_customer(customer, dry_run=dry_run, report=report)
            except Exception as exc:
                report.record("PROVIDER_ERROR")
                report.errors.append({"userId": customer.get("user_id"), "category": "PROVIDER_ERROR", "error": type(exc).__name__})
        return report
