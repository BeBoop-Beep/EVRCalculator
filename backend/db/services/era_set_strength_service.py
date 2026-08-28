"""Canonical Era Set Strength V1 derived only from published Set RIP V1."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean, median
from typing import Any, Mapping, Sequence

from backend.rankings.public_relative import public_relative_rip_tier, public_rip_display_score

METHODOLOGY_VERSION = "era_set_strength_v1_equal_set_mean_of_set_rip_v1"
MINIMUM_RANKABLE_SETS_PER_ERA = 3


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_era_set_strength(set_targets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = [t for t in set_targets if t.get("publicAnalyticsStatus") == "analytics_ready"]
    versions = {str((t.get("setRipV1") or {}).get("methodologyVersion")) for t in eligible
                if (t.get("setRipV1") or {}).get("methodologyVersion")}
    if len(versions) > 1:
        raise ValueError("Era Set Strength requires one Set RIP methodology version")

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for target in eligible:
        name = str(target.get("era") or "Unassigned")
        grouped[(str(target.get("era_id") or name), name)].append(target)

    eras = []
    for (era_id, era_name), targets in grouped.items():
        valid = []
        context = []
        for target in targets:
            block = target.get("setRipV1") or {}
            score = _number(block.get("score")) if block.get("rankable") else None
            context.append({"setId": str(target.get("set_id") or target.get("target_id") or ""),
                            "setName": str(target.get("name") or "Unknown set"),
                            "score": score, "rank": block.get("rank"), "tier": block.get("tier"),
                            "logoImageUrl": target.get("logo_image_url") or target.get("symbol_image_url")})
            if score is not None:
                valid.append((target, score))
        available = len(targets) >= MINIMUM_RANKABLE_SETS_PER_ERA and len(valid) == len(targets)
        score = fmean(value for _, value in valid) if available else None
        strongest = max(valid, key=lambda item: item[1])[0] if available else None
        valid_scores = [value for _, value in valid]
        eras.append({"eraId": era_id, "eraName": era_name, "score": score,
                     "publicScore": public_rip_display_score(score),
                     "tier": public_relative_rip_tier(score), "rank": None,
                     "rankable": available, "status": "available" if available else "unavailable",
                     "statusReason": None if available else "incomplete_set_rip_coverage",
                     "setCount": len(targets), "modeledSetCount": len(targets), "coveredSetCount": len(valid),
                     "medianSetRip": median(valid_scores) if available else None,
                     "minSetRip": min(valid_scores) if available else None,
                     "maxSetRip": max(valid_scores) if available else None,
                     "strongestSet": ({"setId": str(strongest.get("set_id") or strongest.get("target_id")),
                                       "setName": strongest.get("name"),
                                       "score": (strongest.get("setRipV1") or {}).get("score"),
                                       "rank": (strongest.get("setRipV1") or {}).get("rank")} if strongest else None),
                     "topSet": ({"setId": str(strongest.get("set_id") or strongest.get("target_id")),
                                  "setName": strongest.get("name"), "score": (strongest.get("setRipV1") or {}).get("score")} if strongest else None),
                     "constituentSets": context})
    ranked = sorted((e for e in eras if e["rankable"]), key=lambda e: (-e["score"], e["eraName"]))
    for rank, era in enumerate(ranked, 1):
        era["rank"] = rank
        era["cohortSize"] = len(ranked)
    eras.sort(key=lambda e: (e["rank"] is None, e["rank"] or 10**9, e["eraName"]))
    return {"methodologyVersion": METHODOLOGY_VERSION,
            "sourceSetRipMethodologyVersion": next(iter(versions), None),
            "cohortSize": len(ranked), "eras": eras}


def attach_era_set_strength(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["eraSetStrengthV1"] = build_era_set_strength(list(result.get("targets") or []))
    return result
