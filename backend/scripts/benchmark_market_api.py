"""Small production-like Market endpoint latency/size/RSS benchmark.

Usage: python -m backend.scripts.benchmark_market_api --base-url http://localhost:8000 --requests 20

Pass --selected-set-id to include the selected-set 7D movers path used by the
desktop master/detail surface.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

GLOBAL_ENDPOINTS = ("/explore/set-value-market", "/explore/card-market-movers?limit=30")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--selected-set-id")
    args = parser.parse_args()
    endpoints = list(GLOBAL_ENDPOINTS)
    if args.selected_set_id:
        endpoints.append(f"/sets/{args.selected_set_id}/market/movers?window=7D&limit=10")
    report = []
    for endpoint in endpoints:
        durations, sizes, errors = [], [], 0
        for _ in range(max(1, args.requests)):
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(args.base_url.rstrip("/") + endpoint, timeout=20) as response:
                    body = response.read()
                    if response.status >= 400:
                        errors += 1
                    sizes.append(len(body))
            except (urllib.error.URLError, TimeoutError):
                errors += 1
                sizes.append(0)
            durations.append((time.perf_counter() - started) * 1000)
        report.append({"endpoint": endpoint, "requests": len(durations), "p50Ms": round(statistics.median(durations), 2), "p95Ms": round(percentile(durations, .95), 2), "maxMs": round(max(durations), 2), "meanResponseBytes": round(statistics.mean(sizes)), "errors": errors})
    print(json.dumps(report, indent=2))
    return 1 if any(row["errors"] for row in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
