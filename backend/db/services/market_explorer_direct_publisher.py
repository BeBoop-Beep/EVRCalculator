"""Direct PostgreSQL handoff for the guarded Market Explorer prepared publisher.

This module is intentionally tiny: maintained-cache discovery/builds still use the
existing service-role client. Only the expensive prepared-generation publication
uses PostgreSQL wire protocol so it is not bounded by PostgREST/authenticator
statement timeouts.
"""
from __future__ import annotations

import os
from typing import Any, Optional

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_STATEMENT_TIMEOUT_MS = 120_000
PUBLISH_SQL = "select public.run_market_explorer_guarded_publisher_v1(%s::date)"


def resolve_database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")


def safe_error(exc: BaseException, secret: Optional[str]) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if secret:
        message = message.replace(secret, "<REDACTED_DATABASE_URL>")
    return message


def publish_prepared_generation(
    required_market_date: str,
    *,
    database_url: Optional[str] = None,
    rollback_only: bool = False,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
) -> dict[str, Any]:
    dsn = database_url or resolve_database_url()
    if not dsn:
        return {"status": "failed", "error": "direct_db_credential_missing"}

    try:
        import psycopg
    except Exception as exc:  # pragma: no cover - environment-specific
        return {"status": "failed", "error": safe_error(exc, dsn)}

    try:
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            autocommit=False,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select set_config('statement_timeout', %s, true)",
                    (str(int(statement_timeout_ms)),),
                )
                cur.execute(PUBLISH_SQL, (str(required_market_date)[:10],))
                row = cur.fetchone()
                payload = row[0] if row else None
            if rollback_only:
                conn.rollback()
                return {
                    "status": "verified_rollback",
                    "targetMarketDate": str(required_market_date)[:10],
                    "result": payload,
                }
            conn.commit()
            return {
                "status": "refreshed",
                "targetMarketDate": str(required_market_date)[:10],
                "result": payload,
            }
    except Exception as exc:
        return {
            "status": "failed",
            "targetMarketDate": str(required_market_date)[:10],
            "error": safe_error(exc, dsn),
        }
