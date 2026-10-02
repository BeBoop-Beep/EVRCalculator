"""FV-S3 append-only shadow ledger (interface, in-memory reference, dormant DB adapter).

Semantics, identical for every implementation:
* append-only: no update or delete method exists;
* idempotent retry: re-appending the same publication key with the same
  ``content_fingerprint`` is a no-op (the FIRST row, incl. its ``generated_at``, wins);
* a different fingerprint under an existing key is a hard conflict, never an overwrite;
* an outcome is unique per (publication_id, horizon_days) with the same idempotent/conflict rule;
* outcomes and components can only reference an existing publication.

The Supabase adapter is enabled only after the reviewed production migration has been applied. Publication header + members use one atomic database RPC.
Components and outcomes carry persistence fingerprints so exact retries are no-ops and
changed retries fail closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

WRITE_ENABLED = True


class ShadowLedgerError(RuntimeError):
    pass


class ShadowLedgerConflict(ShadowLedgerError):
    pass


class ShadowLedgerDormant(ShadowLedgerError):
    pass


def _pub_key(pub: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (pub["rule_version"], pub["canonical_card_id"], pub["evaluation_date"], pub["information_cutoff"])


class InMemoryShadowLedger:
    """Reference implementation; also the deterministic test double."""

    def __init__(self) -> None:
        self._publications: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._by_id: dict[str, dict[str, Any]] = {}
        self._components: dict[str, dict[str, Any]] = {}
        self._outcomes: dict[tuple[str, int], dict[str, Any]] = {}

    # -- anchor publications -------------------------------------------------
    def append_publication(self, publication: Mapping[str, Any]) -> str:
        key = _pub_key(publication)
        existing = self._publications.get(key)
        if existing is not None:
            if existing["content_fingerprint"] == publication["content_fingerprint"]:
                return "IDEMPOTENT_NOOP"
            raise ShadowLedgerConflict(f"SHADOW_PUBLICATION_CONFLICT key={key}")
        stored = copy.deepcopy(dict(publication))
        self._publications[key] = stored
        self._by_id[stored["publication_id"]] = stored
        return "INSERTED"

    def get_publication(self, publication_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._by_id[publication_id])

    def publications(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._publications[k]) for k in sorted(self._publications)]

    # -- component observations (separate from the anchor) -----------------------
    def append_component(self, observation: Mapping[str, Any]) -> str:
        pid = observation["publication_id"]
        if pid not in self._by_id:
            raise ShadowLedgerError("component references an unknown publication")
        existing = self._components.get(pid)
        if existing is not None:
            if existing == dict(observation):
                return "IDEMPOTENT_NOOP"
            raise ShadowLedgerConflict(f"SHADOW_COMPONENT_CONFLICT publication={pid}")
        self._components[pid] = copy.deepcopy(dict(observation))
        return "INSERTED"

    # -- evaluation outcomes -------------------------------------------------------
    def append_outcome(self, outcome: Mapping[str, Any]) -> str:
        pid, horizon = outcome["publication_id"], int(outcome["horizon_days"])
        if pid not in self._by_id:
            raise ShadowLedgerError("outcome references an unknown publication")
        key = (pid, horizon)
        existing = self._outcomes.get(key)
        if existing is not None:
            if existing == dict(outcome):
                return "IDEMPOTENT_NOOP"
            raise ShadowLedgerConflict(f"SHADOW_OUTCOME_CONFLICT key={key}")
        self._outcomes[key] = copy.deepcopy(dict(outcome))
        return "INSERTED"

    def outcomes(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._outcomes[k]) for k in sorted(self._outcomes)]

    # Deliberately absent: update_*, delete_*, upsert_* .


def _canonical_fingerprint(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SupabaseShadowLedger:
    """Insert-only adapter for the reviewed, applied research-only shadow tables."""

    PUBLICATIONS = "fair_value_shadow_anchor_publications_v1"
    MEMBERS = "fair_value_shadow_anchor_members_v1"
    COMPONENTS = "fair_value_shadow_component_observations_v1"
    OUTCOMES = "fair_value_shadow_evaluation_outcomes_v1"
    PUBLISH_RPC = "publish_fair_value_shadow_anchor_v1"

    def __init__(self, client: Any) -> None:
        self.c = client

    def _require_enabled(self) -> None:
        if not WRITE_ENABLED:
            raise ShadowLedgerDormant("FV_SHADOW_LEDGER_DORMANT: production shadow writes are not enabled")

    @staticmethod
    def _one(rows: Any) -> dict[str, Any] | None:
        data = getattr(rows, "data", None) or []
        return dict(data[0]) if data else None

    def append_publication(self, publication: Mapping[str, Any]) -> str:
        self._require_enabled()
        header = {k: v for k, v in publication.items() if k != "members"}
        result = self.c.rpc(
            self.PUBLISH_RPC,
            {"p_publication": header, "p_members": list(publication.get("members") or [])},
        ).execute()
        value = getattr(result, "data", None)
        if isinstance(value, list) and value:
            value = value[0]
        if isinstance(value, dict):
            value = next(iter(value.values()), None)
        status = str(value or "")
        if status not in {"INSERTED", "IDEMPOTENT_NOOP"}:
            raise ShadowLedgerError(f"unexpected publication RPC result: {status!r}")
        return status

    def _append_fingerprinted(
        self,
        *,
        table: str,
        key_filters: Mapping[str, Any],
        record: Mapping[str, Any],
        conflict_name: str,
    ) -> str:
        self._require_enabled()
        fingerprint = _canonical_fingerprint(record)
        query = self.c.table(table).select("content_fingerprint")
        for key, value in key_filters.items():
            query = query.eq(key, value)
        existing = self._one(query.limit(1).execute())
        if existing is not None:
            if existing.get("content_fingerprint") == fingerprint:
                return "IDEMPOTENT_NOOP"
            raise ShadowLedgerConflict(conflict_name)
        payload = {**dict(record), "content_fingerprint": fingerprint}
        self.c.table(table).insert(payload).execute()
        return "INSERTED"

    def append_outcome(self, outcome: Mapping[str, Any]) -> str:
        self._require_enabled()
        return self._append_fingerprinted(
            table=self.OUTCOMES,
            key_filters={
                "publication_id": outcome["publication_id"],
                "horizon_days": int(outcome["horizon_days"]),
            },
            record=outcome,
            conflict_name=(
                f"SHADOW_OUTCOME_CONFLICT publication={outcome['publication_id']} "
                f"horizon={outcome['horizon_days']}"
            ),
        )

    def append_component(self, observation: Mapping[str, Any]) -> str:
        self._require_enabled()
        return self._append_fingerprinted(
            table=self.COMPONENTS,
            key_filters={"publication_id": observation["publication_id"]},
            record=observation,
            conflict_name=f"SHADOW_COMPONENT_CONFLICT publication={observation['publication_id']}",
        )
