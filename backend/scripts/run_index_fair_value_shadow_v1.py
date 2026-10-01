"""FV-S3 offline tooling: preregistration freeze and as-known-at REPLAY.

OFFLINE ONLY. Reads a local FV-S2 snapshot and frozen research artifacts. No network, no
database, no provider, no ledger writes (an in-memory ledger is used to prove the
contract). A replay is explicitly labelled ``AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE``;
it is not, and can never be mistaken for, a prospective publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import index_fair_value_shadow_anchor_v1 as anchor_mod  # noqa: E402
from backend.scripts import index_fair_value_shadow_evaluation_v1 as ev  # noqa: E402
from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod  # noqa: E402
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2  # noqa: E402

RULE_MODULE = ROOT / "backend/scripts/index_fair_value_sold_clearing_anchor.py"
PREREG_PATH = ROOT / "docs/research/index_fair_value/fv_s3/preregistration_v1.json"
OUT_DIR = ROOT / "backend/artifacts/index_fair_value/shadow_s3"
RULE_SOURCE_COMMIT = "bdfc06e9"  # commit that introduced the frozen FV-S2 rule module


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def preregistration_artifact() -> dict[str, Any]:
    contract = s2.canonical_json(s2.methodology_contract(s2.OBSERVATION_DATE)).encode()
    return {
        "preregistration": ev.PREREGISTRATION,
        "preregistration_sha256": hashlib.sha256(
            json.dumps(ev.PREREGISTRATION, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "frozen_rule_module": "backend/scripts/index_fair_value_sold_clearing_anchor.py",
        "frozen_rule_module_sha256": sha256_lf(RULE_MODULE),
        "frozen_rule_methodology_contract_sha256": hashlib.sha256(contract).hexdigest(),
        "rule_source_commit": RULE_SOURCE_COMMIT,
        "core_panel_fingerprint": s2.EXPECTED_PANEL_FINGERPRINT,
        "first_prospective_publication_exists_at_freeze": False,
        "provider_backed_observation_exists_at_freeze": False,
        "statement": "Frozen before any provider-backed prospective observation. Editing V1 afterwards requires ANCHOR_V2.",
    }


def _structural_inputs() -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    structural = {cid: v["structural_modelc_oof"] for cid, v in s2._structural_lookup().items()
                  if "structural_modelc_oof" in v}
    f1 = {str(r["canonical_card_id"]): r for r in json.loads(s2.F1_DATASET.read_text(encoding="utf-8"))["rows"]}
    return structural, f1


def replay(snapshot: dict[str, Any], panel: dict[str, Any], *, evaluation_date: date,
           information_cutoff: datetime, generated_at: datetime, snapshot_sha256: str) -> dict[str, Any]:
    panel_rows = sorted(panel["rows"], key=lambda r: str(r["canonical_card_id"]))
    provider_by: dict[str, int] = {}
    for ident in snapshot["identities"]:
        provider_by.setdefault(str(ident["canonical_card_id"]), int(ident["provider_card_id"]))
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot["evidence"]:
        by_card[str(row["canonical_card_id"])].append(row)
    structural, f1 = _structural_inputs()
    outcomes = s2._outcomes(snapshot, panel_rows)
    fingerprints = {
        "evidence_snapshot_sha256": snapshot_sha256,
        "frozen_rule_module_sha256": sha256_lf(RULE_MODULE),
        "core_panel_fingerprint": panel["panel_fingerprint"],
    }
    ledger = ledger_mod.InMemoryShadowLedger()
    comparable: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    exclusion_totals: Counter[str] = Counter()
    for pr in panel_rows:
        cid = str(pr["canonical_card_id"])
        expected = provider_by.get(cid)
        rows = [r for r in by_card.get(cid, []) if expected is None or int(r["provider_card_id"]) == expected]
        pub = anchor_mod.build_anchor_publication(
            canonical_card_id=cid, card_variant_id=pr["card_variant_id"], card_number=pr["card_number"],
            evidence_rows=rows, evaluation_date=evaluation_date, information_cutoff=information_cutoff,
            generated_at=generated_at, source_commit=RULE_SOURCE_COMMIT, input_fingerprints=fingerprints,
            prospective=True, replay=True)
        assert ledger.append_publication(pub) == "INSERTED"
        exclusion_totals.update(pub["exclusion_counts"])
        out = outcomes[cid]
        obs = ev.build_component_observation(
            pub, market={"market_price_usd": out["market_price_usd"], "market_price_date": out["market_price_captured_at"]},
            structural={"structural_price_usd": structural.get(cid), "source": "F2_MODELC_OOF_FROZEN_RESEARCH_COMPARATOR"},
            scarcity={"pull_probability": (f1.get(cid) or {}).get("pull_probability"), "source": "F1_DATASET_FROZEN"},
            appeal={"collector_appeal": (f1.get(cid) or {}).get("collector_appeal"), "source": "F1_DATASET_FROZEN"})
        ledger.append_component(obs)
        cards.append({
            "card": f'{pr["card_name"]} {pr["card_number"]}', "set_name": pr["set_name"],
            "publication_id": pub["publication_id"], "status": pub["status"],
            "comps": pub["eligible_comp_count"], "window_days": pub["selected_window_days"],
            "anchor_usd": obs["explicit_nm_sold_clearing_anchor_v1_usd"],
            "market_usd": obs["current_tcgplayer_market_price_usd"],
            "structural_usd": obs["structural_baseline_usd"], "shadow_status": obs["shadow_status"],
            "anchor_minus_market_pct": obs["divergence_sold_anchor_minus_current_market"]["pct_of_reference"],
            "structural_minus_market_pct": obs["divergence_structural_minus_current_market"]["pct_of_reference"],
            "anchor_minus_structural_pct": obs["divergence_sold_anchor_minus_structural"]["pct_of_reference"],
        })
        if obs["explicit_nm_sold_clearing_anchor_v1_usd"] and out["market_price_usd"]:
            comparable.append({"anchor_usd": obs["explicit_nm_sold_clearing_anchor_v1_usd"],
                               "market_price_usd": out["market_price_usd"]})
    curve = []
    for day in range(16, 31, 2):
        d = date(2026, 9, day)
        cutoff = datetime(2026, 9, day, 23, 59, 59, tzinfo=timezone.utc)
        anchored = 0
        for pr in panel_rows:
            cid = str(pr["canonical_card_id"])
            expected = provider_by.get(cid)
            rows = [r for r in by_card.get(cid, []) if expected is None or int(r["provider_card_id"]) == expected]
            anchored += anchor_mod.build_anchor_publication(
                canonical_card_id=cid, card_variant_id=pr["card_variant_id"], card_number=pr["card_number"],
                evidence_rows=rows, evaluation_date=d, information_cutoff=cutoff, generated_at=cutoff,
                source_commit=RULE_SOURCE_COMMIT, input_fingerprints=fingerprints, prospective=True,
                replay=True)["status"] == "ANCHORED"
        curve.append({"evaluation_date": d.isoformat(), "anchored_cards_as_known": anchored})
    collected = sorted(str(r["collected_at"]) for r in snapshot["evidence"] if r.get("collected_at"))
    return {
        "label": "RETROSPECTIVE_AS_KNOWN_REPLAY_NOT_A_PUBLICATION",
        "as_known_availability_curve": curve,
        "evidence_collected_at_range": [collected[0], collected[-1]] if collected else None,
        "evaluation_date": evaluation_date.isoformat(),
        "information_cutoff": information_cutoff.isoformat(),
        "evidence_status": "AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE",
        "publications": len(ledger.publications()),
        "anchored_as_known": sum(c["status"] == "ANCHORED" for c in cards),
        "insufficient_as_known": sum(c["status"] != "ANCHORED" for c in cards),
        "exclusion_totals": dict(sorted(exclusion_totals.items())),
        "accuracy_as_known": ev.stratified_accuracy(comparable, eligible_cards=len(cards)),
        "cards": cards,
        "snapshot_sha256": snapshot_sha256,
        "provider_calls": 0, "provider_credits_used": 0, "database_writes": 0,
    }


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze-preregistration")
    r = sub.add_parser("replay")
    r.add_argument("--snapshot", type=Path, required=True)
    r.add_argument("--out-dir", type=Path, default=OUT_DIR)
    r.add_argument("--evaluation-date", type=date.fromisoformat, default=date(2026, 9, 30))
    r.add_argument("--information-cutoff", type=datetime.fromisoformat,
                   default=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc))
    args = parser.parse_args(argv)
    if args.cmd == "freeze-preregistration":
        PREREG_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREREG_PATH.write_text(_dump(preregistration_artifact()), encoding="utf-8", newline="\n")
        print(json.dumps({"written": str(PREREG_PATH)}))
        return 0
    panel = s2.load_panel()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = replay(snapshot, panel, evaluation_date=args.evaluation_date,
                    information_cutoff=args.information_cutoff, generated_at=args.information_cutoff,
                    snapshot_sha256=s2.sha256_file(args.snapshot))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "as_known_replay_20260930.json").write_text(_dump(result), encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("anchored_as_known", "insufficient_as_known", "publications")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
