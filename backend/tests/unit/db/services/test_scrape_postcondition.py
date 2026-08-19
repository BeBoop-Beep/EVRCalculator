from backend.db.services.scrape_postcondition import (
    reconcile_source_variant_keys, _fetch_by_chunks, POSTGREST_IN_CHUNK_SIZE)

def test_partial_current_day_source_coverage_fails():
    result = reconcile_source_variant_keys([f"p{i}|v" for i in range(400)], ["p0|v"])
    assert result["success"] is False
    assert result["sourceCoverageRatio"] == 1 / 400

def test_complete_accepted_source_variant_coverage_succeeds():
    keys = ["p1|normal", "p1|reverse"]
    result = reconcile_source_variant_keys(keys, keys)
    assert result["success"] is True
    assert result["sourceCoverageRatio"] == 1.0

def test_chunked_fetch_reconciles_more_than_one_chunk_without_loss():
    values = [f"variant-{index}" for index in range(POSTGREST_IN_CHUNK_SIZE * 2 + 17)]
    seen_chunks = []
    class Query:
        def __init__(self, chunk): self.chunk = chunk
        def range(self, start, end): self.start, self.end = start, end; return self
        def execute(self):
            rows = [{"id": value} for value in self.chunk]
            return type("Result", (), {"data": rows[self.start:self.end + 1]})()
    rows = _fetch_by_chunks(values, lambda chunk: seen_chunks.append(list(chunk)) or Query(chunk))
    assert {row["id"] for row in rows} == set(values)
    assert [len(chunk) for chunk in seen_chunks] == [100, 100, 17]
