from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[3] / "scripts" / "refresh_stale_public_snapshots.py").read_text(encoding="utf-8")


def test_global_set_values_refresh_after_per_set_market_and_before_other_globals():
    coordinated = SOURCE.index("_maybe_rebuild_coordinated_market(", SOURCE.index("# Rebuild order for the remaining families"))
    set_values = SOURCE.index("_maybe_rebuild_explore_set_values(", coordinated)
    movers = SOURCE.index("_maybe_rebuild_explore_card_movers(", set_values)
    rankings = SOURCE.index("_maybe_rebuild_rankings(", movers)
    assert coordinated < set_values < movers < rankings


def test_global_set_value_refresh_is_fail_closed():
    function = SOURCE[SOURCE.index("def _maybe_rebuild_explore_set_values("):SOURCE.index("def _maybe_rebuild_set_page(")]
    assert 'summary.global_failed.append("explore_set_values: promoted market date unavailable")' in function
    assert 'summary.global_failed.append(f"explore_set_values: {exc}")' in function
    assert "upsert_explore_set_value_snapshot(candidate" in function
