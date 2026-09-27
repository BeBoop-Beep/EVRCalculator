"""READ-ONLY dry run of the release-driven Rankings builder against current production data.

Builds the RIP-statistics targets payload for the V12 release (default) and for the explicit V14 release, with
ONE shared Collector Appeal bundle (built once, then reused, so the comparison is on identical inputs), and
reports: V12 output identity between the release-driven code and (optionally) a baseline copy of the pre-change
module, the V4/V12 blocks being untouched by the V14 build, and the per-target Financial V5 / Overall V14 result.
Nothing is written to the database or the filesystem outside ``logs/v5_candidate``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
_TIME_KEYS = {"generatedAt", "builtAt", "generated_at", "elapsedMs", "timings", "totalMs", "generatedAtUtc"}


def _strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _TIME_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _norm(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _strip(json.loads(json.dumps(payload, sort_keys=True, default=str)))


def _load_baseline(path: Path):
    spec = importlib.util.spec_from_file_location("backend.db.services._explore_baseline", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-file", default=None, help="pre-change explore_rip_statistics_service.py copy")
    parser.add_argument("--limit", default="200")
    args = parser.parse_args(argv)

    from backend.db.services import explore_rip_statistics_service as new
    from backend.db.services import rip_release as rr

    bundle_cache: Dict[str, Any] = {}
    real_bundle = new.get_collector_appeal_bundle

    def shared_bundle(*a, **k):
        if "b" not in bundle_cache:
            bundle_cache["b"] = real_bundle(*a, **k)
        return bundle_cache["b"]

    new.get_collector_appeal_bundle = shared_bundle
    v14 = next(b for b in rr.RELEASES.values() if b.requires_v5_schema)
    report: Dict[str, Any] = {"readOnly": True}

    v12_new = _norm(new.get_rip_statistics_targets_payload(limit=args.limit))
    if args.baseline_file:
        old = _load_baseline(Path(args.baseline_file))
        old.get_collector_appeal_bundle = shared_bundle
        v12_old = _norm(old.get_rip_statistics_targets_payload(limit=args.limit))
        report["v12ParityWithBaseline"] = {"identical": v12_old == v12_new, "targets": len(v12_new.get("targets") or [])}
    v14_new = _norm(new.get_rip_statistics_targets_payload(limit=args.limit, release=v14))

    by_id = {t["target_id"]: t for t in v12_new["targets"]}
    untouched = all(t.get("financialRipV4") == by_id[t["target_id"]].get("financialRipV4")
                    and t.get("overallRipV12") == by_id[t["target_id"]].get("overallRipV12") for t in v14_new["targets"])
    rows = []
    for t in v14_new["targets"]:
        f, o = t.get("financialRipV5") or {}, t.get("overallRipV14") or {}
        rows.append({"targetId": t["target_id"], "name": t.get("name"), "runId": t.get("calculation_run_id"),
                     "v4": (t.get("financialRipV4") or {}).get("score"), "v12": (t.get("overallRipV12") or {}).get("score"),
                     "v5": f.get("score"), "v5Status": f.get("status"), "v5Version": f.get("version"),
                     "v5SourceRun": (f.get("source") or {}).get("calculationRunId"),
                     "v14": o.get("score"), "v14Status": o.get("status"), "v14Version": o.get("version"),
                     "v14Rank": o.get("rank"), "v5Rank": f.get("rank"), "contractV12": (t.get("publicRipContractV12") or {}).get("contractVersion")})
    ready = [r for r in rows if r["v5Status"] == "ready"]
    cfg = v14_new["meta"]["ripWeightsConfig"]
    report.update({
        "v12BlocksUntouchedByV14Build": untouched, "targets": len(rows),
        "v5Ready": len(ready), "v14Ready": sum(1 for r in rows if r["v14Status"] == "ready"),
        "ranksContiguous": sorted(r["v14Rank"] for r in rows if r["v14Rank"] is not None)
        == list(range(1, sum(1 for r in rows if r["v14Rank"] is not None) + 1)),
        "runMatchesAuthority": all(r["v5SourceRun"] == r["runId"] for r in ready),
        "identity": {"overall": cfg["overallRip"]["version"], "financial": cfg["financialRip"]["version"],
                     "contract": cfg["publicContract"]["version"]},
        "rows": rows})
    out = ROOT / "logs" / "v5_candidate" / "rankings_v14_dry_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
