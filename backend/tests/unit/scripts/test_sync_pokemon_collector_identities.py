from __future__ import annotations

from copy import deepcopy

from backend.scripts.sync_pokemon_collector_identities import (
    build_artist_entity_plan,
    build_identity_sync_report,
    build_trainer_link_plan,
    load_trainer_overrides,
)


class FakeRepository:
    def __init__(self, *, cards, entities=None, entity_links=None, function_refs=None, function_links=None):
        self.cards = deepcopy(cards)
        self.entities = deepcopy(entities or [])
        self.entity_links = deepcopy(entity_links or [])
        self.function_refs = deepcopy(function_refs or [])
        self.function_links = deepcopy(function_links or [])
        self.calls = []
        self._next_entity = 1
        self._next_function = 1

    def list_canonical_cards(self, *, set_id=None):
        self.calls.append(("list_canonical_cards", set_id))
        if set_id:
            return deepcopy([row for row in self.cards if str(row.get("set_id")) == str(set_id)])
        return deepcopy(self.cards)

    def list_entities(self):
        self.calls.append(("list_entities", None))
        return deepcopy(self.entities)

    def list_entity_links(self):
        self.calls.append(("list_entity_links", None))
        return deepcopy(self.entity_links)

    def list_functional_references(self):
        self.calls.append(("list_functional_references", None))
        return deepcopy(self.function_refs)

    def list_functional_links(self):
        self.calls.append(("list_functional_links", None))
        return deepcopy(self.function_links)

    def upsert_entities(self, rows):
        self.calls.append(("upsert_entities", len(rows)))
        by_key = {(row["entity_type"], row["canonical_key"]): row for row in self.entities}
        for row in rows:
            key = (row["entity_type"], row["canonical_key"])
            existing = by_key.get(key)
            if existing is None:
                existing = {**deepcopy(row), "id": f"entity-{self._next_entity}"}
                self._next_entity += 1
                self.entities.append(existing)
                by_key[key] = existing
            else:
                existing.update(deepcopy(row))

    def upsert_entity_links(self, rows):
        self.calls.append(("upsert_entity_links", len(rows)))
        by_key = {
            (row["pokemon_canonical_card_id"], row["collector_entity_id"], row["link_role"]): row
            for row in self.entity_links
        }
        for row in rows:
            key = (row["pokemon_canonical_card_id"], row["collector_entity_id"], row["link_role"])
            existing = by_key.get(key)
            if existing is None:
                existing = deepcopy(row)
                self.entity_links.append(existing)
                by_key[key] = existing
            else:
                existing.update(deepcopy(row))

    def upsert_functional_references(self, rows):
        self.calls.append(("upsert_functional_references", len(rows)))
        by_key = {row["functional_key"]: row for row in self.function_refs}
        for row in rows:
            existing = by_key.get(row["functional_key"])
            if existing is None:
                existing = {**deepcopy(row), "id": f"function-{self._next_function}"}
                self._next_function += 1
                self.function_refs.append(existing)
                by_key[row["functional_key"]] = existing
            else:
                existing.update(deepcopy(row))

    def upsert_functional_links(self, rows):
        self.calls.append(("upsert_functional_links", len(rows)))
        by_key = {
            (row["pokemon_canonical_card_id"], row["functional_reference_id"]): row
            for row in self.function_links
        }
        for row in rows:
            key = (row["pokemon_canonical_card_id"], row["functional_reference_id"])
            existing = by_key.get(key)
            if existing is None:
                existing = deepcopy(row)
                self.function_links.append(existing)
                by_key[key] = existing
            else:
                existing.update(deepcopy(row))


def _card(
    card_id,
    name,
    *,
    supertype="Trainer",
    subtypes=None,
    artist="Artist One",
    rules=None,
    set_id="set-1",
):
    return {
        "id": card_id,
        "set_id": set_id,
        "pokemon_tcg_api_card_id": f"api-{card_id}",
        "name": name,
        "supertype": supertype,
        "subtypes": subtypes or (["Supporter"] if supertype == "Trainer" else ["Basic"]),
        "artist": artist,
        "source_payload": {"rules": rules or [f"Rule for {name}"]},
    }


def _trainer(entity_id, name):
    return {
        "id": entity_id,
        "entity_type": "trainer",
        "canonical_key": f"trainer:{name.lower()}",
        "display_name": name,
        "normalized_name": name.lower(),
        "active": True,
    }


def _artist(entity_id="artist-1", name="Artist One"):
    return {
        "id": entity_id,
        "entity_type": "artist",
        "canonical_key": f"artist:{name.lower()}",
        "display_name": name,
        "normalized_name": name.lower(),
        "active": True,
    }


def test_artist_plan_is_noop_for_seeded_artist_and_adds_only_missing_artist():
    cards = [_card("1", "Iono", artist="Artist One"), _card("2", "Rare Candy", artist="New Artist")]
    plan = build_artist_entity_plan(cards=cards, entities=[_artist()])
    assert len(plan["entity_rows"]) == 1
    assert plan["entity_rows"][0]["canonical_key"] == "artist:new artist"
    assert plan["distinct_artist_keys"] == 2


def test_trainer_plan_resolves_known_named_supporters_and_leaves_generic_supporter_unresolved():
    cards = [
        _card("1", "Iono"),
        _card("2", "Cynthia's Ambition"),
        _card("3", "Professor's Research"),
        _card("4", "Rare Candy", subtypes=["Item"]),
    ]
    plan = build_trainer_link_plan(
        cards=cards,
        trainer_entities=[_trainer("t-iono", "Iono"), _trainer("t-cynthia", "Cynthia")],
        trainer_overrides={},
    )
    assert plan["supporter_count"] == 3
    assert plan["resolved_supporter_count"] == 2
    assert plan["unresolved_supporter_count"] == 1
    assert {row["pokemon_canonical_card_id"] for row in plan["rows"]} == {"1", "2"}
    assert plan["unresolved_samples"][0]["name"] == "Professor's Research"


def test_dry_run_writes_nothing_and_reports_batch_performance_contract():
    repo = FakeRepository(
        cards=[_card("1", "Iono")],
        entities=[_artist(), _trainer("t-iono", "Iono")],
    )
    report = build_identity_sync_report(
        repository=repo,
        set_id=None,
        trainer_overrides={},
        dry_run=True,
    )
    assert report["status"] == "dry_run"
    assert not any(call[0].startswith("upsert_") for call in repo.calls)
    perf = report["diagnostics"]["performanceContract"]
    assert perf["perCardDatabaseQueries"] is False
    assert perf["canonicalPayloadProjection"] == "gameplay_fields_only"


def test_commit_creates_functional_identity_and_then_second_run_is_idempotent():
    repo = FakeRepository(
        cards=[_card("1", "Rare Candy", subtypes=["Item"], rules=["Evolve one Basic Pokemon."])],
        entities=[_artist()],
    )
    first = build_identity_sync_report(
        repository=repo,
        set_id=None,
        trainer_overrides={},
        dry_run=False,
    )
    assert first["status"] == "committed"
    assert first["diagnostics"]["writesPlanned"]["functionalReferences"] == 1
    assert first["diagnostics"]["writesPlanned"]["functionalLinks"] == 1
    assert len(repo.function_refs) == 1
    assert len(repo.function_links) == 1

    repo.calls.clear()
    second = build_identity_sync_report(
        repository=repo,
        set_id=None,
        trainer_overrides={},
        dry_run=False,
    )
    assert second["diagnostics"]["writesPlanned"] == {
        "artistEntities": 0,
        "collectorEntityLinks": 0,
        "functionalReferences": 0,
        "functionalLinks": 0,
    }
    assert not any(call[0].startswith("upsert_") for call in repo.calls)


def test_same_gameplay_signature_reuses_one_functional_reference_for_two_printings():
    repo = FakeRepository(
        cards=[
            _card("1", "Rare Candy", subtypes=["Item"], artist="Artist One", rules=["Evolve one Basic Pokemon."]),
            _card("2", "Rare Candy", subtypes=["Item"], artist="Artist Two", rules=["Evolve one Basic Pokemon."]),
        ],
        entities=[_artist(), _artist("artist-2", "Artist Two")],
    )
    report = build_identity_sync_report(
        repository=repo,
        set_id=None,
        trainer_overrides={},
        dry_run=False,
    )
    assert report["diagnostics"]["uniqueFunctionalIdentities"] == 1
    assert report["diagnostics"]["functionalLinksExpected"] == 2
    assert len(repo.function_refs) == 1
    assert len(repo.function_links) == 2


def test_energy_is_not_given_functional_playability_identity():
    repo = FakeRepository(
        cards=[_card("energy", "Fairy Energy", supertype="Energy", subtypes=["Basic Energy"])],
        entities=[_artist()],
    )
    report = build_identity_sync_report(
        repository=repo,
        set_id=None,
        trainer_overrides={},
        dry_run=True,
    )
    assert report["diagnostics"]["functionalEligibleCards"] == 0
    assert report["diagnostics"]["functionalLinksExpected"] == 0


def test_set_id_scope_is_forwarded_to_single_bulk_card_read():
    repo = FakeRepository(
        cards=[_card("1", "Iono", set_id="set-a"), _card("2", "Rare Candy", set_id="set-b", subtypes=["Item"])],
        entities=[_artist(), _trainer("t-iono", "Iono")],
    )
    report = build_identity_sync_report(
        repository=repo,
        set_id="set-a",
        trainer_overrides={},
        dry_run=True,
    )
    assert report["diagnostics"]["canonicalCardsLoaded"] == 1
    assert ("list_canonical_cards", "set-a") in repo.calls


def test_override_registry_schema_round_trip(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        '{"version":"v1","cardOverrides":{"api-card":["Professor Oak"],"skip":[]}}',
        encoding="utf-8",
    )
    assert load_trainer_overrides(path) == {"api-card": ["Professor Oak"]}
