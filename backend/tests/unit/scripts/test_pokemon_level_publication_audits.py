import copy
from types import SimpleNamespace

from backend.domain.pokemon.market_index import deterministic_fingerprint as market_fp
from backend.domain.pokemon.rip_stats import (POKEMON_RIP_STATS_CONTRACT_VERSION,
    POKEMON_RIP_STATS_METHODOLOGY_VERSION, POKEMON_RIP_STATS_WEIGHTING_VERSION, deterministic_fingerprint)
from backend.scripts import audit_pokemon_market_index_publication as market_audit
from backend.scripts import audit_pokemon_rip_stats_publication as rip_audit


class Result:
    def __init__(self, data): self.data = data


def market_rows():
    rows = []
    for day, multiplier, previous in (("2026-08-16", 1.0, None), ("2026-08-17", 1.1, "2026-08-16")):
        for key, basket, count in (("raw", 100, 20), ("top10", 60, 10)):
            value = basket * multiplier; constituents = [{"setId": "a", "setValue": value, "includedCardCount": count}]
            source = market_fp(constituents)
            rows.append({"index_key": key, "market_date": day, "basket_value": value,
                "normalized_index_value": 100 * multiplier, "daily_return": None if previous is None else .1,
                "previous_market_date": previous, "set_count": 1, "card_count": count,
                "cohort_fingerprint": "cohort", "source_generation_fingerprint": source,
                "constituents_json": constituents})
    return rows


class MarketQuery:
    def __init__(self, public): self.public = public
    def select(self, *_a): return self
    def eq(self, *_a): return self
    def limit(self, *_a): return self
    def execute(self): return Result([{"market_date": "2026-08-17", "payload_json": {"marketOverview": self.public}}])
class MarketClient:
    def __init__(self, public): self.public = public
    def table(self, *_a): return MarketQuery(self.public)


def test_market_audit_rejects_normalized_index_tamper(monkeypatch):
    expected = market_rows(); persisted = copy.deepcopy(expected); persisted[0]["normalized_index_value"] = 999
    monkeypatch.setattr(market_audit, "build_market_index_history", lambda *_a, **_k: expected)
    monkeypatch.setattr(market_audit, "read_index_history", lambda *_a, **_k: persisted)
    public = market_audit.build_market_overview(persisted, market_date="2026-08-17")
    result = market_audit.audit(MarketClient(public), "2026-08-17")
    assert result["status"] == "failed"
    assert any("normalized_index_value" in failure for failure in result["failures"])


def test_market_audit_rejects_public_basket_or_index_tamper(monkeypatch):
    rows = market_rows(); monkeypatch.setattr(market_audit, "build_market_index_history", lambda *_a, **_k: rows)
    monkeypatch.setattr(market_audit, "read_index_history", lambda *_a, **_k: rows)
    public = market_audit.build_market_overview(rows, market_date="2026-08-17"); public["raw"]["basketValue"] += 1
    result = market_audit.audit(MarketClient(public), "2026-08-17")
    assert result["status"] == "failed"
    assert any("marketOverview.raw.basketValue" in failure for failure in result["failures"])


def rip_fixture():
    members = [{"snapshot_id": "snap", "set_id": "a", "calculation_run_id": "run-a", "pack_cost": 5,
        "set_weight": .5, "artifact_outcome_count": 2, "artifact_sha256": "a" * 64, "source_market_date": "2026-08-17"},
        {"snapshot_id": "snap", "set_id": "b", "calculation_run_id": "run-b", "pack_cost": 10,
        "set_weight": .5, "artifact_outcome_count": 2, "artifact_sha256": "b" * 64, "source_market_date": "2026-08-17"}]
    provenance = [{"set_id": row["set_id"], "calculation_run_id": row["calculation_run_id"], "artifact_sha256": row["artifact_sha256"],
        "artifact_outcome_count": row["artifact_outcome_count"], "pack_cost": float(row["pack_cost"]), "market_date": "2026-08-17"} for row in members]
    fingerprint = deterministic_fingerprint(provenance)
    cohort = deterministic_fingerprint([{"set_id": "a"}, {"set_id": "b"}])
    payload = {"contractVersion": POKEMON_RIP_STATS_CONTRACT_VERSION, "population": {"setCount": 2, "outcomeCountPerSet": 2, "totalSourceOutcomeCount": 4, "cohortFingerprint": cohort, "sourceRunFingerprint": fingerprint},
        "packEconomics": {"expectedRetention": 1, "chanceToBeatCost": .5}, "typicalOpening": {"value": 5, "retention": .5},
        "upside": {"p95Value": 10, "p99Value": 20, "p95Retention": 1, "p99Retention": 2},
        "downside": {"hardLossProbability": .25, "softLossShareGivenLoss": .5},
        "onePackPerSet": {"setCount": 2, "totalPackCost": 15, "totalExpectedValue": 15, "expectedEntertainmentCost": 0},
        "entertainmentCost": {"expectedCostRatio": 0}, "methodology": {"version": POKEMON_RIP_STATS_METHODOLOGY_VERSION, "weightingVersion": POKEMON_RIP_STATS_WEIGHTING_VERSION}}
    master = {"id": "snap", "contract_version": POKEMON_RIP_STATS_CONTRACT_VERSION,
        "methodology_version": POKEMON_RIP_STATS_METHODOLOGY_VERSION, "weighting_version": POKEMON_RIP_STATS_WEIGHTING_VERSION,
        "eligible_cohort_count": 2, "exact_outcome_set_count": 2, "total_source_outcome_count": 4,
        "cohort_fingerprint": cohort, "source_run_fingerprint": fingerprint, "payload_json": payload}
    latest = {"market_date": "2026-08-17", "source_run_fingerprint": fingerprint, "payload_json": payload}
    return master, members, latest


class RipQuery:
    def __init__(self, rows): self.rows = rows; self.filters = []
    def select(self, *_a): return self
    def eq(self, column, value): self.filters.append((column, value)); return self
    def limit(self, *_a): return self
    def execute(self): return Result([row for row in self.rows if all(str(row.get(c)) == str(v) for c, v in self.filters)])
class RipClient:
    def __init__(self, master, members): self.master = master; self.members = members
    def table(self, name): return RipQuery([self.master] if name == "pokemon_rip_stats_snapshots" else self.members)


def run_rip(monkeypatch, master, members, latest):
    monkeypatch.setattr(rip_audit, "read_latest_pokemon_rip_stats", lambda *_a: latest)
    statuses = [SimpleNamespace(set_id="a", calculation_run_id="run-a"), SimpleNamespace(set_id="b", calculation_run_id="run-b")]
    monkeypatch.setattr(rip_audit, "evaluate_opening_simulation_freshness", lambda *_a, **_k: SimpleNamespace(ok=True, statuses=statuses))
    monkeypatch.setattr(rip_audit, "load_pack_outcome_artifact", lambda _c, run_id: SimpleNamespace(metadata={"raw_sha256": ("a" if run_id == "run-a" else "b") * 64, "outcome_count": 2}))
    return rip_audit.audit(RipClient(master, members), "2026-08-17")


def test_rip_audit_rejects_latest_payload_tamper(monkeypatch):
    master, members, latest = rip_fixture(); latest = copy.deepcopy(latest); latest["payload_json"]["packEconomics"]["expectedRetention"] = 9
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"


def test_rip_audit_rejects_wrong_methodology_unequal_counts_and_weight(monkeypatch):
    master, members, latest = rip_fixture(); wrong = copy.deepcopy(master); wrong["methodology_version"] = "wrong"
    assert run_rip(monkeypatch, wrong, members, latest)["status"] == "failed"
    master, members, latest = rip_fixture(); members[1]["artifact_outcome_count"] = 3
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"


def test_rip_audit_rejects_cohort_and_public_source_fingerprint_tampering(monkeypatch):
    master, members, latest = rip_fixture(); latest = copy.deepcopy(latest); latest["payload_json"]["population"]["cohortFingerprint"] = "wrong"
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"
    master, members, latest = rip_fixture(); latest = copy.deepcopy(latest); latest["payload_json"]["population"]["sourceRunFingerprint"] = "wrong"
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"
    master, members, latest = rip_fixture(); master["cohort_fingerprint"] = "wrong"
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"
    master, members, latest = rip_fixture(); members[0]["set_weight"] = .6
    assert run_rip(monkeypatch, master, members, latest)["status"] == "failed"
