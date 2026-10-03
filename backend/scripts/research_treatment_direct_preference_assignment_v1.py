"""Generate the frozen Treatment Direct Preference V1 collection schedule.

Input is the frozen 45-triad / 135-pair manifest. Output is 450 blocks of 12
questions, exactly 40 exposures per pair and 20/20 left-right balance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SEED = 20261003
EXPECTED_MANIFEST_FINGERPRINT = "c8777261004c08f011407019819e1a02c58ca5db0f54fd110d20186618cf8c55"
BLOCK_COUNT = 450
QUESTIONS_PER_BLOCK = 12
EXPOSURES_PER_PAIR = 40
ORIENTATIONS_PER_SIDE = 20
EDGE_SLOTS_PER_BLOCK = 4


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def generate(manifest: dict[str, Any]) -> dict[str, Any]:
    subset = manifest.get("study_subset") or {}
    if subset.get("manifest_fingerprint") != EXPECTED_MANIFEST_FINGERPRINT:
        raise RuntimeError("frozen preference manifest fingerprint drift")
    pairs = [dict(row) for row in subset.get("pairs") or []]
    if len(pairs) != 135 or int(subset.get("triad_count") or 0) != 45:
        raise RuntimeError("frozen preference manifest size drift")

    edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        edge = f"{pair['treatment_a']}__{pair['treatment_b']}"
        edges[edge].append(pair)
    if sorted(len(rows) for rows in edges.values()) != [45, 45, 45]:
        raise RuntimeError("frozen edge pool drift")
    edge_order = sorted(edges)

    blocks = [
        {"questions": [], "subjects": Counter(), "edge_counts": Counter()}
        for _ in range(BLOCK_COUNT)
    ]

    for edge_index, edge in enumerate(edge_order):
        pair_rows = list(edges[edge])
        subject_frequency = Counter(row["subject_key"] for row in pair_rows)
        pair_rows.sort(
            key=lambda row: (
                -subject_frequency[row["subject_key"]],
                row["underlying_pair_id"],
            )
        )

        orientations: dict[str, list[str]] = {}
        for pair in pair_rows:
            values = ["A_LEFT"] * ORIENTATIONS_PER_SIDE + ["B_LEFT"] * ORIENTATIONS_PER_SIDE
            pair_seed = int(
                hashlib.sha256(
                    f"{pair['underlying_pair_id']}|{SEED}".encode()
                ).hexdigest()[:16],
                16,
            )
            rr = random.Random(pair_seed)
            rr.shuffle(values)
            orientations[pair["underlying_pair_id"]] = values

        tasks: list[tuple[dict[str, Any], str, int]] = []
        for exposure_round in range(EXPOSURES_PER_PAIR):
            round_pairs = list(pair_rows)
            rr = random.Random(SEED + exposure_round + 1000 * edge_index)
            rr.shuffle(round_pairs)
            for pair in round_pairs:
                tasks.append(
                    (
                        pair,
                        orientations[pair["underlying_pair_id"]][exposure_round],
                        exposure_round,
                    )
                )

        for task_index, (pair, orientation, exposure_round) in enumerate(tasks):
            candidates: list[tuple[tuple[int, int, int, int], int]] = []
            for block_index, block in enumerate(blocks):
                if block["edge_counts"][edge] >= EDGE_SLOTS_PER_BLOCK:
                    continue
                # Hard maximum two was preregistered; candidate scoring strongly
                # prefers zero repetition and the frozen manifest reaches zero.
                if block["subjects"][pair["subject_key"]] >= 2:
                    continue
                tie = int(
                    hashlib.sha256(
                        (
                            f"{SEED}|{pair['underlying_pair_id']}|{orientation}|"
                            f"{block_index}|{task_index}"
                        ).encode()
                    ).hexdigest()[:12],
                    16,
                )
                score = (
                    block["subjects"][pair["subject_key"]],
                    block["edge_counts"][edge],
                    len(block["questions"]),
                    tie,
                )
                candidates.append((score, block_index))
            if not candidates:
                raise RuntimeError(
                    f"assignment infeasible edge={edge} task={task_index} "
                    f"subject={pair['subject_key']}"
                )
            _, block_index = min(candidates)
            block = blocks[block_index]
            if orientation == "A_LEFT":
                left_card_id = pair["card_a_id"]
                right_card_id = pair["card_b_id"]
                left_image = pair["card_a_image_large_url"]
                right_image = pair["card_b_image_large_url"]
            else:
                left_card_id = pair["card_b_id"]
                right_card_id = pair["card_a_id"]
                left_image = pair["card_b_image_large_url"]
                right_image = pair["card_a_image_large_url"]
            block["questions"].append({
                "underlying_pair_id": pair["underlying_pair_id"],
                "set_id": pair["set_id"],
                "set_name": pair["set_name"],
                "era_name": pair["era_name"],
                "subject_key": pair["subject_key"],
                "left_card_id": left_card_id,
                "right_card_id": right_card_id,
                "left_image_url": left_image,
                "right_image_url": right_image,
                "randomized_orientation_receipt": orientation,
                "exposure_round": exposure_round,
            })
            block["subjects"][pair["subject_key"]] += 1
            block["edge_counts"][edge] += 1

    pair_exposures: dict[str, Counter] = defaultdict(Counter)
    output_blocks = []
    max_subject_repeat = 0
    for index, block in enumerate(blocks):
        if len(block["questions"]) != QUESTIONS_PER_BLOCK:
            raise RuntimeError(f"block size drift index={index}")
        if any(block["edge_counts"][edge] != EDGE_SLOTS_PER_BLOCK for edge in edge_order):
            raise RuntimeError(f"edge balance drift index={index}")
        max_subject_repeat = max(max_subject_repeat, max(block["subjects"].values()))
        for q in block["questions"]:
            pair_exposures[q["underlying_pair_id"]]["total"] += 1
            pair_exposures[q["underlying_pair_id"]][q["randomized_orientation_receipt"]] += 1
        block_payload = {
            "block_index": index,
            "questions": block["questions"],
        }
        output_blocks.append({
            "block_id": stable_hash(block_payload)[:24],
            **block_payload,
        })

    if max_subject_repeat != 1:
        raise RuntimeError(f"frozen schedule lost unique-subject blocks max={max_subject_repeat}")
    for pair in pairs:
        counts = pair_exposures[pair["underlying_pair_id"]]
        if counts["total"] != EXPOSURES_PER_PAIR:
            raise RuntimeError(f"pair exposure count drift {pair['underlying_pair_id']}")
        if counts["A_LEFT"] != ORIENTATIONS_PER_SIDE or counts["B_LEFT"] != ORIENTATIONS_PER_SIDE:
            raise RuntimeError(f"pair orientation balance drift {pair['underlying_pair_id']}")

    result = {
        "study_version": "treatment_direct_preference_v1",
        "seed": SEED,
        "source_manifest_fingerprint": EXPECTED_MANIFEST_FINGERPRINT,
        "block_count": BLOCK_COUNT,
        "questions_per_block": QUESTIONS_PER_BLOCK,
        "total_judgments": BLOCK_COUNT * QUESTIONS_PER_BLOCK,
        "pair_count": len(pairs),
        "exposures_per_pair": EXPOSURES_PER_PAIR,
        "orientations_per_side": ORIENTATIONS_PER_SIDE,
        "edge_slots_per_block": EDGE_SLOTS_PER_BLOCK,
        "max_subject_repetition_in_any_block": max_subject_repeat,
        "blocks": output_blocks,
        "production_writes": 0,
    }
    result["schedule_fingerprint"] = stable_hash(output_blocks)
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = generate(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        k: v for k, v in result.items() if k != "blocks"
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
