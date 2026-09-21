"""ONE serving-release authority: the model version named by the active Overall publication pointer.

    active Overall pointer -> run.model_version -> RipReleaseBundle -> every serving choice

The bundle names, together, the Financial version, public contract, ranking method, Best-Open method(s),
target keys and the storage the current Overall/Financial numbers are read from. Serving code resolves the
bundle ONCE at a request/build boundary and passes it down; it does not decide "current" from static
constants when the pointer is available. An unknown model FAILS CLOSED (never treated as V12).

TRANSITIONAL COMPATIBILITY CONTRACT (V12 storage vs the generic ledger)
------------------------------------------------------------------------
The pointer selects the release. Under the V12 release the current V12/V4 numbers keep coming from the live
V12/V4 storage the daily pipeline keeps fresh (the generic ledger's active V12 run is dated 2026-09-10 and is
NOT refreshed daily, so it is not the V12 score authority). Under the V14 release the numbers come from the
generic V14 ledger plus Financial V5 / Ranking V2 / Best-Open V3. Flipping the pointer therefore changes the
whole serving generation with one atomic DB write and no redeploy; repointing to V12 restores V12/V4/V11.
Historical scoring/model constants are unchanged and still used by builders and research; they are not the
serving switch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    BEST_OPEN_PRICE_V2_METHOD_VERSION,
)
from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
)
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V12_VERSION,
    OVERALL_RIP_V14_VERSION,
)

logger = logging.getLogger(__name__)

POINTER_TABLE = "pokemon_overall_rip_current_publication"
RUN_TABLE = "pokemon_overall_rip_publication_runs"

SOURCE_LIVE_V12_STORAGE = "live_v12_v4_storage"
SOURCE_GENERIC_LEDGER = "generic_ledger"


class RipReleaseError(RuntimeError):
    """The active release cannot be resolved safely."""


class UnknownRipRelease(RipReleaseError):
    """The active Overall model has no registered release bundle (never silently V12)."""


@dataclass(frozen=True)
class RipReleaseBundle:
    overall_version: str
    financial_version: str
    public_contract_version: str
    public_contract_key: str
    ranking_method_version: str
    best_open_method_versions: Tuple[str, ...]      # preference order; V14 has exactly one and no fallback
    overall_target_key: str
    financial_target_key: str
    overall_source: str
    # sealed-product columns the release reads (serving SELECTs derive from these; V12 needs no V5 column)
    financial_score_field: str
    financial_version_field: str
    financial_extra_fields: Tuple[str, ...]
    overall_score_field: str
    overall_version_field: str
    overall_rankable_field: str
    requires_v5_schema: bool
    #: "pointer" when read from the DB pointer, "static_fallback" only when the pointer was unreadable.
    resolved_from: str = "pointer"


_V12 = RipReleaseBundle(
    overall_version=OVERALL_RIP_V12_VERSION, financial_version=FINANCIAL_RIP_V4_VERSION,
    public_contract_version="public_rip_contract_v11", public_contract_key="publicRipContractV11",
    ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    best_open_method_versions=(BEST_OPEN_PRICE_V2_METHOD_VERSION, BEST_OPEN_PRICE_METHOD_VERSION),
    overall_target_key="overallRipV12", financial_target_key="financialRipV4",
    overall_source=SOURCE_LIVE_V12_STORAGE,
    financial_score_field="financial_rip_v4_score", financial_version_field="financial_rip_v4_version",
    financial_extra_fields=(),
    overall_score_field="overall_rip_v12_score", overall_version_field="overall_rip_v12_version",
    overall_rankable_field="overall_rip_v12_rankable", requires_v5_schema=False)

_V14 = RipReleaseBundle(
    overall_version=OVERALL_RIP_V14_VERSION, financial_version=FINANCIAL_RIP_V5_VERSION,
    public_contract_version="public_rip_contract_v12", public_contract_key="publicRipContractV12",
    ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    best_open_method_versions=(BEST_OPEN_PRICE_V3_METHOD_VERSION,),
    overall_target_key="overallRipV14", financial_target_key="financialRipV5",
    overall_source=SOURCE_GENERIC_LEDGER,
    financial_score_field="financial_rip_v5_score", financial_version_field="financial_rip_v5_version",
    financial_extra_fields=("financial_rip_v5_status", "financial_rip_v5_rankable"),
    overall_score_field="overall_rip_v14_score", overall_version_field="overall_rip_v14_version",
    overall_rankable_field="overall_rip_v14_rankable", requires_v5_schema=True)

RELEASES: Dict[str, RipReleaseBundle] = {_V12.overall_version: _V12, _V14.overall_version: _V14}


def bundle_for_model(model_version: Optional[str]) -> RipReleaseBundle:
    """The release bundle for an Overall model version. Unknown -> fail closed."""
    try:
        return RELEASES[str(model_version)]
    except KeyError:
        raise UnknownRipRelease(
            "No registered RIP release for Overall model %r; refusing to treat it as V12" % (model_version,))


def static_canonical_bundle() -> RipReleaseBundle:
    """The bundle implied by the static canonical selection (used ONLY as an explicit, marked fallback)."""
    from dataclasses import replace

    return replace(bundle_for_model(CANONICAL_OVERALL_RIP_VERSION), resolved_from="static_fallback")


def read_active_model_version(client: Any) -> str:
    """Pointer -> published run -> model_version. Exactly two reads; no per-item access."""
    pointer = list(client.table(POINTER_TABLE).select("publication_run_id").eq("scope", "pokemon").execute().data or [])
    if not pointer:
        raise RipReleaseError("no active Overall publication pointer")
    runs = list(client.table(RUN_TABLE).select("model_version,status").eq("id", pointer[0]["publication_run_id"])
                .execute().data or [])
    if not runs or runs[0].get("status") != "published":
        raise RipReleaseError("the active pointer does not reference a published run")
    return str(runs[0]["model_version"])


def resolve_active_release(client: Any) -> RipReleaseBundle:
    """The release named by the DB pointer. Raises rather than guessing."""
    return bundle_for_model(read_active_model_version(client))


def resolve_release_or_marked_fallback(client: Any) -> RipReleaseBundle:
    """Pointer-driven; if the pointer is UNREADABLE (not merely unknown), use the static canonical bundle,
    marked ``resolved_from='static_fallback'`` and logged. An unknown model still raises."""
    try:
        return resolve_active_release(client)
    except UnknownRipRelease:
        raise
    except Exception as exc:  # pointer missing / transient read failure
        logger.warning("active RIP release pointer unreadable (%s); using the static canonical bundle", exc)
        return static_canonical_bundle()
