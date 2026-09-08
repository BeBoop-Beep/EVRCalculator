"""Owner-scoped personal-market sources for Market Explorer.

Personal sources deliberately stay outside the semantic/global Market Explorer
cache. Portfolio snapshots are collection *value* history; holdings flows are
not neutralized, so this module never represents them as market return/index.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from backend.db.clients.supabase_client import supabase


PERSONAL_MARKET_METHODOLOGY_VERSION = "personal-value-history-v1"
WISHLIST_UNAVAILABLE_REASON = (
    "Wishlist market history becomes available once saved Wishlist membership is published."
)

_PORTFOLIO_PARTITIONS = {
    "total": ("Total Portfolio", "portfolio_value", None),
    "raw": ("Portfolio · Raw Cards", "cards_value", "cards_count"),
    "sealed": ("Portfolio · Sealed Products", "sealed_value", "sealed_count"),
    "graded": ("Portfolio · Graded Cards", "graded_value", "graded_count"),
}


@dataclass(frozen=True)
class PersonalMarketSource:
    source_type: str
    asset_partition: str
    methodology_version: str
    available: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceType": self.source_type,
            "assetPartition": self.asset_partition,
            "methodologyVersion": self.methodology_version,
            "available": self.available,
            "reason": self.reason,
        }


def _require_owner(authenticated_user_id: str | None, requested_user_id: str | None = None) -> str:
    owner = str(authenticated_user_id or "").strip()
    if not owner:
        raise PermissionError("Authentication is required for personal markets")
    if requested_user_id is not None and str(requested_user_id) != owner:
        raise PermissionError("Personal markets may only be read by their owner")
    return owner


def personal_market_identity(
    authenticated_user_id: str | None,
    source_type: str,
    asset_partition: str,
    methodology_version: str = PERSONAL_MARKET_METHODOLOGY_VERSION,
) -> str:
    """Return an opaque, owner-scoped identity in a private namespace."""
    owner = _require_owner(authenticated_user_id)
    source = str(source_type).strip().lower()
    partition = str(asset_partition).strip().lower()
    if source not in {"portfolio", "wishlist"}:
        raise ValueError("Unsupported personal-market source type")
    if partition not in _PORTFOLIO_PARTITIONS:
        raise ValueError("Unsupported personal-market asset partition")
    digest = sha256(
        f"{owner}\x1f{source}\x1f{partition}\x1f{methodology_version}".encode("utf-8")
    ).hexdigest()
    return f"private:personal:{digest}"


def portfolio_source(asset_partition: str = "total") -> PersonalMarketSource:
    if asset_partition not in _PORTFOLIO_PARTITIONS:
        raise ValueError("Unsupported portfolio asset partition")
    return PersonalMarketSource(
        source_type="portfolio",
        asset_partition=asset_partition,
        methodology_version=PERSONAL_MARKET_METHODOLOGY_VERSION,
        available=True,
    )


def wishlist_source(asset_partition: str = "total") -> PersonalMarketSource:
    if asset_partition not in _PORTFOLIO_PARTITIONS:
        raise ValueError("Unsupported Wishlist asset partition")
    return PersonalMarketSource(
        source_type="wishlist",
        asset_partition=asset_partition,
        methodology_version="wishlist-membership-unpublished-v1",
        available=False,
        reason=WISHLIST_UNAVAILABLE_REASON,
    )


def adapt_portfolio_value_history(
    rows: Sequence[Mapping[str, Any]],
    *,
    authenticated_user_id: str | None,
    asset_partition: str = "total",
    requested_user_id: str | None = None,
) -> dict[str, Any]:
    """Adapt canonical snapshots without pretending cash flows are returns."""
    owner = _require_owner(authenticated_user_id, requested_user_id)
    source = portfolio_source(asset_partition)
    label, value_column, count_column = _PORTFOLIO_PARTITIONS[asset_partition]
    points = []
    for row in sorted(rows, key=lambda item: str(item.get("snapshot_date") or "")):
        point = {
            "date": row.get("snapshot_date"),
            "value": row.get(value_column),
        }
        if count_column:
            point["count"] = row.get(count_column)
        else:
            point["counts"] = {
                "raw": row.get("cards_count"),
                "sealed": row.get("sealed_count"),
                "graded": row.get("graded_count"),
            }
        points.append(point)

    return {
        "key": personal_market_identity(owner, "portfolio", asset_partition),
        "label": label,
        "source": source.to_dict(),
        "valueDimension": "portfolio_value",
        "unit": "USD",
        "seriesKind": "value",
        "isMarketIndex": False,
        "isMarketReturn": False,
        "holdingsFlowNeutralized": False,
        "cachePolicy": {"scope": "request-private", "publicCacheEligible": False},
        "points": points,
    }


def get_portfolio_value_history(
    *,
    authenticated_user_id: str | None,
    asset_partition: str = "total",
    requested_user_id: str | None = None,
) -> dict[str, Any]:
    """Read only the authenticated owner's canonical portfolio snapshots."""
    owner = _require_owner(authenticated_user_id, requested_user_id)
    _, value_column, count_column = _PORTFOLIO_PARTITIONS.get(asset_partition, (None, None, None))
    if value_column is None:
        raise ValueError("Unsupported portfolio asset partition")
    columns = ["snapshot_date", value_column]
    if count_column:
        columns.append(count_column)
    else:
        columns.extend(("cards_count", "sealed_count", "graded_count"))
    response = (
        supabase.table("user_portfolio_value_history")
        .select(",".join(columns))
        .eq("user_id", owner)
        .order("snapshot_date")
        .execute()
    )
    rows = response.data if response and isinstance(response.data, list) else []
    return adapt_portfolio_value_history(
        rows,
        authenticated_user_id=owner,
        asset_partition=asset_partition,
    )


def public_cache_payload_allowed(payload: Mapping[str, Any]) -> bool:
    """Fail closed for all personal payloads at a public-cache boundary."""
    source_type = payload.get("source", {}).get("sourceType") if isinstance(payload.get("source"), Mapping) else None
    return source_type not in {"portfolio", "wishlist"} and not str(payload.get("key", "")).startswith("private:")
