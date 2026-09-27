from backend.benchmarking.publisher_v1 import publish_candidate


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_a): return self
    def eq(self, *_a): return self
    def limit(self, *_a): return self
    def execute(self): return type("R", (), {"data": self.rows})()


class Client:
    def __init__(self, previous=None): self.previous, self.rpc_args = previous, None
    def table(self, _name): return Query([{"id": self.previous}] if self.previous else [])
    def rpc(self, name, args):
        self.rpc_args = (name, args)
        return Query("pub-1")


def test_publisher_passes_revision_predecessor_to_atomic_rpc():
    client = Client("prior-1")
    candidate = {"market_date": "2026-09-15", "expected_entity_count": 2, "expected_row_count": 8,
                 "publish_rpc_request": {"rpc": "publish_pokemon_rip_benchmark_v1", "arguments": {
                     "p_header": {"benchmark_key": "b", "calibration_version": "c", "market_date": "2026-09-15"},
                     "p_rows": [], "p_expected_previous_id": None}}}
    result = publish_candidate(client, candidate)
    assert result["publication_id"] == "pub-1"
    assert client.rpc_args[1]["p_expected_previous_id"] == "prior-1"
