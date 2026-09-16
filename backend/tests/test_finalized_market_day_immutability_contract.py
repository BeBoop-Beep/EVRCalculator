from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.db.services import pokemon_market_rollout_preparation as prep

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "backend/db/proposals/finalized_market_day_immutability.sql"
DAY = "2026-09-15"
ROOT_ID = "root"


class Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_args):
        return self

    def in_(self, key, values):
        allowed = set(values)
        self.rows = [row for row in self.rows if row.get(key) in allowed]
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def execute(self):
        return SimpleNamespace(data=list(self.rows))


class FinalizedClient:
    """RPC reports zero writes because DB precedence protected both final rows."""

    def __init__(self):
        self.history = [
            {
                "set_id": ROOT_ID,
                "snapshot_date": DAY,
                "value_scope": "standard",
                "source": "canonical_root_set_public_rollout_v1",
            },
            {
                "set_id": ROOT_ID,
                "snapshot_date": DAY,
                "value_scope": "top10",
                "source": "canonical_root_top10_public_rollout_v1",
            },
        ]
        self.rpc_calls = []

    def table(self, _name):
        return Query(self.history)

    def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))

        class RPC:
            def execute(self):
                return SimpleNamespace(data={
                    "status": "complete",
                    "marketDate": DAY,
                    "candidateDate": DAY,
                    "rolloutRootCount": 1,
                    "standardRowsUpserted": 0,
                    "top10RowsUpserted": 0,
                })

        return RPC()


def test_candidate_reconciliation_accepts_protected_final_rows_without_downgrade():
    client = FinalizedClient()
    with patch.object(prep, "staged_rollout_root_ids", return_value=[ROOT_ID]):
        result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    writes = result["candidateWrites"]
    assert writes["standardCandidateCount"] == 0
    assert writes["top10CandidateCount"] == 0
    assert writes["standardProtectedFinalCount"] == 1
    assert writes["top10ProtectedFinalCount"] == 1
    assert writes["standardAcceptedCount"] == 1
    assert writes["top10AcceptedCount"] == 1
    assert writes["top10AcceptedSubsetOfStandardAccepted"] is True
    assert client.history[0]["source"] == "canonical_root_set_public_rollout_v1"
    assert client.history[1]["source"] == "canonical_root_top10_public_rollout_v1"


def test_sql_proposal_is_narrow_and_preserves_final_over_candidate_precedence():
    sql = PROPOSAL.read_text(encoding="utf-8")

    assert "v_old_is_final AND v_new_is_candidate" in sql
    assert "RETURN NULL;" in sql
    assert "canonical_root_set_public_rollout_v1" in sql
    assert "canonical_root_top10_public_rollout_v1" in sql
    assert "canonical_root_set_public_rollout_candidate_v1" in sql
    assert "canonical_root_top10_public_rollout_candidate_v1" in sql
    assert "v_old_is_canonical AND NOT v_new_is_canonical" in sql

    lowered = sql.lower()
    assert "drop table" not in lowered
    assert "truncate" not in lowered
    assert "price_storage_v2_scoped_release_gate" not in lowered
    assert "update public.pokemon_set_value_daily_history" not in lowered
    assert "delete from public.pokemon_set_value_daily_history" not in lowered
