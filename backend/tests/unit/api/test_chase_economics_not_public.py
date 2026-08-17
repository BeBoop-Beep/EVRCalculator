from pathlib import Path


API_MAIN = Path(__file__).resolve().parents[3] / "api" / "main.py"


def test_chase_economics_has_no_public_http_route():
    source = API_MAIN.read_text(encoding="utf-8")
    assert '"/tcgs/pokemon/sets/{set_id}/chase-economics"' not in source
    assert "get_pokemon_set_chase_economics_snapshot_payload" not in source
