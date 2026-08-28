"""Canonical-shape public RIP V10 projection.

V9 remains untouched and reproducible. V10 reuses the same stable public shape
while selecting the version-forwarded V10/V4 objects, exactly as V9 did over V8.
No scoring occurs here.

WHAT A CONSUMER SEES
--------------------
The public shape is deliberately unchanged: ``overallRip``, ``financialRip``,
``collectorAppeal``, ``audit`` and the roster block keep their names and their
meanings. A frontend that already parses the V9 contract needs to learn ONE new
key, ``publicRipContractV10``, and nothing else. Public metric names do not move
with a model version - the whole point of the contract layer is that they do
not.

V10 is the current canonical public contract. Its stable projection shape keeps
the prior contract's public names while version-forwarding the canonical V10/V4
objects.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.desirability.public_rip_contract_v9 import build_public_rip_contract_v9
from backend.desirability.scoring_config import OVERALL_RIP_V10_VERSION
from backend.rankings.public_relative import public_leader_rip_tier

PUBLIC_RIP_CONTRACT_V10_KEY = "publicRipContractV10"
PUBLIC_RIP_CONTRACT_V10_VERSION = "public_rip_contract_v10"


def build_public_rip_contract_v10(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project a ranked target into the public V10 contract.

    Reads ``overallRipV10`` and ``financialRipV4`` from the target, stages them
    into the keys the V9 builder expects, and restamps the declared identities.
    The staging is what keeps the projection logic in ONE place: a copied V9
    builder would be a second implementation of the same public shape, free to
    drift.
    """
    staged = dict(target)

    overall_v10 = dict(target.get("overallRipV10") or {})
    # The shared builder fills the public financial slot from a component keyed
    # ``financialRipV3``, while a V10 payload keys it ``financialRipV4`` (it
    # names the model it actually holds). Bridge it here, once, rather than
    # teaching the shared builder about every future version.
    components = dict(overall_v10.get("components") or {})
    if "financialRipV4" in components and "financialRipV3" not in components:
        components["financialRipV3"] = components["financialRipV4"]
        overall_v10["components"] = components
    staged["overallRipV9"] = overall_v10

    # Financial RIP V4 is served under its own top-level key. It is staged into
    # the key the shared builder reads; the CONTRACT then declares which model
    # the object actually is, so nothing downstream has to infer it, and the
    # object carries its own ``scoreVersion`` regardless.
    financial_v4 = target.get("financialRipV4")
    if financial_v4:
        staged["financialRipV3"] = financial_v4

    contract = build_public_rip_contract_v9(staged)
    contract["contractVersion"] = PUBLIC_RIP_CONTRACT_V10_VERSION
    contract["canonicalFinancialRipVersion"] = FINANCIAL_RIP_V4_VERSION
    contract["canonicalOverallRipVersion"] = OVERALL_RIP_V10_VERSION
    contract["canonicalCollectorAppealVersion"] = COLLECTOR_APPEAL_V5_VERSION

    # Publish the financial component of Overall RIP under BOTH names: the
    # stable public slot every existing consumer already parses, and a truthful
    # ``financialRipV4`` slot naming the model that produced it. Adding a key is
    # backward compatible; renaming the existing one would not be, and public
    # metric names do not move with a model version.
    overall = contract.get("overallRip")
    if isinstance(overall, dict):
        overall["leaderNormalizedScore"] = overall_v10.get("leaderNormalizedScore")
        overall["publicTier"] = public_leader_rip_tier(overall.get("leaderNormalizedScore"))
        # ``tier`` is the stable public V9-shaped slot. Its V10 public meaning
        # is deliberately cut over here without changing the model/rank blocks.
        overall["tier"] = overall["publicTier"]
        overall_components = overall.get("components")
        if isinstance(overall_components, dict) and "financialRipV3" in overall_components:
            overall_components["financialRipV4"] = dict(
                overall_components["financialRipV3"]
            )
        overall["financialInputVersion"] = FINANCIAL_RIP_V4_VERSION

    financial = contract.get("financialRip")
    if isinstance(financial, dict):
        financial["leaderNormalizedScore"] = (target.get("financialRipV4") or {}).get(
            "leaderNormalizedScore"
        )
        financial["publicTier"] = public_leader_rip_tier(financial.get("leaderNormalizedScore"))
        financial["tier"] = financial["publicTier"]

    return contract
