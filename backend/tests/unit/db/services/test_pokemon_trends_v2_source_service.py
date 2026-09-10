from backend.db.services.pokemon_trends_v2_source_service import load_pokemon_trends_v2_run


class Query:
    def __init__(self, rows): self.data = rows
    def select(self, *_): return self
    def eq(self, *_): return self
    def limit(self, *_): return self
    def order(self, *_): return self
    def execute(self): return self


class Client:
    def __init__(self, run, observations): self.run=run; self.observations=observations
    def table(self, name): return Query(self.run if name == "pokemon_collector_source_runs" else self.observations)


def test_exact_run_read_preserves_failed_as_null():
    run=[{"id":"run-1","source_name":"google_trends_pokemon_v2","capture_version":"v2","status":"partial_failure","item_count":1025}]
    observations=[]
    for i in range(1025):
        failed=i >= 1020
        observations.append({"collector_entity_id":str(i),"external_entity_key":f"pokedex:{i+1}",
            "normalized_observation_score":None if failed else 50,"raw_value":None if failed else 10,
            "raw_row_json":{"classification":"failed" if failed else "SCORED"}})
    result=load_pokemon_trends_v2_run("run-1",client=Client(run,observations))
    assert result["observations"][-1]["calibratedTrendsValue"] is None
    assert {row["sourceRunId"] for row in result["observations"]} == {"run-1"}
