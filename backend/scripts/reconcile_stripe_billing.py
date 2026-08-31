"""Dry-by-default Stripe billing reconciliation operator command."""

from __future__ import annotations

import argparse
import json

from backend.db.services.billing_service import BillingService
from backend.domain.billing.reconciliation import BillingReconciler, ReconciliationReport


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    scope = result.add_mutually_exclusive_group()
    scope.add_argument("--user-id")
    scope.add_argument("--customer-id")
    scope.add_argument("--subscription-id")
    result.add_argument("--all", action="store_true", help="Explicitly select every mapped Stripe account")
    result.add_argument("--repair", action="store_true", help="Apply repairs; otherwise the command is read-only")
    return result


def run(args, service=None):
    service = service or BillingService()
    if args.subscription_id:
        if not args.repair:
            raise SystemExit("--subscription-id requires --repair; use customer dry-run for comparison")
        row = service.reconcile_subscription(args.subscription_id)
        return {"accountsScanned": 1, "repairs": 1, "subscriptionId": row["provider_subscription_id"]}
    customers = service.repository.list_customers()
    if args.user_id:
        customers = [item for item in customers if item.get("user_id") == args.user_id]
    elif args.customer_id:
        customers = [item for item in customers if item.get("provider_customer_id") == args.customer_id]
    elif not args.all:
        raise SystemExit("Choose --user-id, --customer-id, --subscription-id, or --all")
    return BillingReconciler(service).reconcile_all(dry_run=not args.repair, customers=customers).as_dict()


def main():
    result = run(parser().parse_args())
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
