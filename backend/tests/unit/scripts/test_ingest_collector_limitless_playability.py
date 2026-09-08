from datetime import date

from backend.scripts.ingest_collector_limitless_playability import collect, reconcile


class Client:
    def __init__(self, details, standings):
        self.details, self.standings = details, standings
    def get(self, path, params=None):
        return self.details if path.endswith("/details") else self.standings


def event():
    return {"id":"e1", "game":"PTCG", "format":"STANDARD", "name":"Event",
            "date":"2026-09-01T00:00:00.000Z", "players":32, "decklists":True,
            "specialRules":[], "bannedCards":[]}


def test_collect_all_non_energy_deck_groups_and_reject_custom_rules():
    details = event()
    standing = {"player":"p", "placing":1, "decklist":{
        "pokemon":[{"name":"Pikachu", "set":"SV", "number":"1", "count":2}],
        "trainer":[{"name":"Rare Candy", "set":"SV", "number":"2", "count":4}],
        "energy":[{"name":"Basic Lightning Energy", "count":10}]}}
    accepted, excluded, rows = collect(Client(details, [standing] * 32), [details], .8, 5)
    assert len(accepted) == 1 and not excluded
    assert {row["group"] for row in rows} == {"pokemon", "trainer"}
    details = {**details, "specialRules":["custom"]}
    assert collect(Client(details, [standing] * 32), [details], .8, 5)[1][0]["reasons"] == ["custom_rules"]


def test_reconcile_prefers_source_identifier_and_retains_ambiguity():
    row = {"event":{"id":"e1","name":"E","date":"2026-09-01T00:00:00Z","players":32,"decklists":1},
           "deckId":"d", "placing":1, "group":"trainer", "name":"Rare Candy", "set":"sv", "number":"2", "copies":4}
    matched = reconcile([row], {}, {("sv","2","rare candy"):{"fid"}}, {"rare candy":{"wrong"}}, date(2026, 9, 7))[0]
    assert matched["functional_reference_id"] == "fid"
    assert matched["raw_row_json"]["mappingMethod"] == "ptcgo_code_number_exact_name"
    ambiguous = reconcile([{**row, "set":"none"}], {}, {}, {"rare candy":{"a","b"}}, date(2026, 9, 7))[0]
    assert ambiguous["match_status"] == "ambiguous"
