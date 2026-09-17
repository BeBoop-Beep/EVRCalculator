"""Real PostgreSQL publication tests for the V2 dual-threshold RPC branch.

Structurally parallel to ``test_best_open_publication_postgres.py`` (the V1
file this mirrors): CI provides an isolated postgres:17 service. Local runs
require an explicit DSN and acknowledgement; absence skips the suite rather
than inventing DB passes. This file additionally applies the V2 additive
migration on top of the same V1 schema the V1 file builds, and proves V1 and
V2 coexist under one schema, exactly as the real migration ships.

Phase 9 matrix coverage in this file: items 8-30 (RPC-level V1/V2 dispatch,
required-field/benchmark/threshold validation, rejection matrix, idempotency,
non-determinism rejection, V1/V2 coexistence, role execution). See the plan
doc's Step 5 cross-check for the full 45-item accounting.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import time
from uuid import UUID

import pytest

# Reuse the V1 file's DSN gate, connection helper, and fixture payload so a
# V1 publish inside this file exercises the EXACT same shape the V1 file
# proves, against the now-V2-aware schema (Phase 9 item 8).
from backend.tests.integration.test_best_open_publication_postgres import (
    DSN, VERSIONS, SID, T1, T2, connection,
    fixture_payload as fixture_payload_v1,
)

pytestmark = pytest.mark.skipif(not DSN, reason='isolated PostgreSQL DSN required')
ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / 'supabase/migrations/20260914184759_create_budget_product_best_open_price_store.sql'
NEW = ROOT / 'supabase/migrations/20260914225000_harden_best_open_publication_review.sql'
V2 = ROOT / 'supabase/migrations/20260916120000_add_best_open_price_v2_dual_threshold.sql'
METHOD_V1 = 'budget_product_best_open_price_full_market_v1'
METHOD_V2 = 'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12'


@pytest.fixture(scope='module', autouse=True)
def database():
    if not DSN:
        return
    import os
    from psycopg.conninfo import conninfo_to_dict
    parsed = conninfo_to_dict(DSN)
    assert os.getenv('BEST_OPEN_ACK_DISPOSABLE') == 'yes'
    assert parsed.get('host') in {'127.0.0.1', 'localhost', 'postgres'}
    assert parsed.get('dbname') == 'best_open_test'
    with connection(autocommit=True) as c:
        c.execute('CREATE SCHEMA IF NOT EXISTS extensions')
        c.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions')
        for role in ('anon', 'authenticated', 'service_role'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(f'CREATE ROLE {role} NOLOGIN')
        c.execute('ALTER ROLE service_role BYPASSRLS')
        c.execute('DROP TABLE IF EXISTS budget_product_best_open_price_latest, budget_product_best_open_price_rows, budget_product_best_open_price_snapshots CASCADE')
        c.execute('DROP TABLE IF EXISTS budget_product_ranking_latest, budget_product_ranking_rows, budget_product_ranking_snapshots CASCADE')
        c.execute('''CREATE TABLE budget_product_ranking_snapshots (
            id uuid PRIMARY KEY, published_at timestamptz, market_date date,
            cohort_fingerprint text, eligible_cohort_count int, full_market_budget numeric,
            ranking_method_version text, allocation_method_version text, comparison_scope_version text,
            financial_rip_version text, overall_rip_version text, overall_rip_v12_version text,
            collector_appeal_version text, chase_accessibility_version text, chase_accessibility_transform_version text,
            ranked_under_v12_authority boolean)''')
        c.execute('''CREATE TABLE budget_product_ranking_latest (
            ranking_method_version text, allocation_method_version text, snapshot_id uuid,
            PRIMARY KEY(ranking_method_version, allocation_method_version))''')
        c.execute('''CREATE TABLE budget_product_ranking_rows (
            snapshot_id uuid, sealed_product_id uuid, set_id uuid, product_family text,
            source_calculation_run_id uuid, budget_type text, target_budget numeric,
            product_market_price numeric, quantity int, budget_rank_v12 int,
            overall_rip_v12_score numeric, financial_rip_v4_score numeric, collector_appeal_score numeric,
            chase_accessibility_raw numeric, chance_to_recover_capital numeric, actual_committed_capital numeric,
            financial_only_rank int,
            PRIMARY KEY(snapshot_id, sealed_product_id, budget_type))''')
        # V1 schema/RPC first, exactly like the V1 file's own fixture, then
        # the additive V2 migration on top -- this is the real migration
        # sequence a live database goes through.
        c.execute(OLD.read_text())
        c.execute(NEW.read_text())
        c.execute(V2.read_text())


def fixture_payload_v2():
    """V2 shape: every row/snapshot field ``fixture_payload_v1()`` has, plus
    the Financial-axis columns and both threshold-evidence sets."""
    snap, rows = fixture_payload_v1()
    snap = dict(snap, best_open_price_method_version=METHOD_V2)
    out_rows = []
    for row in rows:
        n = int(row['current_budget_rank'])
        financial_bench = 2 if n == 1 else 1
        financial_threshold = 12.5 if n == 1 else 8.0
        # Threshold evidence belongs to the candidate strategy AT P*, not to
        # the current-market strategy. Keep the fixture internally coherent
        # with the RPC's economic reconciliation: q(P*) * P* for each axis.
        rip_threshold_quantity = int(row['threshold_quantity'])
        rip_threshold_capital = rip_threshold_quantity * row['best_open_price']
        financial_threshold_quantity = int(100 // financial_threshold)
        financial_threshold_capital = financial_threshold_quantity * financial_threshold
        out_rows.append(dict(
            row,
            current_financial_only_rank=n,
            financial_status='current_number_one_with_headroom' if n == 1 else 'resolved_below_market',
            financial_best_open_price=financial_threshold,
            financial_threshold_quantity=financial_threshold_quantity,
            financial_price_gap_dollars=10 - financial_threshold,
            financial_price_gap_percent=(10 - financial_threshold) / 10,
            financial_benchmark_sealed_product_id=str(UUID(int=financial_bench)),
            financial_benchmark_financial_rip_v4_score=80 - financial_bench,
            financial_benchmark_overall_rip_v12_score=90 - financial_bench,
            threshold_financial_rip_v4_score=row['current_financial_rip_v4_score'],
            threshold_overall_rip_v12_score=row['current_overall_rip_v12_score'],
            threshold_chance_to_recover_capital=row['current_chance_to_recover_capital'],
            threshold_actual_committed_capital=rip_threshold_capital,
            financial_threshold_financial_rip_v4_score=row['current_financial_rip_v4_score'],
            financial_threshold_overall_rip_v12_score=row['current_overall_rip_v12_score'],
            financial_threshold_chance_to_recover_capital=row['current_chance_to_recover_capital'],
            financial_threshold_actual_committed_capital=financial_threshold_capital,
        ))
    return snap, out_rows


@pytest.fixture(autouse=True)
def seed(database):
    if not DSN:
        return
    snap, rows = fixture_payload_v1()
    with connection(autocommit=True) as c:
        c.execute('TRUNCATE budget_product_best_open_price_latest, budget_product_best_open_price_rows, budget_product_best_open_price_snapshots, budget_product_ranking_latest, budget_product_ranking_rows, budget_product_ranking_snapshots')
        cols = ['id', 'published_at', 'market_date', 'cohort_fingerprint', 'eligible_cohort_count', 'full_market_budget'] + list(VERSIONS) + ['overall_rip_version', 'ranked_under_v12_authority']
        vals = [SID, T1, '2026-09-08', 'cohort-fixture', 3, 100] + list(VERSIONS.values()) + [VERSIONS['overall_rip_v12_version'], True]
        c.execute('INSERT INTO budget_product_ranking_snapshots (' + ','.join(cols) + ') VALUES (' + ','.join(['%s'] * len(cols)) + ')', vals)
        c.execute('INSERT INTO budget_product_ranking_latest VALUES (%s,%s,%s)', (VERSIONS['ranking_method_version'], VERSIONS['allocation_method_version'], SID))
        for row in rows:
            # financial_only_rank mirrors fixture_payload_v2()'s
            # current_financial_only_rank=n derivation (n == current_budget_rank
            # for this fixture's 3-row cohort), so the V2 RPC's live cross-check
            # of budget_product_ranking_rows.financial_only_rank matches the
            # V2 row payload's declared current_financial_only_rank exactly.
            c.execute('''INSERT INTO budget_product_ranking_rows VALUES
                (%s,%s,%s,%s,%s,'full_market',100,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (SID, row['sealed_product_id'], row['set_id'], row['product_family'], row['source_calculation_run_id'],
                 row['current_market_price'], row['current_quantity'], row['current_budget_rank'],
                 row['current_overall_rip_v12_score'], row['current_financial_rip_v4_score'], row['current_collector_appeal_score'],
                 row['current_chase_accessibility_raw'], row['current_chance_to_recover_capital'], row['current_actual_committed_capital'],
                 row['current_budget_rank']))


def publish(c, snap=None, rows=None):
    from psycopg.types.json import Jsonb
    if snap is None:
        snap, rows = fixture_payload_v2()
    return c.execute('SELECT public.publish_budget_product_best_open_price_snapshot(%s,%s)', (Jsonb(snap), Jsonb(rows))).fetchone()[0]


def counts(c):
    return c.execute('SELECT (SELECT count(*) FROM budget_product_best_open_price_snapshots), (SELECT count(*) FROM budget_product_best_open_price_rows), (SELECT count(*) FROM budget_product_best_open_price_latest)').fetchone()


def latest_count_for_method(c, method):
    return c.execute(
        'SELECT count(*) FROM budget_product_best_open_price_latest WHERE best_open_price_method_version=%s', (method,),
    ).fetchone()[0]


# --- Item 8: V1 still succeeds against the now-V2-aware schema -------------

def test_item8_v1_publish_still_succeeds_on_v2_aware_schema():
    with connection(autocommit=True) as c:
        snap, rows = fixture_payload_v1()
        result = publish(c, snap, rows)
        assert result is not None
        assert latest_count_for_method(c, METHOD_V1) == 1


# --- Item 9: V2 full valid publish succeeds ---------------------------------

def test_item9_v2_full_valid_publish_succeeds():
    with connection(autocommit=True) as c:
        result = publish(c)
        assert result is not None
        assert counts(c) == (1, 3, 1)
        assert latest_count_for_method(c, METHOD_V2) == 1


# --- Items 10-21: each required V2 field/benchmark/score individually ------
# rejected. One case per required Financial-axis / dual-threshold-evidence
# field, parametrized like the V1 file's own rejection matrix.

_V2_REQUIRED_FIELD_CASES = [
    'financial_status', 'financial_best_open_price', 'financial_threshold_quantity',
    'financial_benchmark_sealed_product_id', 'financial_benchmark_financial_rip_v4_score',
    'financial_benchmark_overall_rip_v12_score',
    'threshold_overall_rip_v12_score', 'threshold_actual_committed_capital',
    'financial_threshold_overall_rip_v12_score', 'financial_threshold_actual_committed_capital',
    'current_financial_only_rank',
]


@pytest.mark.parametrize('field', _V2_REQUIRED_FIELD_CASES)
def test_items10_21_required_v2_field_omission_rejected(field):
    import psycopg
    snap, rows = fixture_payload_v2()
    rows[1][field] = None
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            publish(c, snap, rows)
        assert counts(c) == (0, 0, 0)


def test_items10_21_v2_financial_benchmark_must_differ_from_row_product():
    import psycopg
    snap, rows = fixture_payload_v2()
    rows[1]['financial_benchmark_sealed_product_id'] = rows[1]['sealed_product_id']
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            publish(c, snap, rows)
        assert counts(c) == (0, 0, 0)


# --- Item 22: duplicate product rows fail -----------------------------------

def test_item22_duplicate_product_rows_fail():
    import psycopg
    snap, rows = fixture_payload_v2()
    rows[2] = deepcopy(rows[1])
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            publish(c, snap, rows)
        assert counts(c) == (0, 0, 0)


# --- Item 23: incomplete cohort fails ---------------------------------------

def test_item23_incomplete_cohort_fails():
    import psycopg
    snap, rows = fixture_payload_v2()
    rows.pop()
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            publish(c, snap, rows)
        assert counts(c) == (0, 0, 0)


# --- Item 24: source pointer drift fails ------------------------------------

def test_item24_source_pointer_drift_fails():
    import psycopg
    snap, rows = fixture_payload_v2()
    snap['source_budget_snapshot_id'] = str(UUID(int=999))
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            publish(c, snap, rows)
        assert counts(c) == (0, 0, 0)


# --- Item 25: same source + same V2 content idempotently returns same id ---

def test_item25_same_source_and_content_is_idempotent():
    with connection(autocommit=True) as c:
        first = publish(c)
        snap, rows = fixture_payload_v2()
        second = publish(c, snap, list(reversed(rows)))
        assert first == second
        assert counts(c) == (1, 3, 1)


# --- Item 26: same source + changed V2 content fails non-determinism -------

def test_item26_same_source_changed_content_rejected_non_deterministic():
    import psycopg
    with connection(autocommit=True) as c:
        publish(c)
        snap, rows = fixture_payload_v2()
        rows[0]['financial_best_open_price'] = float(rows[0]['financial_best_open_price']) + 1
        with pytest.raises(psycopg.Error, match='non-deterministic'):
            publish(c, snap, rows)
        assert counts(c) == (1, 3, 1)


# --- Item 27: V1 + V2 coexist for the same source identity -----------------

def test_item27_v1_and_v2_coexist_with_distinct_latest_pointers():
    with connection(autocommit=True) as c:
        v1_snap, v1_rows = fixture_payload_v1()
        v1_result = publish(c, v1_snap, v1_rows)
        v2_result = publish(c)
        assert v1_result is not None and v2_result is not None
        assert v1_result != v2_result
        assert latest_count_for_method(c, METHOD_V1) == 1
        assert latest_count_for_method(c, METHOD_V2) == 1
        assert counts(c) == (2, 6, 2)


# --- Items 28-30: anon/authenticated/service_role role execution -----------

@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_items28_29_non_service_roles_cannot_read_write_or_execute_v2(role):
    import psycopg
    with connection(autocommit=True) as c:
        c.execute(f'SET ROLE {role}')
        for table in ('snapshots', 'rows', 'latest'):
            with pytest.raises(psycopg.Error):
                c.execute(f'SELECT * FROM budget_product_best_open_price_{table}')
        with pytest.raises(psycopg.Error):
            publish(c)


def test_item30_service_role_can_execute_v2_publish():
    with connection(autocommit=True) as c:
        c.execute('SET ROLE service_role')
        assert publish(c) is not None
