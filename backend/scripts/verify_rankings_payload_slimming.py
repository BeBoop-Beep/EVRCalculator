"""Post-publication verification + same-window performance harness.

Run AFTER the user publishes with --commit. Reports publication identity, payload
size, and same-window PostgREST / service / HTTP latency over >=25 reads.

Usage:
    python verify_after_publish.py [BASE_URL] [N]
Defaults: http://127.0.0.1:8010, 25
"""
import json, statistics, sys, time, urllib.request
from copy import deepcopy

sys.path.insert(0, r"D:\EVRCalculator")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 25
LEGACY = ("publicRipContractV4", "publicRipContractV5", "publicRipContractV6")


def pct(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


def report(label, v):
    print(f"  {label:<26} p50={pct(v,0.5):>8.1f}ms  p95={pct(v,0.95):>8.1f}ms  min={min(v):>8.1f}ms  max={max(v):>8.1f}ms")


# --- 1. Publication identity + persisted payload size -----------------------
from backend.db.services.pokemon_public_snapshot_service import (
    _load_pokemon_explore_rankings_snapshot_row, service_read_client, create_short_timeout_service_client)
from backend.db.services.public_read_retry import run_public_read_with_retry

row = _load_pokemon_explore_rankings_snapshot_row(service_read_client)
payload = row["ranking_payload_json"]
meta = payload.get("meta") or {}
snap = meta.get("snapshot") or {}
targets = payload.get("targets") or []
persisted_bytes = len(json.dumps(payload, separators=(",", ":"), default=str))

print("=" * 74)
print("PUBLICATION IDENTITY")
print("=" * 74)
print(f"  updated_at            : {row.get('updated_at')}")
print(f"  publicationId         : {snap.get('publicationId') or meta.get('publicationId')}")
print(f"  marketDate            : {(meta.get('comparisonSnapshots') or {}).get('currentMarketDate')}")
print(f"  builtAt               : {meta.get('builtAt') or snap.get('builtAt')}")
print(f"  targets               : {len(targets)}")
print(f"  persisted payload     : {persisted_bytes:,} bytes")

leftover = {k: sum(1 for t in targets if k in t) for k in LEGACY}
print(f"  legacy contracts left : {leftover}")
print(f"  SLIM PROJECTION APPLIED: {'YES' if all(v == 0 for v in leftover.values()) else 'NO  <-- still full payload'}")

v7 = sum(1 for t in targets if isinstance(t.get("publicRipContractV7"), dict) and t["publicRipContractV7"])
print(f"  targets with publicRipContractV7: {v7}/{len(targets)}")

# --- 2. Same-window layer timing -------------------------------------------
print("\n" + "=" * 74)
print(f"SAME-WINDOW LATENCY (n={N})")
print("=" * 74)

pg, svc = [], []
for _ in range(3):
    run_public_read_with_retry(_load_pokemon_explore_rankings_snapshot_row,
        operation_name="verify", initial_client=service_read_client, client_factory=create_short_timeout_service_client)
for _ in range(N):
    t = time.perf_counter()
    r = run_public_read_with_retry(_load_pokemon_explore_rankings_snapshot_row,
        operation_name="verify", initial_client=service_read_client, client_factory=create_short_timeout_service_client)
    pg.append((time.perf_counter() - t) * 1000)
    t2 = time.perf_counter()
    p = r["ranking_payload_json"]
    tg = [x for x in (p.get("targets") or [])][:100]
    deepcopy({**p, "targets": tg})
    json.dumps(p, default=str)
    svc.append((time.perf_counter() - t2) * 1000 + pg[-1])
report("PostgREST call", pg)
report("service total (approx)", svc)

http, sizes = [], []
url = f"{BASE}/explore/rip-statistics/targets?limit=100"
try:
    for _ in range(3):
        urllib.request.urlopen(url, timeout=120).read()
    for _ in range(N):
        t = time.perf_counter()
        body = urllib.request.urlopen(url, timeout=120).read()
        http.append((time.perf_counter() - t) * 1000)
        sizes.append(len(body))
    report("HTTP endpoint", http)
    print(f"  {'response bytes':<26} {min(sizes):,} .. {max(sizes):,}")
except Exception as exc:
    print(f"  HTTP endpoint          : SKIPPED ({type(exc).__name__}: {exc}) — start a backend on {BASE}")

print("\n" + "=" * 74)
print("PRE-SLIM REFERENCE (different window; NOT a valid A/B comparison)")
print("=" * 74)
print("  PostgREST p50 ~713.9ms | service p50 ~766.4ms | HTTP p50 ~861ms | persisted ~2,796,448 B")
