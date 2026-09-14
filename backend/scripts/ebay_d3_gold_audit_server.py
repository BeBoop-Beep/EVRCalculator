"""Local matcher-blind UI for fresh D3 human-gold consistency audit."""
from __future__ import annotations

import argparse
import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qs

from backend.scripts.ebay_d3_fresh_gold_audit import (
    GOLD_MANIFEST, PARTITION, append_audit_event, build_audit_queue, build_undo,
    freeze_gold, read_audit_history, reconstruct_audit_state, summary,
)
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS


def page(row: Mapping[str, Any], reviewed: int, total: int) -> str:
    e=html.escape; options="".join(f"<option>{e(label)}</option>" for label in LABELS)
    return f"""<!doctype html><meta charset="utf-8"><title>D3 Fresh Gold Audit</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:30px auto}}img{{max-height:360px;max-width:500px}}button{{margin:4px;padding:8px}}.cols{{display:flex;gap:30px}}</style>
<h1>Fresh human-gold consistency audit</h1><p>{reviewed}/{total} audited · {total-reviewed} remaining</p>
<p><b>Current human label: {e(str(row['current_human_label']))}</b><br>Human-only reason: {e(str(row['human_only_audit_reason']))}</p>
<div class="cols"><section><h2>Target card</h2><p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>#{e(str(row['target_card_number']))}<br>Treatment: {e(str(row['target_treatment']))}<br>Expected language: English</p></section>
<section><h2>Listing evidence</h2><p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>Condition ID: {e(str(row['condition_id']))}<br>Category: {e(str(row['category_id']))}<br>Aspects: {e(str(row['localized_aspects_json']))}</p><img src="{e(str(row['image_url']))}"><p><a href="{e(str(row['item_url']))}" target="_blank">Inspect listing</a></p></section></div>
<p><button id="keep">KEEP</button> <select id="replacement">{options}</select> <button id="replace">REPLACE</button> <button id="undo">UNDO</button></p>
<script>const id={json.dumps(row['benchmark_row_id'])},original={json.dumps(row['current_human_label'])};function send(action){{let note=prompt('Optional note')||'';fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{row_id:id,action,original_label:original,replacement_label:replacement.value,note}})}}).then(()=>location.reload())}}keep.onclick=()=>send('audit_keep');replace.onclick=()=>send('audit_replace');undo.onclick=()=>fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{action:'audit_undo'}})}}).then(()=>location.reload())</script>"""


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--reviewer",required=True);parser.add_argument("--port",type=int,default=8765);parser.add_argument("--summary",action="store_true");parser.add_argument("--freeze",action="store_true");args=parser.parse_args()
    rows=load_partition(PARTITION,purpose="human_review");ids=[row["benchmark_row_id"] for row in rows]
    base=reconstruct_effective_state(read_history(),PARTITION,args.reviewer,ids)
    if len(base["labels"])!=704 or base["skipped"] or base["unlabeled"]: raise SystemExit("D3 blind human review must be complete")
    queue=build_audit_queue(rows,base["labels"]);audit_ids=[row["benchmark_row_id"] for row in queue]
    state=reconstruct_audit_state(read_audit_history(),args.reviewer,audit_ids)
    print(json.dumps({"partition":PARTITION,"reviewer_id":args.reviewer,**summary(base["labels"],state,len(queue))},sort_keys=True))
    if args.summary:return
    if args.freeze:
        print(json.dumps(freeze_gold(rows,base["labels"],state,args.reviewer),sort_keys=True));return
    if GOLD_MANIFEST.exists():raise SystemExit("fresh D3 human gold is already frozen")
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self)->None:
            with lock:
                current=reconstruct_audit_state(read_audit_history(),args.reviewer,audit_ids)
                index=next((i for i,row in enumerate(queue) if row["benchmark_row_id"] in current["unreviewed"]),None)
                body=(b"<!doctype html><h1>Audit complete</h1><p>Stop the server and run with --freeze.</p>" if index is None else page(queue[index],len(current["decisions"]),len(queue)).encode())
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(body)
        def do_POST(self)->None:
            length=int(self.headers.get("Content-Length","0"));data={key:value[0] for key,value in parse_qs(self.rfile.read(length).decode()).items()}
            with lock:
                if data.get("action")=="audit_undo":
                    event=build_undo(read_audit_history(),args.reviewer,audit_ids)
                    if event:append_audit_event(event)
                elif data.get("action") in {"audit_keep","audit_replace"} and data.get("row_id") in audit_ids:
                    append_audit_event({"partition":PARTITION,"reviewer_id":args.reviewer,**data})
            self.send_response(204);self.end_headers()
        def log_message(self,*_:Any)->None:pass
    url=f"http://127.0.0.1:{args.port}";threading.Timer(.5,lambda:webbrowser.open(url)).start();ThreadingHTTPServer(("127.0.0.1",args.port),Handler).serve_forever()


if __name__=="__main__":main()
