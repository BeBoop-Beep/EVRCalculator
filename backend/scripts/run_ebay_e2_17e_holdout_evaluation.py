"""Evaluate sealed OCR-v3 predictions against frozen E2.17C truth, once."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "artifacts/index_fair_value"
EXPECTED = {
    "corpus": "f032b201ae2b85c16b7cb4296f5bb08c29a90d5d8a19e02a8c9e8716d770fd7d",
    "label": "b3f2f23d11db6d77ed93c9ff997de6c769775a30175ce69e62a2c78299813e22",
    "prediction": "f0d1032df2a64eec10771eb5f153b889212904a3e2a0c347b8ce768a7c943757",
    "ocr_v3": "79bed607ff3a34bf701030d5f2947048f176427010fbc34273c91588a0059756",
}


class PreconditionsFailed(RuntimeError):
    pass


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def wilson(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - margin, center + margin]


def preconditions(out: Path = OUT):
    queue_path = out / "ebay_e2_17c_small_japanese_holdout_queue.csv"
    raw_path = out / "ebay_e2_17c_small_japanese_holdout_raw_internal.jsonl"
    history_path = out / "ebay_e2_17c_small_japanese_holdout_review_history.jsonl"
    prediction_path = out / "ebay_e2_17d_ocr_v3_holdout_predictions.json"
    queue = list(csv.DictReader(queue_path.open(encoding="utf-8", newline="")))
    raw = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line]
    history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line]
    manifest = json.loads((out / "ebay_e2_17c_small_japanese_holdout_manifest.json").read_text(encoding="utf-8"))
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))
    freeze = json.loads((out / "ebay_e2_17d_ocr_v3_freeze_manifest.json").read_text(encoding="utf-8"))
    pred_rows = predictions["rows"]
    ids = lambda rows: [r["row_id"] for r in rows]

    def require(ok: bool, reason: str):
        if not ok:
            raise PreconditionsFailed("EBAY_E2_17E_BLOCKED_" + reason)

    require(len(queue) == len(raw) == len(pred_rows) == 43, "ROW_COUNT")
    require(all(len(set(ids(rows))) == 43 for rows in (queue, raw, pred_rows)), "DUPLICATE_ROW_ID")
    require(set(ids(queue)) == set(ids(raw)) == set(ids(pred_rows)), "ROW_SET")
    raw_by_id = {r["row_id"]: r for r in raw}
    require(all(all(q.get(field) == raw_by_id[q["row_id"]].get(field)
                    for field in ("canonical_card_id", "image_url")) for q in queue), "COHORT_EVIDENCE")
    corpus = digest("|".join(sorted(r["row_id"] + ":" + r["listing_item_id"] for r in raw)))
    labels = digest("\n".join(sorted(r["row_id"] + ":" + r["human_truth_label"] for r in queue)))
    predicted = digest("|".join(sorted(r["row_id"] + ":" + r["ocr_v3_decision"] for r in pred_rows)))
    require(corpus == manifest.get("corpus_fingerprint") == EXPECTED["corpus"], "CORPUS_FINGERPRINT")
    require(labels == manifest.get("label_fingerprint") == EXPECTED["label"], "LABEL_FINGERPRINT")
    require(predicted == predictions.get("prediction_fingerprint_sha256") == EXPECTED["prediction"], "PREDICTION_FINGERPRINT")
    require(predictions.get("ocr_v3_freeze_fingerprint_sha256") == freeze.get("freeze_fingerprint_sha256") == EXPECTED["ocr_v3"], "OCR_V3_FINGERPRINT")
    require(Counter(r["human_truth_label"] for r in queue) == {"JAPANESE": 6, "NOT_JAPANESE": 36, "UNCERTAIN": 1}, "TRUTH_COUNTS")
    require(manifest.get("labels_frozen") is True and manifest.get("development_holdout") is True
            and manifest.get("production_authority") is False, "LABEL_FREEZE")
    require(datetime.fromisoformat(predictions["created_at"]) < datetime.fromisoformat(manifest["review_session_started_at"]), "SEAL_ORDER")
    require(prediction_path.stat().st_mtime < history_path.stat().st_mtime and
            datetime.fromisoformat(predictions["created_at"]) < min(datetime.fromisoformat(e["timestamp"]) for e in history), "SEAL_MUTATION")
    require(history_path.stat().st_mtime < datetime.fromisoformat(manifest["freeze_timestamp"]).timestamp(), "POST_FREEZE_LABEL_MUTATION")
    effective = {}
    undone = {e.get("target_event_id") for e in history if e.get("action") == "undo"}
    for event in history:
        if event.get("action") == "label" and event.get("event_id") not in undone:
            effective[event["row_id"]] = event
    require(set(effective) == set(ids(queue)) and all(q["human_truth_label"] == effective[q["row_id"]]["human_truth_label"] for q in queue), "HISTORY_LABELS")
    # The reviewer page renders a fixed allowlist. The prediction file is only read by freeze verification.
    try:
        from backend.scripts import ebay_e2_17c_holdout_review_server as server
    except ModuleNotFoundError:
        import ebay_e2_17c_holdout_review_server as server
    require(server.REVIEWER_VISIBLE_COLUMNS == {"row_id", "canonical_card_id", "image_url"}, "REVIEWER_BLINDING")
    require("ocr_v3_decision" not in queue[0] and "human_truth_label" not in pred_rows[0], "EVIDENCE_LEAK")
    return queue, pred_rows, {"corpus_fingerprint": corpus, "label_fingerprint": labels,
                             "prediction_fingerprint": predicted, "ocr_v3_freeze_fingerprint": EXPECTED["ocr_v3"],
                             "prediction_created_at": predictions["created_at"],
                             "review_started_at": manifest["review_session_started_at"]}


def evaluate(queue, pred_rows):
    pred = {r["row_id"]: r for r in pred_rows}
    counts = Counter()
    misses = []
    false_positives = []
    uncertain = []
    for row in queue:
        truth = row["human_truth_label"]
        p = pred[row["row_id"]]
        mismatch = p["ocr_v3_decision"] == "JAPANESE_MISMATCH"
        detail = {"row_id": row["row_id"], "canonical_card_id": row["canonical_card_id"],
                  "human_truth_label": truth, **p}
        if truth == "UNCERTAIN":
            uncertain.append(detail)
        elif truth == "JAPANESE":
            counts["TP" if mismatch else "FN"] += 1
            if not mismatch:
                misses.append(detail)
        else:
            counts["FP" if mismatch else "TN"] += 1
            if mismatch:
                false_positives.append(detail)
    tp, fp, fn, tn = (counts[k] for k in ("TP", "FP", "FN", "TN"))
    return {"confusion": {k: counts[k] for k in ("TP", "FP", "FN", "TN")}, "precision": tp / (tp + fp) if tp + fp else None,
            "precision_wilson_95": wilson(tp, tp + fp), "japanese_recall": tp / (tp + fn),
            "false_japanese_mismatch_rate": fp / (fp + tn), "specificity": tn / (fp + tn),
            "japanese_misses": misses, "false_positives": false_positives,
            "uncertain": uncertain}


if __name__ == "__main__":
    queue, pred, integrity = preconditions()
    result = {"stage": "e2_17e_sealed_ocr_v3_holdout_evaluation", "integrity": integrity,
              **evaluate(queue, pred)}
    path = OUT / "ebay_e2_17e_ocr_v3_holdout_evaluation.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("japanese_misses", "false_positives", "uncertain")}, indent=2))
