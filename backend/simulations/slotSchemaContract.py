from __future__ import annotations

from typing import Any, Dict, Mapping


ALLOWED_SLOT_ROLES = frozenset(
    {
        "reverse_parallel",
        "reverse_subset",
        "rare_or_better",
        "holo_or_better",
        "guaranteed_holo_or_better",
        "fixed_outcome",
        "special_main",
        "special_subset_or_main",
    }
)

REQUIRED_PACK_STRUCTURE_FIELDS = frozenset({"common_slots", "uncommon_slots", "rare_family_slots"})
REQUIRED_RARE_FAMILY_SLOT_FIELDS = frozenset({"name", "role"})

OPTIONAL_RARE_FAMILY_SLOT_FIELDS: Dict[str, Any] = {
    "probability_attr": str,
    "probability_key": str,
    "default_outcome": str,
    "metadata": dict,
    "deterministic": bool,
}


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def get_pack_structure(config: Any) -> Dict[str, Any]:
    pack_structure = getattr(config, "PACK_STRUCTURE", None)
    if pack_structure is None:
        raise ValueError(
            "PACK_STRUCTURE is required for slot-schema configs. "
            "Define config.PACK_STRUCTURE as a dict."
        )
    if not isinstance(pack_structure, dict):
        raise ValueError(
            f"PACK_STRUCTURE must be a dict. Received type={type(pack_structure).__name__}."
        )
    return pack_structure


def validate_pack_structure(pack_structure: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(pack_structure, Mapping):
        raise ValueError(
            f"PACK_STRUCTURE must be a dict-like mapping. Received type={type(pack_structure).__name__}."
        )

    missing_top_level = [
        field for field in REQUIRED_PACK_STRUCTURE_FIELDS if field not in pack_structure
    ]
    if missing_top_level:
        raise ValueError(
            "PACK_STRUCTURE is missing required fields: "
            + ", ".join(sorted(missing_top_level))
        )

    common_slots = pack_structure["common_slots"]
    if not _is_non_negative_int(common_slots):
        raise ValueError(
            "PACK_STRUCTURE.common_slots must be a non-negative integer. "
            f"Received value={common_slots!r}."
        )

    uncommon_slots = pack_structure["uncommon_slots"]
    if not _is_non_negative_int(uncommon_slots):
        raise ValueError(
            "PACK_STRUCTURE.uncommon_slots must be a non-negative integer. "
            f"Received value={uncommon_slots!r}."
        )

    rare_family_slots = pack_structure["rare_family_slots"]
    if not isinstance(rare_family_slots, list):
        raise ValueError(
            "PACK_STRUCTURE.rare_family_slots must be a list of slot descriptors. "
            f"Received type={type(rare_family_slots).__name__}."
        )
    if len(rare_family_slots) == 0:
        raise ValueError(
            "PACK_STRUCTURE.rare_family_slots must contain at least one slot descriptor."
        )

    seen_slot_names = set()
    for idx, slot in enumerate(rare_family_slots):
        slot_path = f"PACK_STRUCTURE.rare_family_slots[{idx}]"
        if not isinstance(slot, dict):
            raise ValueError(
                f"{slot_path} must be a dict. Received type={type(slot).__name__}."
            )

        missing_slot_fields = [
            field for field in REQUIRED_RARE_FAMILY_SLOT_FIELDS if field not in slot
        ]
        if missing_slot_fields:
            raise ValueError(
                f"{slot_path} is missing required fields: {', '.join(sorted(missing_slot_fields))}."
            )

        slot_name = slot.get("name")
        if not isinstance(slot_name, str) or not slot_name.strip():
            raise ValueError(f"{slot_path}.name must be a non-empty string.")
        if slot_name in seen_slot_names:
            raise ValueError(
                "PACK_STRUCTURE.rare_family_slots contains duplicate slot names: "
                f"{slot_name!r}."
            )
        seen_slot_names.add(slot_name)

        role = slot.get("role")
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"{slot_path}.role must be a non-empty string.")
        if role not in ALLOWED_SLOT_ROLES:
            raise ValueError(
                f"{slot_path}.role={role!r} is not allowed. "
                f"Allowed roles: {sorted(ALLOWED_SLOT_ROLES)}."
            )

        for optional_field, expected_type in OPTIONAL_RARE_FAMILY_SLOT_FIELDS.items():
            if optional_field in slot and not isinstance(slot[optional_field], expected_type):
                raise ValueError(
                    f"{slot_path}.{optional_field} must be of type "
                    f"{expected_type.__name__}. Received type={type(slot[optional_field]).__name__}."
                )

        if "probability_key" in slot and "probability_attr" not in slot:
            raise ValueError(
                f"{slot_path}.probability_key requires probability_attr to also be provided."
            )

    return {
        "common_slots": common_slots,
        "uncommon_slots": uncommon_slots,
        "rare_family_slot_count": len(rare_family_slots),
        "total_modeled_slots": compute_total_modeled_slots(pack_structure),
    }


def compute_total_modeled_slots(pack_structure: Mapping[str, Any]) -> int:
    common_slots = pack_structure.get("common_slots")
    uncommon_slots = pack_structure.get("uncommon_slots")
    rare_family_slots = pack_structure.get("rare_family_slots")

    if not _is_non_negative_int(common_slots):
        raise ValueError(
            "Cannot compute total_modeled_slots: common_slots must be a non-negative integer."
        )
    if not _is_non_negative_int(uncommon_slots):
        raise ValueError(
            "Cannot compute total_modeled_slots: uncommon_slots must be a non-negative integer."
        )
    if not isinstance(rare_family_slots, list):
        raise ValueError(
            "Cannot compute total_modeled_slots: rare_family_slots must be a list."
        )

    return common_slots + uncommon_slots + len(rare_family_slots)


def validate_slot_schema_config(config: Any) -> Dict[str, Any]:
    pack_structure = get_pack_structure(config)
    return validate_pack_structure(pack_structure)
