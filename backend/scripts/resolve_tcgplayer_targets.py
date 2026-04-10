import argparse
import hashlib
import json
import random
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_bootstrap_report.json")
DEFAULT_RESOLUTION_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_tcgplayer_resolution_report.json")
DEFAULT_READINESS_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_readiness_after_tcgplayer_resolution.json")
DEFAULT_CACHE_PATH = Path("backend/constants/tcg/pokemon/tcgplayer_resolution_cache.json")

CONFIG_PATH_COMPAT_MAP: Dict[str, str] = {
    # Locked reference-era compatibility: bootstrap keys differ from local filenames.
    "scarletAndViolet": "backend/constants/tcg/pokemon/scarletAndVioletEra/scarletAndVioletBase.py",
    "151": "backend/constants/tcg/pokemon/scarletAndVioletEra/scarletAndViolet151.py",
    "scarletAndVioletEnergies": "backend/constants/tcg/pokemon/scarletAndVioletEra/scarletAndVioletBase.py",
    "scarletAndVioletBlackStarPromos": "backend/constants/tcg/pokemon/scarletAndVioletEra/scarletAndVioletBase.py",
}

MANUAL_CONFIRMED_SET_ID_OVERRIDES: Dict[str, int] = {
    # Confirmed valid mapping from targeted research.
    "heartgoldAndSoulSilver": 1402,
    # Era-consistent naming corrections confirmed from resolver report (same_id_ratio=1.00).
    # TCGplayer uses a different label format; set_ids are unambiguous from validation data.
    "base": 604,                      # "Base" -> "Base Set" on TCGplayer
    "hsUnleashed": 1399,              # "HS\u2014Unleashed" -> "Unleashed" on TCGplayer
    "hsUndaunted": 1403,              # "HS\u2014Undaunted" -> "Undaunted" on TCGplayer
    "hsTriumphant": 1381,             # "HS\u2014Triumphant" -> "Triumphant" on TCGplayer
    "breakthrough": 1661,             # "BREAKthrough" -> "XY - BREAKthrough" on TCGplayer
    "breakpoint": 1701,               # "BREAKpoint" -> "XY - BREAKpoint" on TCGplayer
    "flashfire": 1464,                # "Flashfire" -> "XY - Flashfire" on TCGplayer
    "bwBlackStarPromos": 1407,        # "BW Black Star Promos" -> "Black and White Promos"
    "hgssBlackStarPromos": 1453,      # "HGSS Black Star Promos" -> "HGSS Promos"
    "nintendoBlackStarPromos": 1423,  # "Nintendo Black Star Promos" -> "Nintendo Promos"
    "smBlackStarPromos": 1861,        # "SM Black Star Promos" -> "SM Promos"
    "swordAndShield": 2585,           # "Sword & Shield" -> "SWSH01: Sword & Shield Base Set"
    "pokMonRumble": 1433,             # "Pokemon Rumble" -> "Rumble" on TCGplayer
}

# Forced TCGplayer setName search labels for sets where global aggregation returns the wrong
# candidate. Used in place of the normal aggregation-based candidate selection.
# Only applied when the canonical_key matches and the set has not been manually confirmed.
EXCEPTION_SEARCH_LABELS: Dict[str, str] = {
    # XY era base set (TCGplayer may call it "XY Base Set" rather than plain "XY").
    "xy": "XY Base Set",
    # XY Evolutions: global aggregation incorrectly returns Prismatic Evolutions.
    "evolutions": "XY - Evolutions",
    # Sun & Moon base set: TCGplayer uses abbreviated era label "SM Base Set".
    "sunAndMoon": "SM Base Set",
    # Promo sets: TCGplayer drops "Black Star" and shortens era acronyms.
    # Pattern confirmed from HGSS->HGSS Promos, SM->SM Promos, and BW->Black and White Promos.
    "wizardsBlackStarPromos": "WotC Promos",
    "dpBlackStarPromos": "DP Promos",
    # SWSH promos: try full era name following BW pattern (Black and White Promos).
    "swshBlackStarPromos": "Sword & Shield Promos",
    "xyBlackStarPromos": "XY Promos",
    # McDonald's 2021: 25th anniversary specific label.
    "mcdonaldSCollection2021": "McDonald's 25th Anniversary Promos",
    # Futsal and Best of Game: low-confidence; will stay manual if no exact match.
    "pokMonFutsalCollection": "Pokémon Futsal Collection",
    "bestOfGame": "Best of Game Promos",
}

TCGPLAYER_SEARCH_URL = "https://mp-search-api.tcgplayer.com/v1/search/request"

MAX_REQUESTS_PER_SECOND = 1
MAX_REQUESTS_PER_MINUTE = 30
MAX_RETRIES = 3
BACKOFF_SECONDS = 2
TIMEOUT = 10
MIN_THROTTLE_DELAY = 0.8
MAX_THROTTLE_DELAY = 1.6
RATE_LIMIT_PAUSE_MIN = 30
RATE_LIMIT_PAUSE_MAX = 60


@dataclass
class ConfigTargets:
    card_details_url: Optional[str]
    sealed_details_url: Optional[str]
    price_endpoints_count: int
    set_name: Optional[str]


@dataclass
class ResolverCache:
    path: Path
    data: Dict[str, Any]
    dirty: bool = False


class ThrottledRequester:
    """
    Single-threaded request gateway for all outbound resolver traffic.
    """

    def __init__(self, session: requests.Session):
        self.session = session
        self.last_request_ts = 0.0
        self.minute_window: deque = deque()

    def _enforce_minute_window(self) -> None:
        now = time.time()
        while self.minute_window and now - self.minute_window[0] >= 60:
            self.minute_window.popleft()

        if len(self.minute_window) >= MAX_REQUESTS_PER_MINUTE:
            wait_seconds = max(60 - (now - self.minute_window[0]), 0)
            print(f"[resolver] minute cap reached ({MAX_REQUESTS_PER_MINUTE}/min), pausing {wait_seconds:.1f}s")
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            now = time.time()
            while self.minute_window and now - self.minute_window[0] >= 60:
                self.minute_window.popleft()

    def _throttle(self, request_label: str) -> None:
        self._enforce_minute_window()

        now = time.time()
        elapsed = now - self.last_request_ts if self.last_request_ts else 10.0
        jitter_delay = random.uniform(MIN_THROTTLE_DELAY, MAX_THROTTLE_DELAY)
        required_delay = max(jitter_delay, max((1.0 / MAX_REQUESTS_PER_SECOND) - elapsed, 0.0))

        if required_delay > 0:
            time.sleep(required_delay)

        self.last_request_ts = time.time()
        self.minute_window.append(self.last_request_ts)
        print(f"[resolver] throttled request: {request_label}")

    def safe_request(self, method: str, url: str, request_label: str, **kwargs: Any) -> Optional[requests.Response]:
        timeout = kwargs.pop("timeout", TIMEOUT)

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle(request_label)
            try:
                response = self.session.request(method=method, url=url, timeout=timeout, **kwargs)

                if response.status_code == 429 or "rate limit" in response.text.lower():
                    pause_seconds = random.uniform(RATE_LIMIT_PAUSE_MIN, RATE_LIMIT_PAUSE_MAX)
                    print(
                        f"[resolver] rate-limit detected ({response.status_code}); "
                        f"pause {pause_seconds:.1f}s before retry"
                    )
                    time.sleep(pause_seconds)
                    if attempt < MAX_RETRIES:
                        print(f"[resolver] retry attempt {attempt + 1} after 429")
                        continue
                    return None

                if 500 <= response.status_code <= 599:
                    if attempt < MAX_RETRIES:
                        backoff = BACKOFF_SECONDS * attempt
                        print(
                            f"[resolver] retry attempt {attempt + 1} after {response.status_code}; "
                            f"backoff {backoff}s"
                        )
                        time.sleep(backoff)
                        continue
                    return None

                return response
            except requests.RequestException as exc:
                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_SECONDS * attempt
                    print(
                        f"[resolver] retry attempt {attempt + 1} after connection error: {exc}; "
                        f"backoff {backoff}s"
                    )
                    time.sleep(backoff)
                    continue
                return None

        return None


def normalize_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("—", "-").replace("–", "-")
    value = value.replace("’", "'").replace("‘", "'")
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_for_family(value: str) -> str:
    value = normalize_name(value)
    # Family checks should ignore common glue words to avoid punctuation-format false negatives.
    value = re.sub(r"\b(set|collection|the|tcg|pokemon)\b", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def clean_tcg_set_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^[A-Z0-9]+:\s*", "", value)
    return value.strip()


def token_set(value: str) -> set:
    return set(normalize_name(value).split())


def promo_era_token(value: str) -> Optional[str]:
    norm = normalize_for_family(value)
    era_patterns = [
        ("wotc", ["wizards", "wotc"]),
        ("bw", ["black and white", "bw"]),
        ("dp", ["diamond and pearl", "dp"]),
        ("hgss", ["heartgold soulsilver", "hgss"]),
        ("nintendo", ["nintendo"]),
        ("sm", ["sun and moon", "sm"]),
        ("sv", ["scarlet and violet", "sv"]),
        ("swsh", ["sword and shield", "swsh"]),
        ("xy", ["xy"]),
    ]
    for token, patterns in era_patterns:
        if any(pat in norm for pat in patterns):
            return token
    return None


def is_promo_family(value: str) -> bool:
    norm = normalize_for_family(value)
    return "promo" in norm


def is_trainer_kit_family(value: str) -> bool:
    norm = normalize_for_family(value)
    return "trainer kit" in norm


def resolve_config_file_path(row: Dict[str, Any]) -> Path:
    raw_path = row.get("local_config_file_path") or ""
    config_file = Path(raw_path)
    if config_file.exists():
        return config_file

    canonical = row.get("canonical_key") or ""
    mapped = CONFIG_PATH_COMPAT_MAP.get(canonical)
    if mapped:
        mapped_path = Path(mapped)
        if mapped_path.exists():
            return mapped_path

    return config_file


def token_overlap_score(a: str, b: str) -> float:
    ta = token_set(a)
    tb = token_set(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    return intersection / max(len(ta), len(tb))


def parse_python_literal(value: str) -> Any:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return eval(value, {"__builtins__": {}}, {})
    except Exception:
        return None


def parse_assignment_text(py_text: str, name: str) -> Optional[str]:
    pattern = rf"^\s*{re.escape(name)}\s*=\s*(.+)$"
    m = re.search(pattern, py_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_existing_targets(py_text: str) -> ConfigTargets:
    card_raw = parse_assignment_text(py_text, "CARD_DETAILS_URL")
    sealed_raw = parse_assignment_text(py_text, "SEALED_DETAILS_URL")
    price_raw = parse_assignment_text(py_text, "PRICE_ENDPOINTS")
    set_name_raw = parse_assignment_text(py_text, "SET_NAME")

    card_value = parse_python_literal(card_raw) if card_raw else None
    sealed_value = parse_python_literal(sealed_raw) if sealed_raw else None
    price_value = parse_python_literal(price_raw) if price_raw else {}
    set_name_value = parse_python_literal(set_name_raw) if set_name_raw else None

    if not isinstance(price_value, dict):
        price_value = {}

    return ConfigTargets(
        card_details_url=card_value if isinstance(card_value, str) and card_value.strip() else None,
        sealed_details_url=sealed_value if isinstance(sealed_value, str) and sealed_value.strip() else None,
        price_endpoints_count=len(price_value),
        set_name=set_name_value if isinstance(set_name_value, str) else None,
    )


def load_cache(path: Path) -> ResolverCache:
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                parsed.setdefault("set_resolutions", {})
                return ResolverCache(path=path, data=parsed)
        except json.JSONDecodeError:
            pass

    return ResolverCache(path=path, data={"set_resolutions": {}})


def save_cache(cache: ResolverCache) -> None:
    if not cache.dirty:
        return
    cache.path.parent.mkdir(parents=True, exist_ok=True)
    cache.path.write_text(json.dumps(cache.data, indent=2), encoding="utf-8", newline="\n")
    print(f"[resolver] cache write: {cache.path}")
    cache.dirty = False


def cache_key_for_row(row: Dict[str, Any], set_name: str) -> str:
    canonical = row.get("canonical_key") or ""
    if canonical:
        return canonical
    return normalize_name(set_name)


def search_cache_key(query: str, body: Dict[str, Any]) -> str:
    body_serialized = json.dumps(body, sort_keys=True)
    body_hash = hashlib.sha256(body_serialized.encode("utf-8")).hexdigest()
    return f"q={query}|body={body_hash}"


def build_search_body(query_set_name: Optional[str] = None, size: int = 24) -> Dict[str, Any]:
    term_filters: Dict[str, Any] = {
        "productLineName": ["Pokemon"],
        "productTypeName": ["Cards"],
    }
    if query_set_name:
        term_filters["setName"] = [query_set_name]

    return {
        "algorithm": "sales_dismax",
        "from": 0,
        "size": size,
        "filters": {"term": term_filters},
        "listingSearch": {
            "context": {"cart": {}},
            "filters": {
                "term": {
                    "sellerStatus": "Live",
                    "channelId": 0,
                }
            },
        },
        "settings": {"useFuzzySearch": True},
        "sort": {},
        "context": {"cart": {}, "shippingCountry": "US"},
    }


def fetch_global_set_aggregations(requester: ThrottledRequester, query_cache: Dict[str, Any]) -> List[Dict[str, Any]]:
    body = build_search_body(size=0)
    payload = safe_post_search(requester=requester, query="", body=body, cache=query_cache)
    results = (payload.get("results") or [{}])[0]
    return (results.get("aggregations") or {}).get("setName") or []


def safe_post_search(requester: ThrottledRequester, query: str, body: Dict[str, Any], cache: Dict[str, Any]) -> Dict[str, Any]:
    key = search_cache_key(query=query, body=body)
    if key in cache:
        return cache[key]

    params = {"q": query, "isList": "true"}
    response = requester.safe_request(
        method="POST",
        url=TCGPLAYER_SEARCH_URL,
        request_label="tcgplayer search",
        params=params,
        json=body,
    )
    if not response or response.status_code != 200:
        return {}

    payload = response.json()
    cache[key] = payload
    return payload


def pick_candidate_set_name(aggregations: List[Dict[str, Any]], target_name: str) -> Tuple[Optional[str], float, str]:
    if not aggregations:
        return None, 0.0, "No setName aggregations returned"

    target_norm = normalize_name(target_name)

    best_value = None
    best_score = 0.0
    best_note = "No candidate"

    for agg in aggregations:
        value = agg.get("value")
        if not value:
            continue

        candidate_clean = clean_tcg_set_name(value)
        candidate_norm = normalize_name(candidate_clean)

        if candidate_norm == target_norm:
            return value, 1.0, "Exact normalized set-name match"

        overlap = token_overlap_score(candidate_clean, target_name)
        contains = 1.0 if target_norm and (target_norm in candidate_norm or candidate_norm in target_norm) else 0.0
        score = (0.7 * overlap) + (0.3 * contains)

        if score > best_score:
            best_score = score
            best_value = value
            best_note = f"Best normalized overlap score={score:.3f}"

    return best_value, best_score, best_note


def validate_candidate_set_id(
    requester: ThrottledRequester,
    query_cache: Dict[str, Any],
    search_query: str,
    set_name_filter: str,
    expected_set_name: str,
    exception_label: Optional[str] = None,
) -> Tuple[Optional[int], float, str]:
    body = build_search_body(query_set_name=set_name_filter, size=24)
    candidate_queries = [
        search_query,
        normalize_name(search_query),
        set_name_filter,
        clean_tcg_set_name(set_name_filter),
    ]

    items: List[Dict[str, Any]] = []
    for query in candidate_queries:
        query = (query or "").strip()
        if not query:
            continue
        payload = safe_post_search(requester, query=query, body=body, cache=query_cache)
        results = (payload.get("results") or [{}])[0]
        items = results.get("results") or []
        if items:
            break

    if not items:
        return None, 0.0, "Validation returned no product results"

    set_ids = [int(item.get("setId")) for item in items if item.get("setId") is not None]
    set_names = [item.get("setName", "") for item in items if item.get("setName")]
    if not set_ids:
        return None, 0.0, "Validation results missing setId"

    dominant_set_id = max(set(set_ids), key=set_ids.count)
    same_id_ratio = set_ids.count(dominant_set_id) / len(set_ids)

    dominant_set_names = [name for name, sid in zip(set_names, set_ids) if sid == dominant_set_id]
    dominant_name = dominant_set_names[0] if dominant_set_names else ""

    clean_dominant_name = clean_tcg_set_name(dominant_name)
    overlap = token_overlap_score(clean_dominant_name, expected_set_name)
    name_match = normalize_name(clean_dominant_name) == normalize_name(expected_set_name)

    confidence = (0.6 * same_id_ratio) + (0.4 * overlap)
    if name_match:
        confidence = max(confidence, 0.95)

    targeted_rule_note = ""
    if same_id_ratio >= 0.90:
        expected_family_norm = normalize_for_family(expected_set_name)
        dominant_family_norm = normalize_for_family(clean_dominant_name)

        # Punctuation/Unicode normalization-safe acceptance for near-equivalent names.
        if overlap >= 0.65 and (
            expected_family_norm in dominant_family_norm
            or dominant_family_norm in expected_family_norm
        ):
            confidence = max(confidence, 0.92)
            targeted_rule_note = "normalized-equivalence acceptance"

        # Promo-family acceptance only when era-consistent.
        if is_promo_family(expected_set_name) and is_promo_family(clean_dominant_name):
            expected_era = promo_era_token(expected_set_name)
            dominant_era = promo_era_token(clean_dominant_name)
            if expected_era and dominant_era and expected_era == dominant_era and overlap >= 0.45:
                confidence = max(confidence, 0.92)
                targeted_rule_note = "promo-family era-consistent acceptance"

        # Trainer kit family often combines two local variants under one TCGplayer set.
        if is_trainer_kit_family(expected_set_name) and is_trainer_kit_family(clean_dominant_name) and overlap >= 0.55:
            confidence = max(confidence, 0.92)
            targeted_rule_note = "trainer-kit family acceptance"

        # Exception-label deterministic acceptance: if we searched with a known forced label and
        # TCGplayer returned that exact label as the dominant result, accept it.
        if exception_label and not targeted_rule_note:
            clean_exception = clean_tcg_set_name(exception_label)
            if normalize_name(clean_dominant_name) == normalize_name(clean_exception):
                confidence = max(confidence, 0.92)
                targeted_rule_note = "exception-label deterministic acceptance"

    note = (
        f"dominant_set_id={dominant_set_id}, same_id_ratio={same_id_ratio:.2f}, "
        f"overlap={overlap:.2f}, dominant_name='{dominant_name}'"
    )
    if targeted_rule_note:
        note = f"{note}; {targeted_rule_note}"
    return dominant_set_id, confidence, note


def build_priceguide_urls(set_id: int) -> Tuple[str, str]:
    card_url = f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}/cards/?rows=5000&productTypeID=1"
    sealed_url = f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}/cards/?rows=5000&productTypeID=25"
    return card_url, sealed_url


def replace_assignment_line(py_text: str, assignment_name: str, new_value_repr: str) -> Tuple[str, bool]:
    pattern = rf"^(\s*{re.escape(assignment_name)}\s*=\s*)(.+)$"
    m = re.search(pattern, py_text, re.MULTILINE)
    if not m:
        return py_text, False
    replacement = f"{m.group(1)}{new_value_repr}"
    start, end = m.span()
    return py_text[:start] + replacement + py_text[end:], True


def summarize_readiness(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    total = len(rows)
    ready = 0
    for row in rows:
        if row.get("has_card_details_url") or row.get("has_sealed_details_url"):
            ready += 1
    return {
        "total_sets_inspected": total,
        "ready_for_daily_scrape": ready,
        "not_ready": total - ready,
    }


def resolve_single_set(
    requester: ThrottledRequester,
    row: Dict[str, Any],
    apply_changes: bool,
    min_confidence: float,
    global_set_aggregations: List[Dict[str, Any]],
    cache: ResolverCache,
    query_cache: Dict[str, Any],
) -> Dict[str, Any]:
    config_file = resolve_config_file_path(row)
    if not config_file.exists():
        return {
            "resolution_status": "unresolved",
            "confidence": 0.0,
            "validation_notes": "Config file missing",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": 0,
            "existing_card_details_url": None,
            "existing_sealed_details_url": None,
            "existing_price_endpoints_count": 0,
            "notes": "Missing config file",
        }

    py_text = config_file.read_text(encoding="utf-8")
    existing = parse_existing_targets(py_text)

    has_existing_ready = bool(existing.card_details_url or existing.sealed_details_url)
    if has_existing_ready:
        return {
            "resolution_status": "already_ready",
            "confidence": 1.0,
            "validation_notes": "Existing authored target(s) preserved",
            "wrote_changes": False,
            "manual_review_required": False,
            "resolved_card_details_url": existing.card_details_url,
            "resolved_sealed_details_url": existing.sealed_details_url,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "No overwrite performed",
        }

    target_set_name = row.get("set_name") or existing.set_name or row.get("canonical_key") or ""
    row_cache_key = cache_key_for_row(row, target_set_name)

    manual_override_set_id = MANUAL_CONFIRMED_SET_ID_OVERRIDES.get(row.get("canonical_key") or "")
    if manual_override_set_id:
        resolved_card_url, resolved_sealed_url = build_priceguide_urls(manual_override_set_id)
        wrote_changes = False
        patched_text = py_text
        if not existing.card_details_url:
            patched_text, changed = replace_assignment_line(patched_text, "CARD_DETAILS_URL", repr(resolved_card_url))
            wrote_changes = wrote_changes or changed
        if not existing.sealed_details_url:
            patched_text, changed = replace_assignment_line(patched_text, "SEALED_DETAILS_URL", repr(resolved_sealed_url))
            wrote_changes = wrote_changes or changed

        if apply_changes and wrote_changes and patched_text != py_text:
            config_file.write_text(patched_text, encoding="utf-8", newline="\n")

        set_cache = cache.data.setdefault("set_resolutions", {})
        set_cache[row_cache_key] = {
            "set_id": manual_override_set_id,
            "confidence": 1.0,
            "validation_notes": "manual confirmed override",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        cache.dirty = True

        return {
            "resolution_status": "resolved_automatically",
            "confidence": 1.0,
            "validation_notes": "manual confirmed override",
            "wrote_changes": wrote_changes and apply_changes,
            "manual_review_required": False,
            "resolved_card_details_url": existing.card_details_url or resolved_card_url,
            "resolved_sealed_details_url": existing.sealed_details_url or resolved_sealed_url,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": f"Resolved from manual override setId={manual_override_set_id}",
        }

    cached_resolution = (cache.data.get("set_resolutions") or {}).get(row_cache_key)
    if cached_resolution and isinstance(cached_resolution, dict):
        cached_set_id = cached_resolution.get("set_id")
        if isinstance(cached_set_id, int):
            print(f"[resolver] cache hit for set: {target_set_name}")
            resolved_card_url, resolved_sealed_url = build_priceguide_urls(cached_set_id)

            wrote_changes = False
            patched_text = py_text
            if not existing.card_details_url:
                patched_text, changed = replace_assignment_line(patched_text, "CARD_DETAILS_URL", repr(resolved_card_url))
                wrote_changes = wrote_changes or changed
            if not existing.sealed_details_url:
                patched_text, changed = replace_assignment_line(patched_text, "SEALED_DETAILS_URL", repr(resolved_sealed_url))
                wrote_changes = wrote_changes or changed

            if apply_changes and wrote_changes and patched_text != py_text:
                config_file.write_text(patched_text, encoding="utf-8", newline="\n")

            return {
                "resolution_status": "resolved_automatically",
                "confidence": round(float(cached_resolution.get("confidence", 1.0)), 3),
                "validation_notes": cached_resolution.get("validation_notes", "resolved from cache"),
                "wrote_changes": wrote_changes and apply_changes,
                "manual_review_required": False,
                "resolved_card_details_url": existing.card_details_url or resolved_card_url,
                "resolved_sealed_details_url": existing.sealed_details_url or resolved_sealed_url,
                "resolved_price_endpoints_count": existing.price_endpoints_count,
                "existing_card_details_url": existing.card_details_url,
                "existing_sealed_details_url": existing.sealed_details_url,
                "existing_price_endpoints_count": existing.price_endpoints_count,
                "notes": f"Resolved from cache setId={cached_set_id}",
            }

    canonical_key = row.get("canonical_key") or ""
    exception_label = EXCEPTION_SEARCH_LABELS.get(canonical_key)

    best_candidate_name: Optional[str] = None
    best_candidate_score = 0.0
    best_candidate_note = ""

    if exception_label:
        # Bypass aggregation: go directly to validation with the known forced TCGplayer label.
        print(f"[resolver] exception label override for '{target_set_name}': '{exception_label}'")
        best_candidate_name = exception_label
        best_candidate_score = 0.5  # placeholder; real score is set during validation
        best_candidate_note = f"exception_label='{exception_label}'"
    else:
        candidate_name, score, note = pick_candidate_set_name(global_set_aggregations, target_set_name)
        if candidate_name and score > best_candidate_score:
            best_candidate_name = candidate_name
            best_candidate_score = score
            best_candidate_note = f"global_aggregation {note}"

        if best_candidate_score < 1.0:
            staged_queries = [
                target_set_name,
                normalize_name(target_set_name),
                f"pokemon {target_set_name}",
                canonical_key,
            ]
            for query in staged_queries:
                query = (query or "").strip()
                if not query:
                    continue
                body = build_search_body(size=0)
                payload = safe_post_search(requester, query=query, body=body, cache=query_cache)
                results = (payload.get("results") or [{}])[0]
                aggregations = (results.get("aggregations") or {}).get("setName") or []
                candidate_name, score, note = pick_candidate_set_name(aggregations, target_set_name)
                if candidate_name and score > best_candidate_score:
                    best_candidate_name = candidate_name
                    best_candidate_score = score
                    best_candidate_note = f"stage_query='{query}' {note}"
                if score >= 1.0:
                    break

    if not best_candidate_name:
        return {
            "resolution_status": "unresolved",
            "confidence": 0.0,
            "validation_notes": "No setName candidate found via search aggregations",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "Aggregation matching failed",
        }

    set_id, confidence, validation_note = validate_candidate_set_id(
        requester=requester,
        query_cache=query_cache,
        search_query=target_set_name,
        set_name_filter=best_candidate_name,
        expected_set_name=target_set_name,
        exception_label=exception_label,
    )

    if not set_id or confidence < min_confidence:
        return {
            "resolution_status": "validation_failed",
            "confidence": round(confidence, 3),
            "validation_notes": f"{best_candidate_note}; {validation_note}",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "Confidence threshold not met",
        }

    resolved_card_url, resolved_sealed_url = build_priceguide_urls(set_id)

    wrote_changes = False
    patched_text = py_text

    if not existing.card_details_url:
        patched_text, changed = replace_assignment_line(patched_text, "CARD_DETAILS_URL", repr(resolved_card_url))
        wrote_changes = wrote_changes or changed
    if not existing.sealed_details_url:
        patched_text, changed = replace_assignment_line(patched_text, "SEALED_DETAILS_URL", repr(resolved_sealed_url))
        wrote_changes = wrote_changes or changed

    if apply_changes and wrote_changes and patched_text != py_text:
        config_file.write_text(patched_text, encoding="utf-8", newline="\n")

    set_cache = cache.data.setdefault("set_resolutions", {})
    set_cache[row_cache_key] = {
        "set_id": set_id,
        "confidence": round(confidence, 3),
        "validation_notes": f"{best_candidate_note}; {validation_note}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.dirty = True
    print(f"[resolver] cache write for set: {target_set_name}")

    status = "resolved_automatically"
    if (existing.card_details_url and not existing.sealed_details_url) or (existing.sealed_details_url and not existing.card_details_url):
        status = "partially_resolved"

    return {
        "resolution_status": status,
        "confidence": round(confidence, 3),
        "validation_notes": f"{best_candidate_note}; {validation_note}",
        "wrote_changes": wrote_changes and apply_changes,
        "manual_review_required": False,
        "resolved_card_details_url": existing.card_details_url or resolved_card_url,
        "resolved_sealed_details_url": existing.sealed_details_url or resolved_sealed_url,
        "resolved_price_endpoints_count": existing.price_endpoints_count,
        "existing_card_details_url": existing.card_details_url,
        "existing_sealed_details_url": existing.sealed_details_url,
        "existing_price_endpoints_count": existing.price_endpoints_count,
        "notes": f"Resolved setId={set_id}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve missing Pokemon TCGplayer scrape targets deterministically")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Path to pokemon bootstrap report JSON")
    parser.add_argument("--apply", action="store_true", help="Apply validated updates to set config files")
    parser.add_argument("--min-confidence", type=float, default=0.90, help="Minimum confidence to write URLs")
    parser.add_argument("--max-sets", type=int, default=0, help="Optional cap on sets processed from unresolved queue")
    parser.add_argument("--resolution-report", default=str(DEFAULT_RESOLUTION_REPORT_PATH), help="Output resolution report path")
    parser.add_argument("--readiness-report", default=str(DEFAULT_READINESS_REPORT_PATH), help="Output readiness summary report path")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE_PATH), help="Persistent resolver cache file path")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sets = payload.get("sets", [])

    unresolved_queue = [
        row
        for row in sets
        if (not row.get("ready_for_daily_scrape"))
        or (not row.get("has_card_details_url"))
        or (not row.get("has_sealed_details_url"))
    ]

    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    })
    requester = ThrottledRequester(session=session)

    cache = load_cache(Path(args.cache_path))
    query_cache: Dict[str, Any] = {}

    before_ready = sum(1 for row in sets if row.get("ready_for_daily_scrape"))

    if args.max_sets and args.max_sets > 0:
        unresolved_queue = unresolved_queue[: args.max_sets]

    global_set_aggregations = fetch_global_set_aggregations(requester, query_cache)

    resolution_rows: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}
    wrote_count = 0

    for row in unresolved_queue:
        resolution = resolve_single_set(
            requester=requester,
            row=row,
            apply_changes=args.apply,
            min_confidence=args.min_confidence,
            global_set_aggregations=global_set_aggregations,
            cache=cache,
            query_cache=query_cache,
        )

        status = resolution["resolution_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if resolution.get("wrote_changes"):
            wrote_count += 1

        config_path = row.get("local_config_file_path")
        config_targets_after = ConfigTargets(None, None, 0, None)
        if config_path and Path(config_path).exists():
            config_text_after = Path(config_path).read_text(encoding="utf-8")
            config_targets_after = parse_existing_targets(config_text_after)

        resolution_rows.append(
            {
                "era": row.get("era_name"),
                "canonical_key": row.get("canonical_key"),
                "set_name": row.get("set_name"),
                "config_file_path": row.get("local_config_file_path"),
                "existing_card_details_url": resolution.get("existing_card_details_url"),
                "resolved_card_details_url": resolution.get("resolved_card_details_url"),
                "existing_sealed_details_url": resolution.get("existing_sealed_details_url"),
                "resolved_sealed_details_url": resolution.get("resolved_sealed_details_url"),
                "existing_price_endpoints_count": resolution.get("existing_price_endpoints_count", 0),
                "resolved_price_endpoints_count": resolution.get("resolved_price_endpoints_count", 0),
                "resolution_status": resolution.get("resolution_status"),
                "confidence": resolution.get("confidence", 0.0),
                "validation_notes": resolution.get("validation_notes", ""),
                "wrote_changes": resolution.get("wrote_changes", False),
                "manual_review_required": resolution.get("manual_review_required", False),
                "notes": resolution.get("notes", ""),
                "post_apply_has_card_details_url": bool(config_targets_after.card_details_url),
                "post_apply_has_sealed_details_url": bool(config_targets_after.sealed_details_url),
            }
        )

    refreshed_sets: List[Dict[str, Any]] = []
    for row in sets:
        updated = dict(row)
        config_path = row.get("local_config_file_path")
        if config_path and Path(config_path).exists():
            config_text = Path(config_path).read_text(encoding="utf-8")
            targets = parse_existing_targets(config_text)
            updated["has_card_details_url"] = bool(targets.card_details_url)
            updated["has_sealed_details_url"] = bool(targets.sealed_details_url)
            updated["has_price_endpoints"] = targets.price_endpoints_count > 0
            updated["ready_for_daily_scrape"] = bool(targets.card_details_url or targets.sealed_details_url)
        refreshed_sets.append(updated)

    after_ready = sum(1 for row in refreshed_sets if row.get("ready_for_daily_scrape"))
    readiness_summary = summarize_readiness(refreshed_sets)

    readiness_report = {
        "summary": {
            "source_report": str(report_path).replace("\\", "/"),
            "apply_mode": bool(args.apply),
            "sets_inspected": len(sets),
            "sets_in_resolution_queue": len(unresolved_queue),
            "sets_already_ready_before": before_ready,
            "sets_ready_after": after_ready,
            "sets_newly_resolved": max(after_ready - before_ready, 0),
            "sets_with_file_writes": wrote_count,
            "status_counts": status_counts,
            **readiness_summary,
        },
        "sets": refreshed_sets,
    }

    resolution_report = {
        "summary": {
            "source_report": str(report_path).replace("\\", "/"),
            "apply_mode": bool(args.apply),
            "min_confidence": args.min_confidence,
            "sets_inspected": len(sets),
            "sets_in_resolution_queue": len(unresolved_queue),
            "status_counts": status_counts,
            "writes_applied": wrote_count,
            "sets_already_ready_before": before_ready,
            "sets_ready_after": after_ready,
            "newly_ready": max(after_ready - before_ready, 0),
        },
        "sets": resolution_rows,
    }

    resolution_report_path = Path(args.resolution_report)
    readiness_report_path = Path(args.readiness_report)
    resolution_report_path.write_text(json.dumps(resolution_report, indent=2), encoding="utf-8", newline="\n")
    readiness_report_path.write_text(json.dumps(readiness_report, indent=2), encoding="utf-8", newline="\n")
    save_cache(cache)

    print(f"[TCGPLAYER-RESOLVE] sets_inspected={len(sets)}")
    print(f"[TCGPLAYER-RESOLVE] queue={len(unresolved_queue)}")
    print(f"[TCGPLAYER-RESOLVE] ready_before={before_ready} ready_after={after_ready}")
    print(f"[TCGPLAYER-RESOLVE] writes_applied={wrote_count} apply_mode={args.apply}")
    print(f"[TCGPLAYER-RESOLVE] resolution_report={resolution_report_path}")
    print(f"[TCGPLAYER-RESOLVE] readiness_report={readiness_report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
