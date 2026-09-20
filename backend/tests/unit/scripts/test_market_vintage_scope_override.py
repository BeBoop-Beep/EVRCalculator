from types import SimpleNamespace

from backend.scripts import build_pokemon_explore_set_value_snapshot as builder


class _TableQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self._range = None
        self._lte = None
        self._eq = {}
        self._ids = None

    def select(self, *_args):
        return self

    def in_(self, column, values):
        if column == "set_id":
            self._ids = {str(value) for value in values}
        return self

    def eq(self, column, value):
        self._eq[column] = value
        return self

    def lte(self, column, value):
        self._lte = (column, str(value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = list(self.rows)
        if self._ids is not None:
            rows = [row for row in rows if str(row.get("set_id")) in self._ids]
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        if self._lte is not None:
            column, value = self._lte
            rows = [row for row in rows if str(row.get(column) or "") <= value]
        rows.sort(key=lambda row: (str(row.get("snapshot_date") or ""), str(row.get("set_id") or "")))
        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]
        return SimpleNamespace(data=rows)


class _Client:
    def __init__(self, *, profiles=None, standard_history=None, scoped_history=None):
        self.profiles = list(profiles or [])
        self.standard_history = list(standard_history or [])
        self.scoped_history = list(scoped_history or [])

    def table(self, name):
        if name == builder.EDITION_PROFILE_TABLE:
            return _TableQuery(self.profiles)
        if name == "pokemon_set_value_daily_history":
            return _TableQuery(self.standard_history)
        raise AssertionError(name)

    def rpc(self, name, params):
        assert name == builder.CANONICAL_HISTORY_RPC
        ids = {str(value) for value in params["p_root_set_ids"]}
        end = str(params["p_end_date"])
        rows = [
            row for row in self.scoped_history
            if str(row.get("set_id")) in ids and str(row.get("market_date")) <= end
        ]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))


def test_scope_overrides_apply_only_to_registered_vintage_profiles():
    client = _Client(profiles=[
        {"set_id": "neo", "profile": "edition_split"},
        {"set_id": "base", "profile": "base_three_printings"},
        {"set_id": "modern", "profile": "standard"},
    ])

    result = builder._load_market_value_scope_overrides(
        client, ["neo", "base", "modern"]
    )

    assert result == {"neo": "unlimited", "base": "unlimited"}


def test_scoped_history_keeps_only_requested_certified_scope():
    client = _Client(scoped_history=[
        {"set_id": "neo", "market_scope": "unlimited", "market_date": "2026-09-19", "set_value": 13175.75, "certified_on_date": True},
        {"set_id": "neo", "market_scope": "unlimited", "market_date": "2026-09-20", "set_value": 13225.36, "certified_on_date": False},
        {"set_id": "neo", "market_scope": "first_edition", "market_date": "2026-09-19", "set_value": 16960.28, "certified_on_date": True},
    ])

    result = builder._load_scoped_certified_histories(
        client, ["neo"], through_date="2026-09-20", scope_by_set={"neo": "unlimited"}
    )

    assert result["neo"] == [
        {"set_id": "neo", "snapshot_date": "2026-09-19", "set_value": 13175.75}
    ]


def test_post_cutover_override_replaces_only_vintage_standard_history():
    client = _Client(
        standard_history=[
            {"set_id": "neo", "snapshot_date": "2026-09-19", "set_value": 16035.49, "source": "legacy-mixed", "value_scope": "standard"},
            {"set_id": "modern", "snapshot_date": "2026-09-19", "set_value": 500.0, "source": "canonical", "value_scope": "standard"},
            {"set_id": "modern", "snapshot_date": "2026-09-20", "set_value": 510.0, "source": "canonical", "value_scope": "standard"},
        ],
        scoped_history=[
            {"set_id": "neo", "market_scope": "unlimited", "market_date": "2026-09-18", "set_value": 13158.69, "certified_on_date": True},
            {"set_id": "neo", "market_scope": "unlimited", "market_date": "2026-09-19", "set_value": 13175.75, "certified_on_date": True},
            {"set_id": "neo", "market_scope": "unlimited", "market_date": "2026-09-20", "set_value": 13225.36, "certified_on_date": False},
        ],
    )

    result = builder._load_canonical_histories(
        client,
        ["neo", "modern"],
        through_date="2026-09-20",
        market_scope_overrides={"neo": "unlimited"},
    )

    assert [row["set_value"] for row in result["neo"]] == [13158.69, 13175.75]
    assert [row["snapshot_date"] for row in result["neo"]] == ["2026-09-18", "2026-09-19"]
    assert [row["set_value"] for row in result["modern"]] == [500.0, 510.0]
