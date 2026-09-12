from types import SimpleNamespace

import pytest

from backend.db.services.market_explorer_options_snapshot import (
    MarketExplorerOptionsUnavailable, PUBLISH_RPC, READ_RPC,
    publish_market_explorer_options_snapshot, read_market_explorer_options_snapshot,
)


PAYLOAD = {
    "eras": [], "sets": [], "cardRarities": {"rarities": []},
    "cardSegments": {"segments": []}, "pokemon": [],
    "sealedProductFamilies": {"segments": []}, "priceSegments": {},
    "releaseAgeCohorts": [], "compatibility": {"cardRaritySetIds": {}},
}


class Client:
    def __init__(self, current=None, fail_publish=False):
        self.current, self.fail_publish, self.calls = current, fail_publish, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        def execute():
            if name == READ_RPC:
                return SimpleNamespace(data=[self.current] if self.current else [])
            if self.fail_publish:
                raise RuntimeError("publish failed")
            return SimpleNamespace(data=[{"snapshot_id": 7, "payload_bytes": 123}])
        return SimpleNamespace(execute=execute)


def test_reader_is_one_rpc_and_missing_snapshot_is_typed():
    client = Client()
    with pytest.raises(MarketExplorerOptionsUnavailable):
        read_market_explorer_options_snapshot(client)
    assert [name for name, _ in client.calls] == [READ_RPC]


def test_reader_returns_valid_payload_and_snapshot_metadata():
    row = {"payload_json": PAYLOAD, "snapshot_id": 3, "schema_version": "v1", "payload_bytes": 20}
    result = read_market_explorer_options_snapshot(Client(row))
    assert result["cardRarities"] == {"rarities": []}
    assert result["snapshot"]["id"] == 3


def test_publish_failure_cannot_replace_previous_good_snapshot():
    row = {"payload_json": PAYLOAD, "snapshot_id": 3, "schema_version": "v1",
           "payload_bytes": 20, "source_fingerprint": "old"}
    client = Client(row, fail_publish=True)
    with pytest.raises(RuntimeError, match="publish failed"):
        publish_market_explorer_options_snapshot(client, PAYLOAD)
    assert client.current is row
    assert [name for name, _ in client.calls] == [READ_RPC, PUBLISH_RPC]
