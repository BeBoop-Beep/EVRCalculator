from pathlib import Path

from backend.domain.billing.catalog import build_offer_catalog


ROOT = Path(__file__).parents[5]
LAUNCH = (ROOT / "docs/BILLING_EFFORT5_LAUNCH.md").read_text(encoding="utf-8")
REQUIREMENTS = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")


def test_managed_payments_launch_catalog_has_two_products_and_four_unchanged_offers():
    assert "| Index Plus | `plus_monthly` | $9.99 USD / month |" in LAUNCH
    assert "| Index Plus | `plus_annual` | $79.00 USD / year |" in LAUNCH
    assert "| Index Premium | `premium_monthly` | $24.99 USD / month |" in LAUNCH
    assert "| Index Premium | `premium_annual` | $219.00 USD / year |" in LAUNCH
    assert set(build_offer_catalog({})) == {
        "plus_monthly", "plus_annual", "premium_monthly", "premium_annual"
    }


def test_price_mapping_remains_entitlement_authority_and_portal_switching_is_pending():
    assert "Price-ID-to-offer-key-to-internal-plan" in LAUNCH
    assert "Product identity is audit/catalog data only" in LAUNCH
    assert "PORTAL_CROSS_TIER_SWITCHING_PENDING_FINAL_SANDBOX_POLICY" in LAUNCH
    assert "txcd_10103000" in LAUNCH


def test_sdk_pin_and_managed_payments_api_version_contract_are_documented():
    assert "stripe==15.4.0" in REQUIREMENTS
    effort2 = (ROOT / "docs/BILLING_EFFORT2_STRIPE_BACKEND.md").read_text(encoding="utf-8")
    assert "2026-07-29.dahlia" in effort2
    assert "2025-03-31.basil" in effort2
