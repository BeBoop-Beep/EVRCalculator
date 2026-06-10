from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.desirability.pokeapi import build_reference_upsert_payload


class PokemonDesirabilityRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_pokemon_references(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_reference")
                .select("id,pokedex_number,canonical_name,display_name")
                .order("pokedex_number")
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return rows

    def list_source_rows_for_snapshot(self, snapshot_id: Any) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_desirability_source_rows")
                .select(
                    "id,snapshot_id,source_name,pokemon_reference_id,pokedex_number,pokemon_name,"
                    "raw_rank,raw_vote_count,raw_score,raw_tier,source_detail_url,"
                    "extraction_confidence,raw_row_json"
                )
                .eq("snapshot_id", snapshot_id)
                .order("raw_rank")
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return rows

    def update_source_row_reference(self, row_id: Any, pokemon_reference_id: Any, pokedex_number: Any) -> None:
        (
            self.client.table("pokemon_desirability_source_rows")
            .update(
                {
                    "pokemon_reference_id": pokemon_reference_id,
                    "pokedex_number": pokedex_number,
                }
            )
            .eq("id", row_id)
            .execute()
        )

    def list_score_reference_ids(self, snapshot_id: Any, scoring_version: str) -> set[Any]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_desirability_scores")
                .select("pokemon_reference_id")
                .eq("snapshot_id", snapshot_id)
                .eq("scoring_version", scoring_version)
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return {row.get("pokemon_reference_id") for row in rows if row.get("pokemon_reference_id") is not None}

    def upsert_pokemon_references(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = build_reference_upsert_payload(rows)
        if not payload:
            return []

        response = (
            self.client.table("pokemon_reference")
            .upsert(payload, on_conflict="pokedex_number")
            .execute()
        )
        return response.data if response and response.data else []

    def create_snapshot(
        self,
        *,
        source_name: str,
        source_url: str,
        capture_method: str,
        raw_payload_json: Dict[str, Any],
        status: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "source_name": source_name,
            "source_url": source_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "capture_method": capture_method,
            "raw_payload_json": raw_payload_json,
            "status": status,
            "notes": notes,
        }
        response = (
            self.client.table("pokemon_desirability_source_snapshots")
            .insert(payload)
            .execute()
        )
        rows = response.data if response and response.data else []
        if not rows:
            raise RuntimeError("Snapshot insert returned no rows")
        return rows[0]

    def update_snapshot_status(self, snapshot_id: Any, status: str, notes: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"status": status}
        if notes is not None:
            payload["notes"] = notes
        (
            self.client.table("pokemon_desirability_source_snapshots")
            .update(payload)
            .eq("id", snapshot_id)
            .execute()
        )

    def insert_source_rows(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = list(rows)
        if not payload:
            return []
        response = self.client.table("pokemon_desirability_source_rows").insert(payload).execute()
        return response.data if response and response.data else []

    def insert_scores(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [
            {
                "pokemon_reference_id": row.get("pokemon_reference_id"),
                "source_name": row.get("source_name"),
                "snapshot_id": row.get("snapshot_id"),
                "normalized_score": row.get("normalized_score"),
                "normalized_rank": row.get("normalized_rank"),
                "desirability_tier": row.get("desirability_tier"),
                "confidence": row.get("confidence"),
                "scoring_version": row.get("scoring_version"),
            }
            for row in rows
            if row.get("pokemon_reference_id") is not None
        ]
        if not payload:
            return []
        response = self.client.table("pokemon_desirability_scores").insert(payload).execute()
        return response.data if response and response.data else []
