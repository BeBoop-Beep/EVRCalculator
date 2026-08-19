from backend.db.services.scrape_postcondition import reconcile_source_variant_keys

def test_partial_current_day_source_coverage_fails():
    result = reconcile_source_variant_keys([f"p{i}|v" for i in range(400)], ["p0|v"])
    assert result["success"] is False
    assert result["sourceCoverageRatio"] == 1 / 400

def test_complete_accepted_source_variant_coverage_succeeds():
    keys = ["p1|normal", "p1|reverse"]
    result = reconcile_source_variant_keys(keys, keys)
    assert result["success"] is True
    assert result["sourceCoverageRatio"] == 1.0
