"""Chase Accessibility V1 - live Set RIP / set-page read-path wiring.

Proves ``get_pokemon_set_insights_critical_snapshot_payload`` projects the
SAME fields ``chase_accessibility_service.project_chase_accessibility``
produces, read from the same persisted table - never a second computation,
never a fabricated value when the read fails or the row is missing.
"""

from __future__ import annotations

import pytest

from backend.db.services import pokemon_public_snapshot_service as svc
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION


def _fake_row():
    return {
        "set_id": "set-1",
        "calculation_run_id": "run-1",
        "market_date": "2026-08-31",
        "accessibility": 0.00234,
        "chase_depth": 12.5,
        "mapped_hc_mass": 1.0,
        "status": "ready",
        "status_reason": None,
        "version": CHASE_ACCESSIBILITY_VERSION,
    }


def _patch_snapshot_row(monkeypatch, payload_json):
    monkeypatch.setattr(
        svc,
        "_fetch_insights_snapshot_row",
        lambda set_id: (
            {"payload_json": payload_json, "updated_at": "2026-08-31T00:00:00+00:00"},
            {"id": "set-1"},
            "set-1",
            1.0,
            0.0,
        ),
    )
    monkeypatch.setattr(svc, "_resolve_insights_set_identity", lambda row, set_row, resolved: {"id": resolved})


def test_critical_payload_projects_chase_accessibility_fields_when_ready(monkeypatch):
    _patch_snapshot_row(monkeypatch, {"summary": {}, "rip": {}})
    monkeypatch.setattr(svc, "create_service_role_client", lambda: object())
    monkeypatch.setattr(svc, "read_chase_accessibility_snapshot", lambda *, set_id, client: svc.project_chase_accessibility(_fake_row()))

    payload = svc.get_pokemon_set_insights_critical_snapshot_payload("set-1")

    assert payload["chaseAccessibility"] == 0.00234
    assert payload["chaseAccessibilityPct"] == pytest.approx(0.234)
    assert payload["chaseAccessibilityStatus"] == "ready"
    assert payload["chaseAccessibilityVersion"] == CHASE_ACCESSIBILITY_VERSION
    assert payload["chaseDepth"] == 12.5
    assert payload["mappedHcMass"] == 1.0


def test_critical_payload_reports_null_never_zero_when_unavailable(monkeypatch):
    _patch_snapshot_row(monkeypatch, {"summary": {}, "rip": {}})
    monkeypatch.setattr(svc, "create_service_role_client", lambda: object())
    monkeypatch.setattr(svc, "read_chase_accessibility_snapshot", lambda *, set_id, client: svc.project_chase_accessibility(None))

    payload = svc.get_pokemon_set_insights_critical_snapshot_payload("set-1")

    assert payload["chaseAccessibility"] is None
    assert payload["chaseAccessibility"] != 0
    assert payload["chaseAccessibilityPct"] is None


def test_critical_payload_degrades_to_unavailable_on_read_failure_never_fabricates(monkeypatch):
    _patch_snapshot_row(monkeypatch, {"summary": {}, "rip": {}})
    monkeypatch.setattr(svc, "create_service_role_client", lambda: object())

    def _boom(*, set_id, client):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(svc, "read_chase_accessibility_snapshot", _boom)

    payload = svc.get_pokemon_set_insights_critical_snapshot_payload("set-1")

    assert payload["chaseAccessibility"] is None
    assert payload["chaseAccessibilityPct"] is None
