"""Serving-release authority: the DB pointer's model selects the whole serving generation."""
import pytest

from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import product_family_rankings_service as pfr
from backend.db.services import rip_release as rel
from backend.db.services import set_rip_service
from backend.desirability import scoring_config as sc
from backend.desirability.overall_versioned_publication import rank_and_tier
from backend.tests.unit.db.services.test_product_family_rankings_service import row as v12_row

V12, V14 = sc.OVERALL_RIP_V12_VERSION, sc.OVERALL_RIP_V14_VERSION
TARGETS = [{"set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current", "name": "Alpha", "logo_image_url": "logo"}]


class Q:
    def __init__(self, rows, log, name):
        self.rows, self.log, self.name = list(rows), log, name

    def select(self, fields="*"):
        self.log.append((self.name, fields))
        return self

    def eq(self, k, v):
        self.rows = [r for r in self.rows if r.get(k) == v]
        return self

    def in_(self, k, values):
        self.rows = [r for r in self.rows if r.get(k) in values]
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


class Db:
    """Fake production: a pointer to a published run, sealed rows carrying BOTH generations, a generic ledger."""

    def __init__(self, sealed_rows, ledger_scores, model=V12):
        self.model, self.sealed, self.ledger_scores, self.log = model, sealed_rows, ledger_scores, []

    def set_pointer(self, model):
        self.model = model

    def _ledger(self):
        material = [{"sealed_product_id": pid, "source_result_id": pid + "-r", "score": s, "component_lineage": {}}
                    for pid, s in self.ledger_scores.items()]
        return [{"model_version": self.model, "publication_run_id": "run", "rankings_generation_id": "rg",
                 "set_page_generation_id": "sg", "market_date": "2026-09-15", "formula_fingerprint": "f",
                 "cohort_fingerprint": "c", **r} for r in rank_and_tier(material)]

    def table(self, name):
        if name == rel.POINTER_TABLE:
            return Q([{"scope": "pokemon", "publication_run_id": "run"}], self.log, name)
        if name == rel.RUN_TABLE:
            return Q([{"id": "run", "model_version": self.model, "status": "published"}], self.log, name)
        if name == "pokemon_overall_rip_active_v":
            return Q(self._ledger(), self.log, name)
        if name == "simulation_sealed_product_results":
            return Q(self.sealed, self.log, name)
        if name in ("sealed_products", "pokemon_set_chase_accessibility_snapshot_latest"):
            return Q([], self.log, name)
        raise AssertionError(name)

    def selects(self, name):
        return [f for n, f in self.log if n == name]


def _sealed():
    a = v12_row("A", overall=80, financial=70)   # V12 leader
    b = v12_row("B", overall=70, financial=60)
    for r, v5 in ((a, 40.0), (b, 55.0)):
        r.update(financial_rip_v5_score=v5, financial_rip_v5_version=FINANCIAL_RIP_V5_VERSION,
                 financial_rip_v5_status="ready", financial_rip_v5_rankable=True)
    return [a, b]


LEDGER = {"A": 60.0, "B": 90.0}  # V14 reverses the order


def _order(payload):
    return [p["sealedProductId"] for p in payload["families"]["booster_box"]["products"]]


# ------------------------------------------------------------------ bundle

def test_bundles_map_the_whole_generation_and_unknown_models_fail_closed():
    a, b = rel.bundle_for_model(V12), rel.bundle_for_model(V14)
    assert (a.financial_version, a.public_contract_version, a.ranking_method_version, a.overall_target_key,
            a.financial_target_key) == (sc.FINANCIAL_RIP_V4_VERSION, "public_rip_contract_v11", "budget_product_ranking_v1",
                                        "overallRipV12", "financialRipV4")
    assert a.best_open_method_versions[0].endswith("v2_dual_financial_v4_overall_v12") and len(a.best_open_method_versions) == 2
    assert (b.financial_version, b.public_contract_version, b.ranking_method_version, b.overall_target_key,
            b.financial_target_key) == (FINANCIAL_RIP_V5_VERSION, "public_rip_contract_v12", "budget_product_ranking_v2",
                                        "overallRipV14", "financialRipV5")
    assert b.best_open_method_versions == ("budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14",)
    assert a.overall_source == rel.SOURCE_LIVE_V12_STORAGE and b.overall_source == rel.SOURCE_GENERIC_LEDGER
    assert a.requires_v5_schema is False and b.requires_v5_schema is True
    for bad in ("overall_rip_v99", None, "", sc.OVERALL_RIP_V10_VERSION):
        with pytest.raises(rel.UnknownRipRelease):
            rel.bundle_for_model(bad)


def test_pointer_resolution_is_exactly_two_reads_and_unknown_model_never_becomes_v12():
    db = Db(_sealed(), LEDGER)
    assert rel.resolve_active_release(db).overall_version == V12
    assert len(db.log) == 2
    db.set_pointer("overall_rip_v99")
    with pytest.raises(rel.UnknownRipRelease):
        rel.resolve_active_release(db)
    with pytest.raises(rel.UnknownRipRelease):  # the marked fallback does NOT swallow an unknown model
        rel.resolve_release_or_marked_fallback(db)


def test_unreadable_pointer_uses_the_marked_static_fallback_only():
    class Broken:
        def table(self, name):
            raise RuntimeError("db down")
    b = rel.resolve_release_or_marked_fallback(Broken())
    assert b.overall_version == sc.CANONICAL_OVERALL_RIP_VERSION and b.resolved_from == "static_fallback"
    assert rel.resolve_active_release.__name__ == "resolve_active_release"
    assert rel.bundle_for_model(V12).resolved_from == "pointer"


# ------------------------------------------------------------------ query shape

def test_v12_select_is_the_historical_list_and_never_names_an_unlanded_v5_column():
    b12, b14 = rel.bundle_for_model(V12), rel.bundle_for_model(V14)
    assert pfr._result_fields(b12) == pfr.RESULT_FIELDS and "v5" not in pfr._result_fields(b12)
    assert pfr._result_fields(None) == pfr.RESULT_FIELDS
    v14 = pfr._result_fields(b14)
    assert v14.startswith(pfr.RESULT_FIELDS) and all(c in v14 for c in (
        "financial_rip_v5_score", "financial_rip_v5_version", "financial_rip_v5_status", "financial_rip_v5_rankable"))


def test_dormant_deploy_under_v12_never_selects_v5_columns_even_when_the_code_knows_them():
    db = Db(_sealed(), LEDGER, model=V12)
    pfr.build_product_family_rankings(db, set_targets=TARGETS)
    assert db.selects("simulation_sealed_product_results") == [pfr.RESULT_FIELDS]
    assert "pokemon_overall_rip_active_v" not in {n for n, _ in db.log}  # V12 does not read the (stale) ledger


# ------------------------------------------------------------------ service behavior

def test_v12_release_ranks_by_v12_and_v4_exactly_as_before():
    db = Db(_sealed(), LEDGER, model=V12)
    payload = pfr.build_product_family_rankings(db, set_targets=TARGETS)
    assert _order(payload) == ["A", "B"]
    p = payload["families"]["booster_box"]["products"][0]
    assert p["overallRipScore"] == 80 and p["overallRipVersion"] == V12 and p["financialRipScore"] == 70
    assert p["financialRipVersion"] == sc.FINANCIAL_RIP_V4_VERSION


def test_v14_release_uses_v14_and_v5_with_no_v4_or_v12_fallback():
    db = Db(_sealed(), LEDGER, model=V14)
    payload = pfr.build_product_family_rankings(db, set_targets=TARGETS)
    assert _order(payload) == ["B", "A"]                      # V14 order, opposite of V12
    top = payload["families"]["booster_box"]["products"][0]
    assert top["overallRipScore"] == 90.0 and top["overallRipVersion"] == V14
    assert top["financialRipScore"] == 55.0 and top["financialRipVersion"] == FINANCIAL_RIP_V5_VERSION
    assert set(pfr._result_fields(rel.bundle_for_model(V14)).split(",")) >= {"financial_rip_v5_score"}
    assert "financial_rip_v5_score" in db.selects("simulation_sealed_product_results")[0]


def test_v14_financial_v5_is_the_tie_break_and_v4_never_is():
    rows = _sealed()
    db = Db(rows, {"A": 75.0, "B": 75.0}, model=V14)            # exact Overall tie
    assert _order(pfr.build_product_family_rankings(db, set_targets=TARGETS)) == ["B", "A"]  # V5 55 > 40; V4 would say A
    rows[0]["financial_rip_v5_score"] = 60.0
    assert _order(pfr.build_product_family_rankings(Db(rows, {"A": 75.0, "B": 75.0}, model=V14), set_targets=TARGETS)) == ["A", "B"]


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(financial_rip_v5_version=None),
    lambda r: r.update(financial_rip_v5_version=sc.FINANCIAL_RIP_V4_VERSION),
    lambda r: r.pop("financial_rip_v5_version")])
def test_wrong_or_missing_v5_makes_the_product_noncanonical_never_a_v4_fallback(mutate):
    rows = _sealed()
    mutate(rows[0])
    payload = pfr.build_product_family_rankings(Db(rows, LEDGER, model=V14), set_targets=TARGETS)
    assert _order(payload) == ["B"]                          # A dropped, not ranked on its V4/V12 numbers


def test_product_missing_from_the_ledger_is_unrankable_not_borrowed_from_v12():
    payload = pfr.build_product_family_rankings(Db(_sealed(), {"B": 90.0}, model=V14), set_targets=TARGETS)
    assert _order(payload) == ["B"]


def test_pointer_only_activation_and_rollback_change_every_serving_choice_with_no_code_change():
    db = Db(_sealed(), LEDGER, model=V12)
    before = pfr.build_product_family_rankings(db, set_targets=TARGETS)
    assert _order(before) == ["A", "B"]
    assert rel.resolve_active_release(db).public_contract_key == "publicRipContractV11"

    db.set_pointer(V14)                                       # the ONLY change: the DB pointer's model
    after = pfr.build_product_family_rankings(db, set_targets=TARGETS)
    r = rel.resolve_active_release(db)
    assert _order(after) == ["B", "A"]
    assert (r.financial_version, r.public_contract_key, r.ranking_method_version, r.overall_target_key) == (
        FINANCIAL_RIP_V5_VERSION, "publicRipContractV12", "budget_product_ranking_v2", "overallRipV14")
    assert after["families"]["booster_box"]["products"][0]["overallRipVersion"] == V14

    db.set_pointer(V12)                                       # rollback: repoint only
    rolled = pfr.build_product_family_rankings(db, set_targets=TARGETS)
    assert _order(rolled) == ["A", "B"]
    assert [p["overallRipScore"] for p in rolled["families"]["booster_box"]["products"]] == \
           [p["overallRipScore"] for p in before["families"]["booster_box"]["products"]]
    assert len(db.sealed) == 2 and LEDGER == {"A": 60.0, "B": 90.0}   # nothing deleted; V14 data left intact


def test_one_pointer_read_pair_per_build_when_the_release_is_passed_down():
    db = Db(_sealed(), LEDGER, model=V14)
    release = rel.resolve_active_release(db)
    reads = len(db.log)
    pfr.build_product_family_rankings(db, set_targets=TARGETS, release=release)
    pointer_reads = [n for n, _ in db.log if n in (rel.POINTER_TABLE, rel.RUN_TABLE)]
    assert reads == 2 and len(pointer_reads) == 2            # not re-read per product/family


def test_set_rip_target_selection_follows_the_pointer_release_not_static_constants():
    v12_target = {"id": "t", "overallRipV12": {"rank": 1}}
    v14_target = {"id": "u", "overallRipV14": {"rank": 1}}
    b12, b14 = rel.bundle_for_model(V12), rel.bundle_for_model(V14)
    assert [t["id"] for t in set_rip_service._ranked_targets([v12_target, v14_target], b12)] == ["t"]
    assert [t["id"] for t in set_rip_service._ranked_targets([v12_target, v14_target], b14)] == ["t", "u"]  # input order kept; V12 target is a historical fallback
    assert [t["id"] for t in set_rip_service._ranked_targets([v12_target, v14_target])] == ["t"]            # no release: static V12
