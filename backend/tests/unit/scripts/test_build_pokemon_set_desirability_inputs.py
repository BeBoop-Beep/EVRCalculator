from __future__ import annotations

from backend.desirability.component_source import (
    expected_source_versions,
    matches_expected_versions,
)
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION
from backend.scripts import build_pokemon_set_desirability_inputs as combined


LEGACY_V1 = "pokemon_card_desirability_hit_policy_v1"


def test_fallback_pokemon_row_needs_authoritative_refresh():
    row = {
        "source": combined.FALLBACK_SOURCE,
        "supertype": "Pokémon",
        "national_pokedex_numbers": [25],
    }

    assert combined.canonical_row_needs_authoritative_refresh(row) is True


def test_missing_supertype_row_needs_authoritative_refresh():
    row = {"source": "pokemon_tcg_api", "national_pokedex_numbers": [25]}

    assert combined.canonical_row_needs_authoritative_refresh(row) is True


def test_authoritative_pokemon_row_without_pokedex_number_needs_refresh():
    row = {
        "source": "pokemon_tcg_api",
        "supertype": "Pokémon",
        "national_pokedex_numbers": [],
    }

    assert combined.canonical_row_needs_authoritative_refresh(row) is True


def test_authoritative_pokemon_row_with_pokedex_number_does_not_need_refresh():
    row = {
        "source": "pokemon_tcg_api",
        "supertype": "Pokémon",
        "national_pokedex_numbers": [25],
    }

    assert combined.canonical_row_needs_authoritative_refresh(row) is False


def test_authoritative_trainer_row_without_pokedex_number_does_not_need_refresh():
    row = {
        "source": "pokemon_tcg_api",
        "supertype": "Trainer",
        "national_pokedex_numbers": [],
    }

    assert combined.canonical_row_needs_authoritative_refresh(row) is False


def test_empty_canonical_set_needs_authoritative_refresh():
    assert combined.canonical_set_needs_authoritative_refresh([]) is True


def test_combined_builder_default_and_explicit_override():
    default_args = combined.build_parser().parse_args(["--set", "testSet"])
    override_args = combined.build_parser().parse_args(
        ["--set", "testSet", "--hit-policy-version", "custom-policy"]
    )

    assert default_args.hit_policy_version == HIT_POLICY_VERSION
    assert override_args.hit_policy_version == "custom-policy"


def test_combined_stages_receive_one_authoritative_hit_policy(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        combined,
        "PokemonCardDesirabilityLinksRepository",
        lambda: object(),
    )
    monkeypatch.setattr(
        combined,
        "PokemonSetHitDesirabilitySummariesRepository",
        lambda: object(),
    )
    monkeypatch.setattr(
        combined,
        "PokemonSetDesirabilityComponentsRepository",
        lambda: object(),
    )
    monkeypatch.setattr(
        combined,
        "RipDesirabilityPrototypeRepository",
        lambda: object(),
    )

    def capture(name, result):
        def fake(**kwargs):
            calls[name] = kwargs
            return result

        return fake

    monkeypatch.setattr(combined, "build_links_report", capture("links", {}))
    monkeypatch.setattr(combined, "build_set_hit_desirability_summaries_report", capture("summaries", {}))
    monkeypatch.setattr(combined, "build_component_scores_report", capture("components", {}))
    monkeypatch.setattr(combined, "build_report", capture("opening", {"rows": []}))

    combined._build_links(
        selected_set_key="testSet",
        process_all=False,
        hit_policy_version=HIT_POLICY_VERSION,
        dry_run=True,
    )
    combined._build_summaries(
        selected_set_key="testSet",
        process_all=False,
        hit_policy_version=HIT_POLICY_VERSION,
        dry_run=True,
    )
    combined._build_components(
        selected_set_key="testSet",
        process_all=False,
        hit_policy_version=HIT_POLICY_VERSION,
        dry_run=True,
    )
    opening_report = combined._build_opening(
        selected_set_ids=["set-1"],
        hit_policy_version=HIT_POLICY_VERSION,
        dry_run=True,
    )

    assert {call["hit_policy_version"] for call in calls.values()} == {HIT_POLICY_VERSION}
    assert opening_report["hit_policy_version"] == HIT_POLICY_VERSION
    assert LEGACY_V1 not in {call["hit_policy_version"] for call in calls.values()}


def test_combined_report_cannot_mix_hit_policies_between_stages(monkeypatch):
    stage_policies = {}

    monkeypatch.setattr(combined, "get_supabase_client", lambda: object())
    monkeypatch.setattr(combined, "build_valid_set_key_registry", lambda: {})
    monkeypatch.setattr(
        combined,
        "_list_sets",
        lambda client, *, set_key, process_all: [
            {"id": "set-1", "name": "Test Set", "canonical_key": "testSet"}
        ],
    )
    monkeypatch.setattr(
        combined,
        "_process_single_set",
        lambda **kwargs: {"cards_rows": 0},
    )

    def stage(name):
        def fake(**kwargs):
            stage_policies[name] = kwargs["hit_policy_version"]
            return {}

        return fake

    monkeypatch.setattr(combined, "_build_links", stage("links"))
    monkeypatch.setattr(combined, "_build_summaries", stage("summaries"))
    monkeypatch.setattr(combined, "_build_components", stage("components"))
    monkeypatch.setattr(combined, "_build_opening", stage("opening"))

    report = combined.build_set_desirability_inputs_report(
        set_key=None,
        process_all=True,
        dry_run=True,
    )

    assert report["hit_policy_version"] == HIT_POLICY_VERSION
    assert stage_policies == {
        "links": HIT_POLICY_VERSION,
        "summaries": HIT_POLICY_VERSION,
        "components": HIT_POLICY_VERSION,
        "opening": HIT_POLICY_VERSION,
    }


def test_generated_component_version_triple_matches_public_reader_exactly():
    current_row = expected_source_versions()
    legacy_row = {**current_row, "hit_policy_version": LEGACY_V1}

    assert current_row["hit_policy_version"] == HIT_POLICY_VERSION
    assert matches_expected_versions(current_row) is True
    assert matches_expected_versions(legacy_row) is False


def test_authoritative_refresh_replaces_identity_poor_fallback_metadata(monkeypatch):
    monkeypatch.setattr(combined, "fetch_authoritative_api_set", lambda _set_id: {"printedTotal": 84})
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda _client, _set_id: [])
    monkeypatch.setattr(
        combined, "fetch_authoritative_cards",
        lambda _set_id: [
            {"id": "me5-42", "name": "Morpeko ex", "number": "42",
             "supertype": "Pokémon", "subtypes": ["Basic", "ex"],
             "nationalPokedexNumbers": [877], "set": {"id": "me5"}},
            {"id": "me5-118", "name": "Gladion's Final Battle", "number": "118",
             "supertype": "Trainer", "subtypes": ["Supporter"],
             "nationalPokedexNumbers": [], "set": {"id": "me5"}},
        ],
    )
    written = []
    monkeypatch.setattr(combined, "_upsert_canonical_rows", lambda _client, rows: written.extend(rows) or len(rows))

    result = combined._refresh_authoritative_canonical_cards(
        client=object(),
        set_row={"id": "set-1", "canonical_key": "pitchBlack", "pokemon_api_set_id": "me5"},
        dry_run=False,
    )

    assert result == {
        "status": "refreshed", "source": "pokemon_tcg_api", "rows_found": 2,
        "rows_promoted_from_fallback": 0, "rows_upserted_by_api_id": 2, "rows_upserted": 2,
    }
    assert written[0]["supertype"] == "Pokémon"
    assert written[0]["national_pokedex_numbers"] == [877]
    assert written[1]["supertype"] == "Trainer"
    assert written[1]["subtypes"] == ["Supporter"]
    assert all(row["source"] == "pokemon_tcg_api" for row in written)




class _CanonicalPromoteQuery:
    def __init__(self, updates):
        self.updates = updates
        self.payload = None

    def update(self, payload):
        self.payload = dict(payload)
        return self

    def eq(self, field, value):
        self.updates.append((field, value, self.payload))
        return self

    def execute(self):
        return type("Res", (), {"data": [{"id": "fallback-1"}]})()


class _CanonicalPromoteClient:
    def __init__(self):
        self.updates = []

    def table(self, name):
        assert name == "pokemon_canonical_cards"
        return _CanonicalPromoteQuery(self.updates)


def test_authoritative_refresh_promotes_matching_fallback_row_in_place(monkeypatch):
    monkeypatch.setattr(combined, "fetch_authoritative_api_set", lambda _set_id: {"printedTotal": 128})
    monkeypatch.setattr(
        combined,
        "fetch_authoritative_cards",
        lambda _set_id: [{
            "id": "me55-1", "name": "Bulbasaur", "number": "1",
            "supertype": "Pokémon", "subtypes": ["Basic"],
            "nationalPokedexNumbers": [1], "set": {"id": "me55"},
            "images": {"small": "small", "large": "large"},
        }],
    )
    monkeypatch.setattr(
        combined,
        "_list_canonical_for_set",
        lambda _client, _set_id: [{
            "id": "fallback-1",
            "pokemon_tcg_api_card_id": "fallback:set-1:1:bulbasaur",
            "name": "Bulbasaur", "number": "1", "source": combined.FALLBACK_SOURCE,
        }],
    )
    upserts = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: upserts.extend(rows) or len(rows),
    )
    client = _CanonicalPromoteClient()

    result = combined._refresh_authoritative_canonical_cards(
        client=client,
        set_row={"id": "set-1", "canonical_key": "me30thCelebration", "pokemon_api_set_id": "me55"},
        dry_run=False,
    )

    assert result["rows_promoted_from_fallback"] == 1
    assert result["rows_upserted_by_api_id"] == 0
    assert upserts == []
    assert client.updates[0][0:2] == ("id", "fallback-1")
    assert client.updates[0][2]["pokemon_tcg_api_card_id"] == "me55-1"
    assert client.updates[0][2]["source"] == "pokemon_tcg_api"


def test_authoritative_refresh_tries_tcgdex_when_legacy_provider_is_not_ready(monkeypatch):
    monkeypatch.setattr(
        combined, "fetch_authoritative_api_set",
        lambda _set_id: (_ for _ in ()).throw(RuntimeError("not published yet")),
    )
    seen = {}
    def tcgdex_fallback(**kwargs):
        seen.update(kwargs)
        return {
            "status": "refreshed", "source": combined.TCGDEX_SOURCE,
            "rows_found": 2, "rows_upserted": 2,
        }
    monkeypatch.setattr(combined, "_refresh_tcgdex_canonical_cards", tcgdex_fallback)

    result = combined._refresh_authoritative_canonical_cards(
        client=object(),
        set_row={
            "id": "set-1", "name": "Future Set", "canonical_key": "futureSet",
            "pokemon_api_set_id": "future",
        },
        dry_run=False,
    )

    assert result["source"] == combined.TCGDEX_SOURCE
    assert result["rows_upserted"] == 2
    assert "not published yet" in result["upstream_error"]
    assert seen["set_row"]["canonical_key"] == "futureSet"




class _FakeTCGdexCanonical:
    def __init__(self, rows):
        self.rows = list(rows)
        self.names = []

    def fetch_card_details_for_set_name(self, set_name):
        self.names.append(set_name)
        return list(self.rows)


def test_tcgdex_refresh_enriches_fallback_row_in_place_without_relabeling_external_id(monkeypatch):
    cards = [{
        "id": "legacy-1", "set_id": "set-1", "name": "Exeggcute",
        "rarity": "Common", "card_number": "001/128",
        "pokemon_tcg_api_id": None, "image_small_url": None, "image_large_url": None,
    }]
    canonical = [{
        "id": "canon-1", "set_id": "set-1",
        "pokemon_tcg_api_card_id": "fallback:set-1:001/128:exeggcute",
        "name": "Exeggcute", "number": "1", "source": combined.FALLBACK_SOURCE,
    }]
    provider = _FakeTCGdexCanonical([{
        "tcgdex_card_id": "30th-001", "name": "Exeggcute", "number": "001",
        "supertype": "Pokémon", "subtypes": ["Basic"], "rarity": "Common",
        "artist": "Nelnal", "national_pokedex_numbers": [102],
        "image_small_url": "https://assets.tcgdex.net/en/me/30th/001/low.webp",
        "image_large_url": "https://assets.tcgdex.net/en/me/30th/001/high.webp",
        "source_payload": {"id": "30th-001"},
    }])
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda *_a: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda *_a: canonical)
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda *_a: [])
    client = _CanonicalPromoteClient()

    result = combined._refresh_tcgdex_canonical_cards(
        client=client,
        set_row={
            "id": "set-1", "name": "ME: 30th Celebration",
            "canonical_key": "me30thCelebration", "catalog_only": False,
            "is_subset": False,
        },
        dry_run=False,
        tcgdex_client=provider,
    )

    assert result["rows_matched"] == 1
    assert result["rows_upserted"] == 1
    payload = client.updates[0][2]
    assert payload["pokemon_tcg_api_card_id"] == canonical[0]["pokemon_tcg_api_card_id"]
    assert payload["source"] == combined.TCGDEX_SOURCE
    assert payload["source_payload"]["tcgdex_card_id"] == "30th-001"
    assert payload["artist"] == "Nelnal"
    assert payload["national_pokedex_numbers"] == [102]
    assert payload["image_small_url"].startswith("https://assets.tcgdex.net/")


def test_tcgdex_refresh_uses_unique_name_when_classic_local_ids_are_reindexed(monkeypatch):
    cards = [{
        "id": "legacy-1", "set_id": "set-1", "name": "Charizard",
        "rarity": "Rare", "card_number": "4/102",
        "pokemon_tcg_api_id": None, "image_small_url": None, "image_large_url": None,
    }]
    canonical = [{
        "id": "canon-1", "set_id": "set-1",
        "pokemon_tcg_api_card_id": "fallback:set-1:4/102:charizard",
        "name": "Charizard", "number": "4", "source": combined.FALLBACK_SOURCE,
    }]
    provider = _FakeTCGdexCanonical([{
        "tcgdex_card_id": "30th-c-001", "name": "Charizard", "number": "001",
        "supertype": "Pokémon", "subtypes": ["Stage2"], "rarity": "None",
        "artist": "Mitsuhiro Arita", "national_pokedex_numbers": [],
        "image_small_url": None, "image_large_url": None,
        "source_payload": {"id": "30th-c-001"},
    }])
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda *_a: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda *_a: canonical)
    monkeypatch.setattr(
        combined, "_list_pokemon_reference",
        lambda *_a: [{"id": "ref-6", "pokedex_number": 6,
                      "canonical_name": "charizard", "display_name": "Charizard"}],
    )
    client = _CanonicalPromoteClient()

    result = combined._refresh_tcgdex_canonical_cards(
        client=client,
        set_row={
            "id": "set-1", "name": "ME: 30th Celebration Classic Collection",
            "canonical_key": "me30thCelebrationClassicCollection",
            "catalog_only": False, "is_subset": True,
            "counts_toward_parent_set_value": True,
            "counts_toward_parent_opening": True,
        },
        dry_run=False,
        tcgdex_client=provider,
    )

    assert result["rows_matched"] == 1
    payload = client.updates[0][2]
    assert payload["printed_number"] == "4/102", "local provider index must not replace printed identity"
    assert payload["national_pokedex_numbers"] == [6]
    assert payload["source_payload"]["match_method"] == "unique_name"
    assert payload["catalog_role"] == "subset"


def test_tcgdex_refresh_refuses_ambiguous_unique_name_matches(monkeypatch):
    cards = [
        {"id": "a", "name": "Darkrai & Cresselia Legend(Top)", "rarity": "LEGEND",
         "card_number": "99/102", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
        {"id": "b", "name": "Darkrai & Cresselia Legend(Bottom)", "rarity": "LEGEND",
         "card_number": "100/102", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
    ]
    provider = _FakeTCGdexCanonical([
        {"tcgdex_card_id": "30th-c-016", "name": "Darkrai & Cresselia LEGEND", "number": "016",
         "supertype": "Pokémon", "subtypes": ["LEGEND"], "rarity": "LEGEND",
         "artist": "A", "national_pokedex_numbers": [], "source_payload": {}},
        {"tcgdex_card_id": "30th-c-017", "name": "Darkrai & Cresselia LEGEND", "number": "017",
         "supertype": "Pokémon", "subtypes": ["LEGEND"], "rarity": "LEGEND",
         "artist": "B", "national_pokedex_numbers": [], "source_payload": {}},
    ])
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda *_a: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda *_a: [])
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda *_a: [])

    result = combined._refresh_tcgdex_canonical_cards(
        client=object(),
        set_row={
            "id": "set-1", "name": "ME: 30th Celebration Classic Collection",
            "canonical_key": "me30thCelebrationClassicCollection",
            "catalog_only": False, "is_subset": True,
            "counts_toward_parent_set_value": True,
            "counts_toward_parent_opening": True,
        },
        dry_run=True,
        tcgdex_client=provider,
    )

    assert result["rows_matched"] == 0
    assert result["rows_ambiguous"] == 0 or result["rows_unmatched"] == 2


# --- Catalog-only canonical sync (narrow path) -----------------------------------

_CATALOG_SET_ROW = {
    "id": "set-catalog-1", "name": "ME: 30th Celebration",
    "canonical_key": "me30thCelebration", "pokemon_api_set_id": None, "catalog_only": True,
}
_NORMAL_SET_ROW = {
    "id": "set-normal-1", "name": "Some Normal Set",
    "canonical_key": "someNormalSet", "pokemon_api_set_id": None, "catalog_only": False,
    "is_subset": False, "counts_toward_parent_set_value": False,
    "counts_toward_parent_opening": False,
}
_SUBSET_SET_ROW = {
    "id": "set-subset-1", "name": "Some Classic Collection",
    "canonical_key": "someClassicCollection", "pokemon_api_set_id": None,
    "catalog_only": False, "is_subset": True,
    "counts_toward_parent_set_value": True, "counts_toward_parent_opening": True,
}


def _trainer_card(card_id: str, number: str, name: str = "Ultra Ball") -> dict:
    # "ball" matches TRAINER_LIKE_KEYWORDS, so this classifies without needing a
    # pokemon_reference lookup fixture.
    return {"id": card_id, "name": name, "rarity": "Common", "card_number": number,
            "pokemon_tcg_api_id": None, "image_small_url": None, "image_large_url": None}


def _wire_process_single_set(monkeypatch, *, cards, canonical_rows):
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda _client, _set_id: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda _client, _set_id: canonical_rows)
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda _client: [])
    monkeypatch.setattr(combined, "_list_trainer_reference_names", lambda _client: set())
    monkeypatch.setattr(
        combined,
        "_list_authoritative_non_pokemon_name_supertypes",
        lambda _client, _names: {},
    )
    monkeypatch.setattr(
        combined, "_refresh_authoritative_canonical_cards",
        lambda **kwargs: {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0},
    )


def test_catalog_only_fallback_rows_carry_explicit_eligibility_fields(monkeypatch):
    captured_rows = []
    _wire_process_single_set(monkeypatch, cards=[_trainer_card("c1", "001/120")], canonical_rows=[])
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured_rows.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_CATALOG_SET_ROW, dry_run=False)

    assert len(captured_rows) == 1
    row = captured_rows[0]
    assert row["opening_eligible"] is False
    assert row["set_value_eligible"] is True
    assert row["catalog_role"] == "main"
    assert row["canonical_review_status"] == "approved"
    assert "opening simulation" in row["eligibility_reason"]


def test_non_catalog_root_rows_write_explicit_normal_eligibility(monkeypatch):
    captured_rows = []
    _wire_process_single_set(monkeypatch, cards=[_trainer_card("c1", "001/120")], canonical_rows=[])
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured_rows.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_NORMAL_SET_ROW, dry_run=False)

    assert len(captured_rows) == 1
    row = captured_rows[0]
    assert row["catalog_role"] == "main"
    assert row["set_value_eligible"] is True
    assert row["opening_eligible"] is True
    assert row["canonical_review_status"] == "approved"
    assert row["eligibility_reason"] is None


def test_non_catalog_subset_rows_match_established_subset_eligibility(monkeypatch):
    captured_rows = []
    _wire_process_single_set(monkeypatch, cards=[_trainer_card("c1", "CC01")], canonical_rows=[])
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured_rows.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_SUBSET_SET_ROW, dry_run=False)

    assert len(captured_rows) == 1
    row = captured_rows[0]
    assert row["catalog_role"] == "subset"
    assert row["set_value_eligible"] is True
    assert row["opening_eligible"] is True
    assert row["canonical_review_status"] == "approved"
    assert row["eligibility_reason"] == "pack_pulled_subset_card"


def test_authoritative_canonical_row_is_preserved_even_for_a_catalog_only_set(monkeypatch):
    """An existing pokemon_tcg_api-sourced row must never be replaced by a fallback
    row just because the set is catalog-only."""
    existing_authoritative = {
        "id": "canon-1", "set_id": "set-catalog-1", "pokemon_tcg_api_card_id": "me5-1",
        "name": "Ultra Ball", "number": "001", "source": "pokemon_tcg_api",
    }
    captured_rows = []
    _wire_process_single_set(
        monkeypatch, cards=[_trainer_card("c1", "001/120")], canonical_rows=[existing_authoritative],
    )
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured_rows.extend(rows) or len(rows),
    )

    result = combined._process_single_set(client=object(), set_row=_CATALOG_SET_ROW, dry_run=False)

    assert result["rows_upsert_planned"] == 0
    assert captured_rows == []


def test_rerun_is_idempotent_for_catalog_only_fallback_rows(monkeypatch):
    _wire_process_single_set(monkeypatch, cards=[_trainer_card("c1", "001/120")], canonical_rows=[])
    first_rows = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: first_rows.extend(rows) or len(rows),
    )
    combined._process_single_set(client=object(), set_row=_CATALOG_SET_ROW, dry_run=False)

    second_rows = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: second_rows.extend(rows) or len(rows),
    )
    combined._process_single_set(client=object(), set_row=_CATALOG_SET_ROW, dry_run=False)

    assert first_rows == second_rows


def test_canonical_only_mode_stops_before_downstream_builders(monkeypatch):
    monkeypatch.setattr(combined, "get_supabase_client", lambda: object())
    monkeypatch.setattr(combined, "build_valid_set_key_registry", lambda: {})
    monkeypatch.setattr(
        combined, "normalize_set_key_filter",
        lambda raw, registry: {"resolved_set_key_filter": raw},
    )
    monkeypatch.setattr(
        combined, "_list_sets",
        lambda client, *, set_key, process_all: [dict(_CATALOG_SET_ROW)],
    )
    monkeypatch.setattr(
        combined, "_process_single_set",
        lambda **kwargs: {
            "cards_rows": 120, "preexisting_canonical_rows": 0, "rows_upsert_planned": 120,
            "rows_missing_before": 120, "rows_upserted": 0, "rows_skipped_missing_required": 0,
        },
    )
    called = []
    for name in ("_build_links", "_build_summaries", "_build_components", "_build_opening"):
        monkeypatch.setattr(
            combined, name,
            (lambda label: lambda **kwargs: called.append(label) or {})(name),
        )

    report = combined.build_set_desirability_inputs_report(
        set_key="me30thCelebration", process_all=False, dry_run=True, canonical_only=True,
    )

    assert called == []
    assert report["mode"] == "canonical_only"
    assert report["status"] == "dry_run"
    assert "links_report" not in report
    assert "opening_desirability_report" not in report
    assert report["canonical_fallback"]["rows_upsert_planned"] == 120


def test_canonical_only_dry_run_matches_expected_me30th_celebration_shape(monkeypatch):
    """Locks in the exact dry-run numbers reported for the me30thCelebration canary:
    120 scraped cards, 0 preexisting canonical rows, 120 rows planned for upsert."""
    monkeypatch.setattr(combined, "get_supabase_client", lambda: object())
    monkeypatch.setattr(combined, "build_valid_set_key_registry", lambda: {})
    monkeypatch.setattr(
        combined, "normalize_set_key_filter",
        lambda raw, registry: {"resolved_set_key_filter": raw},
    )
    monkeypatch.setattr(
        combined, "_list_sets",
        lambda client, *, set_key, process_all: [dict(_CATALOG_SET_ROW)],
    )
    cards = [_trainer_card(f"c{i}", f"{i:03d}/120") for i in range(120)]
    _wire_process_single_set(monkeypatch, cards=cards, canonical_rows=[])

    report = combined.build_set_desirability_inputs_report(
        set_key="me30thCelebration", process_all=False, dry_run=True, canonical_only=True,
    )

    assert report["canonical_fallback"]["rows_seen_in_cards"] == 120
    assert report["canonical_fallback"]["rows_preexisting_canonical"] == 0
    assert report["canonical_fallback"]["rows_upsert_planned"] == 120
    assert report["set_reports"][0]["rows_upserted"] == 0  # dry-run: no DB writes


def test_full_pipeline_mode_still_invokes_downstream_builders(monkeypatch):
    """Non-canonical-only behavior (the existing full pipeline) is unchanged."""
    monkeypatch.setattr(combined, "get_supabase_client", lambda: object())
    monkeypatch.setattr(combined, "build_valid_set_key_registry", lambda: {})
    monkeypatch.setattr(
        combined, "_list_sets",
        lambda client, *, set_key, process_all: [dict(_NORMAL_SET_ROW)],
    )
    monkeypatch.setattr(combined, "_process_single_set", lambda **kwargs: {"cards_rows": 0})
    called = []
    for name in ("_build_links", "_build_summaries", "_build_components", "_build_opening"):
        monkeypatch.setattr(
            combined, name,
            (lambda label: lambda **kwargs: called.append(label) or {})(name),
        )

    report = combined.build_set_desirability_inputs_report(
        set_key=None, process_all=True, dry_run=True, canonical_only=False,
    )

    assert called == ["_build_links", "_build_summaries", "_build_components", "_build_opening"]
    assert "mode" not in report
    assert "links_report" in report



def _ref(ref_id, pokedex, display, canonical=None):
    return {
        "id": ref_id,
        "pokedex_number": pokedex,
        "display_name": display,
        "canonical_name": canonical or display.lower().replace(" ", "-"),
    }


def test_provider_fallback_reference_matching_uses_form_defaults_and_regional_prefixes():
    refs = [
        _ref(103, 103, "Exeggutor", "exeggutor"),
        _ref(745, 745, "Lycanroc Midday", "lycanroc-midday"),
        _ref(849, 849, "Toxtricity Amped", "toxtricity-amped"),
        _ref(877, 877, "Morpeko Full Belly", "morpeko-full-belly"),
        _ref(925, 925, "Maushold Family Of Four", "maushold-family-of-four"),
    ]
    lookup = combined._build_reference_lookup(refs)

    assert [r["pokedex_number"] for r in combined._match_references_for_card_name(
        name="Alolan Exeggutor", reference_lookup=lookup
    )] == [103]
    assert [r["pokedex_number"] for r in combined._match_references_for_card_name(
        name="Lycanroc", reference_lookup=lookup
    )] == [745]
    assert [r["pokedex_number"] for r in combined._match_references_for_card_name(
        name="Toxtricity", reference_lookup=lookup
    )] == [849]
    assert [r["pokedex_number"] for r in combined._match_references_for_card_name(
        name="Morpeko", reference_lookup=lookup
    )] == [877]
    assert [r["pokedex_number"] for r in combined._match_references_for_card_name(
        name="Maushold", reference_lookup=lookup
    )] == [925]


def test_provider_fallback_reference_matching_handles_vintage_modifiers_and_owner_names():
    refs = [
        _ref(251, 251, "Celebi", "celebi"),
        _ref(248, 248, "Tyranitar", "tyranitar"),
        _ref(649, 649, "Genesect", "genesect"),
        _ref(376, 376, "Metagross", "metagross"),
        _ref(169, 169, "Crobat", "crobat"),
        _ref(39, 39, "Jigglypuff", "jigglypuff"),
    ]
    lookup = combined._build_reference_lookup(refs)

    cases = {
        "Shining Celebi": 251,
        "Dark Tyranitar": 248,
        "Genesect EX(Team Plasma)": 649,
        "Metagross(Delta Species)": 376,
        "Crobat G": 169,
        "Erika's Jigglypuff": 39,
    }
    for name, expected in cases.items():
        matches = combined._match_references_for_card_name(name=name, reference_lookup=lookup)
        assert [r["pokedex_number"] for r in matches] == [expected]


def test_provider_fallback_reference_matching_preserves_multi_pokemon_cards():
    refs = [
        _ref(25, 25, "Pikachu", "pikachu"),
        _ref(644, 644, "Zekrom", "zekrom"),
        _ref(488, 488, "Cresselia", "cresselia"),
        _ref(491, 491, "Darkrai", "darkrai"),
    ]
    lookup = combined._build_reference_lookup(refs)

    tag_team = combined._match_references_for_card_name(
        name="Pikachu & Zekrom GX", reference_lookup=lookup
    )
    legend = combined._match_references_for_card_name(
        name="Darkrai & Cresselia Legend(Bottom)", reference_lookup=lookup
    )

    assert [r["pokedex_number"] for r in tag_team] == [25, 644]
    assert [r["pokedex_number"] for r in legend] == [488, 491]


def test_provider_fallback_exact_trainer_authority_wins_over_pokemon_phrase_matching(monkeypatch):
    cards = [
        {"id": "n-card", "name": "N", "rarity": "Classic Collection",
         "card_number": "101/101", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
        {"id": "misty-card", "name": "Misty", "rarity": "Classic Collection",
         "card_number": "18/132", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
    ]
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda _client, _set_id: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda _client, _set_id: [])
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda _client: [])
    monkeypatch.setattr(combined, "_list_trainer_reference_names", lambda _client: {"n", "misty"})
    monkeypatch.setattr(
        combined, "_list_authoritative_non_pokemon_name_supertypes",
        lambda _client, _names: {},
    )
    monkeypatch.setattr(
        combined, "_refresh_authoritative_canonical_cards",
        lambda **kwargs: {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0},
    )
    captured = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_SUBSET_SET_ROW, dry_run=False)

    assert [row["supertype"] for row in captured] == ["Trainer", "Trainer"]
    assert all(row["national_pokedex_numbers"] == [] for row in captured)


def test_provider_fallback_multi_subjects_persist_all_pokedex_numbers(monkeypatch):
    cards = [
        {"id": "tag-card", "name": "Pikachu & Zekrom GX", "rarity": "Classic Collection",
         "card_number": "33/181", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
    ]
    refs = [
        _ref(25, 25, "Pikachu", "pikachu"),
        _ref(644, 644, "Zekrom", "zekrom"),
    ]
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda _client, _set_id: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda _client, _set_id: [])
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda _client: refs)
    monkeypatch.setattr(combined, "_list_trainer_reference_names", lambda _client: set())
    monkeypatch.setattr(
        combined, "_list_authoritative_non_pokemon_name_supertypes",
        lambda _client, _names: {},
    )
    monkeypatch.setattr(
        combined, "_refresh_authoritative_canonical_cards",
        lambda **kwargs: {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0},
    )
    captured = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_SUBSET_SET_ROW, dry_run=False)

    assert len(captured) == 1
    assert captured[0]["supertype"] == "Pokémon"
    assert captured[0]["national_pokedex_numbers"] == [25, 644]
    assert captured[0]["source_payload"]["matched_pokedex_numbers"] == [25, 644]
    assert captured[0]["source_payload"]["matched_pokedex_number"] is None



def test_authoritative_non_pokemon_exact_name_supertype_wins_without_fuzzy_guess(monkeypatch):
    cards = [
        {"id": "switch-card", "name": "Switch", "rarity": "Common",
         "card_number": "127/128", "pokemon_tcg_api_id": None,
         "image_small_url": None, "image_large_url": None},
    ]
    monkeypatch.setattr(combined, "_list_cards_for_set", lambda _client, _set_id: cards)
    monkeypatch.setattr(combined, "_list_canonical_for_set", lambda _client, _set_id: [])
    monkeypatch.setattr(combined, "_list_pokemon_reference", lambda _client: [])
    monkeypatch.setattr(combined, "_list_trainer_reference_names", lambda _client: set())
    monkeypatch.setattr(
        combined, "_list_authoritative_non_pokemon_name_supertypes",
        lambda _client, _names: {"switch": "Trainer"},
    )
    monkeypatch.setattr(
        combined, "_refresh_authoritative_canonical_cards",
        lambda **kwargs: {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0},
    )
    captured = []
    monkeypatch.setattr(
        combined, "_upsert_canonical_rows",
        lambda _client, rows: captured.extend(rows) or len(rows),
    )

    combined._process_single_set(client=object(), set_row=_NORMAL_SET_ROW, dry_run=False)

    assert len(captured) == 1
    assert captured[0]["supertype"] == "Trainer"
    assert captured[0]["national_pokedex_numbers"] == []
