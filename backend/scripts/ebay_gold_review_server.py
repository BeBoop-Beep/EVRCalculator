"""Minimal local, blinded eBay gold-label reviewer. Human input only."""
from __future__ import annotations
import argparse, html, json, threading, webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from backend.scripts.ebay_gold_access import load_partition, OUT
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS
SHORTCUTS={'1':LABELS[0],'2':LABELS[1],'3':LABELS[2],'4':LABELS[3],'5':LABELS[4],'6':LABELS[5],'7':LABELS[6],'8':LABELS[7],'9':LABELS[8],'0':LABELS[9],'o':LABELS[10]}
HISTORY=OUT/'ebay_gold_review_history.jsonl'
def append_event(event,path=HISTORY):
    event=dict(event);event['recorded_at']=datetime.now(timezone.utc).isoformat()
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
def page(row,index,total,partition):
    e=html.escape; buttons=' '.join(f'<button data-key="{k}">{k}: {e(v)}</button>' for k,v in SHORTCUTS.items())
    return f'''<!doctype html><meta charset="utf-8"><title>eBay Gold Review</title><style>body{{font:16px system-ui;max-width:1100px;margin:30px auto}}img{{max-height:360px;max-width:500px}}button{{margin:4px;padding:8px}}.cols{{display:flex;gap:30px}}</style><h1>Blind identity review</h1><p>{e(partition)} · {index+1}/{total}</p><div class="cols"><section><h2>Target card</h2><p><b>{e(row['target_card_name'])}</b><br>{e(row['target_set_name'])}<br>#{e(row['target_card_number'])}<br>Variant: {e(row['target_treatment'])}<br>Expected language: English</p></section><section><h2>eBay listing</h2><p><b>{e(row['listing_title'])}</b><br>Condition: {e(row['condition'])}<br>Buying: {e(row['buying_options_json'])}</p><img src="{e(row['image_url'])}"><p><a href="{e(row['item_url'])}" target="_blank">Inspect listing</a></p></section></div><div>{buttons}</div><p>Confidence: <select id="confidence"><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select> <button id="note">N: note</button> <button id="skip">S: skip</button> <button id="undo">U: undo</button></p><script>const id={json.dumps(row['benchmark_row_id'])};function send(action,label=''){{let note='';if(action==='label'&&document.activeElement?.id==='note')note=prompt('Note')||'';fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{row_id:id,action,label,confidence:confidence.value,note}})}}).then(()=>location.reload())}}document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>send('label',b.textContent.slice(3)));note.onclick=()=>{{let n=prompt('Reviewer note')||'';fetch('/event',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:new URLSearchParams({{row_id:id,action:'note',note:n}})}})}};skip.onclick=()=>send('skip');undo.onclick=()=>send('undo');onkeydown=e=>{{let k=e.key.toLowerCase();if({json.dumps(list(SHORTCUTS))}.includes(k))send('label',{json.dumps(SHORTCUTS)}[k]);else if(k==='s')send('skip');else if(k==='u')send('undo');else if(k==='n')note.click()}}</script>'''
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--partition',choices=['DEVELOPMENT','VALIDATION','FINAL_BLIND_TEST'],default='DEVELOPMENT');ap.add_argument('--reviewer',required=True);ap.add_argument('--port',type=int,default=8765);a=ap.parse_args();rows=load_partition(a.partition,purpose='human_review');state={'i':0}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=page(rows[state['i']%len(rows)],state['i']%len(rows),len(rows),a.partition).encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body)
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0'));d={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode()).items()};append_event({'partition':a.partition,'reviewer_id':a.reviewer,**d});state['i']+=-1 if d.get('action')=='undo' else 1;state['i']=max(0,state['i']);self.send_response(204);self.end_headers()
        def log_message(self,*_): pass
    url=f'http://127.0.0.1:{a.port}';threading.Timer(.5,lambda:webbrowser.open(url)).start();ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
if __name__=='__main__':main()
