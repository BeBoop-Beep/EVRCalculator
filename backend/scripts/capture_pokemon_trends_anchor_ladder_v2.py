"""Resumable, checkpointed full-universe capture for Pokémon Trends anchor-ladder V2.

Uses the frozen anchor manifest (backend/config/pokemon_trends_anchor_ladder_v1.json)
and the existing pytrends provider (backend.desirability.google_trends) unchanged --
this script only adds tier-based batching, checkpointing, and the calibration/zero-
classification layer (backend.desirability.trends_anchor_ladder).

Scope note: the existing composite (backend/desirability/composite.py) consumes only
the "today 1-m" timeframe's recent_trend_score (see docs/research -- 12-m/5-y/3-m have
no consumers), so this capture targets a single timeframe rather than all four,
cutting request volume ~4x relative to the original V1 four-timeframe estimate.

Resumability contract:
  - checkpoint file is JSONL (one completed-subject record per line), append-only.
  - a header file alongside it pins the manifest fingerprint + code version used; on
    resume, a mismatch aborts (fail closed) rather than silently mixing versions.
  - already-completed subject_ids are skipped on resume, never re-queried or rewritten.
  - a crash mid-batch loses at most the in-flight batch (not yet checkpointed).

This script performs NO database writes. It only reads (once, cached to a local
artifact) the canonical Pokémon universe and fan_popularity_score, and writes local
checkpoint/artifact files. Persisting a new Trends source run to production is a
separate, later step (backend.desirability source-run lifecycle), gated on validating
the completed local capture.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.google_trends import PytrendsGoogleTrendsProvider, QUERY_TYPE_SEARCH_TERM
from backend.desirability.trends_anchor_ladder import (
    RESOLUTION_FLOOR,
    ZeroClassification,
    frozen_ladder_anchors,
    load_frozen_anchor_manifest,
    recover_global_relative,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("trends_v2_capture")

SUBJECT_UNIVERSE_PATH = ROOT / "backend/artifacts/collector_v6_redesign_research/pokemon_subject_universe.json"
CHECKPOINT_DIR = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture"
CHECKPOINT_ROWS_PATH = CHECKPOINT_DIR / "checkpoint_rows.jsonl"
CHECKPOINT_HEADER_PATH = CHECKPOINT_DIR / "checkpoint_header.json"

CODE_VERSION = "capture_pokemon_trends_anchor_ladder_v2_r1"
TIMEFRAME = "today 1-m"
GEO = "US"
DELAY_SECONDS = 8.0
TARGETS_PER_BATCH = 4  # + 1 shared anchor term = batch size 5, matches provider limits
MAX_BATCH_RETRIES = 2
RETRY_BACKOFF_SECONDS = 20.0

# Fixed (not cohort-recomputed) fan_popularity_score thresholds for INITIAL rung
# assignment only -- established once from the audited population distribution
# (docs/research/collector_appeal_v6_pokemon_baseline_transform_final.md Phase 1:
# p25=50.33, median=59.74, p75=69.70, p90=80.81, p95=85.27). This never determines the
# final calibrated value, only which anchor a target is batched with (efficiency).
FAN_TIER_THRESHOLDS = [
    (85.27, "Pikachu"),
    (80.81, "Charizard"),
    (69.70, "Lucario"),
    (59.74, "Torkoal"),
    (50.33, "Stunky"),
    (0.0, "Purugly"),
]

RUNG_ORDER = ["Purugly", "Stunky", "Torkoal", "Lucario", "Charizard", "Pikachu"]


def assign_initial_anchor(fan_popularity_score: Optional[float]) -> str:
    if fan_popularity_score is None:
        return "Purugly"  # most sensitive rung when no tier hint exists
    for threshold, anchor in FAN_TIER_THRESHOLDS:
        if fan_popularity_score >= threshold:
            return anchor
    return "Purugly"


def lower_rung(anchor: str) -> Optional[str]:
    idx = RUNG_ORDER.index(anchor)
    if idx == 0:
        return None
    return RUNG_ORDER[idx - 1]


@dataclass
class CaptureRow:
    subject_id: int
    pokedex_number: int
    pokemon_name: str
    assigned_anchor: str
    escalated: bool
    raw_target: Optional[float]
    raw_anchor: Optional[float]
    global_relative: Optional[float]
    classification: str
    retry_count: int
    failure_detail: Optional[str]
    manifest_version: str
    code_version: str
    query_settings: Dict[str, str]
    timestamp: float


def load_universe() -> List[Dict]:
    with open(SUBJECT_UNIVERSE_PATH, "r", encoding="utf-8") as handle:
        rows = json.load(handle)
    for row in rows:
        row["fan_popularity_score"] = float(row["fan_popularity_score"]) if row.get("fan_popularity_score") is not None else None
    return rows


def load_checkpoint() -> Dict[int, dict]:
    completed: Dict[int, dict] = {}
    if CHECKPOINT_ROWS_PATH.exists():
        with open(CHECKPOINT_ROWS_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                completed[row["subject_id"]] = row
    return completed


def verify_or_init_header(manifest_fingerprint: str) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    if CHECKPOINT_HEADER_PATH.exists():
        with open(CHECKPOINT_HEADER_PATH, "r", encoding="utf-8") as handle:
            header = json.load(handle)
        if header.get("manifest_fingerprint") != manifest_fingerprint or header.get("code_version") != CODE_VERSION:
            raise RuntimeError(
                "Checkpoint header mismatch: existing checkpoint was built with "
                f"manifest_fingerprint={header.get('manifest_fingerprint')!r} "
                f"code_version={header.get('code_version')!r}, current run has "
                f"manifest_fingerprint={manifest_fingerprint!r} code_version={CODE_VERSION!r}. "
                "Failing closed rather than silently mixing versions -- resolve or "
                "start a fresh checkpoint directory."
            )
    else:
        with open(CHECKPOINT_HEADER_PATH, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "manifest_fingerprint": manifest_fingerprint,
                    "code_version": CODE_VERSION,
                    "timeframe": TIMEFRAME,
                    "geo": GEO,
                    "started_at": time.time(),
                },
                handle,
                indent=2,
            )


def manifest_fingerprint(manifest: dict) -> str:
    import hashlib

    payload = json.dumps(
        {"anchorsAscending": manifest["anchorsAscending"], "bridges": manifest["bridges"]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def append_checkpoint_row(row: CaptureRow) -> None:
    with open(CHECKPOINT_ROWS_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(row)) + "\n")
        handle.flush()


def classify_and_record(
    provider: PytrendsGoogleTrendsProvider,
    subject: Dict,
    scale: Dict[str, float],
    manifest_version: str,
    stats: Dict[str, int],
) -> CaptureRow:
    query_settings = {"timeframe": TIMEFRAME, "geo": GEO, "queryType": QUERY_TYPE_SEARCH_TERM}
    anchor = assign_initial_anchor(subject["fan_popularity_score"])
    escalated = False
    retry_count = 0
    raw_target: Optional[float] = None
    raw_anchor: Optional[float] = None
    request_failed = False
    request_missing = False
    failure_detail: Optional[str] = None

    # An anchor cannot be compared with itself: pytrends requires distinct terms.
    # Use the same deterministic lower-rung escalation already frozen for a
    # resolution-limited result.  This changes neither the ladder nor calibration.
    if anchor == subject["pokemon_name"]:
        lower = lower_rung(anchor)
        if lower is None:
            raise RuntimeError(f"lowest ladder anchor {anchor!r} cannot self-calibrate")
        anchor = lower
        escalated = True
        retry_count += 1

    def do_query(anchor_name: str) -> Optional[Dict[str, float]]:
        nonlocal request_failed, failure_detail, stats
        for attempt in range(MAX_BATCH_RETRIES + 1):
            resp = provider.fetch_interest(
                terms=[anchor_name, subject["pokemon_name"]], timeframe=TIMEFRAME, geo=GEO, query_type=QUERY_TYPE_SEARCH_TERM
            )
            stats["requests"] = stats.get("requests", 0) + 1
            if resp.status == "captured":
                return resp.interest_by_term
            if resp.status == "insufficient_data":
                return {}
            stats["retries"] = stats.get("retries", 0) + 1
            if attempt < MAX_BATCH_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            request_failed = True
            failure_detail = f"status={resp.status} error_type={getattr(resp, 'error_type', None)}"
        return None

    interest = do_query(anchor)
    final_state: str
    if interest is None:
        final_state = ZeroClassification.FAILED.value
    else:
        raw_anchor = interest.get(anchor)
        raw_target = interest.get(subject["pokemon_name"])
        if raw_target is None or raw_anchor is None:
            final_state = ZeroClassification.MISSING_EVIDENCE.value
            request_missing = True
        elif raw_target > RESOLUTION_FLOOR:
            final_state = "SCORED"
        else:
            # RESOLUTION_LIMITED_ZERO candidate: escalate to next-lower rung if possible.
            lower = lower_rung(anchor)
            if lower is None:
                final_state = ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE.value
            else:
                escalated = True
                retry_count += 1
                interest2 = do_query(lower)
                if interest2 is None:
                    final_state = ZeroClassification.FAILED.value
                    request_failed = True
                else:
                    raw_anchor2 = interest2.get(lower)
                    raw_target2 = interest2.get(subject["pokemon_name"])
                    if raw_target2 is None or raw_anchor2 is None:
                        final_state = ZeroClassification.MISSING_EVIDENCE.value
                        request_missing = True
                    else:
                        anchor, raw_anchor, raw_target = lower, raw_anchor2, raw_target2
                        final_state = (
                            ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE.value
                            if raw_target <= RESOLUTION_FLOOR
                            else "SCORED"
                        )

    global_relative: Optional[float] = None
    if final_state == "SCORED":
        global_relative = recover_global_relative(raw_target, raw_anchor, scale[anchor])
        stats["scored"] = stats.get("scored", 0) + 1
    elif final_state == ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE.value:
        global_relative = 0.0
        stats["genuine_zero"] = stats.get("genuine_zero", 0) + 1
    elif final_state == ZeroClassification.MISSING_EVIDENCE.value:
        stats["missing"] = stats.get("missing", 0) + 1
    elif final_state == ZeroClassification.FAILED.value:
        stats["failed"] = stats.get("failed", 0) + 1

    return CaptureRow(
        subject_id=subject["pokemon_reference_id"],
        pokedex_number=subject["pokedex_number"],
        pokemon_name=subject["pokemon_name"],
        assigned_anchor=anchor,
        escalated=escalated,
        raw_target=raw_target,
        raw_anchor=raw_anchor,
        global_relative=global_relative,
        classification=final_state,
        retry_count=retry_count,
        failure_detail=failure_detail,
        manifest_version=manifest_version,
        code_version=CODE_VERSION,
        query_settings=query_settings,
        timestamp=time.time(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process at most N remaining subjects (for pilot runs).")
    args = parser.parse_args()

    manifest = load_frozen_anchor_manifest()
    fp = manifest_fingerprint(manifest)
    scale = {a.name: a.global_scale for a in frozen_ladder_anchors(manifest)}
    verify_or_init_header(fp)

    universe = load_universe()
    completed = load_checkpoint()
    log.info("Universe=%d, already completed=%d, manifest_fingerprint=%s", len(universe), len(completed), fp)

    provider = PytrendsGoogleTrendsProvider()
    stats: Dict[str, int] = {"requests": 0, "retries": 0}
    processed_this_run = 0

    for subject in universe:
        if subject["pokemon_reference_id"] in completed:
            continue
        if args.limit is not None and processed_this_run >= args.limit:
            break
        row = classify_and_record(provider, subject, scale, manifest["manifestVersion"], stats)
        append_checkpoint_row(row)
        completed[row.subject_id] = asdict(row)
        processed_this_run += 1
        log.info(
            "[%d/%d] %s (dex %d) -> anchor=%s escalated=%s state=%s global=%s",
            len(completed), len(universe), row.pokemon_name, row.pokedex_number,
            row.assigned_anchor, row.escalated, row.classification,
            f"{row.global_relative:.4f}" if row.global_relative is not None else "n/a",
        )
        time.sleep(DELAY_SECONDS)

    log.info("Run complete. processed_this_run=%d total_completed=%d stats=%s", processed_this_run, len(completed), stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
