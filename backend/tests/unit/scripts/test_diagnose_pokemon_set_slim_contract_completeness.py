from backend.scripts import diagnose_pokemon_set_slim_contract_completeness as diagnose


def test_read_only_guard_constant_is_true():
    assert diagnose.READ_ONLY_DIAGNOSTIC is True


# ---------------------------------------------------------------------------
# is_special_subset_name
# ---------------------------------------------------------------------------


def test_is_special_subset_name_matches_known_patterns():
    assert diagnose.is_special_subset_name("SWSH Black Star Promos") is True
    assert diagnose.is_special_subset_name("Silver Tempest Trainer Gallery") is True
    assert diagnose.is_special_subset_name("Shining Fates Shiny Vault") is True
    assert diagnose.is_special_subset_name("McDonald's Collection 2022") is True


def test_is_special_subset_name_does_not_match_mainline_sets():
    assert diagnose.is_special_subset_name("Crown Zenith") is False
    assert diagnose.is_special_subset_name("Prismatic Evolutions") is False
    assert diagnose.is_special_subset_name(None) is False
    assert diagnose.is_special_subset_name("") is False


# ---------------------------------------------------------------------------
# classify_top_chase_root_cause
# ---------------------------------------------------------------------------


def _top_chase_base(**overrides):
    base = dict(
        has_dashboard_30d=False,
        has_dashboard_365d=False,
        top_chase_cards_count=0,
        top_chase_history_count=0,
        source_observation_count=0,
        canonical_card_count=0,
        variant_count=0,
        is_special_subset=False,
    )
    base.update(overrides)
    return base


def test_top_chase_classification_when_dashboard_row_missing_entirely():
    cause = diagnose.classify_top_chase_root_cause(**_top_chase_base())
    assert cause == "missing_market_dashboard_snapshot_row"


def test_top_chase_classification_healthy_when_30d_row_has_cards():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_30d=True, top_chase_cards_count=10, top_chase_history_count=10)
    )
    assert cause == "healthy"


def test_top_chase_classification_dashboard_row_wrong_window_key():
    """The Phase 5D dominant case: a 365d row exists with cards, but the
    endpoint queries window_key='30d' by default and finds nothing."""
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_365d=True, top_chase_cards_count=10, top_chase_history_count=10)
    )
    assert cause == "dashboard_row_wrong_window_key"


def test_top_chase_classification_cards_exist_but_histories_empty():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_30d=True, top_chase_cards_count=10, top_chase_history_count=0)
    )
    assert cause == "cards_exist_but_histories_empty"


# ---------------------------------------------------------------------------
# is_top_chase_endpoint_repairable_from_365d (Phase 5E)
# ---------------------------------------------------------------------------


def test_is_top_chase_endpoint_repairable_from_365d_true_for_wrong_window():
    assert diagnose.is_top_chase_endpoint_repairable_from_365d("dashboard_row_wrong_window_key") is True


def test_is_top_chase_endpoint_repairable_from_365d_false_for_other_causes():
    for cause in (
        "healthy",
        "missing_market_dashboard_snapshot_row",
        "cards_exist_but_histories_empty",
        "special_subset_not_applicable",
        "canonical_variant_mapping_missing",
        "source_observations_missing",
        "source_observations_exist_but_snapshot_not_built",
        "unknown",
    ):
        assert diagnose.is_top_chase_endpoint_repairable_from_365d(cause) is False


def test_top_chase_classification_dashboard_row_exists_but_cards_json_empty_special_subset():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_365d=True, is_special_subset=True)
    )
    assert cause == "special_subset_not_applicable"


def test_top_chase_classification_canonical_variant_mapping_missing():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_365d=True, source_observation_count=5, canonical_card_count=0, variant_count=0)
    )
    assert cause == "canonical_variant_mapping_missing"


def test_top_chase_classification_source_observations_missing():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_365d=True, canonical_card_count=10, variant_count=10, source_observation_count=0)
    )
    assert cause == "source_observations_missing"


def test_top_chase_classification_source_observations_exist_but_snapshot_not_built():
    cause = diagnose.classify_top_chase_root_cause(
        **_top_chase_base(has_dashboard_365d=True, canonical_card_count=10, variant_count=10, source_observation_count=5)
    )
    assert cause == "source_observations_exist_but_snapshot_not_built"


# ---------------------------------------------------------------------------
# classify_pull_rates_root_cause
# ---------------------------------------------------------------------------


def _pull_rates_base(**overrides):
    base = dict(
        has_page_snapshot=False,
        has_pull_rate_assumptions=False,
        has_simulation_snapshot=False,
        is_special_subset=False,
    )
    base.update(overrides)
    return base


def test_pull_rates_classification_healthy():
    cause = diagnose.classify_pull_rates_root_cause(
        **_pull_rates_base(has_page_snapshot=True, has_pull_rate_assumptions=True)
    )
    assert cause == "healthy"


def test_pull_rates_classification_missing_simulation_snapshot():
    cause = diagnose.classify_pull_rates_root_cause(**_pull_rates_base())
    assert cause == "missing_simulation_snapshot"


def test_pull_rates_classification_missing_page_snapshot_row_when_simulation_exists():
    cause = diagnose.classify_pull_rates_root_cause(**_pull_rates_base(has_simulation_snapshot=True))
    assert cause == "missing_page_snapshot_row"


def test_pull_rates_classification_special_or_unsupported_set_type():
    """Unsupported/special set types (promos, trainer galleries, mini sets)
    are flagged distinctly rather than as a generic missing-data gap."""
    cause = diagnose.classify_pull_rates_root_cause(**_pull_rates_base(is_special_subset=True))
    assert cause == "special_subset_not_applicable"

    cause_with_page = diagnose.classify_pull_rates_root_cause(
        **_pull_rates_base(has_page_snapshot=True, is_special_subset=True)
    )
    assert cause_with_page == "special_subset_not_applicable"


def test_pull_rates_classification_source_exists_but_builder_does_not_read_it():
    cause = diagnose.classify_pull_rates_root_cause(**_pull_rates_base(has_page_snapshot=True))
    assert cause == "source_exists_but_payload_builder_does_not_read_it"


# ---------------------------------------------------------------------------
# classify_shell_root_cause
# ---------------------------------------------------------------------------


def _shell_base(**overrides):
    base = dict(
        has_page_snapshot=False,
        has_split_shell_columns=False,
        has_simulation_snapshot=False,
        is_special_subset=False,
    )
    base.update(overrides)
    return base


def test_shell_classification_healthy():
    cause = diagnose.classify_shell_root_cause(
        **_shell_base(has_page_snapshot=True, has_split_shell_columns=True)
    )
    assert cause == "healthy"


def test_shell_classification_missing_page_snapshot_row():
    """The 138/171-set case: no pokemon_set_page_snapshot_latest row at all,
    and no upstream simulation data either."""
    cause = diagnose.classify_shell_root_cause(**_shell_base())
    assert cause == "missing_simulation_snapshot"


def test_shell_classification_no_page_snapshot_row_when_simulation_exists():
    cause = diagnose.classify_shell_root_cause(**_shell_base(has_simulation_snapshot=True))
    assert cause == "no_page_snapshot_row"


def test_shell_classification_row_exists_but_split_columns_missing():
    cause = diagnose.classify_shell_root_cause(
        **_shell_base(has_page_snapshot=True, has_split_shell_columns=False)
    )
    assert cause == "page_snapshot_row_missing_split_columns"


def test_shell_classification_special_subset():
    cause = diagnose.classify_shell_root_cause(**_shell_base(is_special_subset=True))
    assert cause == "special_subset_not_applicable"


# ---------------------------------------------------------------------------
# recommend_next_action
# ---------------------------------------------------------------------------


def test_recommend_next_action_all_healthy():
    action = diagnose.recommend_next_action(
        top_chase_root_cause="healthy", pull_rates_root_cause="healthy", shell_root_cause="healthy"
    )
    assert action == "no_action_needed"


def test_recommend_next_action_special_subset_only():
    action = diagnose.recommend_next_action(
        top_chase_root_cause="special_subset_not_applicable",
        pull_rates_root_cause="special_subset_not_applicable",
        shell_root_cause="special_subset_not_applicable",
    )
    assert action == "no_action_special_subset"


def test_recommend_next_action_prioritizes_page_snapshot_rebuild_over_window_key_fix():
    """A shell page-snapshot rebuild is cheaper/higher-leverage than a
    top-chase window-key fix, so it must win when both apply."""
    action = diagnose.recommend_next_action(
        top_chase_root_cause="dashboard_row_wrong_window_key",
        pull_rates_root_cause="healthy",
        shell_root_cause="no_page_snapshot_row",
    )
    assert action == "rebuild_page_snapshot"


def test_recommend_next_action_window_key_fix_is_the_dominant_standalone_recommendation():
    action = diagnose.recommend_next_action(
        top_chase_root_cause="dashboard_row_wrong_window_key",
        pull_rates_root_cause="healthy",
        shell_root_cause="healthy",
    )
    assert action == "rebuild_market_dashboard_snapshot_with_30d_window"


def test_recommend_next_action_simulation_pipeline_outranks_smaller_gaps():
    """missing_simulation_snapshot is the deepest, most foundational blocker
    (it blocks shell and pull-rates, and precedes everything downstream), so
    it must win over a top-chase-only gap even when both are present."""
    action = diagnose.recommend_next_action(
        top_chase_root_cause="missing_market_dashboard_snapshot_row",
        pull_rates_root_cause="missing_simulation_snapshot",
        shell_root_cause="missing_simulation_snapshot",
    )
    assert action == "run_simulation_pipeline_then_rebuild_snapshots"


def test_recommend_next_action_unknown_falls_back_to_investigate_further():
    action = diagnose.recommend_next_action(
        top_chase_root_cause="unknown", pull_rates_root_cause="unknown", shell_root_cause="unknown"
    )
    assert action == "investigate_further"
