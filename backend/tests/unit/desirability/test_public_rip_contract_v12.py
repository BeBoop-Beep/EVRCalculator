"""Public RIP contract V12: carries Financial V5 / Overall V14; registered but NOT canonical."""
import copy
import inspect
import json

import pytest

from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION, FINANCIAL_RIP_V5_WEIGHTS
from backend.desirability import public_rip_contract_v12 as v12mod
from backend.desirability.public_rip_contract_v10 import PUBLIC_RIP_CONTRACT_V10_KEY
from backend.desirability.public_rip_contract_v11 import (
    PUBLIC_RIP_CONTRACT_V11_KEY, PUBLIC_RIP_CONTRACT_V11_VERSION, build_public_rip_contract_v11,
)
from backend.desirability.public_rip_contract_v12 import (
    PUBLIC_RIP_CONTRACT_V12_KEY, PUBLIC_RIP_CONTRACT_V12_VERSION, build_public_rip_contract_v12,
)
from backend.desirability import scoring_config as sc
from backend.tests.unit.desirability.test_public_rip_contract_v11 import _target as _v11_target

FIN_COMPONENTS = {k: {"score": 50.0, "weight": w} for k, w in FINANCIAL_RIP_V5_WEIGHTS.items()}


def _target():
    t = _v11_target()
    t["financialRipV5"] = {"score": 52.0, "status": "ready", "rankable": True, "scoreVersion": FINANCIAL_RIP_V5_VERSION,
                           "components": copy.deepcopy(FIN_COMPONENTS), "rank": 3, "tier": "B", "cohortSize": 138,
                           "relativeScore": 0.9}
    t["overallRipV14"] = {"score": 70.1, "status": "ready", "rankable": True, "version": sc.OVERALL_RIP_V14_VERSION,
                          "components": {"financialRipV5": {"score": 52.0, "weight": 0.86},
                                         "chaseAccessibility": {"raw": 0.002, "score": 50.0, "weight": 0.04},
                                         "collectorAppeal": {"score": 60.0, "weight": 0.10}},
                          "rank": 2, "tier": "A", "cohortSize": 138, "relativeScore": 0.95,
                          "leaderNormalizedScore": 0.97, "publicTier": "A"}
    return t


def test_identity_is_unique_and_v11_is_frozen_and_still_canonical():
    assert PUBLIC_RIP_CONTRACT_V12_VERSION == "public_rip_contract_v12" != PUBLIC_RIP_CONTRACT_V11_VERSION
    assert PUBLIC_RIP_CONTRACT_V12_KEY == "publicRipContractV12"
    assert sc.canonical_public_rip_contract_version() == PUBLIC_RIP_CONTRACT_V11_VERSION
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION
    assert sc.CANONICAL_FINANCIAL_RIP_VERSION == sc.FINANCIAL_RIP_V4_VERSION


def test_v11_output_is_unchanged_by_the_existence_of_v12_and_embedded_verbatim():
    target = _target()
    before = json.dumps(build_public_rip_contract_v11(target), sort_keys=True, default=str)
    v12 = build_public_rip_contract_v12(target)
    assert json.dumps(build_public_rip_contract_v11(target), sort_keys=True, default=str) == before
    assert json.dumps(v12[PUBLIC_RIP_CONTRACT_V11_KEY], sort_keys=True, default=str) == before
    assert v12[PUBLIC_RIP_CONTRACT_V11_KEY]["contractVersion"] == PUBLIC_RIP_CONTRACT_V11_VERSION
    assert PUBLIC_RIP_CONTRACT_V10_KEY in v12[PUBLIC_RIP_CONTRACT_V11_KEY]  # full V11 lineage retained
    pre = dict(_target(), **{PUBLIC_RIP_CONTRACT_V11_KEY: {"marker": "v11-was-here"}})
    assert build_public_rip_contract_v12(pre)[PUBLIC_RIP_CONTRACT_V11_KEY] == {"marker": "v11-was-here"}


def test_v12_declares_v14_v5_and_forwards_generic_slots_without_v4_identities():
    c = build_public_rip_contract_v12(_target())
    assert c["contractVersion"] == PUBLIC_RIP_CONTRACT_V12_VERSION
    assert c["canonicalOverallRipVersion"] == sc.OVERALL_RIP_V14_VERSION
    assert c["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V5_VERSION
    o, f = c["overallRipV14"], c["financialRipV5"]
    assert (o["score"], o["rank"], o["tier"], o["cohortSize"], o["status"], o["version"]) == (
        70.1, 2, "A", 138, "ready", sc.OVERALL_RIP_V14_VERSION)
    assert (f["score"], f["rank"], f["tier"], f["status"], f["version"]) == (52.0, 3, "B", "ready", FINANCIAL_RIP_V5_VERSION)
    assert c["overallRip"]["score"] == 70.1 and c["overallRip"]["version"] == sc.OVERALL_RIP_V14_VERSION
    assert c["financialRip"]["score"] == 52.0 and c["financialRip"]["version"] == FINANCIAL_RIP_V5_VERSION
    assert "financial_rip_v4" not in json.dumps(c["financialRip"]) and "financial_rip_v3" not in json.dumps(c["financialRip"])
    # V14 is not the program-wide canonical model yet, so it must not claim to be
    assert o["canonical"] is False and f["canonical"] is False
    assert "overallRipV12" not in c and "overallRipV12Composition" not in c  # only inside embedded V11


def test_composition_is_truthful_86_4_10_with_v5_chase_v1_collector_v5():
    comp = build_public_rip_contract_v12(_target())["overallRipV14Composition"]
    assert comp["version"] == sc.OVERALL_RIP_V14_VERSION
    assert comp["inputs"] == {"financialRip": FINANCIAL_RIP_V5_VERSION,
                              "chaseAccessibility": sc.overall_rip_v14_required_chase_accessibility_version(),
                              "collectorAppeal": sc.overall_rip_v14_required_collector_appeal_version()}
    assert comp["weights"] == {"financial_rip": 0.86, "chase_accessibility": 0.04, "collector_appeal": 0.10}
    assert "shortfall_resilience" in comp["effectiveWeights"] and "loss_resilience" not in comp["effectiveWeights"]
    assert abs(sum(comp["effectiveWeights"].values()) - 1.0) < 1e-9
    assert "financial_rip_v4" not in json.dumps(comp)


@pytest.mark.parametrize("mutate,block", [
    (lambda t: t["overallRipV14"].update(version=sc.OVERALL_RIP_V12_VERSION), "overallRipV14"),
    (lambda t: t["overallRipV14"]["components"].update(financialRipV4={"score": 70.0}), "overallRipV14"),
    (lambda t: t["overallRipV14"].update(components={}), "overallRipV14"),
    (lambda t: t["overallRipV14"].update(rank=None), "overallRipV14"),
    (lambda t: t["overallRipV14"].update(status="unavailable_missing_input"), "overallRipV14"),
    (lambda t: t["financialRipV5"].update(scoreVersion=sc.FINANCIAL_RIP_V4_VERSION), "financialRipV5"),
    (lambda t: t["financialRipV5"]["components"].update(loss_resilience={"score": 1.0}), "financialRipV5"),
    (lambda t: t["financialRipV5"]["components"].pop("shortfall_resilience"), "financialRipV5"),
    (lambda t: t["financialRipV5"].update(status="unavailable"), "financialRipV5")])
def test_inconsistent_or_wrong_version_targets_fail_closed_never_canonical_ready(mutate, block):
    t = _target()
    mutate(t)
    blk = build_public_rip_contract_v12(t)[block]
    assert blk["score"] is None and blk["rankable"] is False and blk["rank"] is None and blk["tier"] is None
    assert blk["status"] != "ready" and blk["statusReason"]


def test_missing_v14_is_truthfully_unavailable_and_generic_slot_follows():
    t = _target()
    del t["overallRipV14"]
    c = build_public_rip_contract_v12(t)
    assert c["overallRipV14"]["score"] is None and c["overallRipV14"]["rankable"] is False
    assert c["overallRip"]["score"] is None and c["overallRip"]["rank"] is None
    assert c["overallRip"]["version"] == sc.OVERALL_RIP_V14_VERSION  # named model, no neighbour substitution


def test_public_vocabulary_and_chase_block_are_unchanged():
    t = _target()
    v11, v12 = build_public_rip_contract_v11(t), build_public_rip_contract_v12(t)
    stable = {"collectorAppeal", "financialRip", "overallRip", "chaseAccessibility", "personalFit", "metricDistinction"}
    assert stable <= set(v11) and stable <= set(v12)
    assert v12["chaseAccessibility"] == v11["chaseAccessibility"]
    # internal methodology term appears only inside the V5 component table, never as a public metric
    text = json.dumps({k: v for k, v in v12.items() if k not in (PUBLIC_RIP_CONTRACT_V11_KEY,)}, default=str).lower()
    assert "shortfall" in json.dumps(v12["financialRipV5"]["components"]).lower()
    stripped = json.dumps({k: v for k, v in v12.items() if k not in (PUBLIC_RIP_CONTRACT_V11_KEY, "financialRipV5", "financialRip",
                                                                    "overallRipV14Composition")}, default=str).lower()
    # identity strings (e.g. ...v5_shortfall_resilience_...) are internal versioning, not labels
    assert "shortfall resilience" not in stripped and "shortfallresilience" not in stripped
    assert "chance of a chase" not in text
    assert "chance of a chase" not in inspect.getsource(v12mod).lower().replace("not chance of a chase", "")


def test_v12_is_explicitly_computable_without_flipping_any_selector():
    build_public_rip_contract_v12(_target())
    assert sc.canonical_public_rip_contract_version() == PUBLIC_RIP_CONTRACT_V11_VERSION
    assert sc.canonical_overall_rip_is_v12() is True
