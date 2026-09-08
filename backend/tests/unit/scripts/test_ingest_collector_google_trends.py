from backend.scripts.ingest_collector_google_trends import collect, query_for
from backend.desirability.google_trends import TrendProviderResponse


class Provider:
    provider_name="fake"
    def fetch_interest(self, *, terms, timeframe, geo, query_type):
        return TrendProviderResponse(status="captured",interest_by_term={term:(50 if term=="Anchor" else 25) for term in terms})


def test_queries_are_disambiguated():
    assert query_for("trainer","Cynthia") == "Cynthia Pokemon"
    assert query_for("trainer", "Will", {"Will": "common-word collision"}) == "Will Pokemon trainer"
    assert query_for("artist","Arita") == "Arita Pokemon cards"


def test_anchor_scaling_and_provenance():
    rows, telemetry=collect(Provider(),[{"id":"1","display_name":"Cynthia"}],"trainer","US","today 12-m","Anchor",0)
    assert rows[0]["normalized_observation_score"] == 50
    assert rows[0]["raw_row_json"]["sourceStatus"] == "valid"
    assert telemetry["networkRequests"] == 1


def test_observed_zero_is_explicitly_genuine_zero():
    class Zero(Provider):
        def fetch_interest(self, *, terms, timeframe, geo, query_type):
            return TrendProviderResponse(status="captured", interest_by_term={terms[0]:0, terms[-1]:50})
    rows, _=collect(Zero(),[{"id":"1","display_name":"Cynthia"}],"trainer","US","today 12-m","Anchor",0)
    assert rows[0]["raw_row_json"]["sourceStatus"] == "genuine_zero"
