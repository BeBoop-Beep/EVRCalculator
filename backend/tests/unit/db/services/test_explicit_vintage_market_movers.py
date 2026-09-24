from __future__ import annotations

from datetime import date, timedelta

from backend.db.services import pokemon_public_snapshot_service as service


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.eq_filters = []
        self.in_filters = []
        self.gte_filter = None
        self.lte_filter = None
        self.limit_value = None
        self.desc = False

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, set(values)))
        return self

    def gte(self, field, value):
        self.gte_filter = (field, value)
        return self

    def lte(self, field, value):
        self.lte_filter = (field, value)
        return self

    def order(self, _field, desc=False):
        self.desc = desc
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        rows = [dict(row) for row in self.client.rows.get(self.table_name, [])]
        for field, value in self.eq_filters:
            rows = [row for row in rows if row.get(field) == value]
        for field, values in self.in_filters:
            rows = [row for row in rows if row.get(field) in values]
        if self.gte_filter:
            field, value = self.gte_filter
            rows = [row for row in rows if str(row.get(field) or "") >= str(value)]
        if self.lte_filter:
            field, value = self.lte_filter
            rows = [row for row in rows if str(row.get(field) or "") <= str(value)]
        rows.sort(key=lambda row: str(row.get("market_date") or ""), reverse=self.desc)
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return Result(rows)


class RpcCall:
    def __init__(self, client, name, args):
        self.client = client
        self.name = name
        self.args = dict(args)

    def execute(self):
        self.client.rpc_calls.append((self.name, dict(self.args)))
        date_key = self.args["p_market_date"]
        return Result(self.client.scoped_rows.get(date_key, []))


class Client:
    def __init__(self):
        latest = date(2026, 9, 22)
        self.rows = {
            "pokemon_market_root_set_value_daily_history_v2_shadow": [
                {
                    "set_id": SET_ID,
                    "market_scope": "unlimited",
                    "market_date": (latest - timedelta(days=offset)).isoformat(),
                    "certified_on_date": True,
                }
                for offset in range(7, -1, -1)
            ],
            "pokemon_market_explorer_card_current_metadata": [{
                "card_variant_id": "unlimited-now",
                "canonical_card_id": "card-a",
                "set_id": SET_ID,
                "card_name": "Vintage Card",
                "card_number": "1",
                "rarity": "Rare",
                "edition": "unlimited",
                "printing_type": "holo",
                "special_type": "",
                "image_url": "https://example.test/card.jpg",
            }],
        }
        self.scoped_rows = {
            "2026-09-22": [{
                "canonical_card_id": "card-a",
                "set_id": SET_ID,
                "market_date": "2026-09-22",
                "market_price": 120,
                "card_variant_id": "unlimited-now",
                "source": "tcgplayer",
                "captured_at": "2026-09-22",
            }],
            "2026-09-15": [{
                "canonical_card_id": "card-a",
                "set_id": SET_ID,
                "market_date": "2026-09-15",
                "market_price": 100,
                "card_variant_id": "unlimited-old",
                "source": "tcgplayer",
                "captured_at": "2026-09-15",
            }],
        }
        self.rpc_calls = []

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, args):
        return RpcCall(self, name, args)


SET_ID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"


def test_market_tab_movers_use_only_requested_explicit_edition_scope(monkeypatch):
    client = Client()
    monkeypatch.setattr(service, "service_read_client", client)

    payload = service.get_pokemon_set_market_movers_snapshot_payload(
        SET_ID,
        window="7D",
        limit=10,
        movement="all",
        value_scope="unlimited",
    )

    assert payload["marketScope"] == "unlimited"
    assert payload["latestMarketDate"] == "2026-09-22"
    assert [row["canonicalCardId"] for row in payload["marketMovers"]["all"]] == ["card-a"]
    mover = payload["marketMovers"]["all"][0]
    assert mover["cardVariantId"] == "unlimited-now"
    assert mover["changeAmount"] == 20
    assert mover["changePercent"] == 20
    assert payload["meta"]["snapshot"]["source"] == "explicit_edition_scope_live_read"

    assert len(client.rpc_calls) == 2
    assert {name for name, _ in client.rpc_calls} == {service.SCOPED_SET_CONSTITUENT_RPC}
    assert {args["p_market_scope"] for _, args in client.rpc_calls} == {"unlimited"}
    assert {args["p_market_date"] for _, args in client.rpc_calls} == {"2026-09-15", "2026-09-22"}
