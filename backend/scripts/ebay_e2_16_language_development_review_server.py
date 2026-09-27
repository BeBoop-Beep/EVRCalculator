"""EBAY E2.16 -- blinded human review server for the LANGUAGE-v1 DEVELOPMENT
corpus (backend/artifacts/index_fair_value/ebay_e2_16_language_development_queue.csv).

DEVELOPMENT ONLY. No certification, no production authority, no policy
freeze. Reuses the proven append-only-history / stable-cursor / Previous /
Undo / edit-relabel review architecture from the E2.9B/E2.13 fresh-blind
review servers (backend/scripts/ebay_e2_13_blind_review_server.py), but is
built as an entirely NEW, E2.16-specific module with its own artifact
paths -- it never touches or reuses the E2.13/E2.9B/D3-v5 session files.

BLINDING CONTRACT (enforced, not just documented): this server reads the
reviewer-facing queue CSV, which the E2.16 corpus builder
(build_ebay_e2_16_language_development_cohort.py) already wrote WITHOUT any
Language aspect, normalized-language, or policy-output column. This module
additionally asserts at startup that none of `FORBIDDEN_REVIEWER_COLUMNS`
is present in the queue file, and the rendered HTML page only ever
interpolates fields from that same forbidden-column-free row -- so there is
no code path by which getItem's Language aspect, LANGUAGE-v1's normalized
result, or any COMBINED policy output could reach the reviewer's screen.

Human truth label schema (per E2.16 spec): ENGLISH / NON_ENGLISH /
UNCERTAIN, plus an optional free-text `human_language_if_known`. The
reviewer judges the PHYSICAL LISTING/PHOTO ONLY -- never provider metadata.

This module performs NO labeling itself. It only serves the review UI for
Donny to label separately (a future E2.16A task performs the FN/FP/TP/TN
analysis against the internal raw artifact that retains the hidden
Language aspect).
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
QUEUE_PATH = OUT / "ebay_e2_16_language_development_queue.csv"
MANIFEST_PATH = OUT / "ebay_e2_16_language_development_manifest.json"
HISTORY_PATH = OUT / "ebay_e2_16_language_development_review_history.jsonl"

REVIEWER_PROTOCOL = "SINGLE_REVIEWER_BLIND_DEVELOPMENT"

HUMAN_TRUTH_CHOICES = ("ENGLISH", "NON_ENGLISH", "UNCERTAIN")

# Fields the queue CSV must NEVER contain -- if any of these are present,
# something has (incorrectly) leaked getItem Language-aspect or policy
# output into the blind reviewer-facing cohort.
FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "languagev1_state", "combined_policy_output", "localized_aspects_json",
    "development_stratum",  # stratum is internal provenance, not shown to keep the reviewer
                             # from inferring the sampling strategy's language-targeting intent
})

HUMAN_VISIBLE_FIELDS = (
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "listing_title", "condition", "buying_options_json", "image_url", "item_url", "seller_id",
)


class ReviewFrozen(RuntimeError):
    pass


class FreezeRefused(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# --------------------------------------------------------------------------
# Queue loading + blinding assertion
# --------------------------------------------------------------------------


def load_queue_rows() -> list[dict[str, Any]]:
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_reviewer_blind(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    present = FORBIDDEN_REVIEWER_COLUMNS & set(rows[0].keys())
    if present:
        raise FreezeRefused("EBAY_E2_16_REVIEW_BLOCKED_LANGUAGE_EVIDENCE_LEAKED_TO_REVIEWER", str(sorted(present)))


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    # Must match build_ebay_e2_16_language_development_cohort.cohort_fingerprint
    # exactly ("|" separator, not "\n") -- this is the same fingerprint the
    # manifest records, and --freeze recomputes and compares against it.
    return hashlib.sha256(
        "|".join(sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


# --------------------------------------------------------------------------
# Append-only review history + resumable reconstruction
# --------------------------------------------------------------------------


def _read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_frozen() -> bool:
    return bool(_read_manifest().get("labels_frozen"))


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


def append_event(event: Mapping[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    if is_frozen():
        raise ReviewFrozen("labels are frozen; no further review-history writes are permitted")
    return _append(event, path or HISTORY_PATH)


def reconstruct_effective_labels(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest non-undone label event per row_id. Undo never deletes history
    -- it appends an undo event referencing the target event_id. Editing an
    already-labeled row (a re-label) is simply a new label event for the
    same row_id -- its result naturally supersedes the prior one here.
    """
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


def build_label_event(row_id: str, reviewer_id: str, human_truth_label: str,
                       language_if_known: str = "", note: str = "") -> dict[str, Any]:
    label = str(human_truth_label or "").strip().upper()
    if label not in HUMAN_TRUTH_CHOICES:
        raise ValueError(f"human_truth_label must be one of {HUMAN_TRUTH_CHOICES}, got {human_truth_label!r}")
    return {
        "action": "label", "row_id": row_id, "reviewer_id": reviewer_id,
        "human_truth_label": label, "human_language_if_known": str(language_if_known or "").strip(),
        "note": note,
    }


def build_undo_last_label_event(events: list[dict[str, Any]], reviewer_id: str) -> Optional[dict[str, Any]]:
    """Undo the single most recently RECORDED label event across the WHOLE
    history, regardless of which row is currently on screen (same fix as
    E2.13's Undo -- targeting the currently displayed row was the defect
    class that E2.9B/E2.13 exist to avoid repeating).
    """
    undone_ids = {e.get("target_event_id") for e in events if e["action"] == "undo"}
    label_events = [e for e in events if e["action"] == "label" and e["event_id"] not in undone_ids]
    if not label_events:
        return None
    target = label_events[-1]
    return {"action": "undo", "row_id": target["row_id"], "reviewer_id": reviewer_id, "target_event_id": target["event_id"]}


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


# --------------------------------------------------------------------------
# Summary / freeze (read-only until --freeze)
# --------------------------------------------------------------------------


def summary(reviewer_id: str) -> dict[str, Any]:
    rows = load_queue_rows()
    effective = reconstruct_effective_labels(read_history())
    label_counts: dict[str, int] = {}
    for event in effective.values():
        label_counts[event["human_truth_label"]] = label_counts.get(event["human_truth_label"], 0) + 1
    return {
        "total_rows": len(rows),
        "reviewed_rows": len(effective),
        "remaining_rows": len(rows) - len(effective),
        "reviewer_id": reviewer_id,
        "human_truth_label_counts": label_counts,
        "frozen": is_frozen(),
        "development_only": True,
        "production_authority": False,
    }


def _row_is_complete(event: Optional[dict[str, Any]]) -> bool:
    if event is None:
        return False
    return bool(str(event.get("human_truth_label", "")).strip()) and bool(event.get("reviewer_id")) and bool(event.get("timestamp"))


def freeze(reviewer_id: str) -> dict[str, Any]:
    if is_frozen():
        raise FreezeRefused("EBAY_E2_16_REVIEW_BLOCKED_ALREADY_FROZEN")
    rows = load_queue_rows()
    assert_reviewer_blind(rows)
    if not MANIFEST_PATH.exists():
        raise FreezeRefused("EBAY_E2_16_REVIEW_BLOCKED_MANIFEST_MISSING")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded_fp = manifest.get("corpus_fingerprint")
    recomputed_fp = cohort_fingerprint(rows)
    if recorded_fp != recomputed_fp:
        raise FreezeRefused("EBAY_E2_16_REVIEW_BLOCKED_CORPUS_FINGERPRINT_MISMATCH",
                             f"recorded={recorded_fp} recomputed={recomputed_fp}")
    effective = reconstruct_effective_labels(read_history())
    incomplete = [r["row_id"] for r in rows if not _row_is_complete(effective.get(r["row_id"]))]
    if incomplete:
        raise FreezeRefused("EBAY_E2_16_REVIEW_BLOCKED_INCOMPLETE_LABELS", f"{len(incomplete)} rows incomplete, e.g. {incomplete[:5]}")

    materialized = []
    for row in rows:
        event = effective[row["row_id"]]
        merged = dict(row)
        merged["human_truth_label"] = event["human_truth_label"]
        merged["human_language_if_known"] = event.get("human_language_if_known", "")
        merged["reviewer_id"] = event["reviewer_id"]
        merged["label_timestamp"] = event["timestamp"]
        merged["review_note"] = event.get("note", "")
        materialized.append(merged)
    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as handle:
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
    manifest["development_only"] = True
    manifest["production_authority"] = False
    _write_manifest(manifest)
    return {"stage": "development_label_freeze", "rows_materialized": len(materialized),
            "label_fingerprint": label_fp, "corpus_fingerprint": recorded_fp, "reviewer_id": reviewer_id}


# --------------------------------------------------------------------------
# HTML rendering -- human-observable fields ONLY, no language evidence
# --------------------------------------------------------------------------


def page(row: Mapping[str, Any], reviewed: int, total: int, position: int = 1, message: str = "") -> str:
    e = html.escape
    row_id = str(row["row_id"])
    target_line = f"{row['target_card_name']} — {row['target_set_name']} — #{row['target_card_number']} — {row['target_treatment']}"
    img_src = str(row.get("image_url") or "")
    cache_bust_sep = "&" if "?" in img_src else "?"
    cache_bust_src = f"{img_src}{cache_bust_sep}_row={row_id}" if img_src else ""
    message_html = f'<p style="color:#0a6;font-weight:bold">{e(message)}</p>' if message else ""
    return f"""<!doctype html><meta charset="utf-8"><title>E2.16 Language Development Review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}img{{max-height:360px;max-width:480px}}
label{{display:block;margin:6px 0}}button{{padding:10px 16px;margin:4px 6px 4px 0;font-size:16px}}
.cols{{display:flex;gap:30px}}.primary{{padding:18px 28px;font-size:20px}}
#englishBtn{{background:#d7f5d0}}#nonEnglishBtn{{background:#f5d0d0}}#uncertainBtn{{background:#f0e6c0}}
#rowHeader{{background:#eef2ff;padding:10px 14px;border-radius:6px;font-family:ui-monospace,monospace;font-size:14px;line-height:1.5}}
#imageRowMarker{{font-family:ui-monospace,monospace;font-size:13px;color:#555}}</style>
<h1>E2.16 language DEVELOPMENT review &mdash; {REVIEWER_PROTOCOL}</h1>
<p><i>DEVELOPMENT CORPUS ONLY. Not certification. Not production authority.
Judge only the listing/photo shown below -- never provider metadata.</i></p>
<div id="rowHeader">
POSITION: {position} / {total}<br>
REVIEWED: {reviewed} / {total}<br><br>
ROW ID:<br><b>{e(row_id)}</b><br><br>
LISTING ITEM ID:<br>{e(str(row.get('listing_item_id', '')))}<br><br>
TARGET (expected English printing):<br>{e(target_line)}<br><br>
LISTING:<br>{e(str(row['listing_title']))}
</div>
{message_html}
<div class="cols">
<section><h2>Target instrument</h2>
<p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>
#{e(str(row['target_card_number']))}<br>Treatment: {e(str(row['target_treatment']))}</p></section>
<section><h2>eBay listing</h2>
<p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>
Buying options: {e(str(row.get('buying_options_json') or ''))}<br>Seller: {e(str(row.get('seller_id') or ''))}</p>
<img id="rowimg-{e(row_id)}" data-row-id="{e(row_id)}" key="{e(row_id)}" src="{e(cache_bust_src)}">
<p id="imageRowMarker">IMAGE ROW: <b>{e(row_id)}</b></p>
<p><a href="{e(str(row.get('item_url') or ''))}" target="_blank">Open listing on eBay</a></p></section>
</div>
<p><b>Does this listing physically show the expected ENGLISH printing of the target card?</b></p>
<p>
<button type="button" class="primary" id="englishBtn">ENGLISH (E)</button>
<button type="button" class="primary" id="nonEnglishBtn">NON-ENGLISH (N)</button>
<button type="button" class="primary" id="uncertainBtn">UNCERTAIN (U)</button>
</p>
<details><summary>If non-English, which language (optional, your best guess from the photo only)</summary>
<label>Language if known<br><input type="text" id="langKnown" style="width:100%"></label>
<label>Note (optional)<br><input type="text" id="note" style="width:100%"></label></details>
<p>
<button type="button" id="prevBtn">&larr; Previous (B)</button>
<button type="button" id="nextBtn">Next (F)</button>
<button type="button" id="undo">Undo Last</button>
</p>
<script>
const rowId={json.dumps(row_id)};
function submitLabel(label){{
  const body={{row_id:rowId,human_truth_label:label,
    human_language_if_known:(document.getElementById('langKnown')||{{}}).value||'',
    note:(document.getElementById('note')||{{}}).value||''}};
  fetch('/label',{{method:'POST',body:new URLSearchParams(body)}}).then(()=>location.href='/');
}}
englishBtn.onclick=()=>submitLabel('ENGLISH');
nonEnglishBtn.onclick=()=>submitLabel('NON_ENGLISH');
uncertainBtn.onclick=()=>submitLabel('UNCERTAIN');
undo.onclick=()=>fetch('/undo',{{method:'POST',body:new URLSearchParams({{}})}}).then(()=>location.href='/');
prevBtn.onclick=()=>fetch('/previous',{{method:'POST'}}).then(()=>location.href='/');
nextBtn.onclick=()=>fetch('/next',{{method:'POST'}}).then(()=>location.href='/');
onkeydown=function(ev){{
  const k=ev.key.toLowerCase();
  if(k==='b'){{prevBtn.click();return;}}
  if(k==='f'){{nextBtn.click();return;}}
  if(k==='e')submitLabel('ENGLISH');else if(k==='n')submitLabel('NON_ENGLISH');else if(k==='u')submitLabel('UNCERTAIN');
}};
</script>"""


# --------------------------------------------------------------------------
# Server run loop
# --------------------------------------------------------------------------


def _run_primary_review(reviewer_id: str, port: int) -> None:
    rows = load_queue_rows()
    if not rows:
        raise SystemExit("Queue is empty -- run build_ebay_e2_16_language_development_cohort.py first.")
    assert_reviewer_blind(rows)
    row_ids = [r["row_id"] for r in rows]

    lock = threading.Lock()

    def compute_effective() -> dict[str, dict[str, Any]]:
        return reconstruct_effective_labels(read_history())

    initial_effective = compute_effective()
    initial_index = next_unreviewed_index(rows, initial_effective, -1)
    cursor: dict[str, Any] = {"index": initial_index if initial_index is not None else 0, "message": ""}

    # Record the session id on first launch (idempotent: if a session id is
    # already recorded, e.g. resuming a partially-reviewed corpus, it is
    # left unchanged).
    manifest = _read_manifest()
    if not manifest.get("review_session_id"):
        manifest["review_session_id"] = f"e2_16_dev_session_{uuid.uuid4().hex[:12]}"
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
                        event = build_label_event(
                            row_id, reviewer_id, data.get("human_truth_label", ""),
                            language_if_known=data.get("human_language_if_known", ""), note=data.get("note", ""),
                        )
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
    parser = argparse.ArgumentParser(description="EBAY E2.16 language development review server")
    parser.add_argument("--reviewer", required=True, help="Reviewer identifier (explicit, never inferred)")
    parser.add_argument("--port", type=int, default=8916)
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
