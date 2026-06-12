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
                .select("id,pokedex_number,canonical_name,display_name,generation")
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

    def list_latest_desirability_source_snapshots(
        self,
        *,
        source_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        response = (
            self.client.table("pokemon_desirability_source_snapshots")
            .select("id,source_name,source_url,status,captured_at,notes")
            .eq("source_name", source_name)
            .order("captured_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response and response.data else []

    def list_desirability_scores_for_snapshot(
        self,
        snapshot_id: Any,
        *,
        scoring_version: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            query = (
                self.client.table("pokemon_desirability_scores")
                .select(
                    "id,pokemon_reference_id,source_name,snapshot_id,normalized_score,"
                    "normalized_rank,desirability_tier,confidence,scoring_version,created_at"
                )
                .eq("snapshot_id", snapshot_id)
                .range(start, start + page_size - 1)
            )
            if scoring_version:
                query = query.eq("scoring_version", scoring_version)
            response = query.execute()
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return rows

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

    def create_trend_snapshot(
        self,
        *,
        source_name: str,
        provider_name: str,
        geo: str,
        timeframe: str,
        window_role: str,
        query_type: str,
        anchor_term: str,
        raw_payload_json: Dict[str, Any],
        status: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "source_name": source_name,
            "provider_name": provider_name,
            "geo": geo,
            "timeframe": timeframe,
            "window_role": window_role,
            "query_type": query_type,
            "anchor_term": anchor_term,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "raw_payload_json": raw_payload_json,
            "notes": notes,
        }
        response = self.client.table("pokemon_trend_source_snapshots").insert(payload).execute()
        rows = response.data if response and response.data else []
        if not rows:
            raise RuntimeError("Trend snapshot insert returned no rows")
        return rows[0]

    def get_trend_snapshot(self, snapshot_id: Any) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("pokemon_trend_source_snapshots")
            .select("id,source_name,provider_name,geo,timeframe,window_role,query_type,anchor_term,status,notes,captured_at")
            .eq("id", snapshot_id)
            .limit(1)
            .execute()
        )
        rows = response.data if response and response.data else []
        return rows[0] if rows else None

    def update_trend_snapshot_status(self, snapshot_id: Any, status: str, notes: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"status": status}
        if notes is not None:
            payload["notes"] = notes
        (
            self.client.table("pokemon_trend_source_snapshots")
            .update(payload)
            .eq("id", snapshot_id)
            .execute()
        )

    def list_trend_source_rows_for_snapshot(self, snapshot_id: Any) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_trend_source_rows")
                .select(
                    "id,snapshot_id,source_name,pokemon_reference_id,pokedex_number,pokemon_name,query_term,"
                    "geo,timeframe,window_role,query_type,anchor_term,batch_key,raw_interest_value,"
                    "anchor_interest_value,relative_to_anchor,is_ambiguous,extraction_confidence,raw_row_json"
                )
                .eq("snapshot_id", snapshot_id)
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

    def list_latest_usable_trend_snapshots(
        self,
        *,
        source_name: str,
        provider_name: Optional[str],
        geo: str,
        timeframes: Iterable[str],
    ) -> Dict[str, Dict[str, Any]]:
        latest_by_timeframe: Dict[str, Dict[str, Any]] = {}
        for timeframe in timeframes:
            query = (
                self.client.table("pokemon_trend_source_snapshots")
                .select("id,source_name,provider_name,geo,timeframe,window_role,query_type,anchor_term,status,captured_at")
                .eq("source_name", source_name)
                .eq("geo", geo)
                .eq("timeframe", timeframe)
                .in_("status", ["captured_relative_search_interest", "captured_partial"])
                .order("captured_at", desc=True)
                .limit(10)
            )
            if provider_name:
                query = query.eq("provider_name", provider_name)
            response = query.execute()
            rows = response.data if response and response.data else []
            if rows:
                latest_by_timeframe[timeframe] = rows[0]
        return latest_by_timeframe

    def list_usable_trend_snapshots(
        self,
        *,
        source_name: str,
        provider_name: Optional[str],
        geo: str,
        timeframe: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("pokemon_trend_source_snapshots")
            .select("id,source_name,provider_name,geo,timeframe,window_role,query_type,anchor_term,status,captured_at")
            .eq("source_name", source_name)
            .eq("geo", geo)
            .eq("timeframe", timeframe)
            .in_("status", ["captured_relative_search_interest", "captured_partial"])
            .order("captured_at", desc=True)
            .limit(limit)
        )
        if provider_name:
            query = query.eq("provider_name", provider_name)
        response = query.execute()
        return response.data if response and response.data else []

    def list_valid_current_trend_source_snapshots(
        self,
        *,
        source_name: str,
        provider_name: str,
        geo: str,
        timeframe: str,
        window_role: str,
        query_type: str,
        status: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        response = (
            self.client.table("pokemon_trend_source_snapshots")
            .select("id,source_name,provider_name,geo,timeframe,window_role,query_type,anchor_term,status,captured_at")
            .eq("source_name", source_name)
            .eq("provider_name", provider_name)
            .eq("geo", geo)
            .eq("timeframe", timeframe)
            .eq("window_role", window_role)
            .eq("query_type", query_type)
            .eq("status", status)
            .order("captured_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data if response and response.data else []

    def insert_trend_source_rows(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [
            {
                "snapshot_id": row.get("snapshot_id"),
                "source_name": row.get("source_name"),
                "pokemon_reference_id": row.get("pokemon_reference_id"),
                "pokedex_number": row.get("pokedex_number"),
                "pokemon_name": row.get("pokemon_name"),
                "query_term": row.get("query_term"),
                "geo": row.get("geo"),
                "timeframe": row.get("timeframe"),
                "window_role": row.get("window_role"),
                "query_type": row.get("query_type"),
                "anchor_term": row.get("anchor_term"),
                "batch_key": row.get("batch_key"),
                "raw_interest_value": row.get("raw_interest_value"),
                "anchor_interest_value": row.get("anchor_interest_value"),
                "relative_to_anchor": row.get("relative_to_anchor"),
                "is_ambiguous": row.get("is_ambiguous"),
                "extraction_confidence": row.get("extraction_confidence"),
                "raw_row_json": row.get("raw_row_json") or {},
            }
            for row in rows
            if row.get("snapshot_id") is not None
        ]
        if not payload:
            return []
        response = self.client.table("pokemon_trend_source_rows").insert(payload).execute()
        return response.data if response and response.data else []

    def insert_trend_scores(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [
            {
                "pokemon_reference_id": row.get("pokemon_reference_id"),
                "source_name": row.get("source_name"),
                "score_name": row.get("score_name"),
                "relative_search_interest_score": row.get("score_value"),
                "normalized_rank": row.get("normalized_rank"),
                "confidence": row.get("confidence"),
                "scoring_version": row.get("scoring_version"),
                "primary_snapshot_id": row.get("primary_snapshot_id"),
                "contributing_snapshot_ids": row.get("contributing_snapshot_ids") or [],
                "score_components_json": row.get("score_components") or {},
            }
            for row in rows
            if row.get("pokemon_reference_id") is not None and row.get("primary_snapshot_id") is not None
        ]
        if not payload:
            return []
        response = self.client.table("pokemon_trend_scores").insert(payload).execute()
        return response.data if response and response.data else []

    def list_trend_score_keys(self, *, scoring_version: str) -> set[tuple[Any, str, str, tuple[Any, ...]]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_trend_scores")
                .select("pokemon_reference_id,score_name,scoring_version,contributing_snapshot_ids")
                .eq("scoring_version", scoring_version)
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return {
            (
                row.get("pokemon_reference_id"),
                str(row.get("score_name")),
                str(row.get("scoring_version")),
                tuple(row.get("contributing_snapshot_ids") or []),
            )
            for row in rows
            if row.get("pokemon_reference_id") is not None and row.get("score_name") is not None
        }

    def list_trend_scores_for_snapshot(
        self,
        *,
        primary_snapshot_id: Any,
        score_name: str,
        scoring_version: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_trend_scores")
                .select(
                    "id,pokemon_reference_id,source_name,score_name,relative_search_interest_score,"
                    "normalized_rank,confidence,scoring_version,primary_snapshot_id,"
                    "contributing_snapshot_ids,score_components_json,created_at"
                )
                .eq("primary_snapshot_id", primary_snapshot_id)
                .eq("score_name", score_name)
                .eq("scoring_version", scoring_version)
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return rows

    def list_composite_score_rows(
        self,
        *,
        fan_popularity_snapshot_id: Any,
        scoring_version: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            response = (
                self.client.table("pokemon_desirability_composite_scores")
                .select("id,pokemon_reference_id,fan_popularity_snapshot_id,scoring_version")
                .eq("fan_popularity_snapshot_id", fan_popularity_snapshot_id)
                .eq("scoring_version", scoring_version)
                .range(start, start + page_size - 1)
                .execute()
            )
            page_rows = response.data if response and response.data else []
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            start += page_size

        return rows

    def insert_desirability_composite_scores(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        updated_at = datetime.now(timezone.utc).isoformat()
        payload = [
            {
                "pokemon_reference_id": row.get("pokemon_reference_id"),
                "pokedex_number": row.get("pokedex_number"),
                "pokemon_name": row.get("pokemon_name"),
                "fan_popularity_score": row.get("fan_popularity_score"),
                "fan_popularity_rank": row.get("fan_popularity_rank"),
                "fan_popularity_snapshot_id": row.get("fan_popularity_snapshot_id"),
                "current_trend_score": row.get("current_trend_score"),
                "current_trend_rank": row.get("current_trend_rank"),
                "current_trend_snapshot_id": row.get("current_trend_snapshot_id"),
                "desirability_score": row.get("desirability_score"),
                "desirability_rank": row.get("desirability_rank"),
                "desirability_tier": row.get("desirability_tier"),
                "scoring_version": row.get("scoring_version"),
                "score_components_json": row.get("score_components_json") or {},
                "updated_at": updated_at,
            }
            for row in rows
            if row.get("pokemon_reference_id") is not None
        ]
        if not payload:
            return []

        fan_snapshot_ids = {row.get("fan_popularity_snapshot_id") for row in payload}
        scoring_versions = {row.get("scoring_version") for row in payload}
        existing_by_reference: Dict[Any, Dict[str, Any]] = {}
        if len(fan_snapshot_ids) == 1 and len(scoring_versions) == 1:
            existing_rows = self.list_composite_score_rows(
                fan_popularity_snapshot_id=next(iter(fan_snapshot_ids)),
                scoring_version=str(next(iter(scoring_versions))),
            )
            existing_by_reference = {
                row.get("pokemon_reference_id"): row
                for row in existing_rows
                if row.get("pokemon_reference_id") is not None
            }

        written_rows: List[Dict[str, Any]] = []
        rows_to_insert: List[Dict[str, Any]] = []
        for row in payload:
            existing = existing_by_reference.get(row.get("pokemon_reference_id"))
            if existing and existing.get("id") is not None:
                response = (
                    self.client.table("pokemon_desirability_composite_scores")
                    .update(row)
                    .eq("id", existing["id"])
                    .execute()
                )
                written_rows.extend(response.data if response and response.data else [row])
            else:
                rows_to_insert.append(row)

        if rows_to_insert:
            response = self.client.table("pokemon_desirability_composite_scores").insert(rows_to_insert).execute()
            written_rows.extend(response.data if response and response.data else rows_to_insert)

        return written_rows
