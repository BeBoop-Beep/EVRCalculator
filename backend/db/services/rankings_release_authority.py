"""Mixed-generation rejection for a Rankings snapshot (and any observed release identity).

A Rankings snapshot must belong to exactly ONE serving release. This module answers, as a list of problems
(empty = coherent), whether a payload's stamped identity and its target blocks all agree with the selected
``RipReleaseBundle``. It never repairs or relabels anything; it only refuses.

Rejected, among others: V14 Overall with a V4 Financial; V14 with Ranking V1 or Contract V11; Ranking V2 with
an Overall V12; a V5 value under a V4 identity (or V14 under a V12 key); a stale snapshot of the other release
presented as current; a target whose V5 evidence was built from a different calculation run.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from backend.db.services import rip_release


def observed_bundle_problems(observed: Mapping[str, Any]) -> List[str]:
    """Coherence of a set of stamped identities against the bundle their Overall model names.

    ``observed`` keys (all optional except ``overall``): ``overall``, ``financial``, ``contract``, ``ranking``,
    ``bestOpen`` (a version string or a collection of them). An unknown Overall model fails closed.
    """
    try:
        bundle = rip_release.bundle_for_model(observed.get("overall"))
    except rip_release.UnknownRipRelease as exc:
        return [f"unknown_release: {exc}"]
    problems: List[str] = []
    if "financial" in observed and observed["financial"] != bundle.financial_version:
        problems.append(f"mixed_authority: overall={bundle.overall_version} with financial={observed['financial']}")
    if "contract" in observed and observed["contract"] != bundle.public_contract_version:
        problems.append(f"mixed_authority: overall={bundle.overall_version} with public_contract={observed['contract']}")
    if "ranking" in observed and observed["ranking"] != bundle.ranking_method_version:
        problems.append(f"mixed_authority: overall={bundle.overall_version} with ranking={observed['ranking']}")
    if "bestOpen" in observed:
        got = observed["bestOpen"]
        got = (got,) if isinstance(got, str) else tuple(got or ())
        if not got or any(v not in bundle.best_open_method_versions for v in got):
            problems.append(f"mixed_authority: overall={bundle.overall_version} with best_open={list(got)}")
    return problems


def snapshot_release_problems(
    payload: Mapping[str, Any], release: Any, *, expected_cohort_fingerprint: Optional[str] = None,
) -> List[str]:
    """Every reason ``payload`` (``{"meta": ..., "targets": [...]}``) is not a coherent snapshot of ``release``."""
    if release is None or not hasattr(release, "overall_version"):
        return ["unknown_release: no release bundle supplied"]
    problems: List[str] = []
    meta = payload.get("meta") if isinstance(payload.get("meta"), Mapping) else {}
    config = meta.get("ripWeightsConfig") if isinstance(meta.get("ripWeightsConfig"), Mapping) else {}
    stamped = {
        "financial": (config.get("financialRip") or {}).get("version"),
        "overall": (config.get("overallRip") or {}).get("version"),
        "contract": (config.get("publicContract") or {}).get("version"),
    }
    for key, want in (("financial", release.financial_version), ("overall", release.overall_version),
                      ("contract", release.public_contract_version)):
        if stamped[key] != want:
            problems.append(f"stale_or_foreign_snapshot: {key} stamp={stamped[key]!r} release={want!r}")
    # the stamped identities must also agree with each other (mixed authority inside the snapshot)
    if stamped["overall"] is not None:
        problems += [p for p in observed_bundle_problems(
            {k: v for k, v in {"overall": stamped["overall"], "financial": stamped["financial"],
                               "contract": stamped["contract"]}.items() if v is not None}) if p not in problems]
    if expected_cohort_fingerprint is not None:
        got = ((meta.get("snapshot") or {}).get("cohortFingerprint") or meta.get("cohortFingerprint"))
        if got != expected_cohort_fingerprint:
            problems.append(f"cohort_fingerprint_mismatch: snapshot={got!r} expected={expected_cohort_fingerprint!r}")

    overall_key, financial_key = release.overall_target_key, release.financial_target_key
    for target in payload.get("targets") or []:
        if not isinstance(target, Mapping):
            continue
        tid = target.get("target_id") or target.get("canonical_key")
        overall, financial = target.get(overall_key), target.get(financial_key)
        ranked = isinstance(overall, Mapping) and overall.get("rank") is not None
        if ranked:
            if overall.get("version") not in (None, release.overall_version):
                problems.append(f"{tid}: {overall_key}.version={overall.get('version')!r}")
            if not isinstance(financial, Mapping) or financial.get("status") != "ready":
                problems.append(f"{tid}: ranked {overall_key} without a ready {financial_key}")
            elif financial.get("version") != release.financial_version:
                problems.append(f"{tid}: {financial_key}.version={financial.get('version')!r}")
            if release.requires_v5_schema and isinstance(financial, Mapping):
                source_run = (financial.get("source") or {}).get("calculationRunId")
                if source_run is not None and str(source_run) != str(target.get("calculation_run_id")):
                    problems.append(f"{tid}: {financial_key} built from run {source_run} but target run is "
                                    f"{target.get('calculation_run_id')}")
        # a value of the OTHER generation must never sit under a differently-named semantic key
        for key, wrong_version in (("financialRipV4", "financial_rip_v5"), ("overallRipV12", "overall_rip_v14")):
            block = target.get(key)
            version = (block or {}).get("version") or (block or {}).get("scoreVersion") if isinstance(block, Mapping) else None
            if version and str(version).startswith(wrong_version):
                problems.append(f"{tid}: {wrong_version} value under {key}")
    return problems
