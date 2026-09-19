import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SQL = ROOT / "supabase/migrations/20260919231000_lock_tcgplayer_price_reads.sql"
MIRROR = ROOT / "backend/db/migrations/20260919231000_lock_tcgplayer_price_reads.sql"
INVENTORY = ROOT / "backend/artifacts/pricing/multi_source_price_consumer_inventory.json"


def test_migration_is_mirrored_and_keeps_multisource_storage():
    sql = SQL.read_bytes()
    assert sql == MIRROR.read_bytes()
    text = sql.decode()
    assert "CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition" in text
    assert "CROSS JOIN LATERAL" in text
    assert "current_row.source = 'TCGPlayer'" in text
    assert "o.source = 'TCGPlayer'" in text
    assert "r.source='TCGPlayer'" in text
    assert "price.source='TCGPlayer'" in text
    assert "CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded" in text
    assert "756f4d28ea3710f59bb23f254ecd3580" in text
    assert "SET search_path TO ''" in text
    assert "ALTER TABLE public.card_variant_price_current_v2" not in text
    assert "REVOKE ALL ON public.card_market_usd_latest_by_condition" not in text
    view = text.split("CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition", 1)[1].split("COMMENT ON VIEW", 1)[0]
    assert "row_number()" not in view.lower()


def test_inventory_has_explicit_classification_and_repairs():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    categories = set(inventory["classification_meaning"])
    assert len(inventory["entries"]) >= 100
    assert all(row["classification"] in categories for row in inventory["entries"])
    defects = [row for row in inventory["entries"] if row["classification"] == "SOURCE_BLIND_BUG"]
    assert defects
    assert all(row.get("fix") and row.get("post_fix_classification") == "TCGPLAYER_AUTHORITY" for row in defects)


def test_production_raw_observation_reads_are_source_explicit():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    for row in inventory["entries"]:
        path = row["consumer"]
        if row["kind"] != "backend_file" or row["classification"] != "SOURCE_BLIND_BUG":
            continue
        content = (ROOT / path).read_text(encoding="utf-8")
        for match in re.finditer(r'\.table\("card_variant_price_observations"\)', content):
            assert '.eq("source", "TCGPlayer")' in content[match.end():match.end() + 300], path
