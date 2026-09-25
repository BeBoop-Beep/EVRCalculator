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
    def __init__(self, *, contract=None, certification=None, standard_history=None, scoped_history=None):
        self.contract = list(contract or [])
        self.certification = list(certification or [])
        self.standard_history = list(standard_history or [])
        self.scoped_history = list(scoped_history or [])
        self.contract_reads = 0

    def table(self, name):
        if name == builder.SCOPE_CONTRACT_VIEW:
            self.contract_reads += 1
            return _TableQuery(self.contract)
        if name == builder.SCOPE_CERTIFICATION_VIEW:
            return _TableQuery(self.certification)
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


def _roots(*ids_names):
    return [{"id": i, "name": n, "canonical_key": n.lower()} for i, n in ids_names]


_LABELS = {"unlimited": "Unlimited", "first_edition": "1st Edition", "shadowless": "Shadowless"}


def _c(set_id, base, scope, ok=True):
    return {
        "set_id": set_id, "base_set_name": base, "market_scope": scope,
        "market_key": f"set:{set_id}" if scope == "standard" else f"set:{set_id}:{scope}",
        "display_label": base if scope == "standard" else f"{base} - {_LABELS[scope]}",
        "publishable_100pct": ok,
    }


def _pt(set_id, scope, day, value, certified=True):
    return {"set_id": set_id, "market_scope": scope, "market_date": day, "set_value": value, "certified_on_date": certified}


def test_no_hidden_default_edition_override_remains():
    assert not hasattr(builder, "DEFAULT_EDITION_SPLIT_DISPLAY_SCOPE")
    assert not hasattr(builder, "_load_market_value_scope_overrides")


def test_roots_expand_from_the_db_scope_contract_with_one_bulk_read():
    client = _Client(contract=[
        _c("modern", "Evolving Skies", "standard"),
        _c("jungle", "Jungle", "unlimited"), _c("jungle", "Jungle", "first_edition"),
        _c("base", "Base", "unlimited", False), _c("base", "Base", "first_edition", False), _c("base", "Base", "shadowless", False),
    ])
    rows = builder._expand_market_scope_rows(
        client, _roots(("modern", "Evolving Skies"), ("jungle", "Jungle"), ("base", "Base"))
    )
    by_key = {row["market_key"]: row for row in rows}
    assert set(by_key) == {
        "set:modern",
        "set:jungle:unlimited", "set:jungle:first_edition",
        "set:base:unlimited", "set:base:first_edition", "set:base:shadowless",
    }
    assert by_key["set:jungle:first_edition"]["name"] == "Jungle - 1st Edition"
    assert by_key["set:base:shadowless"]["name"] == "Base - Shadowless"
    assert not any(row["name"] in {"Jungle", "Base"} for row in rows)
    assert by_key["set:base:first_edition"]["market_current_certification_status"] == "SCOPED_MARKET_INCOMPLETE"
    assert by_key["set:jungle:unlimited"]["market_current_certification_status"] == "CERTIFIED"
    assert client.contract_reads == 1  # one bulk read for <=100 roots, no N+1


def test_unknown_root_is_an_ordinary_standard_market():
    rows = builder._expand_market_scope_rows(_Client(), _roots(("x", "Modern")))
    assert [r["market_key"] for r in rows] == ["set:x"] and rows[0]["name"] == "Modern"


def test_scoped_history_is_keyed_by_market_and_keeps_only_certified_rows():
    client = _Client(scoped_history=[
        _pt("neo", "unlimited", "2026-09-19", 13175.75),
        _pt("neo", "unlimited", "2026-09-20", 13225.36, False),
        _pt("neo", "first_edition", "2026-09-19", 16960.28),
    ])
    markets = [
        {"id": "neo", "market_scope": "unlimited", "market_key": "set:neo:unlimited"},
        {"id": "neo", "market_scope": "first_edition", "market_key": "set:neo:first_edition"},
    ]
    result = builder._load_scoped_certified_histories(client, markets, through_date="2026-09-20")
    assert [r["set_value"] for r in result["set:neo:unlimited"]] == [13175.75]
    assert [r["set_value"] for r in result["set:neo:first_edition"]] == [16960.28]
    assert "set:neo" not in result


def test_source_defect_history_is_withheld_but_current_point_survives():
    client = _Client(
        scoped_history=[_pt("nd", "first_edition", d, 100.0 + i) for i, d in enumerate(["2026-09-20", "2026-09-21", "2026-09-22"])],
        certification=[{"set_id": "nd", "market_scope": "first_edition", "history_publishable": False}],
    )
    markets = [{"id": "nd", "market_scope": "first_edition", "market_key": "set:nd:first_edition", "market_current_certification_status": "CERTIFIED"}]
    result = builder._load_scoped_certified_histories(client, markets, through_date="2026-09-22")
    assert [r["snapshot_date"] for r in result["set:nd:first_edition"]] == ["2026-09-22"]


def test_incomplete_scope_publishes_no_history():
    client = _Client(scoped_history=[_pt("nd", "first_edition", "2026-09-22", 100.0)])
    markets = [{"id": "nd", "market_scope": "first_edition", "market_key": "set:nd:first_edition", "market_current_certification_status": "SCOPED_MARKET_INCOMPLETE"}]
    assert "set:nd:first_edition" not in builder._load_scoped_certified_histories(client, markets, through_date="2026-09-22")


def test_post_cutover_histories_never_copy_scoped_values_into_standard():
    client = _Client(
        standard_history=[
            {"set_id": "neo", "snapshot_date": "2026-09-19", "set_value": 16035.49, "source": "legacy-mixed", "value_scope": "standard"},
            {"set_id": "modern", "snapshot_date": "2026-09-19", "set_value": 500.0, "source": "canonical", "value_scope": "standard"},
            {"set_id": "modern", "snapshot_date": "2026-09-20", "set_value": 510.0, "source": "canonical", "value_scope": "standard"},
        ],
        scoped_history=[
            _pt("neo", "unlimited", "2026-09-19", 13175.75),
            _pt("neo", "first_edition", "2026-09-19", 16960.28),
        ],
    )
    markets = [
        {"id": "neo", "market_scope": "unlimited", "market_key": "set:neo:unlimited"},
        {"id": "neo", "market_scope": "first_edition", "market_key": "set:neo:first_edition"},
        {"id": "modern", "market_scope": "standard", "market_key": "set:modern"},
    ]
    result = builder._load_canonical_histories(client, markets, through_date="2026-09-20")
    assert [r["set_value"] for r in result["set:modern"]] == [500.0, 510.0]
    assert [r["set_value"] for r in result["set:neo:unlimited"]] == [13175.75]
    assert [r["set_value"] for r in result["set:neo:first_edition"]] == [16960.28]
    assert "set:neo" not in result
