"""Merge the five completed targeted retries into the frozen 1,025-row capture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_rows.jsonl"
RETRY = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/targeted_retry_v1.json"
OUTPUT = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/complete_capture_v2.jsonl"
HEADER = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_header.json"


def build(base_path: Path, retry_path: Path) -> list[dict]:
    base = [json.loads(line) for line in base_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retry_doc = json.loads(retry_path.read_text(encoding="utf-8"))
    retry = {row["subject_id"]: row for row in retry_doc["rows"]}
    if len(base) != 1025 or len({r["subject_id"] for r in base}) != 1025 or len(retry) != 5:
        raise RuntimeError("frozen base or targeted retry membership mismatch")
    result = []
    for original in base:
        recovered = retry.get(original["subject_id"])
        if recovered is None:
            result.append(original)  # byte-equivalent object content for all 1,020 valid rows
            continue
        if original["classification"] != "failed" or recovered["classification"] not in {"SCORED", "scored_zero_high_confidence"}:
            raise RuntimeError(f"invalid replacement state for {original['pokemon_name']}")
        merged = dict(recovered)
        merged["actual_query_anchor"] = recovered["assigned_anchor"]
        merged["assigned_anchor"] = original["assigned_anchor"]
        merged["targeted_retry_replacement"] = True
        result.append(merged)
    if any(r.get("classification") not in {"SCORED", "scored_zero_high_confidence"} for r in result):
        raise RuntimeError("complete capture contains unusable rows")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--retry", type=Path, default=RETRY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows = build(args.base, args.retry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "replacements": sum(bool(r.get("targeted_retry_replacement")) for r in rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
