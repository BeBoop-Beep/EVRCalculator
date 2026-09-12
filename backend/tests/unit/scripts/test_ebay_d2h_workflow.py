import csv,html,json
from pathlib import Path
import pytest
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import SHORTCUTS,append_event,page
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS
OUT=Path(__file__).resolve().parents[3]/'artifacts/index_fair_value'
def test_partition_is_complete_unique_and_all_cards_present():
    parts=[]
    for name,n in [('development',450),('validation',250),('final_blind',350)]:
        rows=list(csv.DictReader((OUT/f'ebay_gold_{name}.csv').open(encoding='utf-8')));assert len(rows)==n;assert len({r['canonical_card_id'] for r in rows})==70;parts+=rows
    assert len({r['benchmark_row_id'] for r in parts})==1050
def test_source_and_split_fingerprints_are_stable():
    import hashlib
    m=json.loads((OUT/'ebay_gold_benchmark_manifest.json').read_text())
    assert hashlib.sha256((OUT/'ebay_manual_gold_labels.csv').read_bytes()).hexdigest()==m['sourceQueueFingerprint']
    material='\n'.join(f"{r['benchmark_row_id']}:{r['partition']}" for r in sorted(sum([load_partition(p,purpose='human_review') for p in ('DEVELOPMENT','VALIDATION','FINAL_BLIND_TEST')],[]),key=lambda x:x['benchmark_row_id']))
    assert hashlib.sha256(material.encode()).hexdigest()==m['splitFingerprint']
def test_final_is_sealed_from_matcher_development(tmp_path):
    with pytest.raises(PermissionError):load_partition('FINAL_BLIND_TEST')
    with pytest.raises(PermissionError):load_partition('VALIDATION')
    proof=tmp_path/'freeze.json';proof.write_text(json.dumps({'matcher_version':'v2','matcher_fingerprint':'abc','frozen_commit':'deadbeef'}))
    assert len(load_partition('FINAL_BLIND_TEST',purpose='final_evaluation',freeze_manifest=proof))==350
def test_keyboard_map_and_append_only_history(tmp_path):
    assert tuple(SHORTCUTS.values())==LABELS
    path=tmp_path/'history.jsonl';append_event({'action':'label','label':LABELS[0]},path);append_event({'action':'undo'},path)
    events=path.read_text().splitlines();assert len(events)==2;assert json.loads(events[0])['label']==LABELS[0]
def test_exports_have_empty_human_fields():
    for p in ('development','validation','final_blind'):
        rows=list(csv.DictReader((OUT/f'ebay_gold_{p}.csv').open(encoding='utf-8')))
        assert all(not r['reviewer_1_label'] and not r['adjudicated_label'] for r in rows)
def test_review_page_hides_matcher_and_price_information():
    row=load_partition('DEVELOPMENT',purpose='human_review')[0];markup=page(row,0,450,'DEVELOPMENT')
    assert html.escape(row['listing_title']) in markup
    assert 'D1 matcher' not in markup and 'Fair Value' not in markup
    assert row['price_json'] not in markup
