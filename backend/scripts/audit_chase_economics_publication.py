"""Fail-closed audit for the dedicated Target Chase Economics snapshots."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


def _dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _finite_json(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, float) and not math.isfinite(item):
            return False
    return True


@dataclass
class ChaseSetAudit:
    set_id: str
    calculation_run_id: Optional[str]
    card_count: int = 0
    eligible_card_count: int = 0
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass
class ChaseAuditReport:
    market_date: Optional[str]
    rows: List[ChaseSetAudit] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.error is None and bool(self.rows) and all(row.passed for row in self.rows)

    @property
    def failures(self) -> List[str]:
        return [f"{row.set_id}: {failure}" for row in self.rows for failure in row.failures]

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "passed": self.passed, "failures": self.failures}


def _all_rows(client: Any, table: str, select: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page_size = 1000
    for start in range(0, 100_000, page_size):
        batch = list(client.table(table).select(select).range(start, start + page_size - 1).execute().data or [])
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
    raise RuntimeError(f"{table} audit read exceeded 100000 rows")


def run_audit(client: Any, *, market_date: Optional[str]) -> ChaseAuditReport:
    report = ChaseAuditReport(market_date=market_date)
    try:
        authority_rows = _all_rows(
            client, "explore_rip_statistics_latest", "set_id,calculation_run_id"
        )
        snapshot_ids = [{"set_id": set_id} for set_id in sorted({
            str(row["set_id"]) for row in authority_rows if row.get("set_id")
        })]
        pages = []
        snapshots = {}
        for identity in snapshot_ids:
            set_id = str(identity["set_id"])
            snapshot_rows = list(
                client.table("pokemon_set_chase_economics_snapshot_latest")
                .select("set_id,calculation_run_id,payload_json,card_count,as_of,updated_at")
                .eq("set_id", set_id).execute().data or []
            )
            page_rows = list(
                client.table("pokemon_set_page_snapshot_latest")
                .select("set_id,payload_json").eq("set_id", set_id).execute().data or []
            )
            if snapshot_rows:
                snapshots[set_id] = snapshot_rows[0]
            pages.extend(page_rows)
    except Exception as exc:  # a missing/unreadable audit source is never current
        report.error = f"chase publication surface read failed: {exc}"
        return report

    authorities: Dict[str, str] = {}
    for page in pages:
        payload = page.get("payload_json") if isinstance(page.get("payload_json"), dict) else {}
        rip = payload.get("ripDecision") if isinstance(payload, dict) else None
        run_id = rip.get("sourceCalculationRunId") if isinstance(rip, dict) else None
        if page.get("set_id") and run_id:
            authorities[str(page["set_id"])] = str(run_id)

    if not authorities:
        report.error = "no supported current set-page calculation authorities found"
        return report

    for set_id, run_id in sorted(authorities.items()):
        source = snapshots.get(set_id)
        row = ChaseSetAudit(set_id=set_id, calculation_run_id=run_id)
        report.rows.append(row)
        if source is None:
            row.failures.append("missing Chase snapshot")
            continue
        payload = source.get("payload_json") if isinstance(source.get("payload_json"), dict) else {}
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        row.card_count = int(source.get("card_count") or 0)
        row.eligible_card_count = int(payload.get("eligibleCardCount") or 0)
        if str(source.get("calculation_run_id") or "") != run_id:
            row.failures.append("snapshot calculation_run_id disagrees with set-page authority")
        if payload.get("sourceCalculationRunId") != run_id:
            row.failures.append("payload sourceCalculationRunId disagrees with set-page authority")
        if row.card_count != len(cards):
            row.failures.append("card_count disagrees with cards array length")
        if row.eligible_card_count < row.card_count:
            row.failures.append("eligibleCardCount is less than card_count")
        if not _finite_json(payload):
            row.failures.append("contract JSON is not finite/serializable")
        for card in cards:
            if card.get("currentTargetMarketPrice") is not None and not card.get("currentPriceAsOf"):
                row.failures.append(f"card {card.get('cardVariantId')} is missing current-price provenance")

        try:
            products = list(
                client.table("simulation_sealed_product_results")
                .select("sealed_product_id,product_market_cost,price_as_of,price_source,updated_at")
                .eq("calculation_run_id", run_id)
                .execute().data or []
            )
        except Exception as exc:
            row.failures.append(f"source product rows unreadable: {exc}")
            continue
        snapshot_at = _dt(source.get("updated_at"))
        by_id = {str(p.get("sealed_product_id")): p for p in products}
        represented = {
            str(p.get("sealedProductId")): p
            for card in cards for p in (card.get("products") or [])
            if p.get("sealedProductId")
        }
        for product_id, product in by_id.items():
            block = represented.get(product_id)
            if block is None and cards:
                row.failures.append(f"source product {product_id} is absent from Chase")
                continue
            if block is not None:
                if float(block.get("productPrice") or 0) != float(product.get("product_market_cost") or 0):
                    row.failures.append(f"product {product_id} price is stale")
                if str(block.get("productPriceAsOf") or "") != str(product.get("price_as_of") or ""):
                    row.failures.append(f"product {product_id} price provenance is stale")
            updated_at = _dt(product.get("updated_at"))
            if snapshot_at and updated_at and updated_at > snapshot_at:
                row.failures.append(f"product {product_id} was updated after the Chase snapshot")
            if market_date and str(product.get("price_as_of") or "") < str(market_date):
                row.failures.append(f"product {product_id} market date predates promoted market date")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    from backend.db.clients.supabase_client import supabase
    report = run_audit(supabase, market_date=args.market_date)
    print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
