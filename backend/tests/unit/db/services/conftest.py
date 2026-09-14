"""Focused test isolation for service modules that gained additive readers.

The long-standing sealed-product detail suite uses a deliberately tiny fake
Supabase client and asserts the exact tables needed by its original Product RIP
concerns. Best-Open Price has its own focused tests; keep the legacy suite from
silently turning into an incomplete fake of the new private persistence store.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_best_open_from_legacy_product_detail_suite(monkeypatch, request):
    path = getattr(request.node, "path", None)
    if path is None or path.name != "test_pokemon_sealed_product_detail_service.py":
        return

    from backend.db.services import pokemon_sealed_product_detail_service as service

    monkeypatch.setattr(
        service,
        "load_best_open_price_product",
        lambda *_args, **_kwargs: {
            "available": False,
            "reason": "no_published_snapshot",
            "row": None,
        },
    )
