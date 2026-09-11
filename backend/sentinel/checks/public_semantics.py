"""Read-only semantic probes for the public inDex HTTP surface.

These checks intentionally validate user-visible contracts rather than process
liveness alone. They never send auth/cookie headers and never mutate state.
Freshness/date authority remains owned by the Prompt-3 watchdog/publication
checks; this module asks only whether the public response is usable.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
from urllib.parse import quote

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


DEFAULT_HTTP_TIMEOUT_SECONDS = 12.0
_USER_AGENT = "inDex-Sentinel/1.0"
_SAMPLE_LIMIT = 5


def _bounded_text(value: Any, limit: int = 300) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    return text if len(text) <= limit else text[:limit] + "...<TRUNCATED>"


def _join_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = "/" + str(path or "").lstrip("/")
    return base + suffix if base else suffix


def _probe_json(
    base_url: str,
    path: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    url = _join_url(base_url, path)
    if not str(base_url or "").strip():
        return {
            "url": url,
            "status_code": None,
            "payload": None,
            "elapsed_ms": 0.0,
            "error": "backend base URL is not configured",
            "body_excerpt": "",
        }

    if http_get is None:
        import requests

        http_get = requests.get

    started = time.perf_counter()
    try:
        response = http_get(
            url,
            timeout=float(timeout_seconds),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
    except Exception as exc:
        return {
            "url": url,
            "status_code": None,
            "payload": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
            "error": f"{exc.__class__.__name__}: {_bounded_text(exc)}",
            "body_excerpt": "",
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    status = int(getattr(response, "status_code", 0) or 0)
    body_excerpt = _bounded_text(getattr(response, "text", ""))
    payload = None
    json_error = None
    try:
        payload = response.json()
    except Exception as exc:
        json_error = f"{exc.__class__.__name__}: {_bounded_text(exc)}"
    return {
        "url": url,
        "status_code": status,
        "payload": payload,
        "elapsed_ms": elapsed_ms,
        "error": json_error,
        "body_excerpt": body_excerpt,
    }


def _http_failure(
    context: CheckContext,
    *,
    check_key: str,
    authority: str,
    failure_code: str,
    probe: Mapping[str, Any],
    expected: Mapping[str, Any],
    observed: Optional[Mapping[str, Any]] = None,
) -> CheckResult:
    compact_observed = {
        "status_code": probe.get("status_code"),
        "elapsed_ms": probe.get("elapsed_ms"),
        **dict(observed or {}),
    }
    return CheckResult.failure(
        check_key,
        failure_code=failure_code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        expected=dict(expected),
        observed=compact_observed,
        evidence={
            "url": probe.get("url"),
            "error": probe.get("error"),
            "body_excerpt": probe.get("body_excerpt"),
        },
        checked_at=context.now,
    )


def _probe_contract_failure(
    context: CheckContext,
    *,
    check_key: str,
    authority: str,
    probe: Mapping[str, Any],
    prefix: str,
    expected: Mapping[str, Any],
) -> Optional[CheckResult]:
    if probe.get("status_code") is None:
        return _http_failure(
            context,
            check_key=check_key,
            authority=authority,
            failure_code=f"{prefix}_unreachable",
            probe=probe,
            expected=expected,
        )
    if int(probe.get("status_code") or 0) != 200:
        return _http_failure(
            context,
            check_key=check_key,
            authority=authority,
            failure_code=f"{prefix}_http_error",
            probe=probe,
            expected=expected,
        )
    if not isinstance(probe.get("payload"), dict):
        return _http_failure(
            context,
            check_key=check_key,
            authority=authority,
            failure_code=f"{prefix}_payload_invalid",
            probe=probe,
            expected=expected,
        )
    return None


def _snapshot_identity(payload: Mapping[str, Any], fallback: str) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    snapshot = meta.get("snapshot") if isinstance(meta.get("snapshot"), dict) else {}
    for value in (
        snapshot.get("marketDate"), snapshot.get("market_date"),
        snapshot.get("builtAt"), snapshot.get("built_at"),
        meta.get("marketDate"), meta.get("market_date"),
    ):
        if str(value or "").strip():
            return str(value).strip()
    return fallback


def check_backend_health(
    context: CheckContext,
    *,
    base_url: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    key = "public.backend_health"
    probe = _probe_json(base_url, "/health", http_get=http_get, timeout_seconds=timeout_seconds)
    expected = {"status_code": 200, "status": "ok", "build_present": True}
    generic = _probe_contract_failure(
        context, check_key=key, authority="backend-health", probe=probe,
        prefix="public_backend", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    build = payload.get("build")
    build_present = bool(build)
    if payload.get("status") != "ok" or not build_present:
        return _http_failure(
            context,
            check_key=key,
            authority=str(build or "backend-health"),
            failure_code="public_backend_health_contract_invalid",
            probe=probe,
            expected=expected,
            observed={"status": payload.get("status"), "build_present": build_present},
        )
    return CheckResult.healthy(
        key,
        authority_identity=str(build),
        expected=expected,
        observed={"status_code": 200, "status": "ok", "build_present": True, "elapsed_ms": probe["elapsed_ms"]},
        checked_at=context.now,
    )


def check_market_public_snapshot(
    context: CheckContext,
    *,
    base_url: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    key = "public.market"
    path = "/explore/set-value-market"
    probe = _probe_json(base_url, path, http_get=http_get, timeout_seconds=timeout_seconds)
    expected = {"status_code": 200, "set_count_min": 1, "market_date_present": True, "rows_valid": True}
    generic = _probe_contract_failure(
        context, check_key=key, authority=path, probe=probe,
        prefix="public_market", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    sets = payload.get("sets")
    authority = _snapshot_identity(payload, path)
    if not isinstance(sets, list) or not sets:
        return _http_failure(
            context, check_key=key, authority=authority,
            failure_code="public_market_empty", probe=probe, expected=expected,
            observed={"set_count": len(sets) if isinstance(sets, list) else None},
        )
    market_date = (((payload.get("meta") or {}).get("snapshot") or {}).get("marketDate"))
    invalid = []
    for row in sets:
        try:
            valid_value = float((row or {}).get("currentSetValue")) > 0
        except (TypeError, ValueError):
            valid_value = False
        if not isinstance(row, dict) or not row.get("setId") or not valid_value:
            invalid.append((row or {}).get("setId") if isinstance(row, dict) else None)
    if not market_date:
        code = "public_market_date_missing"
    elif invalid:
        code = "public_market_rows_invalid"
    else:
        return CheckResult.healthy(
            key,
            authority_identity=str(market_date),
            expected=expected,
            observed={
                "status_code": 200,
                "set_count": len(sets),
                "market_date": market_date,
                "sample_set_ids": [row.get("setId") for row in sets[:_SAMPLE_LIMIT] if isinstance(row, dict)],
                "elapsed_ms": probe["elapsed_ms"],
            },
            checked_at=context.now,
        )
    return _http_failure(
        context, check_key=key, authority=authority, failure_code=code,
        probe=probe, expected=expected,
        observed={"set_count": len(sets), "market_date": market_date, "invalid_set_ids": invalid[:_SAMPLE_LIMIT]},
    )


def _rankable_set_targets(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    targets = payload.get("targets")
    if not isinstance(targets, list):
        return []
    rankable = []
    for row in targets:
        block = row.get("setRipV1") if isinstance(row, dict) else None
        try:
            rank = int((block or {}).get("rank"))
            score = float((block or {}).get("score"))
        except (TypeError, ValueError):
            continue
        if rank > 0 and score >= 0 and row.get("target_id") and row.get("name"):
            rankable.append(row)
    return rankable


def check_homepage_rankings(
    context: CheckContext,
    *,
    base_url: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    key = "public.rankings.homepage"
    path = "/explore/rankings/homepage-summary?limit=60"
    probe = _probe_json(base_url, path, http_get=http_get, timeout_seconds=timeout_seconds)
    expected = {"status_code": 200, "rankable_targets_min": 1}
    generic = _probe_contract_failure(
        context, check_key=key, authority=path, probe=probe,
        prefix="public_homepage_rankings", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    rankable = list(_rankable_set_targets(payload))
    authority = _snapshot_identity(payload, path)
    if not rankable:
        return _http_failure(
            context, check_key=key, authority=authority,
            failure_code="public_homepage_rankings_empty", probe=probe, expected=expected,
            observed={"target_count": len(payload.get("targets") or [])},
        )
    top = rankable[0]
    return CheckResult.healthy(
        key,
        authority_identity=authority,
        expected=expected,
        observed={
            "status_code": 200,
            "rankable_target_count": len(rankable),
            "top_target_id": top.get("target_id"),
            "top_rank": (top.get("setRipV1") or {}).get("rank"),
            "elapsed_ms": probe["elapsed_ms"],
        },
        checked_at=context.now,
    )


def check_rankings_lens(
    context: CheckContext,
    *,
    base_url: str,
    lens: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    normalized = str(lens or "").strip().lower()
    if normalized not in {"sets", "eras", "products"}:
        raise ValueError("rankings lens must be one of: sets, eras, products")
    key = f"public.rankings.{normalized}"
    path = f"/explore/rankings/lens/{normalized}?limit=60"
    probe = _probe_json(base_url, path, http_get=http_get, timeout_seconds=timeout_seconds)
    expected = {"status_code": 200, "rows_min": 1, "anonymous_safe": True}
    generic = _probe_contract_failure(
        context, check_key=key, authority=path, probe=probe,
        prefix=f"public_rankings_{normalized}", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    authority = _snapshot_identity(payload, path)

    sample = []
    if normalized == "sets":
        rows = list(_rankable_set_targets(payload))
        sample = [row.get("target_id") for row in rows[:_SAMPLE_LIMIT]]
    elif normalized == "eras":
        block = payload.get("eraSetStrengthV1")
        rows = block.get("eras") if isinstance(block, dict) else []
        rows = rows if isinstance(rows, list) else []
        sample = [row.get("eraName") for row in rows[:_SAMPLE_LIMIT] if isinstance(row, dict)]
    else:
        families = payload.get("productFamilyRankings")
        rows = []
        if isinstance(families, dict):
            for family_key, family in families.items():
                family_rows = family.get("rows") if isinstance(family, dict) else []
                for row in family_rows if isinstance(family_rows, list) else []:
                    rows.append(row)
                    if len(sample) < _SAMPLE_LIMIT:
                        sample.append(f"{family_key}:{(row or {}).get('id') or (row or {}).get('sealedProductId')}")

    if not rows:
        return _http_failure(
            context, check_key=key, authority=authority,
            failure_code=f"public_rankings_{normalized}_empty", probe=probe, expected=expected,
            observed={"row_count": 0},
        )
    return CheckResult.healthy(
        key,
        authority_identity=authority,
        expected=expected,
        observed={"status_code": 200, "row_count": len(rows), "sample": sample, "elapsed_ms": probe["elapsed_ms"]},
        checked_at=context.now,
    )


def check_tcg_directory(
    context: CheckContext,
    *,
    base_url: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    key = "public.tcgs"
    path = "/profile/tcgs"
    probe = _probe_json(base_url, path, http_get=http_get, timeout_seconds=timeout_seconds)
    expected = {"status_code": 200, "tcg_count_min": 1, "pokemon_present": True}
    generic = _probe_contract_failure(
        context, check_key=key, authority="tcg-directory", probe=probe,
        prefix="public_tcgs", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    rows = payload.get("tcgs")
    if not isinstance(rows, list) or not rows:
        return _http_failure(
            context, check_key=key, authority="tcg-directory",
            failure_code="public_tcgs_empty", probe=probe, expected=expected,
            observed={"tcg_count": len(rows) if isinstance(rows, list) else None},
        )
    pokemon_present = any(
        "pokemon" in str((row or {}).get("name") or "").lower().replace("é", "e")
        or str((row or {}).get("slug") or "").lower() == "pokemon"
        for row in rows if isinstance(row, dict)
    )
    if not pokemon_present:
        return _http_failure(
            context, check_key=key, authority="tcg-directory",
            failure_code="public_tcgs_pokemon_missing", probe=probe, expected=expected,
            observed={"tcg_count": len(rows), "sample_names": [row.get("name") for row in rows[:_SAMPLE_LIMIT] if isinstance(row, dict)]},
        )
    return CheckResult.healthy(
        key,
        authority_identity="tcg-directory",
        expected=expected,
        observed={"status_code": 200, "tcg_count": len(rows), "pokemon_present": True, "elapsed_ms": probe["elapsed_ms"]},
        checked_at=context.now,
    )


def check_representative_set_page(
    context: CheckContext,
    *,
    base_url: str,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckResult:
    """Probe the current public #1-ranked set page without hardcoding a set id."""
    key = "public.setpage.representative"
    rankings_probe = _probe_json(
        base_url, "/explore/rankings/homepage-summary?limit=1",
        http_get=http_get, timeout_seconds=timeout_seconds,
    )
    expected = {"ranking_source_available": True, "status_code": 200, "summary_present": True}
    generic = _probe_contract_failure(
        context, check_key=key, authority="representative-set",
        probe=rankings_probe, prefix="public_setpage_source", expected=expected,
    )
    if generic:
        return generic
    rankable = list(_rankable_set_targets(rankings_probe["payload"]))
    if not rankable:
        return _http_failure(
            context, check_key=key, authority="representative-set",
            failure_code="public_setpage_source_empty", probe=rankings_probe, expected=expected,
        )
    set_id = str(rankable[0].get("target_id"))
    path = f"/tcgs/pokemon/sets/{quote(set_id, safe='')}/page"
    probe = _probe_json(base_url, path, http_get=http_get, timeout_seconds=timeout_seconds)
    generic = _probe_contract_failure(
        context, check_key=key, authority=set_id, probe=probe,
        prefix="public_setpage", expected=expected,
    )
    if generic:
        return generic
    payload = probe["payload"]
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return _http_failure(
            context, check_key=key, authority=set_id,
            failure_code="public_setpage_summary_missing", probe=probe, expected=expected,
            observed={"set_id": set_id},
        )
    return CheckResult.healthy(
        key,
        authority_identity=set_id,
        expected=expected,
        observed={
            "status_code": 200,
            "set_id": set_id,
            "summary_present": True,
            "top_hit_count": len(payload.get("top_hits") or []),
            "elapsed_ms": probe["elapsed_ms"],
        },
        checked_at=context.now,
    )
