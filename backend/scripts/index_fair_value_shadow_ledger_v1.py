"""FV-S3 append-only shadow ledger (interface, in-memory reference, dormant DB adapter).

Semantics, identical for every implementation:
* append-only: no update or delete method exists;
* idempotent retry: re-appending the same publication key with the same
  ``content_fingerprint`` is a no-op (the FIRST row, incl. its ``generated_at``, wins);
* a different fingerprint under an existing key is a hard conflict, never an overwrite;
* an outcome is unique per (publication_id, horizon_days) with the same idempotent/conflict rule;
* outcomes and components can only reference an existing publication.

The Supabase adapter is DORMANT (``WRITE_ENABLED = False``) and targets tables from the
UNAPPLIED proposal in docs/research/index_fair_value/fv_s3/migration_proposal_unapplied/.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

WRITE_ENABLED = False


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


class SupabaseShadowLedger:
    """Insert-only adapter for the proposed tables. Dormant: refuses every write."""

    PUBLICATIONS = "fair_value_shadow_anchor_publications_v1"
    MEMBERS = "fair_value_shadow_anchor_members_v1"
    COMPONENTS = "fair_value_shadow_component_observations_v1"
    OUTCOMES = "fair_value_shadow_evaluation_outcomes_v1"

    def __init__(self, client: Any) -> None:
        self.c = client

    def _require_enabled(self) -> None:
        if not WRITE_ENABLED:
            raise ShadowLedgerDormant("FV_SHADOW_LEDGER_DORMANT: the proposed tables are not applied")

    def append_publication(self, publication: Mapping[str, Any]) -> str:
        self._require_enabled()
        header = {k: v for k, v in publication.items() if k != "members"}
        rows = (self.c.table(self.PUBLICATIONS).select("publication_id,content_fingerprint")
                .eq("rule_version", publication["rule_version"])
                .eq("canonical_card_id", publication["canonical_card_id"])
                .eq("evaluation_date", publication["evaluation_date"])
                .eq("information_cutoff", publication["information_cutoff"]).execute().data or [])
        if rows:
            if rows[0]["content_fingerprint"] == publication["content_fingerprint"]:
                return "IDEMPOTENT_NOOP"
            raise ShadowLedgerConflict("SHADOW_PUBLICATION_CONFLICT")
        self.c.table(self.PUBLICATIONS).insert(header).execute()
        members = [{"publication_id": publication["publication_id"], **m} for m in publication["members"]]
        if members:
            self.c.table(self.MEMBERS).insert(members).execute()
        return "INSERTED"

    def append_outcome(self, outcome: Mapping[str, Any]) -> str:
        self._require_enabled()
        self.c.table(self.OUTCOMES).insert(dict(outcome)).execute()
        return "INSERTED"

    def append_component(self, observation: Mapping[str, Any]) -> str:
        self._require_enabled()
        self.c.table(self.COMPONENTS).insert(dict(observation)).execute()
        return "INSERTED"
