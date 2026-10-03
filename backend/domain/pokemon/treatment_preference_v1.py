"""Runtime collection service for Treatment Direct Preference V1.

This surface is research-only. It reconstructs the frozen price-independent
45-triad manifest from canonical/simulation/control authority, verifies its
fingerprint, generates the frozen 450-block assignment schedule, and exposes
only blinded image comparisons to callers.
"""
from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from typing import Any
from uuid import UUID

from backend.scripts.research_treatment_direct_preference_assignment_v1 import (
    EXPECTED_MANIFEST_FINGERPRINT,
    generate as generate_assignment_schedule,
)
from backend.scripts.research_treatment_direct_preference_pair_manifest_v1 import (
    EDGES,
    MARKET_DATE,
    TREATMENTS,
    stable_hash,
)
from backend.scripts.research_treatment_set_relative_expansion_panel_v2 import (
    _paged,
    _subject_keys,
)
from backend.scripts.research_treatment_set_relative_hierarchy_v2 import (
    DOUBLE,
    SIR,
    ULTRA,
    load_controls,
)

STUDY_VERSION = "treatment_direct_preference_v1"
EXPECTED_SCHEDULE_FINGERPRINT = "4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055"
EXPECTED_TRIADS = 45
EXPECTED_PAIRS = 135
EXPECTED_BLOCKS = 450
QUESTIONS_PER_BLOCK = 12

_AUTHORITY_LOCK = threading.Lock()
_AUTHORITY_CACHE: dict[str, Any] | None = None


class TreatmentPreferenceV1Error(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _session_hash(session_id: str) -> str:
    text = str(session_id or "").strip()
    try:
        parsed = UUID(text)
    except (ValueError, TypeError, AttributeError) as exc:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_SESSION_INVALID",
            "A valid anonymous study session is required.",
        ) from exc
    canonical = str(parsed)
    return hashlib.sha256(f"{STUDY_VERSION}|{canonical}".encode()).hexdigest()


def _fast_frozen_manifest(db: Any) -> dict[str, Any]:
    """Rebuild only the frozen study subset, using batched reads.

    The research manifest builder is intentionally explicit but performs many
    per-card lookups. The public collection surface uses the same authorities
    and selection rule with batched simulation/pull reads, then verifies the
    exact preregistered subset fingerprint before any block can be served.
    """
    runs = _paged(
        lambda: db.table("calculation_runs")
        .select("id,target_id,created_at")
        .eq("market_date", MARKET_DATE)
        .eq("target_type", "set")
        .order("created_at", desc=True)
    )
    run_by_set: dict[str, str] = {}
    for row in runs:
        run_by_set.setdefault(str(row["target_id"]), str(row["id"]))
    if not run_by_set:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_AUTHORITY_UNAVAILABLE",
            "The frozen simulation authority is unavailable.",
            status_code=503,
        )

    set_rows: list[dict[str, Any]] = []
    for chunk in _chunks(sorted(run_by_set)):
        set_rows += list(
            db.table("sets").select("id,name,era_id").in_("id", chunk).execute().data
            or []
        )
    set_meta = {str(row["id"]): dict(row) for row in set_rows}
    if set(set_meta) != set(run_by_set):
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_SET_AUTHORITY_DRIFT",
            "The frozen Set authority has drifted.",
            status_code=503,
        )

    era_ids = sorted({str(row["era_id"]) for row in set_rows if row.get("era_id")})
    eras: dict[str, str] = {}
    for chunk in _chunks(era_ids):
        rows = db.table("eras").select("id,name").in_("id", chunk).execute().data or []
        eras.update({str(row["id"]): str(row["name"]) for row in rows})

    cards: list[dict[str, Any]] = []
    for chunk in _chunks(sorted(run_by_set)):
        cards += _paged(
            lambda chunk=chunk: db.table("pokemon_canonical_cards")
            .select(
                "id,set_id,pokemon_tcg_api_card_id,name,number,rarity,"
                "image_small_url,image_large_url"
            )
            .in_("set_id", chunk)
        )
    cards = [
        dict(row)
        for row in cards
        if str(row.get("rarity") or "").casefold() in TREATMENTS
        and row.get("pokemon_tcg_api_card_id")
    ]

    subjects = _subject_keys(db, [str(row["id"]) for row in cards])
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in cards:
        cid = str(row["id"])
        subject = subjects.get(cid)
        if subject:
            grouped[(str(row["set_id"]), subject)].append(row)

    raw_triads: list[dict[str, Any]] = []
    for (set_id, subject_key), group in grouped.items():
        by_rarity = {str(row["rarity"]).casefold(): row for row in group}
        if set(by_rarity) != TREATMENTS:
            continue
        sm = set_meta[set_id]
        raw_triads.append(
            {
                "set_id": set_id,
                "set_name": str(sm["name"]),
                "era_name": eras.get(str(sm.get("era_id")), "Unknown"),
                "subject_key": subject_key,
                "cards": [
                    by_rarity[DOUBLE.casefold()],
                    by_rarity[ULTRA.casefold()],
                    by_rarity[SIR.casefold()],
                ],
            }
        )

    api_ids = sorted(
        {
            str(card["pokemon_tcg_api_card_id"])
            for triad in raw_triads
            for card in triad["cards"]
        }
    )
    legacy_rows: list[dict[str, Any]] = []
    for chunk in _chunks(api_ids):
        legacy_rows += list(
            db.table("cards")
            .select("id,pokemon_tcg_api_id")
            .in_("pokemon_tcg_api_id", chunk)
            .execute()
            .data
            or []
        )
    legacy_by_api = {
        str(row["pokemon_tcg_api_id"]): str(row["id"]) for row in legacy_rows
    }

    candidate_legacy_ids = sorted(
        {
            legacy_by_api[str(card["pokemon_tcg_api_card_id"])]
            for triad in raw_triads
            for card in triad["cards"]
            if str(card["pokemon_tcg_api_card_id"]) in legacy_by_api
        }
    )
    sim_rows: list[dict[str, Any]] = []
    run_ids = sorted(set(run_by_set.values()))
    for chunk in _chunks(candidate_legacy_ids):
        sim_rows += _paged(
            lambda chunk=chunk: db.table("simulation_input_cards")
            .select("calculation_run_id,card_id,card_variant_id")
            .in_("calculation_run_id", run_ids)
            .in_("card_id", chunk)
        )
    sim_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in sim_rows:
        sim_by_key[(str(row["calculation_run_id"]), str(row["card_id"]))].append(
            str(row["card_variant_id"])
        )

    variant_ids = sorted({variant for values in sim_by_key.values() for variant in values})
    pull_rows: list[dict[str, Any]] = []
    for chunk in _chunks(variant_ids):
        pull_rows += _paged(
            lambda chunk=chunk: db.table("simulation_card_variant_pull_rates")
            .select("calculation_run_id,card_variant_id,modeled_probability")
            .in_("calculation_run_id", run_ids)
            .in_("card_variant_id", chunk)
        )
    pull_by_key: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in pull_rows:
        if row.get("modeled_probability") is not None:
            pull_by_key[
                (str(row["calculation_run_id"]), str(row["card_variant_id"]))
            ].append(float(row["modeled_probability"]))

    resolved: list[dict[str, Any]] = []
    for triad in raw_triads:
        run_id = run_by_set[triad["set_id"]]
        out_cards: list[dict[str, Any]] = []
        failed = False
        for card in triad["cards"]:
            legacy_id = legacy_by_api.get(str(card["pokemon_tcg_api_card_id"]))
            if not legacy_id:
                failed = True
                break
            variants = sim_by_key.get((run_id, legacy_id), [])
            if len(variants) != 1:
                failed = True
                break
            probabilities = pull_by_key.get((run_id, variants[0]), [])
            if len(probabilities) != 1 or probabilities[0] <= 0:
                failed = True
                break
            if not card.get("image_large_url"):
                failed = True
                break
            out_cards.append(
                {
                    "canonical_card_id": str(card["id"]),
                    "card_name": str(card["name"]),
                    "number": str(card["number"]),
                    "rarity": str(card["rarity"]),
                    "image_large_url": str(card["image_large_url"]),
                }
            )
        if not failed:
            resolved.append(
                {
                    **{k: v for k, v in triad.items() if k != "cards"},
                    "cards": out_cards,
                }
            )

    card_ids = sorted(
        {
            card["canonical_card_id"]
            for triad in resolved
            for card in triad["cards"]
        }
    )
    controls = load_controls(db, card_ids)

    eligible: list[dict[str, Any]] = []
    for triad in resolved:
        by = {card["rarity"]: card for card in triad["cards"]}
        ids = [by[t]["canonical_card_id"] for t in (DOUBLE, ULTRA, SIR)]
        if any(cid not in controls for cid in ids):
            continue
        subject_vals = [controls[cid]["subject"] for cid in ids]
        play_vals = [controls[cid]["playability"] for cid in ids]
        if max(subject_vals) - min(subject_vals) > 1e-9:
            continue
        if max(play_vals) - min(play_vals) > 1e-9:
            continue
        eligible.append(triad)

    mega_triads = sorted(
        [t for t in eligible if t["era_name"] == "Mega Evolution"],
        key=lambda t: (t["set_name"], t["subject_key"]),
    )
    sv_by_set: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for triad in eligible:
        if triad["era_name"] != "Scarlet and Violet":
            continue
        key = stable_hash(
            {"set_name": triad["set_name"], "subject_key": triad["subject_key"]}
        )
        sv_by_set[triad["set_name"]].append((key, triad))
    for rows in sv_by_set.values():
        rows.sort(key=lambda x: x[0])

    selected_sv = [rows[0][1] for _, rows in sorted(sv_by_set.items())]
    extra_sets = [
        set_name
        for set_name, _ in sorted(
            ((name, len(rows)) for name, rows in sv_by_set.items()),
            key=lambda x: (-x[1], x[0]),
        )[:10]
    ]
    for set_name in extra_sets:
        rows = sv_by_set[set_name]
        if len(rows) < 2:
            raise TreatmentPreferenceV1Error(
                "TREATMENT_PREFERENCE_SUBSET_DRIFT",
                "The frozen preference subset can no longer be reconstructed.",
                status_code=503,
            )
        selected_sv.append(rows[1][1])

    study_triads = mega_triads + selected_sv
    if len(mega_triads) != 21 or len(selected_sv) != 24 or len(study_triads) != EXPECTED_TRIADS:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_SUBSET_DRIFT",
            "The frozen preference subset has drifted.",
            status_code=503,
        )

    pairs: list[dict[str, Any]] = []
    for triad in study_triads:
        by = {card["rarity"]: card for card in triad["cards"]}
        for treatment_a, treatment_b in EDGES:
            a = by[treatment_a]
            b = by[treatment_b]
            payload = {
                "study_version": STUDY_VERSION,
                "set_id": triad["set_id"],
                "set_name": triad["set_name"],
                "era_name": triad["era_name"],
                "subject_key": triad["subject_key"],
                "treatment_a": treatment_a,
                "treatment_b": treatment_b,
                "card_a_id": a["canonical_card_id"],
                "card_a_name": a["card_name"],
                "card_a_number": a["number"],
                "card_a_image_large_url": a["image_large_url"],
                "card_b_id": b["canonical_card_id"],
                "card_b_name": b["card_name"],
                "card_b_number": b["number"],
                "card_b_image_large_url": b["image_large_url"],
            }
            payload["underlying_pair_id"] = stable_hash(payload)[:24]
            pairs.append(payload)

    pairs = sorted(
        pairs,
        key=lambda x: (
            x["era_name"],
            x["set_name"],
            x["subject_key"],
            x["treatment_a"],
            x["treatment_b"],
        ),
    )
    if len(pairs) != EXPECTED_PAIRS:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_PAIR_COUNT_DRIFT",
            "The frozen preference pair count has drifted.",
            status_code=503,
        )
    fingerprint = stable_hash(pairs)
    if fingerprint != EXPECTED_MANIFEST_FINGERPRINT:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_MANIFEST_FINGERPRINT_DRIFT",
            "The frozen preference manifest fingerprint does not match.",
            status_code=503,
        )

    return {
        "study_subset": {
            "manifest_fingerprint": fingerprint,
            "triad_count": EXPECTED_TRIADS,
            "pair_count": EXPECTED_PAIRS,
            "pairs": pairs,
        }
    }


def build_runtime_authority(db: Any) -> dict[str, Any]:
    manifest = _fast_frozen_manifest(db)
    schedule = generate_assignment_schedule(manifest)
    if schedule.get("schedule_fingerprint") != EXPECTED_SCHEDULE_FINGERPRINT:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_SCHEDULE_FINGERPRINT_DRIFT",
            "The frozen preference assignment schedule does not match.",
            status_code=503,
        )
    if len(schedule.get("blocks") or []) != EXPECTED_BLOCKS:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_BLOCK_COUNT_DRIFT",
            "The frozen preference block count does not match.",
            status_code=503,
        )
    pair_by_id = {
        str(row["underlying_pair_id"]): row
        for row in manifest["study_subset"]["pairs"]
    }
    block_by_id = {
        str(row["block_id"]): row for row in schedule["blocks"]
    }
    return {
        "manifest": manifest,
        "schedule": schedule,
        "pair_by_id": pair_by_id,
        "block_by_id": block_by_id,
    }


def runtime_authority(db: Any) -> dict[str, Any]:
    global _AUTHORITY_CACHE
    if _AUTHORITY_CACHE is not None:
        return _AUTHORITY_CACHE
    with _AUTHORITY_LOCK:
        if _AUTHORITY_CACHE is None:
            _AUTHORITY_CACHE = build_runtime_authority(db)
    return _AUTHORITY_CACHE


def clear_runtime_authority_cache() -> None:
    global _AUTHORITY_CACHE
    with _AUTHORITY_LOCK:
        _AUTHORITY_CACHE = None


def claim_block(db: Any, session_id: str) -> dict[str, Any]:
    authority = runtime_authority(db)
    session_hash = _session_hash(session_id)
    rows = (
        db.rpc(
            "claim_pokemon_treatment_preference_v1_block",
            {"p_session_hash": session_hash},
        )
        .execute()
        .data
        or []
    )
    if not rows:
        return {
            "studyVersion": STUDY_VERSION,
            "status": "complete",
            "message": "This collection round is complete.",
        }
    claim = dict(rows[0])
    if claim.get("already_completed"):
        return {
            "studyVersion": STUDY_VERSION,
            "status": "submitted",
            "message": "Your responses were already submitted. Thank you.",
        }

    block_index = int(claim["block_index"])
    blocks = authority["schedule"]["blocks"]
    if block_index < 0 or block_index >= len(blocks):
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_BLOCK_INDEX_INVALID",
            "The assigned preference block is invalid.",
            status_code=503,
        )
    block = blocks[block_index]
    return {
        "studyVersion": STUDY_VERSION,
        "status": "ready",
        "blockId": block["block_id"],
        "claimToken": str(claim["claim_token"]),
        "questionCount": QUESTIONS_PER_BLOCK,
        "prompt": "Which version would you rather own for the artwork/presentation itself?",
        "questions": [
            {
                "pairId": q["underlying_pair_id"],
                "leftImageUrl": q["left_image_url"],
                "rightImageUrl": q["right_image_url"],
            }
            for q in block["questions"]
        ],
    }


def submit_block(
    db: Any,
    *,
    session_id: str,
    block_id: str,
    claim_token: str,
    answers: list[dict[str, str]],
) -> dict[str, Any]:
    authority = runtime_authority(db)
    session_hash = _session_hash(session_id)
    block = authority["block_by_id"].get(str(block_id))
    if not block:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_BLOCK_UNKNOWN",
            "The preference block is not recognized.",
        )
    try:
        token = str(UUID(str(claim_token)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_CLAIM_TOKEN_INVALID",
            "The preference block claim is invalid.",
        ) from exc

    if len(answers) != QUESTIONS_PER_BLOCK:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_ANSWER_COUNT_INVALID",
            f"Exactly {QUESTIONS_PER_BLOCK} answers are required.",
        )
    answer_by_pair: dict[str, str] = {}
    for answer in answers:
        pair_id = str(answer.get("pairId") or "")
        response = str(answer.get("response") or "").upper()
        if response not in {"LEFT", "RIGHT", "TIE"}:
            raise TreatmentPreferenceV1Error(
                "TREATMENT_PREFERENCE_RESPONSE_INVALID",
                "Each response must be LEFT, RIGHT, or TIE.",
            )
        if not pair_id or pair_id in answer_by_pair:
            raise TreatmentPreferenceV1Error(
                "TREATMENT_PREFERENCE_PAIR_DUPLICATE",
                "Each comparison must be answered exactly once.",
            )
        answer_by_pair[pair_id] = response

    expected_ids = {str(q["underlying_pair_id"]) for q in block["questions"]}
    if set(answer_by_pair) != expected_ids:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_PAIR_SET_MISMATCH",
            "The submitted comparisons do not match the assigned block.",
        )

    rows: list[dict[str, Any]] = []
    for q in block["questions"]:
        pair_id = str(q["underlying_pair_id"])
        pair = authority["pair_by_id"][pair_id]
        orientation = str(q["randomized_orientation_receipt"])
        if orientation == "A_LEFT":
            left_treatment = pair["treatment_a"]
            right_treatment = pair["treatment_b"]
        else:
            left_treatment = pair["treatment_b"]
            right_treatment = pair["treatment_a"]
        rows.append(
            {
                "underlying_pair_id": pair_id,
                "set_id": q["set_id"],
                "subject_key": q["subject_key"],
                "left_card_id": q["left_card_id"],
                "right_card_id": q["right_card_id"],
                "left_treatment": left_treatment,
                "right_treatment": right_treatment,
                "randomized_orientation_receipt": orientation,
                "response": answer_by_pair[pair_id],
            }
        )

    result = (
        db.rpc(
            "submit_pokemon_treatment_preference_v1_block",
            {
                "p_session_hash": session_hash,
                "p_claim_token": token,
                "p_block_index": int(block["block_index"]),
                "p_responses": rows,
            },
        )
        .execute()
        .data
        or []
    )
    if not result:
        raise TreatmentPreferenceV1Error(
            "TREATMENT_PREFERENCE_SUBMISSION_FAILED",
            "The preference responses could not be recorded.",
            status_code=503,
        )
    receipt = dict(result[0])
    return {
        "studyVersion": STUDY_VERSION,
        "status": "submitted",
        "acceptedResponses": int(receipt.get("accepted_responses") or 0),
        "alreadySubmitted": bool(receipt.get("already_completed")),
        "message": "Thank you. Your blinded preference responses were recorded.",
    }
