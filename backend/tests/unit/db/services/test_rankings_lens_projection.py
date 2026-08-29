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


def _run(monkeypatch, lens, row):
    client = _Client(row)
    monkeypatch.setattr(service, "service_read_client", client)
    monkeypatch.setattr(service, "run_public_read_with_retry", lambda load, **_kwargs: load(client))
    monkeypatch.setattr(service, "_rankings_publication_identity_mismatches", lambda _payload: [])
    return service.get_pokemon_explore_rankings_lens_payload(lens, limit=1), client


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
