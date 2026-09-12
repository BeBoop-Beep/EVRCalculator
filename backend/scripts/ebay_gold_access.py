"""Fail-closed access layer for eBay D2H label partitions."""
from __future__ import annotations
import csv, json
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'artifacts/index_fair_value'
FILES={'DEVELOPMENT':'ebay_gold_development.csv','VALIDATION':'ebay_gold_validation.csv','FINAL_BLIND_TEST':'ebay_gold_final_blind.csv'}
def load_partition(partition, purpose='matcher_development', freeze_manifest=None):
    partition=partition.upper()
    if partition not in FILES: raise ValueError('unknown partition')
    if partition=='VALIDATION' and purpose not in {'threshold_validation','human_review'}: raise PermissionError('validation labels are unavailable to matcher construction')
    if partition=='FINAL_BLIND_TEST':
        if purpose=='human_review': pass
        elif purpose=='final_evaluation' and freeze_manifest:
            proof=json.loads(Path(freeze_manifest).read_text(encoding='utf-8'))
            if not all(proof.get(k) for k in ('matcher_version','matcher_fingerprint','frozen_commit')): raise PermissionError('incomplete matcher freeze proof')
        else: raise PermissionError('final blind labels are sealed')
    with (OUT/FILES[partition]).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
