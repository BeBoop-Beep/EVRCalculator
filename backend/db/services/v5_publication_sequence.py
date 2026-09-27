"""The future Financial V5 / Overall V14 candidate publication sequence, as validated data.

This makes the intended ORDER representable and testable without changing the current production
publication sequence: ``run_daily_opening_publication.py`` does not import this module and keeps
publishing V4/V12. Each step names the module that implements it (all built in Prompts 5/5A/5A.2/5B) and
whether it can mutate the database. The final step, pointer activation, is explicit-authorization-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SequenceStep:
    order: int
    key: str
    description: str
    implemented_by: str
    writes_database: bool
    requires_explicit_authorization: bool = False


V5_CANDIDATE_SEQUENCE: Tuple[SequenceStep, ...] = (
    SequenceStep(1, "resolve_market_date", "Resolve the promoted market date", "opening_simulation_gate", False),
    SequenceStep(2, "verify_or_run_simulations", "Verify (or run) the opening simulations for the date",
                 "opening_simulation_gate", True),
    SequenceStep(3, "verify_exact_run_map", "Verify the exact current set -> calculation_run_id map",
                 "sealed_product_rip_finalization_service.resolve_finalization_cohort", False),
    SequenceStep(4, "rebuild_chase_accessibility", "Rebuild Chase Accessibility for those exact runs",
                 "chase_accessibility_service", True),
    SequenceStep(5, "finalize_financial_v5", "Exact-artifact Financial V5 finalization (V5 columns only)",
                 "sealed_product_financial_v5_finalization_service.finalize_financial_rip_v5", True),
    SequenceStep(6, "build_overall_v14_candidate", "Collector V5 + Overall V14 -> inactive generic-ledger candidate",
                 "overall_v14_candidate_publication.write_v14_candidate", True),
    SequenceStep(7, "evaluate_candidate_readiness", "Candidate readiness gate (independent of canonical health)",
                 "v5_v14_candidate_readiness.evaluate_v5_v14_candidate_readiness", False),
    SequenceStep(8, "publish_ranking_v2", "Explicit Ranking V2 (Financial V5 + Overall V14)",
                 "budget_ranking_v2_orchestration.publish_ranking_v2", True),
    SequenceStep(9, "publish_best_open_v3", "Explicit Best-Open V3 sourced from Ranking V2",
                 "budget_best_open_v3_orchestration.publish_best_open_v3", True),
    SequenceStep(10, "build_public_snapshots_and_generations",
                 "Public snapshot / set-page generations carrying contract V12",
                 "public_rip_contract_v12.build_public_rip_contract_v12", True),
    SequenceStep(11, "validate_candidate", "Full candidate validation (readiness re-run on persisted state)",
                 "v5_v14_candidate_readiness.evaluate_v5_v14_candidate_readiness", False),
    SequenceStep(12, "activate_pointer", "Move the active Overall pointer + canonical selectors",
                 "promote_pokemon_overall_rip_publication (NOT implemented here)", True,
                 requires_explicit_authorization=True),
)


def validate_sequence(steps: Sequence[SequenceStep] = V5_CANDIDATE_SEQUENCE) -> List[str]:
    """Problems with the sequence definition; empty when it is well formed."""
    problems: List[str] = []
    if [s.order for s in steps] != list(range(1, len(steps) + 1)):
        problems.append("orders are not contiguous from 1")
    keys = [s.key for s in steps]
    if len(set(keys)) != len(keys):
        problems.append("duplicate step keys")
    activation = [s for s in steps if s.requires_explicit_authorization]
    if len(activation) != 1 or steps[-1] is not activation[0]:
        problems.append("exactly one authorization-gated step is allowed and it must be last")
    by_key: Dict[str, int] = {s.key: s.order for s in steps}
    for before, after in (("finalize_financial_v5", "build_overall_v14_candidate"),
                          ("build_overall_v14_candidate", "publish_ranking_v2"),
                          ("publish_ranking_v2", "publish_best_open_v3"),
                          ("evaluate_candidate_readiness", "activate_pointer"),
                          ("rebuild_chase_accessibility", "finalize_financial_v5")):
        if by_key.get(before, 10**6) >= by_key.get(after, -1):
            problems.append(f"{before} must precede {after}")
    return problems


def steps_before_activation() -> Tuple[SequenceStep, ...]:
    return tuple(s for s in V5_CANDIDATE_SEQUENCE if not s.requires_explicit_authorization)


def authorized_prefix(explicit_activation_authorization: bool, upto: Optional[str] = None) -> Tuple[SequenceStep, ...]:
    """The steps a caller may run. Activation is only ever included on explicit authorization."""
    steps = V5_CANDIDATE_SEQUENCE if explicit_activation_authorization else steps_before_activation()
    if upto is None:
        return tuple(steps)
    out: List[SequenceStep] = []
    for s in steps:
        out.append(s)
        if s.key == upto:
            break
    return tuple(out)
