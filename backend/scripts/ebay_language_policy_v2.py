"""Frozen candidate LANGUAGE-v2: provider Korean/Chinese and OCR-v3 Japanese veto.

Research policy only; no production integration or network calls.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from backend.scripts.ebay_language_policy_v1 import (
    LANGUAGE_MATCH, LANGUAGE_MISMATCH, LANGUAGE_UNVERIFIED,
    extract_language_aspect, normalize_language_value,
)

METHOD_VERSION = "ebay_language_policy_v2"
SUPPORTED_PROVIDER_VOCABULARY = ("ENGLISH", "JAPANESE", "KOREAN", "CHINESE")
OCR_V3_MISMATCH = "JAPANESE_MISMATCH"


@dataclass(frozen=True)
class LanguageResultV2:
    language_state: str
    observed_language: Optional[str]
    ocr_v3_decision: str
    reason: str
    method_version: str = METHOD_VERSION

    @property
    def may_reject(self) -> bool:
        return self.language_state == LANGUAGE_MISMATCH


def evaluate(localized_aspects: Optional[Iterable[Mapping[str, Any]]],
             ocr_v3_decision: str = "UNVERIFIED") -> LanguageResultV2:
    observed = normalize_language_value(extract_language_aspect(localized_aspects))
    if observed in ("KOREAN", "CHINESE"):
        return LanguageResultV2(LANGUAGE_MISMATCH, observed, ocr_v3_decision,
                                "provider_korean_or_chinese_contradiction")
    if ocr_v3_decision == OCR_V3_MISMATCH:
        return LanguageResultV2(LANGUAGE_MISMATCH, observed, ocr_v3_decision,
                                "ocr_v3_japanese_contradiction")
    if observed == "ENGLISH":
        return LanguageResultV2(LANGUAGE_MATCH, observed, ocr_v3_decision,
                                "provider_english_supported")
    return LanguageResultV2(LANGUAGE_UNVERIFIED, observed, ocr_v3_decision,
                            "provider_not_authoritative_or_evidence_missing")


def policy_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
