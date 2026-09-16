from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "backend/db/proposals/finalized_market_day_immutability.sql"
DAY = "2026-09-15"
ROOT_ID = "root"
OTHER_ROOT_ID = "other-root"


def _package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load test target {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load exact source files without executing backend.db.services.__init__, which
# imports unrelated application dependencies not installed in this isolated CI.
_package("backend", ROOT / "backend")
_package("backend.db", ROOT / "backend/db")
_package("backend.db.services", ROOT / "backend/db/services")
_package("backend.domain", ROOT / "backend/domain")
_package("backend.domain.pokemon", ROOT / "backend/domain/pokemon")
_load(
    "backend.db.services.price_storage_v2_integration",
    "backend/db/services/price_storage_v2_integration.py",
)
_load(
    "backend.domain.pokemon.market_index",
    "backend/domain/pokemon/market_index.py",
)
cohort = types.ModuleType("backend.db.services.pokemon_market_rollout_cohort")
cohort.MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE = "2026-09-10"
cohort.resolve_market_root_ids = lambda *_args, **_kwargs: [ROOT_ID]
sys.modules["backend.db.services.pokemon_market_rollout_cohort"] = cohort
prep = _load(
    "backend.db.services.pokemon_market_rollout_preparation",
    "backend/db/services/pokemon_market_rollout_preparation.py",
)


class Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def in_(self, key, values):
        allowed = set(values)
        self.rows = [row for row in self.rows if row.get(key) in allowed]
        return self

    def execute(self):
        return SimpleNamespace(data=list(self.rows))


class Client:
    def __init__(
        self,
        *,
        index_rows=None,
        history=None,
        response=None,
        preserve_final=False,
    ):
        self.index_rows = list(index_rows or [])
        self.history = list(history or [])
        self.response = response or {
            "status": "complete",
            "marketDate": DAY,
            "candidateDate": DAY,
            "rolloutRootCount": 1,
            "standardRowsUpserted": 1,
            "top10RowsUpserted": 1,
        }
        self.preserve_final = preserve_final
        self.rpc_calls = []

    def table(self, name):
        if name == prep.MARKET_INDEX_TABLE:
            return Query(self.index_rows)
        if name == prep.HISTORY_TABLE:
            return Query(self.history)
        raise AssertionError(f"unexpected table access: {name}")

    def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        client = self

        class RPC:
            def execute(self):
                if name == prep.AUTHORITY_SYNC_RPC:
                    return SimpleNamespace(data={
                        "status": "complete",
                        "marketDate": DAY,
                        "rowsActivated": 0,
                        "structuralRootCount": 1,
                        "activeAuthorityRootCount": 1,
                        "missingStructuralRootCount": 0,
                        "structuralFingerprint": "fixture",
                    })
                if not client.preserve_final:
                    client.history = [
                        {
                            "set_id": ROOT_ID,
                            "snapshot_date": DAY,
                            "value_scope": "standard",
                            "source": prep.CANDIDATE_SOURCES["standard"],
                        },
                        {
                            "set_id": ROOT_ID,
                            "snapshot_date": DAY,
                            "value_scope": "top10",
                            "source": prep.CANDIDATE_SOURCES["top10"],
                        },
                    ]
                return SimpleNamespace(data=client.response)

        return RPC()


def _index_row(key: str, *, set_id=ROOT_ID, tcg="pokemon", methodology=None):
    return {
        "index_key": key,
        "tcg": tcg,
        "methodology_version": methodology or prep.MARKET_INDEX_METHODOLOGY_VERSION,
        "market_date": DAY,
        "set_count": 1,
        "constituents_json": [{"setId": set_id}],
    }


def _final_history():
    return [
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


def test_exact_published_authority_day_skips_candidate_rpc_entirely():
    client = Client(
        index_rows=[_index_row("raw"), _index_row("top10")],
        history=_final_history(),
    )
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    assert result["status"] == "already_finalized"
    assert result["rpcInvoked"] is False
    assert result["candidatePreparationSkipped"] is True
    assert result["finalizedMarket"]["ready"] is True
    assert result["finalizedMarket"]["exactConstituents"] == {
        "raw": True,
        "top10": True,
    }
    assert client.rpc_calls == [
        (prep.AUTHORITY_SYNC_RPC, {"p_market_date": DAY}),
    ]


def test_same_count_wrong_constituent_fails_closed_and_runs_candidate_prep():
    client = Client(
        index_rows=[_index_row("raw"), _index_row("top10", set_id=OTHER_ROOT_ID)],
    )
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    assert result["rpcInvoked"] is True
    assert client.rpc_calls[-1] == (
        prep.CANDIDATE_PREPARATION_RPC,
        {"p_market_date": DAY},
    )


def test_wrong_tcg_or_methodology_cannot_certify_finalized_day():
    client = Client(
        index_rows=[
            _index_row("raw", tcg="other"),
            _index_row("top10", methodology="wrong-version"),
        ],
    )
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    assert result["rpcInvoked"] is True


def test_candidate_reconciliation_accepts_protected_final_rows_without_downgrade():
    client = Client(
        history=_final_history(),
        response={
            "status": "complete",
            "marketDate": DAY,
            "candidateDate": DAY,
            "rolloutRootCount": 1,
            "standardRowsUpserted": 0,
            "top10RowsUpserted": 0,
        },
        preserve_final=True,
    )
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    writes = result["candidateWrites"]
    assert writes["standardCandidateCount"] == 0
    assert writes["top10CandidateCount"] == 0
    assert writes["standardProtectedFinalCount"] == 1
    assert writes["top10ProtectedFinalCount"] == 1
    assert writes["standardAcceptedCount"] == 1
    assert writes["top10AcceptedCount"] == 1
    assert client.history == _final_history()


def test_sql_proposal_is_narrow_and_only_adds_final_to_candidate_precedence():
    sql = PROPOSAL.read_text(encoding="utf-8")

    assert "v_old_is_final AND v_new_is_candidate" in sql
    assert "canonical_root_set_public_rollout_v1" in sql
    assert "canonical_root_top10_public_rollout_v1" in sql
    assert "canonical_root_set_public_rollout_candidate_v1" in sql
    assert "canonical_root_top10_public_rollout_candidate_v1" in sql
    assert "counts_toward_parent_set_value = true" in sql
    assert "v_old_is_canonical" not in sql

    lowered = sql.lower()
    assert "drop table" not in lowered
    assert "truncate" not in lowered
    assert "price_storage_v2_scoped_release_gate" not in lowered
    assert "update public.pokemon_set_value_daily_history" not in lowered
    assert "delete from public.pokemon_set_value_daily_history" not in lowered
