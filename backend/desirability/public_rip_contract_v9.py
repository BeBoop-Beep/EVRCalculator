"""Canonical public RIP V9 projection.

V8 remains untouched and reproducible.  V9 reuses its stable public shape while
selecting the version-forwarded V9/V5 objects and contextual roster payload.
No scoring occurs here.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.desirability.public_rip_contract_v8 import build_public_rip_contract_v8
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    OVERALL_RIP_V9_VERSION,
)

PUBLIC_RIP_CONTRACT_V9_KEY = "publicRipContractV9"
PUBLIC_RIP_CONTRACT_V9_VERSION = "public_rip_contract_v9"


def build_public_rip_contract_v9(target: Mapping[str, Any]) -> Dict[str, Any]:
    staged = dict(target)
    staged["overallRipV8"] = target.get("overallRipV9") or {}
    contract = build_public_rip_contract_v8(staged)
    contract["contractVersion"] = PUBLIC_RIP_CONTRACT_V9_VERSION
    contract["canonicalFinancialRipVersion"] = CANONICAL_FINANCIAL_RIP_VERSION
    contract["canonicalOverallRipVersion"] = OVERALL_RIP_V9_VERSION
    contract["canonicalCollectorAppealVersion"] = COLLECTOR_APPEAL_V5_VERSION

    opening = target.get("openingExperience") or {}
    roster = opening.get("rosterDesirability") or {}
    collector_roster = ((contract.get("collectorAppeal") or {}).get("components") or {}).get("rosterDesirability") or {}
    collector_roster["interpretation"] = (
        "How desirable the Pokemon represented by this set's meaningful chase cards are, "
        "with supporting credit for the wider collectible roster. EV evidence establishes "
        "chase context; market value is not scored as Pokemon desirability."
    )
    collector_roster["evidenceStatus"] = opening.get("contextualEvidenceStatus") or (
        "available" if roster.get("score") is not None else "unavailable"
    )
    contract["universalSetDesirability"] = dict(collector_roster)
    contract["universalSetDesirability"]["version"] = roster.get("version")
    return contract
