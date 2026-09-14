"""Focused, mocked-DB tests for the maintained-cache axis provisioning
script -- proves the finite-broad-single-axis discovery contract without
touching a live database.
"""
from __future__ import annotations

from unittest.mock import patch

import backend.scripts.provision_market_explorer_maintained_cards_axes as prov


FAKE_OPTIONS = {
    "eras": [
        {"id": "era-sv", "label": "Scarlet and Violet"},
        {"id": "era-swsh", "label": "Sword and Shield"},
    ],
    "cardSegments": {
        "segments": [
            {"key": "specialIllustrationRare", "label": "Special Illustration Rare"},
            {"key": "illustrationRare", "label": "Illustration Rare"},
        ],
    },
    "cardRarities": {"rarities": [
        {"key": "specialIllustrationRare", "label": "Special Illustration Rare"},
        {"key": "illustrationRare", "label": "Illustration Rare"},
        {"key": "legend", "label": "LEGEND"},
    ]},
    "priceSegments": {
        "cards": [
            {"id": "obtainable", "label": "Obtainable"},
            {"id": "intermediate", "label": "Intermediate"},
            {"id": "premium", "label": "Premium"},
        ],
    },
    "releaseAgeCohorts": [
        {"id": "new", "label": "New"},
        {"id": "established", "label": "Established"},
    ],
}


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.eq_filters = {}
        self._updating = None

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.eq_filters[field] = value
        return self

    def limit(self, _n):
        return self

    def update(self, values):
        self._updating = values
        return self

    def execute(self):
        if self._updating is not None:
            fingerprint = self.eq_filters.get("query_fingerprint")
            row = self.client.cache_rows.get(fingerprint)
            if row and row.get("status") == self.eq_filters.get("status", row.get("status")):
                row.update(self._updating)
            return Response([])
        fingerprint = self.eq_filters.get("query_fingerprint")
        row = self.client.cache_rows.get(fingerprint)
        return Response([dict(row)] if row else [])


class Client:
    def __init__(self, cache_rows=None):
        self.cache_rows = cache_rows or {}

    def table(self, name):
        return Query(self, name)


def test_candidate_discovery_covers_era_rarity_price_and_release_age_axes():
    """Items 4/5/6: maintained spec discovery includes canonical rarity
    segments, price segments, and release-age cohorts -- pulled from the
    live options registry, never a hardcoded list."""
    with patch.object(prov, "build_market_explorer_filter_options", return_value=FAKE_OPTIONS):
        candidates = prov.discover_candidate_specs(Client())
    kinds = {kind for _, kind, _ in candidates}
    assert kinds == {"era", "rarity_segment", "price_segment", "release_age"}
    labels = {label for label, _, _ in candidates}
    assert "rarity:Special Illustration Rare" in labels
    assert "price:Premium" in labels
    assert "releaseAge:Established" in labels
    assert "era:Scarlet and Violet" in labels


def test_no_compound_or_pokemon_axis_is_ever_discovered():
    """Item 8: Pokemon and compound/combinatorial markets are not
    mass-maintained -- every discovered spec has exactly one active
    non-asset filter axis and no Pokemon axis at all."""
    with patch.object(prov, "build_market_explorer_filter_options", return_value=FAKE_OPTIONS):
        candidates = prov.discover_candidate_specs(Client())
    for _, _, spec in candidates:
        assert list(spec["pokemonIds"]) == []
        active_axes = sum(bool(spec[key]) for key in (
            "eraIds", "setIds", "segmentIds", "priceSegmentIds", "releaseAgeCohortIds",
        ))
        assert active_axes == 1, spec


def test_filter_only_rarity_is_never_discovered_for_maintained_provisioning():
    with patch.object(prov, "build_market_explorer_filter_options", return_value=FAKE_OPTIONS):
        candidates = prov.discover_candidate_specs(Client())
    rarity_ids = {spec["segmentIds"][0] for _, kind, spec in candidates if kind == "rarity_segment"}
    assert rarity_ids == {"specialIllustrationRare", "illustrationRare"}
    assert "legend" not in rarity_ids


def test_semantically_identical_screen_and_builder_spec_share_one_fingerprint():
    """Item 7: a prepared Screen's spec and an equivalent hand-built Builder
    spec must normalize to the identical fingerprint this script keys on --
    proving provisioning a Screen's market also covers its Builder
    equivalent, and vice versa, with no separate identity."""
    from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

    screen_spec = normalize_query_spec(asset="cards", mode="all", release_age_cohort_ids=["established"])
    builder_spec = normalize_query_spec(
        asset="cards", mode="all", era_ids=[], set_ids=[], segment_ids=[],
        pokemon_ids=[], price_segment_ids=[], release_age_cohort_ids=["established"], top_n=None,
    )
    assert query_fingerprint(screen_spec) == query_fingerprint(builder_spec)


def test_already_maintained_candidate_is_skipped_not_rebuilt():
    """Item 12 (shared contract): an already-current maintained cache is
    never rebuilt merely because the provisioning script ran again."""
    from backend.domain.pokemon.market_explorer_query import normalize_query_spec, query_fingerprint

    spec = normalize_query_spec(asset="cards", mode="all", release_age_cohort_ids=["established"])
    fingerprint = query_fingerprint(spec)
    client = Client(cache_rows={fingerprint: {
        "query_fingerprint": fingerprint, "status": "ready", "cache_kind": "maintained",
        "computed_through": "2026-09-05",
    }})
    report = prov.provision_one(
        client, commit=True, label="releaseAge:Established", spec_kind="release_age", spec=spec,
    )
    assert report.already_maintained is True
    assert report.built is False
    assert report.promoted is False


def test_dry_run_never_writes():
    with patch.object(prov, "build_market_explorer_filter_options", return_value=FAKE_OPTIONS):
        result = prov.run_provision(Client(), commit=False)
    assert result["dry_run"] is True
    assert result["built"] == 0
    assert result["promoted"] == 0
    assert result["candidates_considered"] > 0


def test_only_label_is_exact_and_process_isolatable():
    with patch.object(prov, "build_market_explorer_filter_options", return_value=FAKE_OPTIONS):
        result = prov.run_provision(
            Client(), commit=False, only_labels=("price:Premium",),
        )
    assert result["candidates_considered"] == 1
    assert result["reports"][0]["label"] == "price:Premium"


def test_a_failed_candidate_does_not_block_the_others():
    """Cache prewarm/provisioning failure isolation, mirrored from the
    accepted prewarm-orchestrator contract: one candidate's build error must
    not abort the remaining candidates."""
    from backend.domain.pokemon.market_explorer_query import normalize_query_spec

    ok_spec = normalize_query_spec(asset="cards", mode="all", price_segment_ids=["obtainable"])
    bad_spec = normalize_query_spec(asset="cards", mode="all", price_segment_ids=["premium"])

    class ExplodingClient(Client):
        def table(self, name):
            return Query(self, name)

    client = ExplodingClient()
    calls = []

    def fake_provision_one(_client, *, commit, label, spec_kind, spec):
        calls.append(label)
        if "premium" in label.lower():
            return prov.AxisReport(label=label, spec_kind=spec_kind, fingerprint="bad", error="boom")
        return prov.AxisReport(label=label, spec_kind=spec_kind, fingerprint="ok", built=True, promoted=True)

    with patch.object(prov, "discover_candidate_specs", return_value=[
        ("price:Obtainable", "price_segment", ok_spec),
        ("price:Premium", "price_segment", bad_spec),
    ]), patch.object(prov, "provision_one", side_effect=fake_provision_one):
        result = prov.run_provision(client, commit=True)

    assert calls == ["price:Obtainable", "price:Premium"]
    assert result["built"] == 1
    assert result["failures"] == 1
