"""COMBINED-IDENTITY-v4: unchanged v3 combination with LANGUAGE-v2 input."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Optional

from backend.scripts.ebay_combined_identity_policy_v3 import CombinedResultV3, combine as combine_v3
from backend.scripts.ebay_language_policy_v2 import LanguageResultV2

METHOD_VERSION = "ebay_combined_identity_policy_v4"


def combine(text_state: str, image_state: str, language_result: LanguageResultV2,
            text_row_fields: Optional[Mapping[str, str]] = None) -> CombinedResultV3:
    result = combine_v3(text_state, image_state, language_result, text_row_fields)
    result.method_version = METHOD_VERSION
    if language_result.may_reject:
        result.reason = "language_v2_mismatch_hard_veto_before_tier_eligibility"
    return result


def policy_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
