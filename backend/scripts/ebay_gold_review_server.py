"""Local, blinded, append-only eBay gold-label reviewer."""
from __future__ import annotations

import argparse
import html
import json
import threading
import uuid
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import parse_qs

from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS

SHORTCUTS = dict(zip(("1","2","3","4","5","6","7","8","9","0","o"), LABELS))
CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW"})
HISTORY = OUT / "ebay_gold_review_history.jsonl"


def read_history(path: Path = HISTORY) -> list[dict[str, Any]]:
    """Read valid events without modifying or rejecting an append-only ledger."""
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(event, dict):
                event = dict(event)
                event["_event_id"] = str(event.get("event_id") or f"legacy:{line_number}")
                events.append(event)
    return events


def _scope(event: Mapping[str, Any]) -> tuple[str, str]:
    return str(event.get("partition", "")).upper(), str(event.get("reviewer_id", ""))


def _valid_action(event: Mapping[str, Any], row_ids: set[str]) -> bool:
    if str(event.get("row_id", "")) not in row_ids:
        return False
    if event.get("action") == "skip":
        return True
    return (
        event.get("action") == "label"
        and event.get("label") in LABELS
        and str(event.get("confidence", "")).upper() in CONFIDENCES
    )


def applicable_actions(
    events: Iterable[Mapping[str, Any]], partition: str, reviewer: str,
    row_ids: set[str],
) -> list[dict[str, Any]]:
    """Return active label/skip actions after applying append-only undo events."""
    scoped: list[dict[str, Any]] = []
    undone: set[str] = set()
    expected_scope = (partition.upper(), reviewer)
    for raw in events:
        event = dict(raw)
        if _scope(event) != expected_scope:
            continue
        event_id = str(event.get("_event_id") or event.get("event_id") or "")
        if event.get("action") == "undo":
            target = str(event.get("reverses_event_id") or "")
            if target and any(item["_event_id"] == target for item in scoped):
                undone.add(target)
            elif not target:
                candidate = next(
                    (item for item in reversed(scoped) if item["_event_id"] not in undone),
                    None,
                )
                if candidate:
                    undone.add(candidate["_event_id"])
            continue
        event["_event_id"] = event_id
        if _valid_action(event, row_ids):
            scoped.append(event)
    return [event for event in scoped if event["_event_id"] not in undone]


def reconstruct_effective_state(
    events: Iterable[Mapping[str, Any]], partition: str, reviewer: str,
    row_ids: Iterable[str],
) -> dict[str, Any]:
    valid_ids = set(row_ids)
    actions = applicable_actions(events, partition, reviewer, valid_ids)
    latest = {str(event["row_id"]): event for event in actions}
    labels = {row_id: event for row_id, event in latest.items() if event["action"] == "label"}
    skipped = {row_id for row_id, event in latest.items() if event["action"] == "skip"}
    return {
        "labels": labels,
        "skipped": skipped,
        "unlabeled": valid_ids - set(labels),
        "actions": actions,
    }


def review_summary(state: Mapping[str, Any], total: int) -> dict[str, Any]:
    labels = state["labels"]
    return {
        "effective_labeled_count": len(labels),
        "skipped_count": len(state["skipped"]),
        "unlabeled_count": total - len(labels),
        "confidence_breakdown": dict(sorted(Counter(
            str(event["confidence"]).upper() for event in labels.values()
        ).items())),
        "label_breakdown": dict(sorted(Counter(
            str(event["label"]) for event in labels.values()
        ).items())),
    }


def next_review_index(
    rows: list[Mapping[str, Any]], state: Mapping[str, Any], after: int = -1,
) -> Optional[int]:
    """Prefer unskipped unlabeled rows; revisit skipped rows after that queue."""
    labeled, skipped = set(state["labels"]), set(state["skipped"])
    for allow_skipped in (False, True):
        for offset in range(1, len(rows) + 1):
            index = (after + offset) % len(rows)
            row_id = str(rows[index]["benchmark_row_id"])
            if row_id not in labeled and (allow_skipped or row_id not in skipped):
                return index
    return None


def build_undo_event(
    events: Iterable[Mapping[str, Any]], partition: str, reviewer: str,
    row_ids: Iterable[str],
) -> Optional[dict[str, str]]:
    actions = applicable_actions(events, partition, reviewer, set(row_ids))
    if not actions:
        return None
    target = actions[-1]
    return {
        "partition": partition.upper(),
        "reviewer_id": reviewer,
        "row_id": str(target["row_id"]),
        "action": "undo",
        "reverses_event_id": str(target["_event_id"]),
        "reverses_action": str(target["action"]),
        "reverses_row_id": str(target["row_id"]),
    }


def append_event(event: Mapping[str, Any], path: Path = HISTORY) -> dict[str, Any]:
    stored = {key: value for key, value in dict(event).items() if not key.startswith("_")}
    stored.setdefault("event_id", str(uuid.uuid4()))
    stored["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n")
    return stored


def page(
    row: Mapping[str, Any], index: int, total: int, partition: str,
    reviewed: Optional[int] = None, remaining: Optional[int] = None,
    summary: Optional[Mapping[str, Any]] = None,
) -> str:
    e = html.escape
    reviewed = index if reviewed is None else reviewed
    remaining = total - reviewed if remaining is None else remaining
    buttons = " ".join(
        f'<button data-key="{key}">{key}: {e(label)}</button>'
        for key, label in SHORTCUTS.items()
    )
    summary_text = e(json.dumps(dict(summary or {}), sort_keys=True))
    return f"""<!doctype html><meta charset="utf-8"><title>eBay Gold Review</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:30px auto}}img{{max-height:360px;max-width:500px}}button{{margin:4px;padding:8px}}.cols{{display:flex;gap:30px}}</style>
<h1>Blind identity review</h1><p>{e(partition)} · {reviewed}/{total} reviewed · {remaining} remaining</p>
<details><summary>Review summary</summary><pre>{summary_text}</pre></details>
<div class="cols"><section><h2>Target card</h2><p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>#{e(str(row['target_card_number']))}<br>Variant: {e(str(row['target_treatment']))}<br>Expected language: English</p></section>
<section><h2>eBay listing</h2><p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>Buying: {e(str(row['buying_options_json']))}</p><img src="{e(str(row['image_url']))}"><p><a href="{e(str(row['item_url']))}" target="_blank">Inspect listing</a></p></section></div>
<div>{buttons}</div><p>Confidence: <select id="confidence"><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select> <button id="note">N: note</button> <button id="skip">S: skip</button> <button id="undo">U: undo</button></p>
<script>const id={json.dumps(row['benchmark_row_id'])};function send(action,label=''){{fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{row_id:id,action,label,confidence:confidence.value}})}}).then(()=>location.reload())}}document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>send('label',b.textContent.slice(3)));note.onclick=()=>{{let n=prompt('Reviewer note')||'';if(n)fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{row_id:id,action:'note',note:n}})}}).then(()=>location.reload())}};skip.onclick=()=>send('skip');undo.onclick=()=>send('undo');onkeydown=e=>{{let k=e.key.toLowerCase();if({json.dumps(list(SHORTCUTS))}.includes(k))send('label',{json.dumps(SHORTCUTS)}[k]);else if(k==='s')send('skip');else if(k==='u')send('undo');else if(k==='n')note.click()}}</script>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--partition",
        choices=["DEVELOPMENT", "VALIDATION", "FINAL_BLIND_TEST"],
        default="DEVELOPMENT",
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    rows = load_partition(args.partition, purpose="human_review")
    row_ids = [str(row["benchmark_row_id"]) for row in rows]
    lock = threading.Lock()
    cursor: dict[str, Optional[int]] = {"index": None}

    def refresh(after: int = -1) -> tuple[dict[str, Any], dict[str, Any]]:
        effective = reconstruct_effective_state(
            read_history(), args.partition, args.reviewer, row_ids,
        )
        cursor["index"] = next_review_index(rows, effective, after)
        return effective, review_summary(effective, len(rows))

    effective, summary = refresh()
    print(json.dumps(
        {"partition": args.partition, "reviewer_id": args.reviewer, **summary},
        sort_keys=True,
    ))
    if args.summary:
        return

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                prior = cursor["index"] - 1 if cursor["index"] is not None else -1
                state, current_summary = refresh(prior)
                index = cursor["index"]
                if index is None:
                    body = b"<!doctype html><h1>Review complete</h1>"
                else:
                    body = page(
                        rows[index], index, len(rows), args.partition,
                        len(state["labels"]), len(state["unlabeled"]), current_summary,
                    ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = {
                key: value[0]
                for key, value in parse_qs(self.rfile.read(length).decode()).items()
            }
            with lock:
                events = read_history()
                current = cursor["index"] if cursor["index"] is not None else -1
                if data.get("action") == "undo":
                    event = build_undo_event(
                        events, args.partition, args.reviewer, row_ids,
                    )
                    if event:
                        append_event(event)
                        current = row_ids.index(event["row_id"]) - 1
                elif data.get("action") == "note":
                    if data.get("note"):
                        append_event({
                            "partition": args.partition,
                            "reviewer_id": args.reviewer,
                            **data,
                        })
                    current -= 1
                elif data.get("action") in {"label", "skip"} and data.get("row_id") in row_ids:
                    append_event({
                        "partition": args.partition,
                        "reviewer_id": args.reviewer,
                        **data,
                    })
                refresh(current)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass

    url = f"http://127.0.0.1:{args.port}"
    threading.Timer(.5, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
