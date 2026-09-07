"""Run the exact-source SQL contract checks without unittest's run() dispatch.

The fixture class intentionally exposes a class-level SQL helper named `run`.
Calling its test methods directly preserves that helper while still exercising
all assertions. This runner exists only for the isolated SQL contract suite.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tests.test_price_storage_v2_real_source_sql import RealSourceContractTests


def main() -> int:
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")
    cls = RealSourceContractTests
    cls.setUpClass()
    names = sorted(
        name for name, value in inspect.getmembers(cls, predicate=inspect.isfunction)
        if name.startswith("test_")
    )
    if not names:
        raise AssertionError("no real-source SQL contract checks discovered")
    for name in names:
        case = cls(methodName=name)
        getattr(case, name)()
        print(f"{name}: ok", flush=True)
    print(f"REAL_SOURCE_SQL_CONTRACTS={len(names)} passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
