"""Public, blinded collection endpoints for Treatment Direct Preference V1."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.db.clients.supabase_client import service_read_client
from backend.domain.pokemon.treatment_preference_v1 import (
    TreatmentPreferenceV1Error,
    claim_block,
    submit_block,
)

router = APIRouter(prefix="/research/treatment-preference-v1", tags=["research"])


class TreatmentPreferenceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairId: str = Field(min_length=24, max_length=24)
    response: Literal["LEFT", "RIGHT", "TIE"]


class TreatmentPreferenceSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessionId: UUID
    blockId: str = Field(min_length=24, max_length=24)
    claimToken: UUID
    answers: list[TreatmentPreferenceAnswer] = Field(min_length=12, max_length=12)


def _error(exc: TreatmentPreferenceV1Error) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers={"Cache-Control": "private, no-store"},
        content={"message": exc.message, "code": exc.code},
    )


@router.get("/block")
def get_treatment_preference_v1_block(
    session_id: UUID = Query(..., alias="sessionId"),
):
    try:
        payload = claim_block(service_read_client, str(session_id))
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "private, no-store"},
        )
    except TreatmentPreferenceV1Error as exc:
        return _error(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "TREATMENT_PREFERENCE_COLLECTION_UNAVAILABLE",
                "message": "The preference study is temporarily unavailable.",
            },
        ) from exc


@router.post("/submit")
def post_treatment_preference_v1_submit(body: TreatmentPreferenceSubmitRequest):
    try:
        payload = submit_block(
            service_read_client,
            session_id=str(body.sessionId),
            block_id=body.blockId,
            claim_token=str(body.claimToken),
            answers=[row.model_dump() for row in body.answers],
        )
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "private, no-store"},
        )
    except TreatmentPreferenceV1Error as exc:
        return _error(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "TREATMENT_PREFERENCE_SUBMISSION_UNAVAILABLE",
                "message": "The preference responses could not be recorded.",
            },
        ) from exc
