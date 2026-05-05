"""Read-only audit tool for set image URL health in public.sets.

Examples:
  python backend/scripts/audit_set_image_urls.py --era "Mega Evolution"
  python backend/scripts/audit_set_image_urls.py --sets "Perfect Order" "Ascended Heroes"
  python backend/scripts/audit_set_image_urls.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

# Keep script runnable from repo root and direct script execution.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.db.clients.supabase_client import public_read_client  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass
class UrlAuditResult:
    url: Optional[str]
    state: str
    http_status: Optional[int]
    content_type: Optional[str]
    error: Optional[str]


def _normalize_url(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _url_shape(url: Optional[str]) -> Dict[str, Any]:
    if url is None:
        return {
            "present": False,
            "scheme": None,
            "host": None,
            "path": None,
            "https": False,
            "contains_whitespace": False,
            "looks_malformed": False,
        }

    parsed = urlparse(url)
    return {
        "present": True,
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path": parsed.path,
        "https": parsed.scheme == "https",
        "contains_whitespace": any(ch.isspace() for ch in url),
        "looks_malformed": not parsed.scheme or not parsed.netloc,
    }


def _check_url(url: Optional[str], timeout_seconds: float) -> UrlAuditResult:
    if url is None:
        return UrlAuditResult(
            url=None,
            state="null",
            http_status=None,
            content_type=None,
            error=None,
        )

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "EVR-set-image-audit/1.0", "Accept": "image/*,*/*"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return UrlAuditResult(
                url=url,
                state="ok" if 200 <= response.status < 300 else "http_error",
                http_status=response.status,
                content_type=response.headers.get("Content-Type"),
                error=None,
            )
    except urllib.error.HTTPError as exc:
        return UrlAuditResult(
            url=url,
            state="http_error",
            http_status=exc.code,
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive path
        return UrlAuditResult(
            url=url,
            state="request_error",
            http_status=None,
            content_type=None,
            error=str(exc),
        )


def _fetch_eras() -> List[Dict[str, Any]]:
    result = public_read_client.table("eras").select("id,name,canonical_key").execute()
    return result.data or []


def _fetch_sets() -> List[Dict[str, Any]]:
    result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,pokemon_api_set_id,logo_image_url,symbol_image_url,hero_image_url,era_id")
        .execute()
    )
    return result.data or []


def _resolve_era_ids(eras: Iterable[Dict[str, Any]], requested_era: str) -> List[str]:
    needle = requested_era.strip().lower()
    if not needle:
        return []

    matched: List[str] = []
    for row in eras:
        name = str(row.get("name") or "").strip().lower()
        canonical = str(row.get("canonical_key") or "").strip().lower()
        row_id = str(row.get("id") or "").strip().lower()
        if needle in {name, canonical, row_id}:
            raw_id = row.get("id")
            if raw_id is not None:
                matched.append(str(raw_id))
    return matched


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only audit for set image URL health")
    parser.add_argument("--era", type=str, default=None, help="Filter sets by era name/canonical key/id")
    parser.add_argument("--sets", nargs="+", default=None, help="Filter by one or more exact set names")
    parser.add_argument("--all", action="store_true", help="Audit all sets with any image URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout per URL in seconds (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional JSON output path",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.all and not args.era and not args.sets:
        parser.error("Provide at least one filter: --all, --era, or --sets")

    eras = _fetch_eras()
    sets = _fetch_sets()

    era_by_id = {str(row.get("id")): row for row in eras if row.get("id") is not None}
    selected = list(sets)

    if args.era:
        allowed_era_ids = set(_resolve_era_ids(eras, args.era))
        selected = [row for row in selected if str(row.get("era_id")) in allowed_era_ids]

    if args.sets:
        allowed_names = {name.strip().lower() for name in args.sets if str(name).strip()}
        selected = [row for row in selected if str(row.get("name") or "").strip().lower() in allowed_names]

    # Always keep this script read-only and focused on image-bearing rows.
    selected = [
        row
        for row in selected
        if _normalize_url(row.get("logo_image_url"))
        or _normalize_url(row.get("symbol_image_url"))
        or _normalize_url(row.get("hero_image_url"))
    ]

    url_cache: Dict[str, UrlAuditResult] = {}

    def get_cached_check(url: Optional[str]) -> UrlAuditResult:
        if url is None:
            return _check_url(None, args.timeout)
        if url not in url_cache:
            url_cache[url] = _check_url(url, args.timeout)
        return url_cache[url]

    rows: List[Dict[str, Any]] = []
    status_summary = {
        "logo": {"ok": 0, "broken": 0, "missing": 0},
        "symbol": {"ok": 0, "broken": 0, "missing": 0},
        "hero": {"ok": 0, "broken": 0, "missing": 0},
    }

    for row in sorted(selected, key=lambda item: str(item.get("name") or "").lower()):
        logo_url = _normalize_url(row.get("logo_image_url"))
        symbol_url = _normalize_url(row.get("symbol_image_url"))
        hero_url = _normalize_url(row.get("hero_image_url"))

        logo_check = get_cached_check(logo_url)
        symbol_check = get_cached_check(symbol_url)
        hero_check = get_cached_check(hero_url)

        def bump(metric_name: str, result: UrlAuditResult) -> None:
            if result.state == "null":
                status_summary[metric_name]["missing"] += 1
            elif result.state == "ok":
                status_summary[metric_name]["ok"] += 1
            else:
                status_summary[metric_name]["broken"] += 1

        bump("logo", logo_check)
        bump("symbol", symbol_check)
        bump("hero", hero_check)

        era_id = str(row.get("era_id")) if row.get("era_id") is not None else None
        era_row = era_by_id.get(era_id) if era_id else None

        rows.append(
            {
                "set_name": row.get("name"),
                "canonical_key": row.get("canonical_key"),
                "pokemon_api_set_id": row.get("pokemon_api_set_id"),
                "era_id": era_id,
                "era_name": (era_row or {}).get("name"),
                "logo_image_url": logo_url,
                "logo_url_shape": _url_shape(logo_url),
                "logo_status": {
                    "state": logo_check.state,
                    "http_status": logo_check.http_status,
                    "content_type": logo_check.content_type,
                    "error": logo_check.error,
                },
                "symbol_image_url": symbol_url,
                "symbol_url_shape": _url_shape(symbol_url),
                "symbol_status": {
                    "state": symbol_check.state,
                    "http_status": symbol_check.http_status,
                    "content_type": symbol_check.content_type,
                    "error": symbol_check.error,
                },
                "hero_image_url": hero_url,
                "hero_url_shape": _url_shape(hero_url),
                "hero_status": {
                    "state": hero_check.state,
                    "http_status": hero_check.http_status,
                    "content_type": hero_check.content_type,
                    "error": hero_check.error,
                },
            }
        )

    report = {
        "meta": {
            "read_only": True,
            "cwd": os.getcwd(),
            "filters": {
                "all": bool(args.all),
                "era": args.era,
                "sets": args.sets or [],
            },
            "timeout_seconds": args.timeout,
            "rows_returned": len(rows),
            "unique_urls_checked": len(url_cache),
        },
        "summary": status_summary,
        "rows": rows,
    }

    rendered = json.dumps(report, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
