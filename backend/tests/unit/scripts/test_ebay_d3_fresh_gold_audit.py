import html
import hashlib
import json
from pathlib import Path

from backend.scripts.ebay_d3_fresh_gold_audit import (
    AUDIT_HISTORY, GOLD_MANIFEST, append_audit_event, build_audit_queue, build_undo, effective_gold_fingerprint,
    effective_labels, has_human_visible_graded_evidence, read_audit_history,
    reconstruct_audit_state,
)
from backend.scripts.ebay_d3_gold_audit_server import page
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state

OUT=Path(__file__).resolve().parents[3]/"artifacts/index_fair_value"


def base(label):return {"label":label,"confidence":"HIGH"}


def test_exact_edge_labels_and_human_visible_image_only_selection():
    labels=["RELATED_BUT_WRONG_VARIANT","LOT_OR_BUNDLE","SEALED_OR_ACCESSORY","WRONG_SET","WRONG_LANGUAGE","WRONG_CARD_NUMBER","GRADED","GRADED"]
    rows=[{"benchmark_row_id":str(i),"listing_title":"card" if i==6 else "PSA 10 card" if i==7 else "card","condition":"Ungraded","condition_id":"4000","localized_aspects_json":"[]"} for i in range(len(labels))]
    queue=build_audit_queue(rows,{str(i):base(label) for i,label in enumerate(labels)})
    assert [row["benchmark_row_id"] for row in queue]==["0","1","2","3","4","6"]
    assert queue[-1]["human_only_audit_reason"]=="IMAGE_ONLY_GRADED_CANDIDATE"


def test_structured_graded_evidence_uses_only_visible_fields():
    assert has_human_visible_graded_evidence({"listing_title":"card","condition":"Graded","condition_id":"2750","localized_aspects_json":"[]"})
    assert has_human_visible_graded_evidence({"listing_title":"card","condition":"Ungraded","condition_id":"4000","localized_aspects_json":json.dumps([{"name":"Professional Grader","values":["TAG"]}])})
    assert not has_human_visible_graded_evidence({"listing_title":"card","condition":"Ungraded","condition_id":"4000","localized_aspects_json":"[]","matcher_state":"HIGH_CONFIDENCE"})


def test_page_hides_matcher_cohort_and_prices():
    row={"benchmark_row_id":"1","current_human_label":"WRONG_SET","human_only_audit_reason":"EDGE_IDENTITY_LABEL:WRONG_SET","target_card_name":"A","target_set_name":"S","target_card_number":"1","target_treatment":"regular","listing_title":"A","condition":"Ungraded","condition_id":"4000","category_id":"","localized_aspects_json":"[]","image_url":"","item_url":"","matcher_state":"secret","cohort_membership":"secret","price_json":"secret"}
    markup=page(row,0,1)
    assert html.escape(row["listing_title"]) in markup and "WRONG_SET" in markup
    assert "matcher" not in markup.lower() and "cohort" not in markup.lower() and "price" not in markup.lower() and "secret" not in markup


def test_append_only_undo_and_effective_reconstruction(tmp_path):
    path=tmp_path/"audit.jsonl"
    append_audit_event({"partition":"D3_BLIND_REVIEW","reviewer_id":"Donny","row_id":"1","action":"audit_keep","original_label":"WRONG_SET"},path)
    append_audit_event({"partition":"D3_BLIND_REVIEW","reviewer_id":"Donny","row_id":"2","action":"audit_replace","original_label":"LOT_OR_BUNDLE","replacement_label":"AMBIGUOUS"},path)
    before=path.read_bytes();undo=build_undo(read_audit_history(path),"Donny",["1","2"]);append_audit_event(undo,path)
    assert path.read_bytes().startswith(before)
    state=reconstruct_audit_state(read_audit_history(path),"Donny",["1","2"])
    assert set(state["decisions"])=={"1"} and state["unreviewed"]=={"2"}
    labels=effective_labels({"1":base("WRONG_SET"),"2":base("LOT_OR_BUNDLE")},state)
    assert labels=={"1":"WRONG_SET","2":"LOT_OR_BUNDLE"}


def test_effective_gold_fingerprint_is_order_stable():
    assert effective_gold_fingerprint({"2":"GRADED","1":"EXACT_TARGET_MATCH"})==effective_gold_fingerprint({"1":"EXACT_TARGET_MATCH","2":"GRADED"})


def test_frozen_fresh_gold_manifest_reconstructs_without_matcher_data():
    manifest=json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    rows=load_partition("D3_BLIND_REVIEW",purpose="human_review");ids=[row["benchmark_row_id"] for row in rows]
    base_state=reconstruct_effective_state(read_history(),"D3_BLIND_REVIEW","Donny",ids)
    queue=build_audit_queue(rows,base_state["labels"])
    audit_state=reconstruct_audit_state(read_audit_history(),"Donny",[row["benchmark_row_id"] for row in queue])
    labels=effective_labels(base_state["labels"],audit_state)
    assert len(labels)==704 and not base_state["skipped"] and not base_state["unlabeled"]
    assert len(queue)==len(audit_state["decisions"])==43 and not audit_state["unreviewed"]
    assert effective_gold_fingerprint(labels)==manifest["effective_human_gold_fingerprint"]=="635365a6773910f8acb5c57efecba81163e187c147eb34f844a50a71bdf85a8c"
    assert hashlib.sha256(AUDIT_HISTORY.read_bytes()).hexdigest()==manifest["audit_history_fingerprint"]
    assert hashlib.sha256((OUT/"ebay_gold_review_history.jsonl").read_bytes()).hexdigest()==manifest["review_history_fingerprint"]
    assert hashlib.sha256((OUT/"ebay_d3_blind_review_queue.csv").read_bytes()).hexdigest()==manifest["original_review_queue_fingerprint"]
    assert manifest["matcher_predictions_consulted"] is False


def test_fresh_gold_freeze_remains_matcher_blind_after_certification():
    gold_manifest=json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    certification=json.loads((OUT/"ebay_d3_v3_final_certification_manifest.json").read_text(encoding="utf-8"))
    assert gold_manifest["matcher_predictions_consulted"] is False
    assert certification["human_gold_fingerprint"]==gold_manifest["effective_human_gold_fingerprint"]
    assert certification["review_queue_fingerprint"]==gold_manifest["original_review_queue_fingerprint"]
