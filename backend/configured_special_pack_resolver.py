from __future__ import annotations

from typing import Mapping, Optional, Sequence

import pandas as pd


def _normalize_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _normalize_rarity(value: object) -> str:
    return _normalize_text(value).lower()


def _has_card_number_column(df: pd.DataFrame) -> bool:
    return (
        "Card Number" in df.columns
        and df["Card Number"].astype(str).str.strip().replace("", pd.NA).notna().any()
    )


def _coerce_card_spec(card_spec: object) -> dict:
    if isinstance(card_spec, Mapping):
        return {
            "name": _normalize_text(card_spec.get("name")),
            "number": _normalize_text(card_spec.get("number")),
            "rarity": _normalize_text(card_spec.get("rarity")),
            "special_type": _normalize_text(card_spec.get("special_type")),
            "raw": dict(card_spec),
            "legacy_string": False,
        }

    spec_text = _normalize_text(card_spec)
    name = spec_text
    number = ""
    if " - " in spec_text:
        name, number = [part.strip() for part in spec_text.rsplit(" - ", 1)]

    return {
        "name": name,
        "number": number,
        "rarity": "",
        "special_type": "",
        "raw": card_spec,
        "legacy_string": True,
    }


def _narrow_candidates(
    candidates: pd.DataFrame,
    *,
    number: str,
    name: str,
    rarity: str,
    special_type: str,
) -> pd.DataFrame:
    narrowed = candidates
    if number and "Card Number" in narrowed.columns:
        narrowed = narrowed[narrowed["Card Number"].astype(str).str.strip() == number]

    if name and "Card Name" in narrowed.columns:
        narrowed = narrowed[narrowed["Card Name"].astype(str).str.strip() == name]

    if rarity and "Rarity" in narrowed.columns:
        narrowed = narrowed[narrowed["Rarity"].astype(str).str.strip().str.lower() == rarity.lower()]

    if special_type and "Special Type" in narrowed.columns:
        narrowed = narrowed[
            narrowed["Special Type"].astype(str).str.strip().str.lower() == special_type.lower()
        ]

    return narrowed


def _emit_unmatched(context_label: str, index: int, card_spec: dict, reason: str) -> None:
    print(
        f"[GOD_PACK_IDENTITY_UNMATCHED] {context_label} card[{index}] {card_spec['raw']!r} "
        f"could not be resolved: {reason}"
    )


def _emit_ambiguous(context_label: str, index: int, card_spec: dict, candidates: pd.DataFrame) -> None:
    candidate_preview = []
    for _, row in candidates.head(5).iterrows():
        candidate_preview.append(
            {
                "name": _normalize_text(row.get("Card Name")),
                "number": _normalize_text(row.get("Card Number")),
                "rarity": _normalize_text(row.get("Rarity")),
            }
        )

    print(
        f"[GOD_PACK_IDENTITY_AMBIGUOUS] {context_label} card[{index}] {card_spec['raw']!r} "
        f"matched {len(candidates)} rows. Using first row deterministically. "
        f"Candidates: {candidate_preview}"
    )


def _resolve_single_configured_row(
    card_spec: object,
    df: pd.DataFrame,
    *,
    context_label: str,
    index: int,
    has_card_number: bool,
) -> Optional[pd.DataFrame]:
    normalized_spec = _coerce_card_spec(card_spec)
    name = normalized_spec["name"]
    number = normalized_spec["number"]
    rarity = normalized_spec["rarity"]
    special_type = normalized_spec["special_type"]

    if not name and not number:
        _emit_unmatched(context_label, index, normalized_spec, "missing both name and number")
        return None

    if number and has_card_number:
        candidates = df[df["Card Number"].astype(str).str.strip() == number]
        if candidates.empty:
            _emit_unmatched(
                context_label,
                index,
                normalized_spec,
                f"no DataFrame row with Card Number '{number}'",
            )
            return None

        candidates = _narrow_candidates(
            candidates,
            number=number,
            name=name,
            rarity=rarity,
            special_type=special_type,
        )
        if candidates.empty:
            _emit_unmatched(
                context_label,
                index,
                normalized_spec,
                "configured fields did not match the Card Number row",
            )
            return None
        if len(candidates) > 1:
            _emit_ambiguous(context_label, index, normalized_spec, candidates)
        return candidates.iloc[[0]].copy()

    if number and not has_card_number:
        print(
            f"[GOD_PACK_IDENTITY_FALLBACK] {context_label} card[{index}] {normalized_spec['raw']!r} "
            "includes a card number but DataFrame has no usable 'Card Number' column. "
            "Falling back to exact name resolution."
        )

    if not name:
        _emit_unmatched(
            context_label,
            index,
            normalized_spec,
            "card number could not be used and no card name was provided",
        )
        return None

    if "Card Name" not in df.columns:
        _emit_unmatched(context_label, index, normalized_spec, "DataFrame has no 'Card Name' column")
        return None

    candidates = df[df["Card Name"].astype(str).str.strip() == name]
    if candidates.empty:
        _emit_unmatched(
            context_label,
            index,
            normalized_spec,
            f"no DataFrame row with Card Name '{name}'",
        )
        return None

    candidates = _narrow_candidates(
        candidates,
        number=number,
        name=name,
        rarity=rarity,
        special_type=special_type,
    )
    if candidates.empty:
        _emit_unmatched(
            context_label,
            index,
            normalized_spec,
            "configured fields did not match the Card Name row",
        )
        return None

    if len(candidates) > 1:
        _emit_ambiguous(context_label, index, normalized_spec, candidates)

    return candidates.iloc[[0]].copy()


def resolve_configured_god_pack_rows(
    card_specs: Sequence[object],
    df: pd.DataFrame,
    *,
    context_label: str,
) -> pd.DataFrame:
    """Resolve configured fixed-card specs into concrete dataframe rows.

    Supports structured config objects as the primary format:
    {"name": str, "number": str, "rarity": str, "special_type": str}
    and partial forms that omit any of those fields.
    Legacy string specs remain supported for backwards compatibility.
    """
    if df.empty or not card_specs:
        return df.iloc[0:0].copy()

    has_card_number = _has_card_number_column(df)
    matched_rows = []

    for index, card_spec in enumerate(card_specs):
        resolved = _resolve_single_configured_row(
            card_spec,
            df,
            context_label=context_label,
            index=index,
            has_card_number=has_card_number,
        )
        if resolved is not None and not resolved.empty:
            matched_rows.append(resolved)

    if not matched_rows:
        return df.iloc[0:0].copy()

    return pd.concat(matched_rows, ignore_index=True)