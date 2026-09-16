from pathlib import Path

from backend.services import pokemon_new_set_discovery_service as service
from backend.services.tcgplayer_set_catalog_service import PRODUCT_TYPE_CARDS


def _cards_only(aggregations):
    """fetch_global_set_aggregations fake: returns `aggregations` for the cards product
    type and nothing for sealed, so existing cards-focused tests are unaffected by the
    sealed-discovery pass added alongside them."""
    def fake(_requester, _cache, product_type_names=None):
        source = (product_type_names or [PRODUCT_TYPE_CARDS])[0]
        return aggregations if source == PRODUCT_TYPE_CARDS else []
    return fake


def test_parse_tcgplayer_set_id_uses_url_identity():
    assert service.parse_tcgplayer_set_id(
        "https://infinite-api.tcgplayer.com/priceguide/set/24688/cards/?productTypeID=1"
    ) == "24688"
    assert service.parse_tcgplayer_set_id("https://example.test/no-id") is None


def test_discovery_is_idempotent_for_known_provider_id(monkeypatch, tmp_path: Path):
    root = tmp_path / "pokemon"
    root.mkdir()
    (root / "known.py").write_text(
        "SET_NAME = 'Known Set'\nCARD_DETAILS_URL = "
        "'https://infinite-api.tcgplayer.com/priceguide/set/42/cards/?productTypeID=1'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Brand New Set", "count": 100}]),
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (42, 0.99, "stable"),
    )
    result = service.discover_new_sets(commit=False, pokemon_root=root)
    assert result["detected"] == 0
    assert result["unchanged"] == 1


def test_dry_run_detects_without_writing(monkeypatch, tmp_path: Path):
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Brand New Set", "count": 100}]),
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (999, 0.95, "stable"),
    )
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2", lambda **kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    result = service.discover_new_sets(commit=False, pokemon_root=root)
    assert result["detected"] == 1
    assert result["dry_run"] is True


def test_commit_creates_one_stable_id_job_and_repeat_reuses_it(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    stored = {}
    monkeypatch.setattr(
        service, "_database_catalog",
        lambda: (set(), set(stored), set()),
    )
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Brand New Set", "count": 100}]),
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (999, 0.95, "stable"),
    )
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: stored.setdefault(
            kwargs["source_set_id"], kwargs,
        ) and {"disposition": "inserted"},
    )
    monkeypatch.setattr(service, "queue_alert", lambda *args, **kwargs: None)
    first = service.discover_new_sets(commit=True, pokemon_root=root)
    second = service.discover_new_sets(commit=True, pokemon_root=root)
    assert first["detected"] == 1
    assert second["detected"] == 0
    assert len(stored) == 1
    assert stored["999"]["source_set_id"] == "999"


def test_low_confidence_stable_id_becomes_manual_review(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    rows = []
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Ambiguous Set", "count": 10}]),
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (123, 0.55, "ambiguous"),
    )
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: rows.append(kwargs) or {"disposition": "inserted"},
    )
    monkeypatch.setattr(service, "queue_alert", lambda *args, **kwargs: None)
    result = service.discover_new_sets(commit=True, pokemon_root=root)
    assert result["manual_review"] == 1
    assert rows[0]["candidate_status"] == "manual_review"


def test_same_name_new_provider_id_is_not_prefiltered(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    (root / "known.py").write_text("SET_NAME = 'Same Name'\nCARD_DETAILS_URL = 'https://x/set/1/cards/'")
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(service, "fetch_global_set_aggregations", _cards_only([{"value": "Same Name"}]))
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (2, 0.99, "stable"))
    result = service.discover_new_sets(commit=False, pokemon_root=root)
    assert result["detected"] == 1


def test_sealed_only_new_set_is_detected(monkeypatch, tmp_path):
    """A set whose sealed products list before singles must be found even though the
    Cards aggregation never mentions it."""
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))

    def fake_aggregations(_requester, _cache, product_type_names=None):
        from backend.services.tcgplayer_set_catalog_service import PRODUCT_TYPE_CARDS, PRODUCT_TYPE_SEALED
        source = (product_type_names or [PRODUCT_TYPE_CARDS])[0]
        if source == PRODUCT_TYPE_SEALED:
            return [{"value": "Preorder Only Set", "count": 5}]
        # Cards is the required source: non-empty but with no candidate resolving to a
        # new identity, so this test's detection comes entirely from the sealed pass.
        return [{"value": "Some Other Known Set", "count": 1}]

    monkeypatch.setattr(service, "fetch_global_set_aggregations", fake_aggregations)
    seen_product_types = []

    from backend.services.tcgplayer_set_catalog_service import PRODUCT_TYPE_SEALED

    def fake_validate(_requester, _cache, _query, _filter, _expected, exception_label=None, product_type_names=None):
        seen_product_types.append(product_type_names)
        if product_type_names == (PRODUCT_TYPE_SEALED,):
            return (555, 0.99, "stable")
        return (None, 0.0, "no match")

    monkeypatch.setattr(service, "validate_candidate_set_id", fake_validate)
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=False, pokemon_root=root)

    sealed_evidence = [row for row in result["evidence"] if row["evidence_source"] == "sealed"]
    assert result["detected"] == 1
    assert (PRODUCT_TYPE_SEALED,) in seen_product_types
    assert sealed_evidence and sealed_evidence[0]["resolved_set_id"] == 555


def test_card_aggregation_failure_does_not_block_run(monkeypatch, tmp_path):
    """Cards is the required source (empty/failed aggregation fails the run, as before);
    Sealed is additive and must not take the whole run down with it."""
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))

    def fake_aggregations(_requester, _cache, product_type_names=None):
        from backend.services.tcgplayer_set_catalog_service import PRODUCT_TYPE_CARDS, PRODUCT_TYPE_SEALED
        source = (product_type_names or [PRODUCT_TYPE_CARDS])[0]
        if source == PRODUCT_TYPE_SEALED:
            raise RuntimeError("sealed endpoint down")
        return [{"value": "Brand New Set", "count": 1}]

    monkeypatch.setattr(service, "fetch_global_set_aggregations", fake_aggregations)
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (999, 0.95, "stable"))
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=False, pokemon_root=root)

    assert result["detected"] == 1
    assert result["sealed_aggregation_error"] == "sealed endpoint down"


def test_card_and_sealed_discovery_of_same_set_id_collapses_to_one_identity(monkeypatch, tmp_path):
    """A set that shows up in both the Cards and Sealed aggregations under the same
    provider name and resolves to the same setId must be recorded once, not twice."""
    root = tmp_path / "pokemon"
    root.mkdir()
    stored = {}
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(stored), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        lambda *_a, **_k: [{"value": "Dual Listed Set", "count": 10}],
    )
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (777, 0.99, "stable"))
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: stored.setdefault(
            kwargs["source_set_id"], kwargs,
        ) and {"disposition": "inserted"},
    )
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=True, pokemon_root=root)

    assert result["detected"] == 1
    assert result["unchanged"] == 1
    assert len(stored) == 1


def test_already_known_job_never_reaches_reconcile_rpc(monkeypatch, tmp_path):
    """An identity already tracked as a job (e.g. progressed past discovery) must never
    be re-submitted through reconcile_discovery_v2: client-side _classify_known short-
    circuits it before the RPC could even consider rewinding/overwriting the job."""
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), {"999"}, set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Already Running Set", "count": 100}]),
    )
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (999, 0.99, "stable"))
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("reconcile called for known job")),
    )
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=True, pokemon_root=root)

    assert result["detected"] == 0
    assert result["unchanged"] == 1


def test_reconcile_disposition_is_recorded_in_evidence(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        _cards_only([{"value": "Brand New Set", "count": 100}]),
    )
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (999, 0.95, "stable"))
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2", lambda **kwargs: {"disposition": "stale_observation_ignored"},
    )
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=True, pokemon_root=root)

    assert result["evidence"][0]["reconcile_disposition"] == "stale_observation_ignored"


def test_unresolved_evidence_is_persisted_and_deduplicated(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    stored = {}
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(stored), set()))
    monkeypatch.setattr(service, "fetch_global_set_aggregations", _cards_only([{"value": "Mystery"}]))
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (None, 0, "none"))
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: stored.setdefault(
            kwargs["source_set_id"], kwargs,
        ) and {"disposition": "inserted"},
    )
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)
    assert service.discover_new_sets(commit=True, pokemon_root=root)["manual_review"] == 1
    assert service.discover_new_sets(commit=True, pokemon_root=root)["unchanged"] == 1
    assert len(stored) == 1
    assert next(iter(stored)).startswith("unresolved:")


def test_unknown_names_have_priority_over_bounded_same_name_audit(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    for index in range(120):
        (root / f"known_{index}.py").write_text(
            f"SET_NAME = 'Known {index}'\nCARD_DETAILS_URL = 'https://x/set/{index + 1}/cards/'\n"
        )
    aggregations = [{"value": f"Known {index}"} for index in range(120)]
    aggregations.extend([{"value": "Unknown A"}, {"value": "Unknown B"}])
    seen = []
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set(), set()))
    monkeypatch.setattr(service, "fetch_global_set_aggregations", _cards_only(aggregations))
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda _requester, _cache, name, *_args, **_kwargs: seen.append(name) or (999, 0.99, "stable"),
    )

    service.discover_new_sets(
        commit=False, pokemon_root=root, max_candidates=2, max_same_name_audits=3,
    )

    assert seen[:2] == ["Unknown A", "Unknown B"]
    assert seen[2:] == ["Known 0", "Known 1", "Known 2"]
