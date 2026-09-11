"""Triage provider boundary. AI is intentionally disabled in Prompt 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass(frozen=True)
class TriageDecision:
    status: str
    summary: str
    metadata: Dict[str, Any]


class TriageProvider(Protocol):
    def triage(self, evidence: Dict[str, Any]) -> TriageDecision: ...


class DisabledTriageProvider:
    def triage(self, evidence: Dict[str, Any]) -> TriageDecision:
        return TriageDecision(
            status="disabled",
            summary="AI triage is disabled for the Sentinel kernel.",
            metadata={"provider": "disabled", "request_made": False},
        )
