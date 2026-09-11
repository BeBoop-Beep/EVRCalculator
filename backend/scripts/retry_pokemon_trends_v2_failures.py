"""Retry only the five frozen Trends V2 failures and retain request evidence."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from backend.desirability.google_trends import PytrendsGoogleTrendsProvider
from backend.desirability.trends_anchor_ladder import frozen_ladder_anchors, load_frozen_anchor_manifest
from backend.scripts import capture_pokemon_trends_anchor_ladder_v2 as capture

ROOT = Path(__file__).resolve().parents[2]
FAILURES = {"Pidgeot", "Skiploom", "Torkoal", "Latias", "Stunky"}
DEFAULT_OUTPUT = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/targeted_retry_v1.json"


class RecordingProvider:
    def __init__(self, provider):
        self.provider = provider
        self.requests = []

    def fetch_interest(self, **kwargs):
        started = time.time()
        response = self.provider.fetch_interest(**kwargs)
        self.requests.append({
            "attempt": len(self.requests) + 1,
            "requested_at": started,
            "completed_at": time.time(),
            "request": kwargs,
            "response": {
                "status": response.status,
                "interest_by_term": response.interest_by_term,
                "error": response.error,
                "error_type": response.error_type,
                "retryable": response.retryable,
                "raw_payload": response.raw_payload,
            },
        })
        return response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = load_frozen_anchor_manifest()
    scale = {a.name: a.global_scale for a in frozen_ladder_anchors(manifest)}
    subjects = [r for r in capture.load_universe() if r["pokemon_name"] in FAILURES]
    if {r["pokemon_name"] for r in subjects} != FAILURES:
        raise RuntimeError("canonical retry subject set mismatch")
    provider = RecordingProvider(PytrendsGoogleTrendsProvider())
    rows = []
    stats = {"requests": 0, "retries": 0}
    for index, subject in enumerate(subjects):
        rows.append(asdict(capture.classify_and_record(
            provider, subject, scale, manifest["manifestVersion"], stats
        )))
        if index + 1 < len(subjects):
            time.sleep(capture.DELAY_SECONDS)
    artifact = {
        "artifact_version": "pokemon_trends_v2_targeted_retry_v1",
        "manifest_version": manifest["manifestVersion"],
        "manifest_fingerprint": capture.manifest_fingerprint(manifest),
        "capture_code_version": capture.CODE_VERSION,
        "query_settings": {"timeframe": capture.TIMEFRAME, "geo": capture.GEO, "queryType": "search_term"},
        "created_at": time.time(),
        "stats": stats,
        "rows": rows,
        "requests": provider.requests,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "stats": stats,
                      "results": [{"name": r["pokemon_name"], "classification": r["classification"]} for r in rows]}, indent=2))
    usable = {"SCORED", capture.ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE.value}
    return 0 if all(r["classification"] in usable for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
