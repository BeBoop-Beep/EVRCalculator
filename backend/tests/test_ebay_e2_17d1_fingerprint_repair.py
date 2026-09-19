"""Regression coverage for the E2.17C immutable cohort freeze contract."""
import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from backend.scripts import build_ebay_e2_17c_small_japanese_holdout as builder
from backend.scripts import ebay_e2_17c_holdout_review_server as server


def fixture_rows():
    raw = [{"row_id": f"r{i:02d}", "listing_item_id": f"listing{i}",
            "canonical_card_id": f"card{i}", "image_url": f"image{i}"}
           for i in range(43)]
    queue = [{**r, "human_truth_label": "", "human_note": ""} for r in raw]
    pred = [{"row_id": r["row_id"]} for r in raw]
    return raw, queue, pred


def check(tmp_path, raw, queue, pred, recorded=None):
    raw_path = tmp_path / "raw.jsonl"
    pred_path = tmp_path / "pred.json"
    raw_path.write_text("".join(json.dumps(r) + "\n" for r in raw), encoding="utf-8")
    pred_path.write_text(json.dumps({"rows": pred}), encoding="utf-8")
    return server.verify_cohort(queue, raw_path, pred_path,
                                recorded or builder.cohort_fingerprint(fixture_rows()[0]))


def test_builder_contract_labels_and_newlines(tmp_path):
    raw, queue, pred = fixture_rows()
    expected = builder.cohort_fingerprint(raw)
    assert server.corpus_fingerprint(raw) == expected == check(tmp_path, raw, queue, pred)
    queue[0]["human_truth_label"] = "JAPANESE"
    queue[0]["human_note"] = "reviewed"
    assert check(tmp_path, raw, queue, pred) == expected
    for newline in ("\r\n", "\n"):
        path = tmp_path / "queue.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=queue[0].keys(), lineterminator=newline)
            writer.writeheader()
            writer.writerows(queue)
        assert check(tmp_path, raw, server.load_queue_rows(path), pred) == expected


@pytest.mark.parametrize("mutation", ["missing_raw", "extra_raw", "canonical",
                                      "image", "listing", "membership", "predictions"])
def test_mutated_cohort_blocks(tmp_path, mutation):
    raw, queue, pred = fixture_rows()
    if mutation == "missing_raw":
        raw.pop()
    elif mutation == "extra_raw":
        raw.append({**raw[0], "row_id": "extra"})
    elif mutation == "canonical":
        queue[0]["canonical_card_id"] = "changed"
    elif mutation == "image":
        queue[0]["image_url"] = "changed"
    elif mutation == "listing":
        raw[0]["listing_item_id"] = "changed"
    elif mutation == "membership":
        queue[0]["row_id"] = "changed"
    elif mutation == "predictions":
        pred[0]["row_id"] = "changed"
    with pytest.raises(server.FreezeRefused):
        check(tmp_path, raw, queue, pred)


def test_original_manifest_hash_recomputes():
    raw_path = server.RAW_INTERNAL_PATH
    manifest = json.loads(server.MANIFEST_PATH.read_text(encoding="utf-8"))
    raw = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    assert builder.cohort_fingerprint(raw) == server.corpus_fingerprint(raw)
    assert server.corpus_fingerprint(raw) == manifest["corpus_fingerprint"]
    assert manifest["corpus_fingerprint"] == "f032b201ae2b85c16b7cb4296f5bb08c29a90d5d8a19e02a8c9e8716d770fd7d"
