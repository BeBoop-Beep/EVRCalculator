from types import SimpleNamespace

import pytest

from backend.db.services.pokemon_market_rollout_preparation import (
    AUTHORITY_SYNC_RPC,
    sync_market_root_authority,
)


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        payload = self.payload

        class _RPC:
            def execute(self):
                return SimpleNamespace(data=payload)

        return _RPC()


def _payload(**overrides):
    value = {
        "status": "complete",
        "marketDate": "2026-09-14",
        "rowsActivated": 0,
        "structuralRootCount": 155,
        "activeAuthorityRootCount": 155,
        "missingStructuralRootCount": 0,
        "structuralFingerprint": "f61c619e1f346924b55eb288cffaff6c3802e1c2519cb42426e10b1d8e3b24eb",
    }
    value.update(overrides)
    return value


def test_zero_missing_structural_roots_is_success_not_falsy_failure():
    client = _Client(_payload(missingStructuralRootCount=0))
    result = sync_market_root_authority(client, "2026-09-14")

    assert result["missingStructuralRootCount"] == 0
    assert client.calls == [
        (AUTHORITY_SYNC_RPC, {"p_market_date": "2026-09-14"}),
    ]


@pytest.mark.parametrize("missing", [None, 1])
def test_missing_or_positive_missing_structural_count_fails_closed(missing):
    client = _Client(_payload(missingStructuralRootCount=missing))

    with pytest.raises(RuntimeError, match="left structural roots missing"):
        sync_market_root_authority(client, "2026-09-14")
