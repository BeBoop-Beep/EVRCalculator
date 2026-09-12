from backend.desirability.google_trends import TrendProviderResponse
from backend.scripts.capture_pokemon_trends_anchor_ladder_v2 import (
    assign_initial_anchor, classify_and_record,
)


class Provider:
    def __init__(self): self.calls = []
    def fetch_interest(self, **kwargs):
        self.calls.append(kwargs)
        terms = kwargs["terms"]
        return TrendProviderResponse(status="captured", interest_by_term={terms[0]: 20.0, terms[1]: 10.0})


def test_anchor_subject_uses_frozen_lower_rung_instead_of_duplicate_query():
    provider = Provider()
    subject = {"pokemon_reference_id": 324, "pokedex_number": 324,
               "pokemon_name": "Torkoal", "fan_popularity_score": 60.0}
    row = classify_and_record(provider, subject, {"Stunky": 2.2236}, "manifest-v1", {})
    assert provider.calls[0]["terms"] == ["Stunky", "Torkoal"]
    assert row.assigned_anchor == "Torkoal"
    assert row.actual_query_anchor == "Stunky"
    assert row.escalated is True
    assert row.retry_count == 1
    assert row.classification == "SCORED"


def test_non_collision_anchor_assignment_and_query_are_unchanged():
    provider = Provider()
    subject = {"pokemon_reference_id": 18, "pokedex_number": 18,
               "pokemon_name": "Pidgeot", "fan_popularity_score": 60.0}
    row = classify_and_record(provider, subject, {"Torkoal": 8.0}, "manifest-v1", {})
    assert assign_initial_anchor(60.0) == "Torkoal"
    assert provider.calls[0]["terms"] == ["Torkoal", "Pidgeot"]
    assert row.assigned_anchor == "Torkoal"
    assert row.actual_query_anchor == "Torkoal"
    assert row.escalated is False
