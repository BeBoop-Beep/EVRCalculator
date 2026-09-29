from __future__ import annotations

import pytest

from backend.pricing_pipeline.active_supply_credentials import (
    ActiveSupplyCredentialUnavailable, load_active_supply_credentials,
)


def test_dedicated_seller_key_is_stable_and_redacted(tmp_path):
    key = "dedicated-active-supply-secret-000000000000"
    first = load_active_supply_credentials({"ACTIVE_SUPPLY_SELLER_HASH_KEY": key}, repo_root=tmp_path)
    second = load_active_supply_credentials({"ACTIVE_SUPPLY_SELLER_HASH_KEY": key}, repo_root=tmp_path)
    assert first.fingerprint == second.fingerprint
    assert key not in repr(first)
    assert first.source == "process-environment"


def test_seller_key_never_falls_back_to_provider_key(tmp_path):
    with pytest.raises(ActiveSupplyCredentialUnavailable):
        load_active_supply_credentials({"PKMNPRICES_API_KEY": "x" * 40}, repo_root=tmp_path)


def test_short_seller_key_fails_closed(tmp_path):
    with pytest.raises(ActiveSupplyCredentialUnavailable, match="at least 32"):
        load_active_supply_credentials({"ACTIVE_SUPPLY_SELLER_HASH_KEY": "short"}, repo_root=tmp_path)
