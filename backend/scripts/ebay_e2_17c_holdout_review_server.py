"""EBAY E2.17C -- blinded human review server for the small independent
Japanese-vs-not-Japanese DEVELOPMENT HOLDOUT
(backend/artifacts/index_fair_value/ebay_e2_17c_small_japanese_holdout_queue.csv).

DEVELOPMENT ONLY. No production authority. This server performs NO OCR of
any kind and NEVER runs OCR-v2 against a row during review (see the task's
"do not build any code path that would run it during review" requirement).
It only shows the reviewer the listing image(s) and collects one of exactly
three labels.

HUMAN REVIEW CONTRACT (per task spec, enforced not just documented):
  Only three buttons: JAPANESE / NOT_JAPANESE / UNCERTAIN.
  NOT_JAPANESE means "confidently not Japanese" regardless of which other
  language it actually is (Korean, Chinese, English, anything).
  UNCERTAIN means the physical card language cannot be identified
  confidently from the photo(s).

BLINDING CONTRACT (enforced): the reviewer-facing queue CSV
(REVIEWER_VISIBLE_COLUMNS below) never includes provider Language aspect,
sampling stratum, search query term, listing title, or any OCR-v2 output
(kana/Hangul/Han counts, confidence, decision). assert_reviewer_blind()
checks the loaded CSV against FORBIDDEN_REVIEWER_COLUMNS at every server
start and at freeze, and the HTML renderer only ever interpolates fields
from REVIEWER_VISIBLE_COLUMNS -- there is no code path by which hidden
columns could reach the page.

Reuses the proven append-only-history / stable-cursor / Previous / Undo /
relabel review architecture from ebay_e2_16b_japanese_language_development_review_server.py
and ebay_e2_17a_specific_language_review_server.py, as a new dedicated
E2.17C module with its own artifact paths.

This module performs NO labeling itself. reviewed_count starts at 0 and
stays 0 until Donny runs a live review session separately.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/index_fair_value"
QUEUE_PATH = OUT / "ebay_e2_17c_small_japanese_holdout_queue.csv"
MANIFEST_PATH = OUT / "ebay_e2_17c_small_japanese_holdout_manifest.json"
HISTORY_PATH = OUT / "ebay_e2_17c_small_japanese_holdout_review_history.jsonl"
RAW_INTERNAL_PATH = OUT / "ebay_e2_17c_small_japanese_holdout_raw_internal.jsonl"
PREDICTIONS_PATH = OUT / "ebay_e2_17d_ocr_v3_holdout_predictions.json"

REVIEWER_PROTOCOL = "SINGLE_REVIEWER_BLIND_DEVELOPMENT_E2_17C"

# Exactly three buttons. No other label is ever accepted.
LABEL_CHOICES = ("JAPANESE", "NOT_JAPANESE", "UNCERTAIN")

ROW_IDENTITY_COLUMNS = ("row_id", "canonical_card_id")

# Only these columns may ever be interpolated into the rendered review page.
REVIEWER_VISIBLE_COLUMNS = frozenset({"row_id", "canonical_card_id", "image_url"})

FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "development_stratum", "search_language_term", "listing_title",
    "ocr_v2_decision", "japanese_kana_count", "korean_hangul_count",
    "cjk_shared_count", "confidence", "seller_query_language",
    "high_conf_kana_count", "num_regions", "mean_region_conf",
})

EXPECTED_ROW_COUNT_RANGE = (20, 45)


class ReviewFrozen(RuntimeError):
    pass


class FreezeRefused(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def load_queue_rows(path: Optional[Path] = None) -> list[dict[str, Any]]:
    path = path or QUEUE_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_reviewer_blind(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    present = FORBIDDEN_REVIEWER_COLUMNS & set(rows[0].keys())
    if present:
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_EVIDENCE_LEAKED_TO_REVIEWER", str(sorted(present)))


def corpus_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "|".join(sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)).encode("utf-8")
    ).hexdigest()


def verify_cohort(queue_rows: list[dict[str, Any]], raw_path: Path,
                  predictions_path: Path, recorded_fp: str) -> str:
    """Verify captured membership and evidence before writing human labels."""
    try:
        with raw_path.open(encoding="utf-8") as handle:
            raw_rows = [json.loads(line) for line in handle if line.strip()]
        predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
        prediction_rows = predictions["rows"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_COHORT_ARTIFACT_INVALID", str(exc)) from exc

    def indexed(rows: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
        ids = [r.get("row_id") for r in rows]
        if len(rows) != 43 or any(not x for x in ids) or len(set(ids)) != 43:
            raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_ROW_MEMBERSHIP_MISMATCH", name)
        return {r["row_id"]: r for r in rows}

    queue = indexed(queue_rows, "queue")
    raw = indexed(raw_rows, "retained raw")
    sealed = indexed(prediction_rows, "sealed predictions")
    if queue.keys() != raw.keys() or queue.keys() != sealed.keys():
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_ROW_MEMBERSHIP_MISMATCH")
    for row_id, row in queue.items():
        for field in ("row_id", "canonical_card_id", "image_url"):
            if row.get(field) != raw[row_id].get(field):
                raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_COHORT_EVIDENCE_MISMATCH",
                                    f"{row_id}:{field}")
        if not raw[row_id].get("listing_item_id"):
            raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_COHORT_EVIDENCE_MISMATCH",
                                f"{row_id}:listing_item_id")
    recomputed = corpus_fingerprint(raw_rows)
    if recorded_fp != recomputed:
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_CORPUS_FINGERPRINT_MISMATCH",
                            f"recorded={recorded_fp} recomputed={recomputed}")
    return recomputed


def _read_manifest(path: Optional[Path] = None) -> dict[str, Any]:
    path = path or MANIFEST_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(manifest: dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or MANIFEST_PATH
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_frozen(path: Optional[Path] = None) -> bool:
    return bool(_read_manifest(path).get("labels_frozen"))


def read_history(path: Optional[Path] = None, actions: frozenset = frozenset({"label", "undo"})) -> list[dict[str, Any]]:
    path = path or HISTORY_PATH
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("action") in actions:
                events.append(event)
    return events


def _append(event: Mapping[str, Any], path: Path) -> dict[str, Any]:
    stored = dict(event)
    stored.setdefault("event_id", uuid.uuid4().hex)
    stored.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n")
    return stored


def append_event(event: Mapping[str, Any], path: Optional[Path] = None, manifest_path: Optional[Path] = None) -> dict[str, Any]:
    if is_frozen(manifest_path):
        raise ReviewFrozen("labels are frozen; no further review-history writes are permitted")
    return _append(event, path or HISTORY_PATH)


def reconstruct_effective_labels(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_row: dict[str, list[dict[str, Any]]] = {}
    undone_ids: set[str] = set()
    for event in events:
        if event["action"] == "label":
            by_row.setdefault(event["row_id"], []).append(event)
        elif event["action"] == "undo":
            undone_ids.add(event.get("target_event_id"))
    effective: dict[str, dict[str, Any]] = {}
    for row_id, row_events in by_row.items():
        valid = [e for e in row_events if e["event_id"] not in undone_ids]
        if valid:
            effective[row_id] = valid[-1]
    return effective


def build_label_event(row_id: str, reviewer_id: str, label: str, note: str = "") -> dict[str, Any]:
    label = str(label or "").strip().upper()
    if label not in LABEL_CHOICES:
        raise ValueError(f"label must be one of {LABEL_CHOICES}, got {label!r}")
    return {"action": "label", "row_id": row_id, "reviewer_id": reviewer_id,
            "human_truth_label": label, "note": note}


def build_undo_last_label_event(events: list[dict[str, Any]], reviewer_id: str) -> Optional[dict[str, Any]]:
    undone_ids = {e.get("target_event_id") for e in events if e["action"] == "undo"}
    label_events = [e for e in events if e["action"] == "label" and e["event_id"] not in undone_ids]
    if not label_events:
        return None
    target = label_events[-1]
    return {"action": "undo", "row_id": target["row_id"], "reviewer_id": reviewer_id,
            "target_event_id": target["event_id"]}


def next_unreviewed_index(rows: list[dict[str, Any]], effective: Mapping[str, dict[str, Any]], after: int = -1) -> Optional[int]:
    n = len(rows)
    for offset in range(1, n + 1):
        i = (after + offset) % n
        if rows[i]["row_id"] not in effective:
            return i
    return None


def _clamped_index(index: int, n: int) -> int:
    if n <= 0:
        return 0
    return max(0, min(n - 1, index))


def summary(reviewer_id: str, queue_path: Optional[Path] = None, history_path: Optional[Path] = None,
            manifest_path: Optional[Path] = None) -> dict[str, Any]:
    rows = load_queue_rows(queue_path)
    effective = reconstruct_effective_labels(read_history(history_path))
    label_counts: dict[str, int] = {}
    for event in effective.values():
        label_counts[event["human_truth_label"]] = label_counts.get(event["human_truth_label"], 0) + 1
    return {
        "total_rows": len(rows),
        "reviewed_rows": len(effective),
        "remaining_rows": len(rows) - len(effective),
        "reviewer_id": reviewer_id,
        "label_counts": label_counts,
        "frozen": is_frozen(manifest_path),
        "development_holdout": True,
        "production_authority": False,
    }


def _row_is_complete(event: Optional[dict[str, Any]]) -> bool:
    if event is None:
        return False
    return bool(str(event.get("human_truth_label", "")).strip()) and bool(event.get("reviewer_id")) and bool(event.get("timestamp"))


def freeze(reviewer_id: str, queue_path: Optional[Path] = None, history_path: Optional[Path] = None,
           manifest_path: Optional[Path] = None, raw_path: Optional[Path] = None,
           predictions_path: Optional[Path] = None) -> dict[str, Any]:
    queue_path = queue_path or QUEUE_PATH
    manifest_path = manifest_path or MANIFEST_PATH
    if is_frozen(manifest_path):
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_ALREADY_FROZEN")
    rows = load_queue_rows(queue_path)
    lo, hi = EXPECTED_ROW_COUNT_RANGE
    if not (lo <= len(rows) <= hi):
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_ROW_COUNT_OUT_OF_RANGE", f"expected [{lo},{hi}], got {len(rows)}")
    assert_reviewer_blind(rows)
    manifest = _read_manifest(manifest_path)
    recorded_fp = manifest.get("corpus_fingerprint")
    verify_cohort(rows, raw_path or RAW_INTERNAL_PATH,
                  predictions_path or PREDICTIONS_PATH, recorded_fp)
    history = read_history(history_path)
    row_ids = {r["row_id"] for r in rows}
    if any(event.get("row_id") not in row_ids for event in history):
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_REVIEW_MEMBERSHIP_MISMATCH")
    effective = reconstruct_effective_labels(history)
    if set(effective) != row_ids:
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_REVIEW_MEMBERSHIP_MISMATCH")
    incomplete = [r["row_id"] for r in rows if not _row_is_complete(effective.get(r["row_id"]))]
    if incomplete:
        raise FreezeRefused("EBAY_E2_17C_REVIEW_BLOCKED_INCOMPLETE_LABELS", f"{len(incomplete)} rows incomplete")

    materialized = []
    for row in rows:
        event = effective[row["row_id"]]
        merged = dict(row)
        merged["human_truth_label"] = event["human_truth_label"]
        merged["human_note"] = event.get("note", "")
        merged["reviewer_id"] = reviewer_id
        merged["label_timestamp"] = event.get("timestamp", "")
        materialized.append(merged)

    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(materialized)

    label_fp = hashlib.sha256(
        "\n".join(sorted(f"{r['row_id']}:{r['human_truth_label']}" for r in materialized)).encode()
    ).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    manifest["labels_frozen"] = True
    manifest["reviewer_protocol"] = REVIEWER_PROTOCOL
    manifest["reviewer_id"] = reviewer_id
    manifest["freeze_timestamp"] = now
    manifest["label_fingerprint"] = label_fp
    manifest["corpus_fingerprint"] = recorded_fp
    manifest["row_count"] = len(materialized)
    label_counts: dict[str, int] = {}
    for r in materialized:
        label_counts[r["human_truth_label"]] = label_counts.get(r["human_truth_label"], 0) + 1
    manifest["label_counts"] = label_counts
    manifest["development_holdout"] = True
    manifest["production_authority"] = False
    _write_manifest(manifest, manifest_path)
    return {"stage": "e2_17c_holdout_label_freeze", "rows_materialized": len(materialized),
            "label_fingerprint": label_fp, "corpus_fingerprint": recorded_fp,
            "reviewer_id": reviewer_id, "label_counts": label_counts,
            "development_holdout": True, "production_authority": False}


def page(row: Mapping[str, Any], reviewed: int, total: int, position: int = 1, message: str = "") -> str:
    e = html.escape
    safe_row = {k: row[k] for k in REVIEWER_VISIBLE_COLUMNS if k in row}
    row_id = str(safe_row["row_id"])
    canonical_card_id = str(safe_row.get("canonical_card_id", ""))
    image_url = str(safe_row.get("image_url", ""))
    image_urls = [image_url] if image_url else []
    imgs_html = "".join(
        f'<img class="listingimg" data-row-id="{e(row_id)}" src="{e(u)}{"&" if "?" in u else "?"}_row={e(row_id)}_{i}">'
        for i, u in enumerate(image_urls)
    )
    message_html = f'<p style="color:#0a6;font-weight:bold">{e(message)}</p>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>E2.17C Holdout Review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}
.listingimg{{max-height:460px;max-width:600px;margin:4px}}
button{{padding:12px 20px;margin:4px 8px 4px 0;font-size:18px}}
#japaneseBtn{{background:#d7e8f5}}#notJapaneseBtn{{background:#e0e0e0}}#uncertainBtn{{background:#f0e6c0}}
#rowHeader{{background:#eef2ff;padding:10px 14px;border-radius:6px;font-family:ui-monospace,monospace;font-size:14px;line-height:1.5}}
#guidance{{background:#fafafa;border:1px solid #ddd;padding:10px 14px;border-radius:6px;font-size:14px}}</style></head>
<body>
<h1>E2.17C small Japanese holdout DEVELOPMENT review &mdash; {REVIEWER_PROTOCOL}</h1>
<p><i>DEVELOPMENT HOLDOUT ONLY. Not certification. Not production authority. No provider metadata,
no OCR output, and no listing title are shown to you -- judge the photographed card only.</i></p>
<div id="guidance"><b>Guidance</b><ul>
<li><b>JAPANESE</b> &mdash; the physical card is confidently Japanese-language.</li>
<li><b>NOT_JAPANESE</b> &mdash; confidently NOT Japanese, regardless of what language it actually is
(Korean, Chinese, English, or anything else). Do not try to name the specific language.</li>
<li><b>UNCERTAIN</b> &mdash; you cannot confidently tell from the photo(s). Prefer UNCERTAIN over guessing.</li>
</ul></div>
<div id="rowHeader">
POSITION: {position} / {total}<br>
REVIEWED: {reviewed} / {total}<br><br>
ROW ID:<br><b>{e(row_id)}</b><br><br>
TARGET CARD (canonical_card_id):<br>{e(canonical_card_id)}
</div>
{message_html}
<section><h2>Listing image(s)</h2>
<div id="imgwrap-{e(row_id)}">{imgs_html}</div></section>
<p><b>Is the photographed card Japanese?</b></p>
<p>
<button type="button" id="japaneseBtn">JAPANESE (J)</button>
<button type="button" id="notJapaneseBtn">NOT_JAPANESE (N)</button>
<button type="button" id="uncertainBtn">UNCERTAIN (U)</button>
</p>
<details><summary>Note (optional)</summary>
<label>Note<br><input type="text" id="note" style="width:100%"></label></details>
<p>
<button type="button" id="prevBtn">&larr; Previous (B)</button>
<button type="button" id="nextBtn">Next (F)</button>
<button type="button" id="undo">Undo Last</button>
</p>
<script>
(function(){{
  const rowId={json.dumps(row_id)};
  const $ = function(id){{ return document.getElementById(id); }};
  function submitLabel(label){{
    const noteEl = $('note');
    const body = new URLSearchParams({{
      row_id: rowId, human_truth_label: label, note: noteEl ? noteEl.value || '' : ''
    }});
    fetch('/label', {{method:'POST', body: body}})
      .then(function(resp){{
        if (resp.status === 409) {{ alert('This page is out of date. Reloading.'); }}
        location.href = '/';
      }})
      .catch(function(err){{ alert('Request failed: ' + err); }});
  }}
  function post(path){{
    fetch(path, {{method:'POST', body: new URLSearchParams({{}})}})
      .then(function(){{ location.href = '/'; }})
      .catch(function(err){{ alert('Request failed: ' + err); }});
  }}
  function wire(id, handler){{ const el = $(id); if (el) {{ el.addEventListener('click', handler); }} }}
  wire('japaneseBtn', function(){{ submitLabel('JAPANESE'); }});
  wire('notJapaneseBtn', function(){{ submitLabel('NOT_JAPANESE'); }});
  wire('uncertainBtn', function(){{ submitLabel('UNCERTAIN'); }});
  wire('undo', function(){{ post('/undo'); }});
  wire('prevBtn', function(){{ post('/previous'); }});
  wire('nextBtn', function(){{ post('/next'); }});
  document.addEventListener('keydown', function(ev){{
    const tag = (ev.target && ev.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    const k = ev.key.toLowerCase();
    if (k === 'b') {{ post('/previous'); return; }}
    if (k === 'f') {{ post('/next'); return; }}
    if (k === 'j') submitLabel('JAPANESE');
    else if (k === 'n') submitLabel('NOT_JAPANESE');
    else if (k === 'u') submitLabel('UNCERTAIN');
  }});
}})();
</script>
</body></html>"""


def _run_primary_review(reviewer_id: str, port: int) -> None:
    rows = load_queue_rows()
    if not rows:
        raise SystemExit("Queue is empty -- run build_ebay_e2_17c_small_japanese_holdout.py first.")
    assert_reviewer_blind(rows)
    row_ids = [r["row_id"] for r in rows]

    lock = threading.Lock()

    def compute_effective() -> dict[str, dict[str, Any]]:
        return reconstruct_effective_labels(read_history())

    initial_effective = compute_effective()
    initial_index = next_unreviewed_index(rows, initial_effective, -1)
    cursor: dict[str, Any] = {"index": initial_index if initial_index is not None else 0, "message": ""}

    manifest = _read_manifest()
    if not manifest.get("corpus_fingerprint"):
        manifest["corpus_fingerprint"] = corpus_fingerprint(rows)
    if not manifest.get("review_session_id"):
        manifest["review_session_id"] = f"e2_17c_holdout_session_{uuid.uuid4().hex[:12]}"
        manifest["review_session_started_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest)

    print(json.dumps(summary(reviewer_id), indent=2, sort_keys=True))

    class Handler(BaseHTTPRequestHandler):
        def _no_cache_headers(self) -> None:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")

        def do_GET(self) -> None:
            with lock:
                query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
                row_param = query.get("row", [None])[0]
                if row_param and row_param in row_ids:
                    cursor["index"] = row_ids.index(row_param)
                effective = compute_effective()
                index = cursor["index"]
                message = cursor.get("message") or ""
                cursor["message"] = ""
                body = page(rows[index], len(effective), len(rows), position=index + 1, message=message).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._no_cache_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            with lock:
                try:
                    if self.path == "/undo":
                        event = build_undo_last_label_event(read_history(), reviewer_id)
                        if event:
                            append_event(event)
                            undone_row_id = event["row_id"]
                            if undone_row_id in row_ids:
                                cursor["index"] = row_ids.index(undone_row_id)
                            cursor["message"] = f"UNDID LABEL FOR {undone_row_id}"
                    elif self.path == "/previous":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) - 1, len(rows))
                    elif self.path == "/next":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) + 1, len(rows))
                    elif self.path == "/label":
                        row_id = data.get("row_id")
                        current_index = cursor["index"] or 0
                        displayed_row_id = rows[current_index]["row_id"]
                        if row_id != displayed_row_id or row_id not in row_ids:
                            self.send_response(409)
                            self._no_cache_headers()
                            self.end_headers()
                            return
                        event = build_label_event(row_id, reviewer_id, data.get("human_truth_label", ""),
                                                    note=data.get("note", ""))
                        append_event(event)
                        effective = compute_effective()
                        next_index = next_unreviewed_index(rows, effective, current_index)
                        cursor["index"] = next_index if next_index is not None else current_index
                except ReviewFrozen:
                    self.send_response(423)
                    self._no_cache_headers()
                    self.end_headers()
                    return
            self.send_response(204)
            self._no_cache_headers()
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass

    url = f"http://127.0.0.1:{port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EBAY E2.17C small Japanese holdout review server")
    parser.add_argument("--reviewer", required=True, help="Reviewer identifier (explicit, never inferred)")
    parser.add_argument("--port", type=int, default=8919)
    parser.add_argument("--summary", action="store_true", help="Print progress summary and exit")
    parser.add_argument("--freeze", action="store_true", help="Materialize final labels into the queue CSV and exit")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.summary:
        print(json.dumps(summary(args.reviewer), indent=2, sort_keys=True))
        return
    if args.freeze:
        result = freeze(args.reviewer)
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    _run_primary_review(args.reviewer, args.port)


if __name__ == "__main__":
    main()
