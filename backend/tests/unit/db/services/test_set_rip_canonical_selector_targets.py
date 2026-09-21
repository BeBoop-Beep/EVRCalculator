"""Set RIP owning-target selection follows the canonical selector; V12 behavior is unchanged."""
from backend.db.services import public_rip_publication_contract as pubc
from backend.db.services import set_rip_service as service
from backend.desirability import scoring_config as sc


def _legacy_ranked(targets):
    """The pre-change V12/V11/V10 precedence, reproduced verbatim as the parity reference."""
    out = []
    for c in targets:
        if (c.get("overallRipV12") or {}).get("rank") is not None:
            out.append(c)
        elif (((c.get("publicRipContractV11") or {}).get("overallRip") or {}).get("rank")) is not None:
            out.append(c)
        elif (c.get("overallRipV10") or {}).get("rank") is not None:
            out.append(c)
        elif (((c.get("publicRipContractV10") or {}).get("overallRip") or {}).get("rank")) is not None:
            out.append(c)
    return out


TARGETS = [
    {"id": "a", "overallRipV12": {"rank": 1}},
    {"id": "b", "publicRipContractV11": {"overallRip": {"rank": 2}}},
    {"id": "c", "overallRipV10": {"rank": 3}},
    {"id": "d", "publicRipContractV10": {"overallRip": {"rank": 4}}},
    {"id": "e", "overallRipV12": {"rank": None}},
    {"id": "f"},
]


def test_v12_canonical_selection_is_identical_to_the_legacy_precedence():
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION
    assert [t["id"] for t in service._ranked_targets(TARGETS)] == [t["id"] for t in _legacy_ranked(TARGETS)] == ["a", "b", "c", "d"]


def test_candidate_only_targets_never_displace_the_canonical_v12_authority():
    cand = [{"id": "x", "overallRipV14": {"rank": 1}}, {"id": "y", "publicRipContractV12": {"overallRip": {"rank": 2}}}]
    assert service._ranked_targets(cand) == []
    assert [t["id"] for t in service._ranked_targets(cand + TARGETS[:1])] == ["a"]


def test_a_controlled_v14_canonical_flip_selects_v14_and_keeps_historical_fallbacks(monkeypatch):
    monkeypatch.setattr(pubc, "CANONICAL_OVERALL_RIP_VERSION", sc.OVERALL_RIP_V14_VERSION)
    assert pubc.canonical_public_rip_contract_target_key() == "publicRipContractV12"
    targets = [{"id": "x", "overallRipV14": {"rank": 1}},
               {"id": "y", "publicRipContractV12": {"overallRip": {"rank": 2}}},
               {"id": "z", "overallRipV12": {"rank": 3}}]  # not rebuilt for V14: historical fallback only
    assert [t["id"] for t in service._ranked_targets(targets)] == ["x", "y", "z"]
    assert service._ranked_targets([{"id": "n", "overallRipV14": {"rank": None}}]) == []


def test_contract_key_is_selector_driven_and_fails_closed(monkeypatch):
    assert pubc.canonical_public_rip_contract_target_key() == "publicRipContractV11"
    monkeypatch.setattr(pubc, "CANONICAL_OVERALL_RIP_VERSION", "overall_rip_v99")
    import pytest
    with pytest.raises(RuntimeError):
        pubc.canonical_public_rip_contract_target_key()
