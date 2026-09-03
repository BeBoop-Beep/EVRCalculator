from backend.scripts import audit_market_explorer_variant_identity as audit_module


# --- audit() wiring: end-to-end against a small fake client ------------------
class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table_name = table
        self.filters = []  # list of (method, field, value)

    def select(self, _columns):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.filters.append(("gte", field, value))
        return self

    def gt(self, field, value):
        self.filters.append(("gt", field, value))
        return self

    def limit(self, _n):
        return self

    def range(self, _start, _end):
        return self

    def execute(self):
        if self.table_name not in self.db.filter_calls:
            self.db.filter_calls[self.table_name] = []
        self.db.filter_calls[self.table_name].append(list(self.filters))

        rows = list(self.db.tables.get(self.table_name, []))
        for method, field, value in self.filters:
            if method == "eq":
                rows = [r for r in rows if str(r.get(field)) == str(value)]
            elif method == "gte":
                rows = [r for r in rows if str(r.get(field) or "") >= str(value)]
            elif method == "gt":
                rows = [r for r in rows if (r.get(field) or 0) > value]
        return _FakeResult(rows)


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.filter_calls = {}

    def table(self, name):
        return _FakeQuery(self, name)


def _synthetic_audit_client():
    """One synthetic set with a drift case: canonical selected-price row
    is stale, raw NM observations on the same variant are fresh. All ids
    are synthetic -- never real production UUIDs."""
    return _FakeClient({
        "pokemon_canonical_cards": [{
            "id": "canon-1", "set_id": "set-1", "name": "Test Mon", "number": "1",
            "printed_number": "1", "pokemon_tcg_api_card_id": "api-1", "rarity": "Common",
        }],
        "pokemon_canonical_card_legacy_identity_links": [],
        "cards": [{
            "id": "card-1", "set_id": "set-1", "name": "Test Mon",
            "card_number": "1", "pokemon_tcg_api_id": "api-1",
        }],
        "card_variants": [{
            "id": "variant-1", "card_id": "card-1", "edition": None,
            "printing_type": None, "special_type": None, "pokemon_tcg_api_id": None,
        }],
        "sets": [{"id": "set-1", "name": "Synthetic Set", "era_id": "era-1", "release_date": "2020-01-01"}],
        "eras": [{"id": "era-1", "name": "Synthetic Era"}],
        "pokemon_card_desirability_links": [],
        "pokemon_reference": [],
        "conditions": [{"id": "cond-nm", "name": "Near Mint", "abbreviation": "NM"}],
        "pokemon_canonical_card_market_prices_latest": [{
            "canonical_card_id": "canon-1", "set_id": "set-1", "card_variant_id": "variant-1",
            "condition_id": "cond-nm", "market_price": 5.0, "captured_at": "2026-07-01T00:00:00Z",
        }],
        "card_variant_price_observations": [{
            "id": "obs-1", "card_variant_id": "variant-1", "condition_id": "cond-nm",
            "captured_at": "2026-09-02T00:00:00Z", "market_price": 6.0,
        }],
    })


def test_audit_wiring_surfaces_canonical_price_identity_drift_end_to_end():
    client = _synthetic_audit_client()

    result = audit_module.audit(client)

    drift = result["canonicalPriceIdentityDrift"]
    assert len(drift) == 1
    assert drift[0]["setId"] == "set-1"
    assert drift[0]["selectedLatestDate"] == "2026-07-01"
    assert drift[0]["rawLatestDate"] == "2026-09-02"
    assert drift[0]["rawIdentityCount"] == 1


def test_audit_bounds_the_raw_observation_read_with_a_captured_at_lower_bound():
    """Regression: the raw NM observation read must never be a full-table
    scan -- it must carry a captured_at gte filter bounding it to the
    identity-drift lookback window."""
    client = _synthetic_audit_client()

    audit_module.audit(client)

    calls = client.filter_calls.get("card_variant_price_observations", [])
    assert calls, "card_variant_price_observations was never read"
    # The paged read for raw NM observations (not the per-variant
    # has_nm_history probe) must include a captured_at gte bound.
    bounded_calls = [
        call for call in calls
        if any(method == "gte" and field == "captured_at" for method, field, _ in call)
    ]
    assert bounded_calls, f"no captured_at gte bound found in calls: {calls}"


def test_stale_selected_price_flagged_when_raw_observations_are_current():
    """Regression fixture modeled on Nintendo Black Star Promos: raw NM
    observations are current on the target date, canonical selected-price
    rows exist but stop 16 days earlier because no selected identity
    reaches the target date. Synthetic ids only -- never real production
    UUIDs."""
    set_id = "set-synthetic-promos"
    canonical_card_id = "canonical-raichu-27"
    stale_variant_id = "variant-old-identity"
    fresh_variant_id = "variant-new-identity"

    # canonical selected-price row still points at the stale (old) identity
    selected_rows = [{
        "canonical_card_id": canonical_card_id,
        "card_variant_id": stale_variant_id,
        "condition_id": "condition-nm",
        "market_price": 5.0,
        "captured_at": "2026-08-17T00:00:00Z",
    }]
    # raw NM observations: stale identity has old data, a DIFFERENT
    # (unlinked) fresh identity has data through the target date -- this
    # models "fresh observations exist on replacement TCGPlayer identities"
    raw_rows = [
        {"card_variant_id": stale_variant_id, "condition_id": "condition-nm",
         "market_price": 5.0, "captured_at": "2026-08-17T00:00:00Z"},
        {"card_variant_id": fresh_variant_id, "condition_id": "condition-nm",
         "market_price": 6.0, "captured_at": "2026-09-02T00:00:00Z"},
    ]

    result = audit_module._compute_canonical_price_identity_drift(
        set_id=set_id,
        canonical_key="nintendo-black-star-promos-synthetic",
        selected_rows=selected_rows,
        raw_observation_rows=raw_rows,
    )

    assert len(result) == 1
    drift = result[0]
    assert drift["setId"] == set_id
    assert drift["canonicalKey"] == "nintendo-black-star-promos-synthetic"
    assert drift["selectedLatestDate"] == "2026-08-17"
    assert drift["rawLatestDate"] == "2026-09-02"
    assert drift["selectedRowCount"] == 1
    assert drift["rawIdentityCount"] == 2


def test_no_drift_flagged_when_selected_price_tracks_raw_freshness():
    set_id = "set-synthetic-healthy"
    selected_rows = [{
        "canonical_card_id": "canonical-x",
        "card_variant_id": "variant-x",
        "condition_id": "condition-nm",
        "market_price": 10.0,
        "captured_at": "2026-09-02T00:00:00Z",
    }]
    raw_rows = [{
        "card_variant_id": "variant-x", "condition_id": "condition-nm",
        "market_price": 10.0, "captured_at": "2026-09-02T00:00:00Z",
    }]

    result = audit_module._compute_canonical_price_identity_drift(
        set_id=set_id, canonical_key="healthy-set",
        selected_rows=selected_rows, raw_observation_rows=raw_rows,
    )

    assert result == []


def test_no_drift_flagged_when_no_selected_rows_exist():
    result = audit_module._compute_canonical_price_identity_drift(
        set_id="set-synthetic-empty", canonical_key="empty-set",
        selected_rows=[], raw_observation_rows=[{
            "card_variant_id": "variant-x", "condition_id": "condition-nm",
            "market_price": 1.0, "captured_at": "2026-09-02T00:00:00Z",
        }],
    )

    assert result == []
