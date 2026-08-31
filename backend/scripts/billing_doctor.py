"""Read-only billing production-readiness diagnostics; never prints secrets."""

from __future__ import annotations

import json
import os

from backend.db.repositories.billing_repository import BillingRepository
from backend.domain.billing.catalog import build_offer_catalog


def diagnose(repository=None, environ=None):
    source = os.environ if environ is None else environ
    offers = build_offer_catalog(source)
    result = {
        "configuration": {
            "stripeSecretConfigured": bool((source.get("STRIPE_SECRET_KEY") or "").strip()),
            "webhookSecretConfigured": bool((source.get("STRIPE_WEBHOOK_SECRET") or "").strip()),
            "frontendBaseUrlConfigured": bool((source.get("FRONTEND_BASE_URL") or "").strip()),
            "configuredOfferCount": sum(offer.purchasable for offer in offers.values()),
        },
        "schemaReachable": False,
        "webhooks": {"failed": [], "failedCount": 0, "staleProcessingCount": 0},
        "errors": [],
    }
    try:
        repo = repository or BillingRepository()
        repo.list_customers()
        result["webhooks"] = repo.webhook_diagnostics()
        result["schemaReachable"] = True
    except Exception as exc:
        result["errors"].append({"code": "BILLING_SCHEMA_UNREACHABLE", "type": type(exc).__name__})
    return result


def main():
    result = diagnose()
    print(json.dumps(result, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
