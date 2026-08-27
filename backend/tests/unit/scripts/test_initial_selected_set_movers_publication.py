import json

from backend.scripts.build_pokemon_explore_set_value_snapshot import (
    _attach_initial_selected_set_movers,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, row):
        self.row = row
        self.select_fields = ""

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return _Result([self.row])


class _Client:
    def __init__(self, row):
        self.query = _Query(row)

    def table(self, name):
        assert name == "pokemon_set_cards_snapshot_latest"
        return self.query


def test_initial_selected_movers_belong_to_first_set_and_use_narrow_canonical_7d_path():
    canonical = [
        {
            "canonicalCardId": f"card-{index}",
            "cardVariantId": f"variant-{index}",
            "conditionId": "nm",
            "setId": "set-one",
            "name": f"Card {index}",
            "marketPrice": 20 + index,
            "changeAmount": -index,
            "changePercent": -index / 2,
            "window": "7D",
            "startDate": "2026-08-20",
            "endDate": "2026-08-27",
            "priceHistory": [["2026-08-20", 1]],
            "desirability": {"score": 99},
        }
        for index in range(1, 13)
    ]
    client = _Client({
        "items": canonical,
        "snapshot_meta": {"marketAsOfDate": "2026-08-27"},
    })
    row = {
        "payload_json": {"sets": [{"setId": "set-one"}, {"setId": "set-two"}]},
        "source_generation_fingerprint": "before",
        "payload_size_bytes": 0,
    }

    _attach_initial_selected_set_movers(client, row)

    contract = row["payload_json"]["initialSelectedSetMovers"]
    assert contract["setId"] == row["payload_json"]["sets"][0]["setId"]
    assert contract["window"] == "7D"
    assert [item["canonicalCardId"] for item in contract["items"]] == [
        item["canonicalCardId"] for item in canonical[:10]
    ]
    assert "cards_json" not in client.query.select_fields
    assert "canonicalMarketMoversByWindow->7D->all" in client.query.select_fields
    assert "priceHistory" not in contract["items"][0]
    assert "desirability" not in contract["items"][0]
    assert row["payload_size_bytes"] == len(json.dumps(row["payload_json"], separators=(",", ":")).encode())
