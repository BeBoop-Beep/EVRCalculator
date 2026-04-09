# Phase 1 Portfolio Delta Wiring (Backend)

This note records where Phase 1 orchestration is implemented.

## Single-user refresh orchestration

- Route/controller: `backend/api/main.py` -> `refresh_collection_summary`
- Service orchestration: `backend/db/services/collection_summary_service.py` -> `refresh_user_summary_with_history_and_deltas`
- Repository/DB access: `backend/db/repositories/user_collection_summary_repository.py`

Execution order in service:

1. recompute summary from holdings and upsert `user_collection_summary`
2. execute `snapshot_user_portfolio_history(user_id)`
3. execute `refresh_user_collection_deltas(user_id)`
4. read `user_collection_summary` snapshot
5. return updated summary payload

## All-users daily reconciliation

- HTTP entry point: `backend/api/main.py` -> `run_portfolio_daily_reconciliation_job`
- Job/CLI entry point: `backend/jobs/portfolio_daily_reconciliation.py` -> `run`
- Service orchestration: `backend/db/services/collection_summary_service.py` -> `run_daily_portfolio_reconciliation_all_users`

Execution order in service:

1. verify summary source readiness (`has_stale_user_collection_summary_rows` must be false)
2. execute `snapshot_all_user_portfolio_history()`
3. execute `refresh_user_collection_deltas()`

## Summary read fields

Summary reads now include all portfolio delta fields via:

- `backend/db/repositories/user_collection_summary_repository.py` -> `load_user_collection_summary_snapshot`
- `backend/db/services/collection_summary_service.py` -> `get_user_collection_summary_snapshot`
- `backend/db/services/collection_portfolio_service.py` -> `_public_summary_response_from_snapshot`
