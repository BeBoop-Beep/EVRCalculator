"""Runtime/database registry preflight for the daily Pokémon scrape cohort.

Why this exists
---------------
On 2026-08-03 the scraper VM was running a commit 19 revisions behind ``main``
that predated 37 ``otherEra`` config files. Database metadata had already been
synchronized from a newer code generation, so 34 database cohort rows named
canonical keys the *deployed* runtime could not resolve. Every one of those jobs
failed with ``invalid_set_key_filter``, each burned three attempts, and the batch
never completed — which correctly (fail-closed) kept the previous market date
public, but left the pipeline stuck with no actionable signal.

Nothing in the pipeline ever asked the one question that would have caught it
before a single job ran: *does the database cohort agree with the registry this
process can actually resolve?* This module is that question.

It is deliberately a PRE-flight. Detecting the drift after enqueueing 201 jobs is
too late; the point is to refuse to create the batch at all, and to say exactly
which keys diverged and which code revision was running when it happened.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.db.services.pokemon_set_lifecycle_flags import (
    normalize_details_url,
    supports_opening_simulation,
)

logger = logging.getLogger(__name__)

PREFLIGHT_TAG = "[scrape-runtime-preflight]"

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Mismatch categories. Callers branch on these, never on prose.
MISMATCH_MISSING_LOCAL_KEY = "missing_local_key"
MISMATCH_UNEXPECTED_DB_KEY = "unexpected_db_key"
MISMATCH_URL = "url_mismatch"
MISMATCH_LIFECYCLE_FLAG = "lifecycle_flag_mismatch"


def _git(*args: str) -> Optional[str]:
    """Best-effort git query. Never raises — provenance must not break preflight."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:  # pragma: no cover - git absent / sandboxed
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def _stable_key_hash(keys: List[str]) -> str:
    """SHA-256 over the sorted, newline-joined canonical keys.

    Stable across processes and platforms, so the same code revision always
    produces the same hash and two runtimes can be compared by one short string.
    """
    payload = "\n".join(sorted(keys)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class RuntimePreflightReport:
    """Structured verdict comparing the local registry to the database cohort."""

    runtime_git_sha: Optional[str] = None
    runtime_git_branch: Optional[str] = None
    runtime_git_dirty: Optional[bool] = None
    repository_root: str = str(_REPO_ROOT)
    python_executable: str = sys.executable
    working_directory: str = field(default_factory=os.getcwd)
    pythonpath: Optional[str] = field(default_factory=lambda: os.environ.get("PYTHONPATH"))
    loaded_eras: List[str] = field(default_factory=list)

    local_registry_key_count: int = 0
    local_eligible_key_count: int = 0
    database_cohort_count: int = 0

    local_registry_hash: Optional[str] = None
    database_cohort_hash: Optional[str] = None

    missing_local_keys: List[str] = field(default_factory=list)
    unexpected_db_keys: List[str] = field(default_factory=list)
    url_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    lifecycle_flag_mismatches: List[Dict[str, Any]] = field(default_factory=list)

    error: Optional[str] = None

    @property
    def mismatch_count(self) -> int:
        return (
            len(self.missing_local_keys)
            + len(self.unexpected_db_keys)
            + len(self.url_mismatches)
            + len(self.lifecycle_flag_mismatches)
        )

    @property
    def ok(self) -> bool:
        # An unreadable authority is a failure, never a pass (fail-closed).
        if self.error is not None:
            return False
        return self.mismatch_count == 0

    @property
    def registry_hashes_match(self) -> bool:
        return (
            self.local_registry_hash is not None
            and self.local_registry_hash == self.database_cohort_hash
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "runtime": {
                "git_sha": self.runtime_git_sha,
                "git_branch": self.runtime_git_branch,
                "git_dirty": self.runtime_git_dirty,
                "repository_root": self.repository_root,
                "python_executable": self.python_executable,
                "loaded_eras": self.loaded_eras,
                # Cron misconfiguration shows up here: a working directory or
                # import root pointing at a second checkout.
                "working_directory": self.working_directory,
                "pythonpath": self.pythonpath,
            },
            "counts": {
                "local_registry_keys": self.local_registry_key_count,
                "local_eligible_keys": self.local_eligible_key_count,
                "database_cohort": self.database_cohort_count,
            },
            "hashes": {
                "local_eligible_registry_sha256": self.local_registry_hash,
                "database_cohort_sha256": self.database_cohort_hash,
                "match": self.registry_hashes_match,
            },
            "mismatches": {
                "count": self.mismatch_count,
                MISMATCH_MISSING_LOCAL_KEY: self.missing_local_keys,
                MISMATCH_UNEXPECTED_DB_KEY: self.unexpected_db_keys,
                MISMATCH_URL: self.url_mismatches,
                MISMATCH_LIFECYCLE_FLAG: self.lifecycle_flag_mismatches,
            },
        }

    def report_lines(self) -> List[str]:
        """Greppable summary for cron logs and Slack."""
        lines = [
            f"{PREFLIGHT_TAG} ok={self.ok} sha={self.runtime_git_sha} "
            f"branch={self.runtime_git_branch} root={self.repository_root} "
            f"python={self.python_executable}",
            f"{PREFLIGHT_TAG} local_registry={self.local_registry_key_count} "
            f"local_eligible={self.local_eligible_key_count} "
            f"db_cohort={self.database_cohort_count} "
            f"local_hash={self.local_registry_hash} db_hash={self.database_cohort_hash} "
            f"hashes_match={self.registry_hashes_match}",
        ]
        if self.error:
            lines.append(f"{PREFLIGHT_TAG} authority_error={self.error}")
        if self.missing_local_keys:
            lines.append(
                f"{PREFLIGHT_TAG} {MISMATCH_MISSING_LOCAL_KEY} "
                f"({len(self.missing_local_keys)}): {', '.join(self.missing_local_keys)}"
            )
        if self.unexpected_db_keys:
            lines.append(
                f"{PREFLIGHT_TAG} {MISMATCH_UNEXPECTED_DB_KEY} "
                f"({len(self.unexpected_db_keys)}): {', '.join(self.unexpected_db_keys)}"
            )
        for row in self.url_mismatches:
            lines.append(
                f"{PREFLIGHT_TAG} {MISMATCH_URL} key={row.get('canonical_key')} "
                f"db={row.get('database_url')!r} config={row.get('config_url')!r}"
            )
        for row in self.lifecycle_flag_mismatches:
            lines.append(
                f"{PREFLIGHT_TAG} {MISMATCH_LIFECYCLE_FLAG} key={row.get('canonical_key')} "
                f"field={row.get('field')} db={row.get('database_value')} "
                f"config={row.get('config_value')}"
            )
        return lines


def _default_registry_loader() -> Dict[str, Any]:
    # Imported lazily: importing the scrape runner pulls in the scraper stack, and
    # the preflight must stay importable from lightweight contexts and tests.
    from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry

    return build_valid_set_key_registry()


def load_database_cohort_rows() -> List[Dict[str, Any]]:
    """Read the rows that would enter the CORRECTED daily cohort.

    Mirrors ``public.pokemon_scrape_ready_cohort()`` exactly, including the
    ``catalog_only`` guard added by migration 058.
    """
    from backend.db.clients.supabase_client import supabase

    page_size = 1000
    offset = 0
    rows: List[Dict[str, Any]] = []
    while True:
        query = (
            supabase.table("sets")
            .select(
                "id,name,canonical_key,card_details_url,has_card_details_url,"
                "ready_for_daily_scrape,catalog_only,supports_opening_simulation"
            )
            .eq("ready_for_daily_scrape", True)
            .eq("has_card_details_url", True)
            .eq("catalog_only", False)
            .not_.is_("card_details_url", "null")
            .order("canonical_key")
        )
        range_fn = getattr(query, "range", None)
        if range_fn is None:  # unit fakes without pagination support
            result = query.execute()
            return list((result.data if result else []) or [])
        result = range_fn(offset, offset + page_size - 1).execute()
        page = list((result.data if result else []) or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def run_runtime_preflight(
    *,
    registry_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    cohort_loader: Optional[Callable[[], List[Dict[str, Any]]]] = None,
) -> RuntimePreflightReport:
    """Compare the local runtime registry against the database daily cohort.

    ``registry_loader`` / ``cohort_loader`` are a test-only dependency-injection
    seam. There is deliberately NO production bypass flag: a preflight an operator
    can switch off is not a guarantee.
    """
    report = RuntimePreflightReport(
        runtime_git_sha=_git("rev-parse", "HEAD"),
        runtime_git_branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
    )
    dirty = _git("status", "--porcelain")
    report.runtime_git_dirty = bool(dirty) if dirty is not None else None

    try:
        registry = (registry_loader or _default_registry_loader)()
    except Exception as exc:
        report.error = f"local registry could not be built ({exc})"
        return report

    config_map: Dict[str, Any] = registry.get("config_map") or {}
    report.loaded_eras = list(registry.get("loaded_eras") or [])
    report.local_registry_key_count = len(registry.get("valid_keys") or [])

    # The local set the DB cohort is expected to equal: resolvable, not
    # catalog-only, and carrying a card URL.
    local_eligible: Dict[str, Any] = {}
    for canonical_key, config_cls in config_map.items():
        if not isinstance(canonical_key, str) or not canonical_key.strip():
            continue
        if bool(getattr(config_cls, "CATALOG_ONLY", False)):
            continue
        card_url = getattr(config_cls, "CARD_DETAILS_URL", None)
        if not (card_url and str(card_url).strip()):
            continue
        local_eligible[canonical_key] = config_cls

    report.local_eligible_key_count = len(local_eligible)
    report.local_registry_hash = _stable_key_hash(list(local_eligible))

    try:
        cohort_rows = (cohort_loader or load_database_cohort_rows)()
    except Exception as exc:
        report.error = f"database cohort could not be read ({exc})"
        return report

    db_keys: List[str] = []
    for row in cohort_rows:
        canonical_key = row.get("canonical_key")
        canonical_key = str(canonical_key).strip() if canonical_key else ""

        if not canonical_key:
            report.missing_local_keys.append(f"<missing canonical_key set_id={row.get('id')}>")
            continue

        db_keys.append(canonical_key)

        config_cls = local_eligible.get(canonical_key)
        if config_cls is None:
            # Either the deployed runtime cannot resolve the key at all (the
            # 2026-08-03 failure), or it resolves it but the config disqualifies
            # it. Both mean the database is ahead of this runtime.
            report.missing_local_keys.append(canonical_key)
            if canonical_key in config_map:
                resolved = config_map[canonical_key]
                if bool(getattr(resolved, "CATALOG_ONLY", False)):
                    report.lifecycle_flag_mismatches.append(
                        {
                            "canonical_key": canonical_key,
                            "field": "catalog_only",
                            "database_value": bool(row.get("catalog_only")),
                            "config_value": True,
                        }
                    )
                else:
                    report.lifecycle_flag_mismatches.append(
                        {
                            "canonical_key": canonical_key,
                            "field": "has_card_details_url",
                            "database_value": bool(row.get("has_card_details_url")),
                            "config_value": False,
                        }
                    )
            continue

        db_url = normalize_details_url(row.get("card_details_url"))
        config_url = normalize_details_url(getattr(config_cls, "CARD_DETAILS_URL", None))
        if db_url != config_url:
            report.url_mismatches.append(
                {
                    "canonical_key": canonical_key,
                    "database_url": row.get("card_details_url"),
                    "config_url": getattr(config_cls, "CARD_DETAILS_URL", None),
                }
            )

        for field_name, db_value, config_value in (
            ("ready_for_daily_scrape", row.get("ready_for_daily_scrape"), True),
            ("catalog_only", row.get("catalog_only"), False),
            (
                "supports_opening_simulation",
                row.get("supports_opening_simulation"),
                supports_opening_simulation(config_cls),
            ),
        ):
            # Absent columns are not asserted against: a runtime predating
            # migration 058 must not report phantom mismatches.
            if db_value is None:
                continue
            if bool(db_value) != bool(config_value):
                report.lifecycle_flag_mismatches.append(
                    {
                        "canonical_key": canonical_key,
                        "field": field_name,
                        "database_value": bool(db_value),
                        "config_value": bool(config_value),
                    }
                )

    report.database_cohort_count = len(cohort_rows)
    report.database_cohort_hash = _stable_key_hash(db_keys)

    db_key_set = set(db_keys)
    # Locally eligible but absent from the DB cohort: metadata sync has not run
    # yet. This does not corrupt a batch, but it silently under-scrapes, so it is
    # still a mismatch the operator must resolve.
    report.unexpected_db_keys = sorted(set(local_eligible) - db_key_set)

    report.missing_local_keys = sorted(set(report.missing_local_keys))
    return report


def preflight_alert_payload(report: RuntimePreflightReport, *, market_date: str) -> Dict[str, Any]:
    """Payload for the configuration/deployment alert raised on failure."""
    payload = report.to_dict()
    payload["market_date"] = market_date
    return payload


def format_preflight_json(report: RuntimePreflightReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
