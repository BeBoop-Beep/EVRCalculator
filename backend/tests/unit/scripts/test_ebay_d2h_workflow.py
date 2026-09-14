import csv,html,json
from pathlib import Path
import pytest
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import (
    SHORTCUTS,
    append_event,
    build_undo_event,
    next_review_index,
    page,
    read_history,
    reconstruct_effective_state,
    review_summary,
)
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


def _event(row_id, action='label', **extra):
    return {
        'partition':'DEVELOPMENT','reviewer_id':'Donny','row_id':row_id,
        'action':action,'label':LABELS[0],'confidence':'HIGH',**extra,
    }


def test_prior_labels_survive_restart_and_resume_at_next_unlabeled(tmp_path):
    rows=load_partition('DEVELOPMENT',purpose='human_review')
    path=tmp_path/'history.jsonl'
    append_event(_event(rows[0]['benchmark_row_id']),path)
    append_event(_event(rows[0]['benchmark_row_id']),path)
    append_event(_event(rows[1]['benchmark_row_id']),path)
    state=reconstruct_effective_state(
        read_history(path),'DEVELOPMENT','Donny',
        [row['benchmark_row_id'] for row in rows],
    )
    assert len(state['labels'])==2
    assert next_review_index(rows,state)==2
    assert review_summary(state,450)['unlabeled_count']==448


def test_undo_is_append_only_and_reconstructs_previous_state(tmp_path):
    rows=load_partition('DEVELOPMENT',purpose='human_review')[:3]
    ids=[row['benchmark_row_id'] for row in rows]
    path=tmp_path/'history.jsonl'
    append_event(_event(ids[0]),path)
    append_event(_event(ids[1],action='skip'),path)
    before=path.read_bytes()
    undo=build_undo_event(read_history(path),'DEVELOPMENT','Donny',ids)
    assert undo['reverses_action']=='skip' and undo['reverses_row_id']==ids[1]
    append_event(undo,path)
    assert path.read_bytes().startswith(before)
    state=reconstruct_effective_state(read_history(path),'DEVELOPMENT','Donny',ids)
    assert set(state['labels'])=={ids[0]}
    assert not state['skipped']


def test_notes_and_skips_do_not_complete_rows_and_skips_remain_addressable():
    rows=load_partition('DEVELOPMENT',purpose='human_review')[:3]
    ids=[row['benchmark_row_id'] for row in rows]
    events=[
        _event(ids[0],action='note',note='check image'),
        _event(ids[0],action='skip'),
    ]
    for number,event in enumerate(events,1):
        event['_event_id']=f'legacy:{number}'
    state=reconstruct_effective_state(events,'DEVELOPMENT','Donny',ids)
    assert not state['labels']
    assert state['skipped']=={ids[0]}
    assert review_summary(state,3)['unlabeled_count']==3
    assert next_review_index(rows,state)==1
    assert next_review_index(rows,state,after=2)==1


def test_all_development_rows_remain_addressable():
    rows=load_partition('DEVELOPMENT',purpose='human_review')
    state=reconstruct_effective_state([], 'DEVELOPMENT','Donny',
                                      [row['benchmark_row_id'] for row in rows])
    visited={next_review_index(rows,state,after=index-1) for index in range(len(rows))}
    assert visited==set(range(450))


def test_state_is_partition_and_reviewer_scoped():
    rows=load_partition('DEVELOPMENT',purpose='human_review')[:1]
    row_id=rows[0]['benchmark_row_id']
    event=_event(row_id);event['_event_id']='legacy:1'
    assert reconstruct_effective_state([event],'DEVELOPMENT','Other',[row_id])['labels']=={}
    assert reconstruct_effective_state([event],'VALIDATION','Donny',[row_id])['labels']=={}
