from backend.db.services import pokemon_public_snapshot_service as service


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, row, selected):
        self.row = row
        self.selected = selected

    def select(self, value):
        self.selected.append(value)
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return _Result([self.row])


class _Client:
    def __init__(self, row):
        self.row = row
        self.selected = []

    def table(self, name):
        assert name == "pokemon_explore_rankings_snapshot_latest"
        return _Query(self.row, self.selected)

    def rpc(self, *_args, **_kwargs):
        raise RuntimeError("compact RPC unavailable in unit fixture")


def _run(monkeypatch, lens, row, limit=1):
    client = _Client(row)
    monkeypatch.setattr(service, "service_read_client", client)
    monkeypatch.setattr(service, "run_public_read_with_retry", lambda load, **_kwargs: load(client))
    monkeypatch.setattr(service, "_rankings_publication_identity_mismatches", lambda _payload: [])
    return service.get_pokemon_explore_rankings_lens_payload(lens, limit=limit), client


def test_sets_lens_projects_only_targets_meta_and_default(monkeypatch):
    payload, client = _run(monkeypatch, "sets", {
        "targets": [{"id": "set-1", "isOpeningSet": True}, {"id": "set-2", "isOpeningSet": True}],
        "default_target_json": {"id": "set-1"}, "meta": {}, "updated_at": "now",
    })

    assert [row["id"] for row in payload["targets"]] == ["set-1"]
    assert "ranking_payload_json->targets" in client.selected[0]
    assert "ranking_payload_json," not in client.selected[0]


def test_products_lens_does_not_read_targets(monkeypatch):
    families = {"booster_box": {"rows": [{"id": "product-1"}]}}
    payload, client = _run(monkeypatch, "products", {
        "productFamilyRankings": families, "meta": {}, "updated_at": "now",
    })

    assert payload["productFamilyRankings"] == families
    assert "productFamilyRankings" in client.selected[0]
    assert "->targets" not in client.selected[0]


def test_eras_lens_prefers_persisted_canonical_contract(monkeypatch):
    persisted = {"methodology": "era-set-strength-v1", "eras": [{"eraName": "Modern"}]}
    payload, client = _run(monkeypatch, "eras", {
        "eraSetStrengthV1": persisted,
        "targets": [{"id": "set-1", "isOpeningSet": True}],
        "meta": {}, "updated_at": "now",
    })

    assert payload["eraSetStrengthV1"] == persisted
    assert payload["meta"]["snapshot"]["source"] == "pokemon_explore_rankings_snapshot_latest"
    assert "eraSetStrengthV1" in client.selected[0]


def test_eras_lens_derives_canonical_fallback_from_published_targets(monkeypatch):
    targets = [{"id": "set-1", "isOpeningSet": True}]
    derived = {"methodology": "era-set-strength-v1", "eras": [{"eraName": "Modern"}]}
    monkeypatch.setattr(service, "build_era_set_strength", lambda rows: derived if rows == targets else None)

    payload, _client = _run(monkeypatch, "eras", {
        "eraSetStrengthV1": None, "targets": targets, "meta": {}, "updated_at": "now",
    })

    assert payload["eraSetStrengthV1"] == derived
    assert payload["meta"]["snapshot"]["source"] == "canonical_era_set_strength_v1_fallback_from_published_targets"
    assert payload["meta"]["snapshot"]["persistedProjectionAvailable"] is False


def test_sets_lens_retains_ranked_cohort_through_backend_projection(monkeypatch):
    targets = [
        {"id": f"set-{index}", "isOpeningSet": True, "setRipV1": {"rank": index, "score": 90 - index, "tier": "A"}}
        for index in range(1, 23)
    ]
    payload, _client = _run(monkeypatch, "sets", {
        "targets": targets, "default_target_json": targets[0], "meta": {}, "updated_at": "now",
    }, limit=60)

    assert len(payload["targets"]) == 22
    assert payload["targets"][0]["setRipV1"] == {"rank": 1, "score": 89, "tier": "A"}
