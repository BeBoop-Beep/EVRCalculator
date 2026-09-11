"""Validation helpers for the price-independent Treatment Preference T2 study."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable, Mapping

SOURCE_CLASSES = frozenset({"A", "B", "C", "D", "E"})
CONFIDENCE_STATES = frozenset({"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"})
MARKET_FIELDS = frozenset(
    {
        "price",
        "market_price",
        "sales_volume",
        "grading_population",
        "listing_scarcity",
        "pull_scarcity",
        "rarity_rank",
        "set_value",
        "price_premium",
    }
)


def validate_source(source: Mapping[str, Any]) -> None:
    """Enforce the auditable source fields and the A-E classification vocabulary."""
    required = {
        "id", "classification", "url", "publicationDate", "sampleSize",
        "participantPopulation", "priceShown", "rarityShown",
        "treatmentLabelsKnown", "withinEra", "subjectChanged", "artistChanged",
        "responseLevel", "reproducible", "commercialReuse", "biasRisks",
        "usableForAuthority", "reason",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError(f"source missing required fields: {missing}")
    if source["classification"] not in SOURCE_CLASSES:
        raise ValueError("unknown source classification")
    if source["usableForAuthority"] and source["classification"] != "A":
        raise ValueError("only direct collector preference can construct authority")
    if source["usableForAuthority"] and source["priceShown"] is not False:
        raise ValueError("authority evidence must be demonstrably price blind")


def assert_price_independent(payload: Any, *, path: str = "root") -> None:
    """Reject market-derived fields from preference-construction payloads."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in MARKET_FIELDS:
                raise ValueError(f"market field prohibited at {path}.{key}")
            assert_price_independent(value, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_price_independent(value, path=f"{path}[{index}]")


def connected_components(nodes: Iterable[str], edges: Iterable[Mapping[str, Any]]) -> list[list[str]]:
    """Return graph components using only accepted direct preference edges."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    node_set = set(nodes)
    for edge in edges:
        if not edge.get("acceptedDirectPreference"):
            continue
        left, right = edge["treatmentA"], edge["treatmentB"]
        node_set.update((left, right))
        adjacency[left].add(right)
        adjacency[right].add(left)
    components: list[list[str]] = []
    unseen = set(node_set)
    while unseen:
        start = min(unseen)
        queue = deque([start])
        component: list[str] = []
        unseen.remove(start)
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in sorted(adjacency[node]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return sorted(components)


def market_validation_eligible(manifest: Mapping[str, Any]) -> bool:
    """Market validation is legal only after a supported, frozen candidate exists."""
    return bool(
        manifest.get("candidateFrozen")
        and manifest.get("authorityType") != "D_NO_SCORE"
        and manifest.get("directPreferenceEdges", 0) > 0
        and manifest.get("verdict")
        in {"TREATMENT_PREFERENCE_SUPPORTED", "TREATMENT_PREFERENCE_SUPPORTED_ERA_LOCAL_ONLY"}
    )
