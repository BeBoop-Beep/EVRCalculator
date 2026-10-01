"""FV-S2 research harness: EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1 on the frozen Core Panel.

READ-ONLY. No provider calls, no provider credits, no database writes, no VM
access. Two phases, so results are deterministic and auditable:

  fetch    read-only SELECTs against Supabase -> local snapshot JSON (hash recorded)
  analyze  pure offline computation from a snapshot -> artifacts

The database handle is wrapped so that only ``table(...).select(...)`` chains
exist; there is no insert/update/upsert/delete/rpc surface to call.

The target TCGplayer market price is used ONLY as the evaluation outcome. It is
loaded after, and independently of, anchor construction and never passed to it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import index_fair_value_sold_clearing_anchor as anchor_rules  # noqa: E402

PANEL_MANIFEST = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"
EXPECTED_PANEL_FINGERPRINT = "9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f"
OBSERVATION_DATE = date(2026, 9, 30)
F2_OOF = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f2_oof_predictions.csv"
F2R_PRED = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f2r_target_blind_predictions.csv"
F1_DATASET = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f1_dataset.json"
OUT_DIR = ROOT / "backend/artifacts/index_fair_value/sold_clearing_anchor_v1"

EVIDENCE_COLUMNS = (
    "provider_listing_id,provider_card_id,canonical_card_id,title,price,currency,grader,grade,"
    "graded,provider_variant,attribution,sold_at,ingested_at,collected_at,identity_state,"
    "fair_value_signal_eligible,exclusion_reason,run_id"
)
PRICE_COLUMNS = (
    "canonical_card_id,card_variant_id,condition_id,printing_type,market_price,captured_at,source,"
    "price_selection_reason,refreshed_at"
)
PRICE_BANDS = (
    (0.0, 25.0, "under_25"), (25.0, 100.0, "25_to_under_100"), (100.0, math.inf, "100_plus"),
)
FINE_BANDS = (
    (-math.inf, 5, "under_5"), (5, 10, "5_to_under_10"), (10, 25, "10_to_under_25"),
    (25, 50, "25_to_under_50"), (50, 100, "50_to_under_100"), (100, 250, "100_to_under_250"),
    (250, math.inf, "250_plus"),
)
PRISMATIC_CASES = (
    ("Leafeon ex", "144"), ("Flareon ex", "146"), ("Vaporeon ex", "149"),
    ("Glaceon ex", "150"), ("Jolteon ex", "153"), ("Espeon ex", "155"),
    ("Sylveon ex", "156"), ("Umbreon ex", "161"), ("Eevee ex", "167"),
)
PRISMATIC_SET = "Prismatic Evolutions"


# --------------------------------------------------------------------------- guard
class ReadOnlyQuery:
    """Exposes only the query-builder methods needed for SELECTs."""

    _ALLOWED = frozenset({"eq", "in_", "order", "range", "limit", "execute", "gte", "lte"})

    def __init__(self, inner: Any, log: list[str]) -> None:
        self._inner = inner
        self._log = log

    def __getattr__(self, name: str) -> Any:
        if name not in self._ALLOWED:
            raise PermissionError(f"READ_ONLY_GUARD: query method {name!r} is not allowed")
        attr = getattr(self._inner, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            result = attr(*args, **kwargs)
            if name == "execute":
                self._log.append("execute")
                return result
            return ReadOnlyQuery(result, self._log)

        return call


class ReadOnlyTable:
    def __init__(self, inner: Any, log: list[str]) -> None:
        self._inner = inner
        self._log = log

    def select(self, *args: Any, **kwargs: Any) -> ReadOnlyQuery:
        return ReadOnlyQuery(self._inner.select(*args, **kwargs), self._log)

    def __getattr__(self, name: str) -> Any:
        raise PermissionError(f"READ_ONLY_GUARD: table method {name!r} is not allowed")


class ReadOnlyClient:
    """The only surface the harness gets: ``table(name).select(...)``."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.read_requests: list[str] = []

    def table(self, name: str) -> ReadOnlyTable:
        return ReadOnlyTable(self._inner.table(name), self.read_requests)

    def __getattr__(self, name: str) -> Any:
        raise PermissionError(f"READ_ONLY_GUARD: client attribute {name!r} is not allowed")


def make_read_only_client(env_file: Path) -> ReadOnlyClient:
    from dotenv import dotenv_values
    from supabase import create_client

    values = dotenv_values(env_file)
    url, key = values.get("SUPABASE_URL"), values.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing from env file")
    return ReadOnlyClient(create_client(url, key))


# --------------------------------------------------------------------------- helpers
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _panel_fingerprint(manifest: Mapping[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k not in {"panel_fingerprint", "audit"}}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_panel(path: Path = PANEL_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    recomputed = _panel_fingerprint(manifest)
    if manifest.get("panel_fingerprint") != EXPECTED_PANEL_FINGERPRINT or recomputed != EXPECTED_PANEL_FINGERPRINT:
        raise RuntimeError(
            f"FV_S2_PANEL_FINGERPRINT_MISMATCH declared={manifest.get('panel_fingerprint')} "
            f"recomputed={recomputed}"
        )
    if len(manifest["rows"]) != 207:
        raise RuntimeError("FV_S2_PANEL_SIZE_MISMATCH")
    return manifest


def _paged(factory: Any, page: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = list(factory().range(start, start + page - 1).execute().data or [])
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


# --------------------------------------------------------------------------- fetch
def fetch_snapshot(db: ReadOnlyClient, panel: Mapping[str, Any]) -> dict[str, Any]:
    canonical_ids = sorted(str(r["canonical_card_id"]) for r in panel["rows"])
    identities: list[dict[str, Any]] = []
    for chunk in _chunks(canonical_ids, 50):
        identities.extend(_paged(lambda c=chunk: db.table("pkmnprices_card_identity_v1")
            .select("provider_card_id,canonical_card_id,tcgplayer_product_id,language")
            .in_("canonical_card_id", c).eq("language", "English").order("provider_card_id")))
    evidence: list[dict[str, Any]] = []
    for cid in canonical_ids:
        evidence.extend(_paged(lambda c=cid: db.table("pkmnprices_ebay_sold_evidence_v1")
            .select(EVIDENCE_COLUMNS).eq("canonical_card_id", c)
            .order("provider_card_id").order("provider_listing_id")))
    prices: list[dict[str, Any]] = []
    for chunk in _chunks(canonical_ids, 50):
        prices.extend(_paged(lambda c=chunk: db.table("pokemon_canonical_card_market_prices_latest")
            .select(PRICE_COLUMNS).in_("canonical_card_id", c).order("canonical_card_id")))
    # Evaluation outcome at the observation date: the TCGplayer NM observation row
    # for the exact (variant, condition) the canonical latest-price authority selected.
    variant_ids = sorted({str(p["card_variant_id"]) for p in prices if p.get("card_variant_id")})
    observed: list[dict[str, Any]] = []
    for chunk in _chunks(variant_ids, 50):
        observed.extend(_paged(lambda c=chunk: db.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,captured_at,source,currency")
            .in_("card_variant_id", c).eq("captured_at", OBSERVATION_DATE.isoformat())
            .order("card_variant_id").order("condition_id")))
    # Evaluation outcome at the observation date: the TCGplayer NM observation row for the
    # exact (variant, condition) the canonical latest-price authority selected.
    variant_ids = sorted({str(p["card_variant_id"]) for p in prices if p.get("card_variant_id")})
    observed: list[dict[str, Any]] = []
    for chunk in _chunks(variant_ids, 50):
        observed.extend(_paged(lambda c=chunk: db.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,captured_at,source,currency")
            .in_("card_variant_id", c).eq("captured_at", OBSERVATION_DATE.isoformat())
            .order("card_variant_id").order("condition_id")))
    snapshot = {
        "snapshot_version": "fv_s2_input_snapshot_v1",
        "panel_fingerprint": panel["panel_fingerprint"],
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only_select_requests": len(db.read_requests),
        "identities": sorted(identities, key=lambda r: (str(r["canonical_card_id"]), int(r["provider_card_id"]))),
        "evidence": sorted(evidence, key=lambda r: (int(r["provider_card_id"]), int(r["provider_listing_id"]))),
        "prices": sorted(prices, key=lambda r: str(r["canonical_card_id"])),
        "observation_prices": sorted(observed, key=lambda r: (str(r["card_variant_id"]), str(r["condition_id"]))),
    }
    return snapshot


# --------------------------------------------------------------------------- analysis
def _band(price: float, bands: Iterable[tuple[float, float, str]]) -> str:
    return next(label for low, high, label in bands if low <= price < high)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    ape = [abs(r["anchor_usd"] - r["market_price_usd"]) / r["market_price_usd"] for r in rows]
    signed = [(r["anchor_usd"] - r["market_price_usd"]) / r["market_price_usd"] for r in rows]
    abs_err = [abs(r["anchor_usd"] - r["market_price_usd"]) for r in rows]
    return {
        "n": len(rows),
        "mdape_pct": round(statistics.median(ape) * 100, 4),
        "mape_pct": round(statistics.fmean(ape) * 100, 4),
        "median_signed_error_pct": round(statistics.median(signed) * 100, 4),
        "mae_usd": round(statistics.fmean(abs_err), 4),
        "median_abs_error_usd": round(statistics.median(abs_err), 4),
        "within_10pct": round(sum(a <= 0.10 for a in ape) / len(ape) * 100, 4),
        "within_30pct": round(sum(a <= 0.30 for a in ape) / len(ape) * 100, 4),
        "max_ape_pct": round(max(ape) * 100, 4),
    }


def _structural_lookup() -> dict[str, dict[str, float]]:
    import pandas as pd

    out: dict[str, dict[str, float]] = defaultdict(dict)
    f2 = pd.read_csv(F2_OOF)
    for r in f2[f2["model"] == "ModelC"].itertuples():
        out[str(r.canonical_card_id)]["structural_modelc_oof"] = float(r.predicted_price)
    f2r = pd.read_csv(F2R_PRED)
    for r in f2r[f2r["method"] == "R1_local_residual_10"].itertuples():
        out[str(r.canonical_card_id)]["market_anchored_r1"] = float(r.predicted_price)
    return out


def _compute_anchors(
    panel_rows: list[dict[str, Any]],
    by_card: Mapping[str, list[dict[str, Any]]],
    provider_by_canonical: Mapping[str, int],
    observation_date: date,
    *,
    strict: bool = False,
    boundary_extra_days: int = 0,
) -> dict[str, dict[str, Any]]:
    """Phase 1. Receives NO price of any kind -- the signature is the leakage guard."""
    anchors: dict[str, dict[str, Any]] = {}
    for pr in panel_rows:
        cid = str(pr["canonical_card_id"])
        expected = provider_by_canonical.get(cid)
        usable, mismatched = [], 0
        for row in by_card.get(cid, []):
            if expected is not None and int(row["provider_card_id"]) != expected:
                mismatched += 1
                continue
            usable.append(row)
        result = anchor_rules.build_card_result(
            usable, card_number=pr["card_number"], observation_date=observation_date,
            reject_conflicting_numbers=strict, boundary_extra_days=boundary_extra_days,
        )
        if mismatched:
            result["exclusion_counts"]["PROVIDER_IDENTITY_MISMATCH"] = mismatched
        result["provider_identity_resolved"] = expected is not None
        anchors[cid] = result
    return anchors


def _outcomes(snapshot: Mapping[str, Any], panel_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Phase 2. Evaluation outcome: TCGplayer NM price observed on the observation date."""
    latest = {str(p["canonical_card_id"]): p for p in snapshot["prices"]}
    observed = {
        (str(o["card_variant_id"]), str(o["condition_id"])): o
        for o in snapshot.get("observation_prices", [])
    }
    out: dict[str, dict[str, Any]] = {}
    for pr in panel_rows:
        cid = str(pr["canonical_card_id"])
        lat = latest.get(cid) or {}
        obs = observed.get((str(lat.get("card_variant_id")), str(lat.get("condition_id"))))
        market = None
        basis = "MISSING_OBSERVATION_DATE_ROW"
        if obs and obs.get("market_price") not in (None, ""):
            market, basis = float(obs["market_price"]), f"observation_{obs['captured_at']}"
        has_latest = lat.get("market_price") not in (None, "")
        out[cid] = {
            "market_price_usd": market, "market_price_basis": basis,
            "market_price_captured_at": obs.get("captured_at") if obs else None,
            "market_price_source": (obs or {}).get("source"),
            "latest_market_price_usd": float(lat["market_price"]) if has_latest else None,
            "latest_market_price_captured_at": lat.get("captured_at"),
            "market_price_variant_matches_panel": (
                str(lat.get("card_variant_id")) == str(pr["card_variant_id"]) if lat else None
            ),
        }
    return out


def _assemble_cards(
    panel_rows: list[dict[str, Any]],
    anchors: Mapping[str, Mapping[str, Any]],
    outcomes: Mapping[str, Mapping[str, Any]],
    provider_by_canonical: Mapping[str, int],
    structural: Mapping[str, Mapping[str, float]],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for pr in panel_rows:
        cid = str(pr["canonical_card_id"])
        a, o = anchors[cid], outcomes[cid]
        market = o["market_price_usd"]
        row = {
            "canonical_card_id": cid, "card_variant_id": pr["card_variant_id"],
            "set_name": pr["set_name"], "card_name": pr["card_name"], "card_number": pr["card_number"],
            "manifest_price_band": pr["price_band"],
            "provider_card_id": provider_by_canonical.get(cid),
            "status": a["status"], "selected_window_days": a["selected_window_days"],
            "comp_count": a["comp_count"], "anchor_usd": a["anchor_usd"],
            "anchor_median_usd_2dp": a.get("median_usd_2dp"),
            "eligible_counts_by_window": a["eligible_counts_by_window"],
            "q1": a.get("q1"), "q3": a.get("q3"), "iqr": a.get("iqr"), "mad": a.get("mad"),
            "distinct_sale_days": a.get("distinct_sale_days"),
            "oldest_sold_at": a.get("oldest_sold_at"), "newest_sold_at": a.get("newest_sold_at"),
            "collected_at_min": a.get("collected_at_min"), "collected_at_max": a.get("collected_at_max"),
            "rows_seen": a["rows_seen"], "eligible_rows_all_time": a["eligible_rows_all_time"],
            "selected_comps_with_conflicting_card_number": a.get("selected_comps_with_conflicting_card_number", 0),
            "exclusion_counts": a["exclusion_counts"],
            "evidence_semantics": a["evidence_semantics"], "rule_version": a["rule_version"],
            # ---- evaluation-only fields ----
            **o,
        }
        if market and a["anchor_usd"] is not None:
            row["abs_pct_error"] = round(abs(a["anchor_usd"] - market) / market * 100, 4)
            row["signed_pct_error"] = round((a["anchor_usd"] - market) / market * 100, 4)
            row["abs_error_usd"] = round(abs(a["anchor_usd"] - market), 4)
        row.update({k: round(v, 4) for k, v in structural.get(cid, {}).items()})
        cards.append(row)
    return cards


def _ge(rows: list[dict[str, Any]], low: float) -> list[dict[str, Any]]:
    return [r for r in rows if r["market_price_usd"] >= low]


def _headline(cards: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [c for c in cards if c["market_price_usd"]]
    covered = [c for c in priced if c["status"] == "ANCHORED"]
    return {
        "coverage_overall": f"{len(covered)} / {len(priced)}",
        "coverage_ge_25": f"{len(_ge(covered, 25))} / {len(_ge(priced, 25))}",
        "coverage_ge_100": f"{len(_ge(covered, 100))} / {len(_ge(priced, 100))}",
        "mdape_overall_pct": _metrics(covered).get("mdape_pct"),
        "mdape_ge_25_pct": _metrics(_ge(covered, 25)).get("mdape_pct"),
        "mdape_ge_100_pct": _metrics(_ge(covered, 100)).get("mdape_pct"),
        "mae_ge_100_usd": _metrics(_ge(covered, 100)).get("mae_usd"),
    }


def analyze(
    snapshot: Mapping[str, Any],
    panel: Mapping[str, Any],
    *,
    observation_date: date = OBSERVATION_DATE,
    snapshot_sha256: str | None = None,
    include_structural: bool = True,
) -> dict[str, Any]:
    if snapshot["panel_fingerprint"] != EXPECTED_PANEL_FINGERPRINT:
        raise RuntimeError("FV_S2_SNAPSHOT_PANEL_MISMATCH")
    panel_rows = sorted(panel["rows"], key=lambda r: str(r["canonical_card_id"]))
    panel_ids = {str(r["canonical_card_id"]) for r in panel_rows}

    provider_by_canonical: dict[str, int] = {}
    for ident in snapshot["identities"]:
        provider_by_canonical.setdefault(str(ident["canonical_card_id"]), int(ident["provider_card_id"]))

    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    out_of_panel = 0
    for row in snapshot["evidence"]:
        cid = str(row["canonical_card_id"])
        if cid not in panel_ids:
            out_of_panel += 1
            continue
        by_card[cid].append(row)

    # Phase 1 (no prices in scope) then Phase 2 (outcome only).
    anchors = _compute_anchors(panel_rows, by_card, provider_by_canonical, observation_date)
    outcomes = _outcomes(snapshot, panel_rows)
    structural = _structural_lookup() if include_structural else {}
    cards = _assemble_cards(panel_rows, anchors, outcomes, provider_by_canonical, structural)

    priced = [c for c in cards if c["market_price_usd"]]
    covered = [c for c in priced if c["status"] == "ANCHORED"]
    uncovered = [c for c in priced if c["status"] != "ANCHORED"]

    coverage = {
        "panel_cards": len(cards), "cards_with_market_price": len(priced),
        "cards_missing_observation_date_price": len(cards) - len(priced),
        "anchored_cards": len(covered), "insufficient_cards": len(uncovered),
        "coverage_overall": f"{len(covered)} / {len(priced)}",
        "coverage_ge_25": f"{len(_ge(covered, 25))} / {len(_ge(priced, 25))}",
        "coverage_ge_100": f"{len(_ge(covered, 100))} / {len(_ge(priced, 100))}",
        "selected_window_distribution": dict(sorted(
            Counter(str(c["selected_window_days"]) for c in covered).items(), key=lambda kv: int(kv[0]))),
        "comp_count_quantiles": _quantiles([c["comp_count"] for c in covered]),
        "uncovered_cards": [
            {"card": f'{c["card_name"]} {c["card_number"]}', "set_name": c["set_name"],
             "market_price_usd": c["market_price_usd"],
             "eligible_counts_by_window": c["eligible_counts_by_window"],
             "eligible_rows_all_time": c["eligible_rows_all_time"]}
            for c in sorted(uncovered, key=lambda c: -c["market_price_usd"])
        ],
        "uncovered_market_price_range_usd": (
            [min(c["market_price_usd"] for c in uncovered), max(c["market_price_usd"] for c in uncovered)]
            if uncovered else None
        ),
    }

    def strict_cards(**kw: Any) -> list[dict[str, Any]]:
        return _assemble_cards(
            panel_rows,
            _compute_anchors(panel_rows, by_card, provider_by_canonical, observation_date, **kw),
            outcomes, provider_by_canonical, structural)

    evaluation = {
        "diagnostic_only_note": "Price bands are evaluation diagnostics; target price never influenced eligibility or window choice.",
        "outcome": "TCGplayer Near Mint market price observed on the observation date",
        "overall": _metrics(covered),
        "ge_25": _metrics(_ge(covered, 25)),
        "ge_100": _metrics(_ge(covered, 100)),
        "by_coarse_band": {label: _metrics([c for c in covered if _band(c["market_price_usd"], PRICE_BANDS) == label])
                           for _, _, label in PRICE_BANDS},
        "by_fine_band": {label: _metrics([c for c in covered if _band(c["market_price_usd"], FINE_BANDS) == label])
                         for _, _, label in FINE_BANDS},
        "by_selected_window": {w: _metrics([c for c in covered if str(c["selected_window_days"]) == w])
                               for w in sorted({str(c["selected_window_days"]) for c in covered}, key=int)},
        "scarcity_and_tail_context": _scarcity_context(cards, panel_rows) if include_structural else None,
        "sensitivity_diagnostics_not_applied": {
            "primary_v1": _headline(cards),
            "strict_reject_conflicting_card_numbers": _headline(strict_cards(strict=True)),
            "window_boundary_plus_one_day": _headline(strict_cards(boundary_extra_days=1)),
            "latest_price_instead_of_observation_date": _headline([
                {**c, "market_price_usd": c["latest_market_price_usd"]} for c in cards
                if c["latest_market_price_usd"]]),
        },
    }
    if include_structural:
        comparable = [c for c in covered if "structural_modelc_oof" in c]

        def as_structural(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [{**c, "anchor_usd": c["structural_modelc_oof"]} for c in rows]

        evaluation["structural_comparison_same_cards"] = {
            "n": len(comparable),
            "anchor": _metrics(comparable),
            "structural_modelc_oof": _metrics(as_structural(comparable)),
            "ge_100_anchor": _metrics(_ge(comparable, 100)),
            "ge_100_structural_modelc_oof": _metrics(as_structural(_ge(comparable, 100))),
        }

    by_key = {(c["set_name"], c["card_name"], str(c["card_number"])): c for c in cards}
    prismatic = []
    for name, number in PRISMATIC_CASES:
        c = by_key.get((PRISMATIC_SET, name, number))
        if c is None:
            prismatic.append({"card": f"{name} {number}", "status": "NOT_IN_PANEL"})
            continue
        entry = {k: c.get(k) for k in (
            "card_name", "card_number", "market_price_usd", "latest_market_price_usd", "status",
            "selected_window_days", "comp_count", "anchor_usd", "anchor_median_usd_2dp", "abs_pct_error",
            "signed_pct_error", "q1", "q3", "iqr", "mad", "distinct_sale_days", "oldest_sold_at",
            "newest_sold_at", "eligible_counts_by_window", "selected_comps_with_conflicting_card_number",
            "structural_modelc_oof", "market_anchored_r1")}
        if entry.get("structural_modelc_oof") and c["market_price_usd"]:
            entry["structural_signed_pct_error"] = round(
                (c["structural_modelc_oof"] - c["market_price_usd"]) / c["market_price_usd"] * 100, 4)
        prismatic.append(entry)

    totals: Counter[str] = Counter()
    for c in cards:
        totals.update(c["exclusion_counts"])
    eligible_with_other_number = 0
    for pr in panel_rows:
        for row in by_card.get(str(pr["canonical_card_id"]), []):
            comp, _ = anchor_rules.classify_row(
                row, card_number=pr["card_number"], observation_date=observation_date)
            if comp and anchor_rules.title_has_conflicting_card_number(row["title"], pr["card_number"]):
                eligible_with_other_number += 1
    exclusion_audit = {
        "rows_in_panel_evidence": sum(c["rows_seen"] for c in cards),
        "rows_outside_panel_ignored": out_of_panel,
        "eligible_rows_all_time": sum(c["eligible_rows_all_time"] for c in cards),
        "eligible_rows_also_carrying_a_different_card_number": eligible_with_other_number,
        "exclusion_totals": dict(sorted(totals.items())),
        "cards_without_provider_identity": sorted(c["canonical_card_id"] for c in cards if c["provider_card_id"] is None),
        "priced_cards_at_or_above_25_with_all_time_eligible_lt_10": [
            f'{c["card_name"]} {c["card_number"]}' for c in cards
            if c["market_price_usd"] and c["market_price_usd"] >= 25 and c["eligible_rows_all_time"] < 10],
        "note": "Each row is counted once under the first failing rule, in the order the rules are evaluated.",
    }

    price_dates = Counter(str(c["market_price_captured_at"]) for c in cards)
    contract = methodology_contract(observation_date)
    run_manifest = {
        "rule_version": anchor_rules.RULE_VERSION,
        "panel_fingerprint": panel["panel_fingerprint"],
        "observation_date": observation_date.isoformat(),
        "evidence_semantics": anchor_rules.EVIDENCE_SEMANTICS,
        "snapshot_sha256": snapshot_sha256,
        "snapshot_fetched_at_utc": snapshot.get("fetched_at_utc"),
        "evidence_rows_in_snapshot": len(snapshot["evidence"]),
        "target_price_captured_at_distribution": dict(sorted(price_dates.items())),
        "provider_calls": 0, "provider_credits_used": 0, "database_writes": 0,
        "target_price_inputs_to_anchor_construction": 0,
        "methodology_contract_sha256": sha256_bytes(canonical_json(contract).encode()),
        "structural_sources": (
            {"f2_oof": sha256_file(F2_OOF), "f2r_predictions": sha256_file(F2R_PRED),
             "f1_dataset": sha256_file(F1_DATASET)}
            if include_structural else None
        ),
    }
    return {
        "methodology_contract": contract, "card_results": cards, "coverage_report": coverage,
        "price_band_evaluation": evaluation, "prismatic_case_study": prismatic,
        "exclusion_audit": exclusion_audit, "run_manifest": run_manifest,
    }


def _quantiles(values: list[int]) -> dict[str, float] | None:
    if not values:
        return None
    s = sorted(values)
    q = statistics.quantiles(s, n=4, method="inclusive") if len(s) > 1 else [s[0]] * 3
    return {"min": s[0], "q1": q[0], "median": q[1], "q3": q[2], "max": s[-1]}


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def _slope(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    return None if sxx <= 0 else sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx


def _scarcity_context(cards: list[dict[str, Any]], panel_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Context only: exact pull scarcity vs price, and top-tail compression of each estimator.

    Uses the frozen F1 pull probabilities and the observation-date outcome price. Nothing
    here feeds the anchor.
    """
    f1 = {str(r["canonical_card_id"]): r for r in json.loads(F1_DATASET.read_text(encoding="utf-8"))["rows"]}
    set_by_card = {str(p["canonical_card_id"]): str(p["root_set_id"]) for p in panel_rows}
    pts = []
    for c in cards:
        prob = (f1.get(c["canonical_card_id"]) or {}).get("pull_probability")
        if c["market_price_usd"] and prob and float(prob) > 0:
            pts.append((c["canonical_card_id"], math.log(c["market_price_usd"]), -math.log(float(prob))))
    xs, ys = [p[2] for p in pts], [p[1] for p in pts]
    by_set: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for cid, ly, sx in pts:
        by_set[set_by_card[cid]].append((sx, ly))
    cx, cy = [], []
    for members in by_set.values():
        mx = statistics.fmean(m[0] for m in members)
        my = statistics.fmean(m[1] for m in members)
        cx += [m[0] - mx for m in members]
        cy += [m[1] - my for m in members]
    out: dict[str, Any] = {
        "n": len(pts),
        "pearson_log_price_vs_neg_ln_pull_probability": None if _pearson(xs, ys) is None else round(_pearson(xs, ys), 4),
        "within_set_centered_pearson": None if _pearson(cx, cy) is None else round(_pearson(cx, cy), 4),
        "f1_dataset_sha256": sha256_file(F1_DATASET),
        "reproduction_note": "Collector-Appeal / transaction-velocity LOSO R^2 comparisons are context from the Oct 1 study and are NOT reproduced in this bucket.",
    }
    for floor in (0, 25, 100):
        for label, key in (("anchor", "anchor_usd"), ("structural_modelc_oof", "structural_modelc_oof")):
            pairs = [(math.log(c["market_price_usd"]), math.log(c[key])) for c in cards
                     if c["market_price_usd"] and c["market_price_usd"] >= floor
                     and c.get(key) and c["status"] == "ANCHORED" and c.get("structural_modelc_oof")]
            slope = _slope([a for a, _ in pairs], [b for _, b in pairs])
            out[f"log_log_slope_{label}_vs_market_ge_{floor}"] = None if slope is None else round(slope, 4)
            out[f"log_log_slope_n_ge_{floor}"] = len(pairs)
    out["log_log_slope_note"] = (
        "slope of log(estimate) on log(market) over anchored cards; slope < 1 means the estimator "
        "compresses the high-price tail. Floors 0/25/100 are the same bands used elsewhere."
    )
    return out


def methodology_contract(observation_date: date) -> dict[str, Any]:
    return {
        "construct": anchor_rules.RULE_VERSION,
        "contract_version": anchor_rules.RULE_CONTRACT_VERSION,
        "status": "RESEARCH_ONLY_NOT_PRODUCTION_FAIR_VALUE",
        "not_a_condition_normalization_authority": True,
        "independent_of": ["D3 condition research", "TCGplayer market price", "structural Fair Value model"],
        "observation_date": observation_date.isoformat(),
        "evidence_semantics": anchor_rules.EVIDENCE_SEMANTICS,
        "windows_days_in_order": list(anchor_rules.WINDOWS_DAYS),
        "window_definition": "trailing window of exactly N calendar days: observation_date-N+1 <= sold_at <= observation_date",
        "min_eligible_comps": anchor_rules.MIN_COMPS,
        "point_estimate": "median of eligible completed-sale prices in the selected window",
        "reported_statistics": ["count", "window", "oldest/newest sold_at", "median", "q1/q3/iqr (linear percentile)",
                                "mad (unscaled, about median)", "distinct sale days", "exclusion counts"],
        "eligibility": {
            "panel": "canonical card in frozen Core Panel",
            "identity_state": "EXACT", "attribution": "exact", "graded": False, "currency": "USD",
            "provider_identity": "evidence.provider_card_id must equal the persisted exact identity for the canonical card",
            "title_requires": ["explicit card number as a standalone numeric token (N/M numerator, #N, or bare); slash denominators never count; non-numeric numbers never match",
                               "explicit NM or Near Mint"],
            "title_rejects": {
                "worse_condition": "LP, Lightly Played, MP, Moderately Played, HP, Heavily Played, Damaged, DMG, crease(s), torn, water damage",
                "grade_evidence": "PSA, BGS, Beckett, CGC, SGC, AGS; TAG/ACE + numeric grade; Gem Mint; Black Label; Pristine",
                "wrong_object": "proxy, fan art, custom card/case, extended-art case, no card, sticker, digital, code card, lot, bundle, repack, metal card",
            },
            "fail_closed": True,
            "known_unapplied_tightening": "titles that also carry a DIFFERENT card number are accepted by V1 (matches the reproduced study); strict rejection is reported as a sensitivity only",
        },
        "window_selection_inputs": ["eligible comp count", "sold dates", "fixed observation date"],
        "window_selection_forbidden_inputs": ["target TCGplayer market price", "any value derived from it"],
        "not_blended_with": ["TCGplayer price", "structural Fair Value model"],
        "forward_replay_requirements": ["record sold_at", "record collected_at/ingested_at", "record evaluation timestamp",
                                        "exclude rows with collected_at > evaluation timestamp (information_cutoff)"],
        "provider_calls": 0, "provider_credits": 0, "database_writes": 0,
    }


# --------------------------------------------------------------------------- IO
ARTIFACT_FILES = {
    "methodology_contract": "methodology_contract.json",
    "card_results": "card_results.json",
    "coverage_report": "coverage_report.json",
    "price_band_evaluation": "price_band_evaluation.json",
    "prismatic_case_study": "prismatic_case_study.json",
    "exclusion_audit": "exclusion_audit.json",
    "run_manifest": "run_manifest.json",
}


def write_artifacts(result: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for key, name in ARTIFACT_FILES.items():
        text = canonical_json(result[key])
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
        hashes[name] = sha256_bytes(text.encode())
    return hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="read-only SELECTs -> snapshot JSON")
    f.add_argument("--env-file", type=Path, required=True)
    f.add_argument("--snapshot", type=Path, required=True)
    a = sub.add_parser("analyze", help="offline analysis from a snapshot")
    a.add_argument("--snapshot", type=Path, required=True)
    a.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a.add_argument("--observation-date", type=date.fromisoformat, default=OBSERVATION_DATE)
    args = parser.parse_args(argv)

    panel = load_panel()
    if args.cmd == "fetch":
        db = make_read_only_client(args.env_file)
        snap = fetch_snapshot(db, panel)
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(canonical_json(snap), encoding="utf-8", newline="\n")
        print(json.dumps({"snapshot": str(args.snapshot), "sha256": sha256_file(args.snapshot),
                          "evidence_rows": len(snap["evidence"]), "identities": len(snap["identities"]),
                          "prices": len(snap["prices"]), "select_requests": len(db.read_requests),
                          "writes": 0, "provider_calls": 0}, sort_keys=True))
        return 0
    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = analyze(snap, panel, observation_date=args.observation_date,
                     snapshot_sha256=sha256_file(args.snapshot))
    hashes = write_artifacts(result, args.out_dir)
    print(json.dumps({"artifacts": hashes, "coverage": result["coverage_report"]["coverage_overall"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
