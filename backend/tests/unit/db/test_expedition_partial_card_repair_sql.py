from pathlib import Path


SQL = Path(
    "backend/db/repairs/repair_expedition_aug23_partial_cards.sql"
).read_text(encoding="utf-8")


def test_repair_is_narrow_and_fail_closed():
    assert "canonical_key = 'expeditionBaseSet'" in SQL
    assert "split_part(coalesce(c.card_number, ''), '/', 2) = '102'" in SQL
    assert "2026-08-24 04:27:14.165795+00" in SQL
    assert "candidate_count <> 101" in SQL
    assert "legitimate_raw_count <> 165" in SQL
    assert "canonical_count <> 165" in SQL
    assert "variant_count <> 0" in SQL
    assert "observation_count <> 0" in SQL
    assert "identity_count <> 0" in SQL
    assert "FROM pg_constraint" in SQL
    assert "DELETE FROM public.cards" in SQL


def test_repair_rediscovers_ids_and_protects_base_counts():
    assert "CREATE TEMP TABLE expedition_aug23_partial_cards" in SQL
    assert "WHERE c.id = doomed.id" in SQL
    assert "expedition_repair_base_invariants" in SQL
    assert "base_after IS DISTINCT FROM base_before" in SQL
    assert "remaining_102 <> 0 OR remaining_165 <> 165 OR canonical_count <> 165" in SQL
