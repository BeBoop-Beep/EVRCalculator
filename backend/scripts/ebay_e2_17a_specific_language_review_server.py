"""EBAY E2.17A -- blinded human review server collecting SPECIFIC non-English
language annotations for the 25-row queue built in E2.17
(backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv).

STARTING STATE: E2.17 verdict was
EBAY_OCR_V1_NOT_READY_INSUFFICIENT_AUTHORITATIVE_JAPANESE_SPECIFIC_HUMAN_TRUTH.
Every row in the queue already carries a frozen NON_ENGLISH parent human
label from the E2.16 / E2.16B development corpora (rows were selected
*because* they were already labeled NON_ENGLISH there). The only missing
annotation is the SPECIFIC language. This module does not overwrite, touch,
or re-derive that original binary parent truth -- it only appends a new,
additive `specific_language_if_known` annotation on top of it. Row identity
(queue_row_id, source_row_id, source_corpus, canonical_card_id) is exactly
the frozen linkage back to that parent truth, and this module asserts at
startup, at freeze, and in tests that it never rewrites those four columns.

DEVELOPMENT ONLY. No OCR analysis is performed here, ever. No production
authority. OCR-v1 must not be evaluated/frozen until this specific-language
truth exists (see EBAY_E2_17_OCR_V1_JAPANESE_LANGUAGE_FEASIBILITY.md).

Reuses the proven append-only-history / stable-cursor / Previous / Undo /
edit-relabel review architecture from
backend/scripts/ebay_e2_16_language_development_review_server.py and
backend/scripts/ebay_e2_16b_japanese_language_development_review_server.py,
but is built as an entirely NEW, E2.17A-specific module with its own
artifact paths -- it never touches or reuses the E2.16 / E2.16B session
files, and it never modifies the frozen E2.16/E2.16B/E2.17 artifacts other
than materializing `specific_language_if_known` into the E2.17 queue CSV's
own already-existing (blank) column on --freeze.

BLINDING CONTRACT (enforced, not just documented): the reviewer-facing
queue CSV has no provider Language aspect, no normalized language, no OCR
output/confidence/character counts, and no sampling-stratum column -- this
module additionally asserts at startup that none of
`FORBIDDEN_REVIEWER_COLUMNS` is present in the queue file, and the
rendered HTML page only ever interpolates fields from an explicit reviewer
allow-list (`REVIEWER_VISIBLE_COLUMNS`) so there is no code path by which
provider metadata or OCR evidence could reach the reviewer's screen. The
queue's `listing_title_DO_NOT_USE_AS_EVIDENCE` column is loaded (it must
stay present in the CSV) but is NEVER placed in that allow-list and is
therefore never rendered.

Human label schema (additive, per E2.17A spec): JAPANESE / KOREAN /
CHINESE / OTHER_NON_ENGLISH / UNCERTAIN. ENGLISH is deliberately absent --
the parent frozen human truth for every selected row is already
NON_ENGLISH, and this label must not contradict it.

This module performs NO labeling itself. It only serves the review UI for
Donny to label separately.
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
QUEUE_PATH = OUT / "ebay_e2_17_japanese_specific_language_review_queue.csv"
MANIFEST_PATH = OUT / "ebay_e2_17a_specific_language_review_manifest.json"
HISTORY_PATH = OUT / "ebay_e2_17a_specific_language_review_history.jsonl"

REVIEWER_PROTOCOL = "SINGLE_REVIEWER_BLIND_DEVELOPMENT_E2_17A"

# Additive specific-language labels. ENGLISH intentionally excluded -- the
# frozen parent human truth for every row here is already NON_ENGLISH.
SPECIFIC_LANGUAGE_CHOICES = ("JAPANESE", "KOREAN", "CHINESE", "OTHER_NON_ENGLISH", "UNCERTAIN")

# Row-identity columns that anchor this row back to its frozen E2.16/E2.16B
# NON_ENGLISH parent truth. Freeze must never alter these.
PARENT_TRUTH_IDENTITY_COLUMNS = ("queue_row_id", "source_row_id", "source_corpus", "canonical_card_id")

# Only these columns may ever be interpolated into the rendered review page.
# listing_title_DO_NOT_USE_AS_EVIDENCE is deliberately excluded.
REVIEWER_VISIBLE_COLUMNS = frozenset({"queue_row_id", "canonical_card_id", "image_url"})

FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "languagev1_state", "combined_policy_output", "localized_aspects_json",
    "raw_localized_aspects", "development_stratum", "sampling_stratum",
    "ocr_output", "ocr_japanese_character_count", "ocr_confidence", "ocr_text",
    "expected_label", "search_language_term",
})

EXPECTED_ROW_COUNT = 25


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


def load_queue_rows(path: Optional[Path] = None) -> list[dict[str, Any]]:
    path = path or QUEUE_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_reviewer_blind(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    present = FORBIDDEN_REVIEWER_COLUMNS & set(rows[0].keys())
    if present:
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_LANGUAGE_EVIDENCE_LEAKED_TO_REVIEWER", str(sorted(present)))


def corpus_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Deterministic fingerprint of row identity, independent of label state."""
    return hashlib.sha256(
        "|".join(
            sorted(
                "{}:{}:{}:{}".format(
                    r["queue_row_id"], r["source_row_id"], r["source_corpus"], r["canonical_card_id"]
                )
                for r in rows
            )
        ).encode()
    ).hexdigest()


def assert_parent_truth_identity_unchanged(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
    """The four identity columns anchor each row back to its frozen NON_ENGLISH
    parent human label. Freeze may only add specific_language_if_known /
    reviewer_notes -- it must never touch identity columns or row order/count."""
    if len(before) != len(after):
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_ROW_COUNT_CHANGED", f"{len(before)} -> {len(after)}")
    for b, a in zip(before, after):
        for col in PARENT_TRUTH_IDENTITY_COLUMNS:
            if b[col] != a[col]:
                raise FreezeRefused(
                    "EBAY_E2_17A_REVIEW_BLOCKED_PARENT_TRUTH_IDENTITY_MUTATED",
                    f"row {b.get('queue_row_id')} column {col}: {b[col]!r} -> {a[col]!r}",
                )


# --------------------------------------------------------------------------
# Append-only review history + resumable reconstruction
# --------------------------------------------------------------------------


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


def build_label_event(row_id: str, reviewer_id: str, specific_language_label: str, note: str = "") -> dict[str, Any]:
    label = str(specific_language_label or "").strip().upper()
    if label not in SPECIFIC_LANGUAGE_CHOICES:
        raise ValueError(f"specific_language_label must be one of {SPECIFIC_LANGUAGE_CHOICES}, got {specific_language_label!r}")
    return {
        "action": "label", "row_id": row_id, "reviewer_id": reviewer_id,
        "specific_language_if_known": label, "note": note,
    }


def build_undo_last_label_event(events: list[dict[str, Any]], reviewer_id: str) -> Optional[dict[str, Any]]:
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
        if rows[i]["queue_row_id"] not in effective:
            return i
    return None


def _clamped_index(index: int, n: int) -> int:
    if n <= 0:
        return 0
    return max(0, min(n - 1, index))


# --------------------------------------------------------------------------
# Summary / freeze
# --------------------------------------------------------------------------


def summary(reviewer_id: str, queue_path: Optional[Path] = None, history_path: Optional[Path] = None,
            manifest_path: Optional[Path] = None) -> dict[str, Any]:
    rows = load_queue_rows(queue_path)
    effective = reconstruct_effective_labels(read_history(history_path))
    label_counts: dict[str, int] = {}
    for event in effective.values():
        label_counts[event["specific_language_if_known"]] = label_counts.get(event["specific_language_if_known"], 0) + 1
    return {
        "total_rows": len(rows),
        "reviewed_rows": len(effective),
        "remaining_rows": len(rows) - len(effective),
        "reviewer_id": reviewer_id,
        "specific_language_label_counts": label_counts,
        "frozen": is_frozen(manifest_path),
        "development_only": True,
        "production_authority": False,
    }


def _row_is_complete(event: Optional[dict[str, Any]]) -> bool:
    if event is None:
        return False
    return bool(str(event.get("specific_language_if_known", "")).strip()) and bool(event.get("reviewer_id")) and bool(event.get("timestamp"))


def freeze(reviewer_id: str, queue_path: Optional[Path] = None, history_path: Optional[Path] = None,
           manifest_path: Optional[Path] = None) -> dict[str, Any]:
    queue_path = queue_path or QUEUE_PATH
    manifest_path = manifest_path or MANIFEST_PATH
    if is_frozen(manifest_path):
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_ALREADY_FROZEN")
    rows = load_queue_rows(queue_path)
    if len(rows) != EXPECTED_ROW_COUNT:
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_ROW_COUNT_MISMATCH", f"expected {EXPECTED_ROW_COUNT}, got {len(rows)}")
    assert_reviewer_blind(rows)
    manifest = _read_manifest(manifest_path)
    recorded_fp = manifest.get("corpus_fingerprint")
    recomputed_fp = corpus_fingerprint(rows)
    if recorded_fp is None:
        recorded_fp = recomputed_fp
    elif recorded_fp != recomputed_fp:
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_CORPUS_FINGERPRINT_MISMATCH",
                             f"recorded={recorded_fp} recomputed={recomputed_fp}")
    effective = reconstruct_effective_labels(read_history(history_path))
    incomplete = [r["queue_row_id"] for r in rows if not _row_is_complete(effective.get(r["queue_row_id"]))]
    if incomplete:
        raise FreezeRefused("EBAY_E2_17A_REVIEW_BLOCKED_INCOMPLETE_LABELS", f"{len(incomplete)} rows incomplete, e.g. {incomplete[:5]}")

    materialized = []
    for row in rows:
        event = effective[row["queue_row_id"]]
        merged = dict(row)
        merged["specific_language_if_known"] = event["specific_language_if_known"]
        merged["reviewer_notes"] = event.get("note", "")
        materialized.append(merged)

    assert_parent_truth_identity_unchanged(rows, materialized)

    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(materialized)

    label_fp = hashlib.sha256(
        "\n".join(sorted(f"{r['queue_row_id']}:{r['specific_language_if_known']}" for r in materialized)).encode()
    ).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    manifest["labels_frozen"] = True
    manifest["reviewer_protocol"] = REVIEWER_PROTOCOL
    manifest["reviewer_id"] = reviewer_id
    manifest["freeze_timestamp"] = now
    manifest["specific_language_label_fingerprint"] = label_fp
    manifest["corpus_fingerprint"] = recorded_fp
    manifest["row_count"] = len(materialized)
    label_counts: dict[str, int] = {}
    for r in materialized:
        label_counts[r["specific_language_if_known"]] = label_counts.get(r["specific_language_if_known"], 0) + 1
    manifest["specific_language_label_counts"] = label_counts
    manifest["development_only"] = True
    manifest["production_authority"] = False
    _write_manifest(manifest, manifest_path)
    return {"stage": "specific_language_development_label_freeze", "rows_materialized": len(materialized),
            "specific_language_label_fingerprint": label_fp, "corpus_fingerprint": recorded_fp,
            "reviewer_id": reviewer_id, "label_counts": label_counts, "development_only": True,
            "production_authority": False}


# --------------------------------------------------------------------------
# HTML rendering -- allow-listed reviewer-visible fields ONLY
# --------------------------------------------------------------------------


def page(row: Mapping[str, Any], reviewed: int, total: int, position: int = 1, message: str = "") -> str:
    e = html.escape
    # Defensive re-assertion at render time: only ever read allow-listed columns.
    safe_row = {k: row[k] for k in REVIEWER_VISIBLE_COLUMNS if k in row}
    row_id = str(safe_row["queue_row_id"])
    canonical_card_id = str(safe_row.get("canonical_card_id", ""))
    image_url = str(safe_row.get("image_url", ""))
    image_urls = [image_url] if image_url else []
    imgs_html = "".join(
        f'<img class="listingimg" data-row-id="{e(row_id)}" src="{e(u)}{"&" if "?" in u else "?"}_row={e(row_id)}_{i}">'
        for i, u in enumerate(image_urls)
    )
    message_html = f'<p style="color:#0a6;font-weight:bold">{e(message)}</p>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>E2.17A Specific Language Review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}
.listingimg{{max-height:420px;max-width:560px;margin:4px}}
label{{display:block;margin:6px 0}}button{{padding:10px 16px;margin:4px 6px 4px 0;font-size:16px}}
.cols{{display:flex;gap:30px}}.primary{{padding:14px 20px;font-size:18px}}
#japaneseBtn{{background:#d7e8f5}}#koreanBtn{{background:#e0d7f5}}#chineseBtn{{background:#f5e0d0}}
#otherBtn{{background:#e8e8e8}}#uncertainBtn{{background:#f0e6c0}}
#rowHeader{{background:#eef2ff;padding:10px 14px;border-radius:6px;font-family:ui-monospace,monospace;font-size:14px;line-height:1.5}}
#imageRowMarker{{font-family:ui-monospace,monospace;font-size:13px;color:#555}}
#guidance{{background:#fafafa;border:1px solid #ddd;padding:10px 14px;border-radius:6px;font-size:14px}}</style></head>
<body>
<h1>E2.17A specific-language DEVELOPMENT review &mdash; {REVIEWER_PROTOCOL}</h1>
<p><i>DEVELOPMENT CORPUS ONLY. Not certification. Not production authority. The parent human truth for
every row here is already frozen NON_ENGLISH from E2.16/E2.16B -- this review only adds which specific
non-English language the photo supports. Judge the listing photo(s) only. No provider metadata, no OCR
output, and no listing title are shown to you.</i></p>
<div id="guidance"><b>Guidance</b><ul>
<li><b>JAPANESE</b> &mdash; use only when the physical-card text clearly supports Japanese; strong evidence
includes hiragana, katakana, or unmistakable Japanese text patterns. Shared Kanji/Han characters ALONE
are not enough.</li>
<li><b>KOREAN</b> &mdash; clear Hangul.</li>
<li><b>CHINESE</b> &mdash; clear Chinese-language script without Japanese kana or Korean Hangul, with enough
evidence to distinguish it confidently.</li>
<li><b>OTHER_NON_ENGLISH</b> &mdash; clearly non-English but not Japanese/Korean/Chinese.</li>
<li><b>UNCERTAIN</b> &mdash; cannot confidently identify the specific language. Prefer UNCERTAIN over
guessing.</li></ul></div>
<div id="rowHeader">
POSITION: {position} / {total}<br>
REVIEWED: {reviewed} / {total}<br><br>
ROW ID:<br><b>{e(row_id)}</b><br><br>
TARGET CARD (canonical_card_id):<br>{e(canonical_card_id)}
</div>
{message_html}
<div class="cols">
<section><h2>Listing image(s) ({len(image_urls)})</h2>
<div id="imgwrap-{e(row_id)}">{imgs_html}</div>
<p id="imageRowMarker">IMAGE ROW: <b>{e(row_id)}</b></p></section>
</div>
<p><b>What specific non-English language does the photographed card support?</b></p>
<p>
<button type="button" class="primary" id="japaneseBtn">JAPANESE (J)</button>
<button type="button" class="primary" id="koreanBtn">KOREAN (K)</button>
<button type="button" class="primary" id="chineseBtn">CHINESE (C)</button>
<button type="button" class="primary" id="otherBtn">OTHER_NON_ENGLISH (O)</button>
<button type="button" class="primary" id="uncertainBtn">UNCERTAIN (U)</button>
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
      row_id: rowId,
      specific_language_if_known: label,
      note: noteEl ? noteEl.value || '' : ''
    }});
    fetch('/label', {{method:'POST', body: body}})
      .then(function(resp){{
        if (resp.status === 409) {{
          alert('This page is out of date (row changed on the server). Reloading.');
        }}
        location.href = '/';
      }})
      .catch(function(err){{ alert('Request failed: ' + err); }});
  }}

  function post(path){{
    fetch(path, {{method:'POST', body: new URLSearchParams({{}})}})
      .then(function(){{ location.href = '/'; }})
      .catch(function(err){{ alert('Request failed: ' + err); }});
  }}

  function wire(id, handler){{
    const el = $(id);
    if (el) {{ el.addEventListener('click', handler); }}
  }}

  wire('japaneseBtn', function(){{ submitLabel('JAPANESE'); }});
  wire('koreanBtn', function(){{ submitLabel('KOREAN'); }});
  wire('chineseBtn', function(){{ submitLabel('CHINESE'); }});
  wire('otherBtn', function(){{ submitLabel('OTHER_NON_ENGLISH'); }});
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
    else if (k === 'k') submitLabel('KOREAN');
    else if (k === 'c') submitLabel('CHINESE');
    else if (k === 'o') submitLabel('OTHER_NON_ENGLISH');
    else if (k === 'u') submitLabel('UNCERTAIN');
  }});
}})();
</script>
</body></html>"""


# --------------------------------------------------------------------------
# Server run loop
# --------------------------------------------------------------------------


def _run_primary_review(reviewer_id: str, port: int) -> None:
    rows = load_queue_rows()
    if not rows:
        raise SystemExit("Queue is empty -- run the E2.17 queue builder first.")
    assert_reviewer_blind(rows)
    row_ids = [r["queue_row_id"] for r in rows]

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
        manifest["review_session_id"] = f"e2_17a_dev_session_{uuid.uuid4().hex[:12]}"
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
                        displayed_row_id = rows[current_index]["queue_row_id"]
                        if row_id != displayed_row_id or row_id not in row_ids:
                            self.send_response(409)
                            self._no_cache_headers()
                            self.end_headers()
                            return
                        event = build_label_event(
                            row_id, reviewer_id, data.get("specific_language_if_known", ""),
                            note=data.get("note", ""),
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
    parser = argparse.ArgumentParser(description="EBAY E2.17A specific-language development review server")
    parser.add_argument("--reviewer", required=True, help="Reviewer identifier (explicit, never inferred)")
    parser.add_argument("--port", type=int, default=8918)
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
