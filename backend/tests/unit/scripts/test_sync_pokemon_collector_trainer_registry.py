from backend.scripts.sync_pokemon_collector_trainer_registry import build_rows, sync


class Repo:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.writes = []

    def list_entities(self):
        return self.rows

    def upsert_entities(self, rows):
        self.writes.extend(rows)


def payload():
    return {"registryVersion":"v1", "sources":{"official":"https://pokemon.example"},
            "trainers":[{"name":"Cynthia", "source":"official"}]}


def test_build_rows_preserves_provenance_and_uses_trainer_namespace():
    row = build_rows(payload())[0]
    assert row["canonical_key"] == "trainer:cynthia"
    assert row["identity_metadata_json"]["confidence"] == 1.0
    assert row["identity_metadata_json"]["authoritativeSource"] == "https://pokemon.example"


def test_dry_run_never_writes_and_repeat_is_unchanged():
    repo = Repo()
    assert sync(repo, payload())["inserts"] == 1
    assert repo.writes == []
    existing = build_rows(payload())
    report = sync(Repo(existing), payload())
    assert report == {**report, "inserts": 0, "updates": 0, "unchanged": 1}
