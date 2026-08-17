from __future__ import annotations

from backend.desirability.component_source import (
    expected_source_versions,
    matches_expected_versions,
)
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION
from backend.scripts import build_pokemon_set_desirability_inputs as combined


LEGACY_V1 = "pokemon_card_desirability_hit_policy_v1"


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

    assert result == {"status": "refreshed", "source": "pokemon_tcg_api", "rows_found": 2, "rows_upserted": 2}
    assert written[0]["supertype"] == "Pokémon"
    assert written[0]["national_pokedex_numbers"] == [877]
    assert written[1]["supertype"] == "Trainer"
    assert written[1]["subtypes"] == ["Supporter"]
    assert all(row["source"] == "pokemon_tcg_api" for row in written)


def test_authoritative_refresh_falls_back_cleanly_when_provider_is_not_ready(monkeypatch):
    monkeypatch.setattr(
        combined, "fetch_authoritative_api_set",
        lambda _set_id: (_ for _ in ()).throw(RuntimeError("not published yet")),
    )
    result = combined._refresh_authoritative_canonical_cards(
        client=object(),
        set_row={"id": "set-1", "canonical_key": "futureSet", "pokemon_api_set_id": "future"},
        dry_run=False,
    )
    assert result["status"] == "unavailable_using_fallback"
    assert result["rows_upserted"] == 0
