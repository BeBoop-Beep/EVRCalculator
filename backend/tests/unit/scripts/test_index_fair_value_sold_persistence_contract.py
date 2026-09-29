from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "backend" / "scripts" / "run_index_fair_value_sold_signal_pilot.py"
WORKFLOW = ROOT / ".github" / "workflows" / "index-fair-value-sold-signal-pilot.yml"


def test_broad_sold_signal_pilot_can_persist_shadow_evidence():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PkmnPricesStore" in text
    assert "--persist-evidence" in text
    assert "pkmnprices_fair_value_pilot_persist_v1" in text
    assert "store.insert_evidence" in text
    assert "set_value_nm_eligible_count" in text
    assert "condition_equivalence_assumed" in text
    assert "set_value_authority_unchanged" in text


def test_broad_pilot_workflow_persists_without_extra_collection_step():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--persist-evidence" in text
    assert "run_index_fair_value_sold_signal_pilot.py" in text
    assert "raw sold transactions are persisted to shadow DB evidence tables" in text
    # Persistence is attached to the same bounded API collection; the workflow
    # does not invoke a second provider collector for the 207-card sample.
    assert text.count("run_index_fair_value_sold_signal_pilot.py") == 2
