from pathlib import Path


MIGRATIONS = Path(__file__).parents[4] / "supabase/migrations"
EXPECTED = [
    "20260901000000_billing_effort1_foundation.sql",
    "20260901000001_billing_effort2_stripe_backend.sql",
    "20260901000002_billing_effort4_atomic_reliability.sql",
]


def test_billing_migrations_are_unique_and_ordered_after_every_preexisting_migration():
    names = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
    billing = [name for name in names if "_billing_effort" in name]
    assert billing == EXPECTED
    nonbilling = [name for name in names if "_billing_effort" not in name]
    assert max(nonbilling) < EXPECTED[0]


def test_obsolete_billing_migration_timestamps_are_absent():
    for name in [
        "20260831184744_billing_effort1_foundation.sql",
        "20260831190018_billing_effort2_stripe_backend.sql",
        "20260831212547_billing_effort4_atomic_reliability.sql",
    ]:
        assert not (MIGRATIONS / name).exists()
