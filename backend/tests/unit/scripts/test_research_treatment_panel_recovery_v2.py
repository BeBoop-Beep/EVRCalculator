from backend.scripts.research_treatment_panel_recovery_v2 import _provider_variant, _history_rows

def test_provider_variant_modern_holo():
    assert _provider_variant({"printing_type":"holo","special_type":None,"edition":None})=="Holofoil"

def test_provider_variant_vintage_exact():
    assert _provider_variant({"printing_type":"holo","special_type":None,"edition":"1st-edition"})=="1st Edition Holofoil"

def test_special_variant_fails_closed():
    assert _provider_variant({"printing_type":"reverse-holo","special_type":"master_ball","edition":None}) is None

def test_history_parser_keeps_positive_daily_rows():
    rows=_history_rows({"data":[{"date":"2026-09-01","avg":3.5},{"date":"2026-09-02","avg":0},{"date":"2026-09-03","market_price":"4.25"}]})
    assert rows==[{"date":"2026-09-01","price":3.5},{"date":"2026-09-03","price":4.25}]
