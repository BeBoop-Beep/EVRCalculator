from pathlib import Path


def test_runner_threads_same_market_date_to_parent_and_stage1():
    source = (Path(__file__).resolve().parents[3] / "jobs" / "evr_runner.py").read_text(encoding="utf-8")
    assert 'market_date=metadata.get("market_date")' in source
    parent = source.index("persist_parent_run_with_price_snapshots(")
    stage1 = source.index("run_stage1_sealed_product_rip(", parent)
    assert 'market_date=metadata.get("market_date")' in source[parent:stage1]
    assert 'market_date=metadata.get("market_date")' in source[stage1:stage1 + 700]
