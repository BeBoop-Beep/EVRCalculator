"""Build the blinded human chase-labeling packet (Stage III, Phases 2-5).

RESEARCH ONLY. Writes small review artifacts under
``docs/research/chase_labeling_v1/`` and touches no production table, score,
ranking snapshot, endpoint or schema.

    python -m backend.scripts.build_chase_labeling_packet

No simulation is run. Card identity and current near-mint prices come from
``EVRInputPreparationService`` - the same input assembly the authoritative run
uses - and the algorithm-selection union comes from the existing Stage-II
artifact, so the packet is cheap to rebuild and cannot drift from the study it
will be used to evaluate.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.research.set_chase_efficiency.labeling import (
    CHASE_LABELING_SCHEMA_VERSION,
    LABELING_COHORT,
    PACKET_COLUMNS,
    build_candidate_pool,
    packet_row,
    write_label_template_csv,
    write_packet_csv,
)

TAG = "[CHASE_LABELING_PACKET]"
DEFAULT_OUT = "docs/research/chase_labeling_v1"
DEFAULT_STAGE2 = "docs/research/set_chase_efficiency_stage2.json"


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN
            return ""
    except Exception:
        pass
    return str(value).strip()


def stage2_index(path: Path) -> Dict[str, Dict[str, Any]]:
    """Per-set pack cost and the UNION of every Stage-II method's selections.

    The union matters: a benchmarked method whose picks were missing from the
    labeling pool would score a low recall for a reason that has nothing to do
    with the method.
    """
    report = json.loads(path.read_text(encoding="utf-8"))
    index: Dict[str, Dict[str, Any]] = {}
    for entry in report["sets"]:
        selected: set[str] = set()
        for universe in entry["universes"]:
            for member in universe.get("members") or ():
                if member.get("cardVariantId"):
                    selected.add(str(member["cardVariantId"]))
        index[entry["canonicalKey"]] = {
            "setId": entry["setId"],
            "setName": entry["setName"],
            "packEquivalentCost": entry["acquisitionCost"]["packEquivalentCost"],
            "algorithmSelectedIds": sorted(selected),
            "eligibleChaseUniverse": entry["coverage"]["eligibleChaseUniverse"],
        }
    return index


def cards_for_set(config: Any, canonical_key: str, preparation: Any) -> List[Dict[str, Any]]:
    """Every drawable exact printing with its current near-mint price.

    Base and reverse columns are separate printings with separate prices and
    separate identifiers, exactly as the simulator treats them, so a labeler is
    never asked to judge "Charizard" without knowing which printing.
    """
    prepared = preparation.prepare_for_set(
        config, canonical_key, str(getattr(config, "SET_NAME", canonical_key)))
    frame = prepared["dataframe"]
    rows: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        base_variant = _text(row.get("card_variant_id"))
        if base_variant:
            rows.append({
                "card_id": _text(row.get("card_id")),
                "card_variant_id": base_variant,
                "card_name": _text(row.get("Card Name")),
                "card_number": _text(row.get("Card Number")),
                "rarity": _text(row.get("Rarity")),
                "treatment": _text(row.get("Special Type")),
                "printing_type": _text(row.get("printing_type")),
                "market_price": row.get("Price ($)"),
                "image_url": "",
            })
        reverse_variant = _text(row.get("reverse_variant_id"))
        if reverse_variant:
            rows.append({
                "card_id": _text(row.get("card_id")),
                "card_variant_id": reverse_variant,
                "card_name": _text(row.get("Card Name")),
                "card_number": _text(row.get("Card Number")),
                "rarity": _text(row.get("Rarity")),
                "treatment": _text(row.get("Special Type")),
                "printing_type": _text(row.get("reverse_printing_type")) or "reverse",
                "market_price": row.get("Reverse Variant Price ($)"),
                "image_url": "",
            })
    return rows


def render_html(rows: Sequence[Dict[str, Any]], *, market_date: str,
                schema_version: str) -> str:
    """A single self-contained review sheet, grouped by set.

    Deliberately plain: the labeler is being asked for a judgement about cards,
    and any visual emphasis would itself be a hint about which rows matter.
    """
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_set.setdefault(row["set_name"], []).append(row)

    parts = [
        "<title>Chase Labeling Packet</title>",
        "<style>",
        "body{font:14px system-ui,sans-serif;margin:24px;max-width:1100px}",
        "h1{font-size:20px} h2{font-size:16px;margin-top:32px;border-bottom:1px solid #ccc}",
        "table{border-collapse:collapse;width:100%;margin-top:8px}",
        "th,td{border:1px solid #ddd;padding:4px 8px;text-align:left;font-size:13px}",
        "th{background:#f4f4f4} td.num{text-align:right;font-variant-numeric:tabular-nums}",
        ".note{background:#fffbe6;border:1px solid #e8d98a;padding:12px;margin:16px 0}",
        "</style>",
        "<h1>Chase Labeling Packet</h1>",
        f"<p>Market date <b>{html.escape(market_date)}</b> &middot; schema "
        f"<code>{html.escape(schema_version)}</code> &middot; "
        f"{len(rows)} candidate cards across {len(by_set)} sets.</p>",
        "<div class='note'><b>How to label.</b> For each card choose one of:"
        "<ul>"
        "<li><b>CORE_CHASE</b> &mdash; a primary chase target of the set.</li>"
        "<li><b>EXTENDED_CHASE</b> &mdash; a meaningful secondary chase; a hit you "
        "would be pleased with, but not a defining headline card.</li>"
        "<li><b>NOT_CHASE</b> &mdash; not reasonably part of the chase pool.</li>"
        "<li><b>UNSURE</b> &mdash; you cannot confidently classify it.</li>"
        "</ul>"
        "Record answers in the matching <code>*_labels_template.csv</code>. "
        "<b>UNSURE is a real answer</b> &mdash; please use it rather than guessing; "
        "those rows are analysed separately and are not folded into either class."
        "<br><br>This packet deliberately shows no model outputs, scores or "
        "algorithm selections, so that your judgement stays independent of the "
        "methods it will be used to evaluate.</div>",
    ]
    for set_name in sorted(by_set):
        entries = sorted(by_set[set_name],
                         key=lambda row: -float(row["market_price"] or 0))
        pack = entries[0]["pack_price"] if entries else ""
        parts.append(f"<h2>{html.escape(set_name)} "
                     f"<small>(pack ${html.escape(str(pack))} &middot; "
                     f"{len(entries)} candidates)</small></h2>")
        parts.append("<table><tr><th>#</th><th>Card</th><th>Number</th><th>Rarity</th>"
                     "<th>Treatment</th><th>Printing</th><th class='num'>Price</th>"
                     "<th class='num'>Packs</th></tr>")
        for index, row in enumerate(entries, 1):
            parts.append(
                f"<tr><td class='num'>{index}</td>"
                f"<td>{html.escape(row['card_name'])}</td>"
                f"<td>{html.escape(row['card_number'])}</td>"
                f"<td>{html.escape(row['rarity'])}</td>"
                f"<td>{html.escape(row['treatment'])}</td>"
                f"<td>{html.escape(row['printing_type'])}</td>"
                f"<td class='num'>${html.escape(row['market_price'])}</td>"
                f"<td class='num'>{html.escape(row['value_in_packs'])}&times;</td></tr>")
        parts.append("</table>")
    return "\n".join(parts)


def build(client: Any, *, out_dir: Path, stage2_path: Path,
          market_date: Optional[str]) -> Dict[str, Any]:
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.scripts.build_set_chase_efficiency_research import _resolve_market_date

    day = str(market_date)[:10] if market_date else _resolve_market_date(client)
    index = stage2_index(stage2_path)
    preparation = EVRInputPreparationService()

    all_rows: List[Dict[str, Any]] = []
    per_set: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for entry in LABELING_COHORT:
        meta = index.get(entry.canonical_key)
        if meta is None:
            skipped.append({"canonicalKey": entry.canonical_key,
                            "reason": "not present in the Stage-II artifact"})
            print(f"{TAG} SKIP {entry.set_name}: absent from Stage-II artifact")
            continue
        config_cls, canonical_key = _resolve_set_config(entry.canonical_key)
        cards = cards_for_set(config_cls(), canonical_key, preparation)
        pool = build_candidate_pool(
            cards, pack_price=meta["packEquivalentCost"],
            algorithm_selected_ids=meta["algorithmSelectedIds"])
        rows = [packet_row(card, set_id=meta["setId"], set_name=meta["setName"],
                           pack_price=meta["packEquivalentCost"])
                for card in pool["pool"]]
        rows.sort(key=lambda row: -float(row["market_price"] or 0))
        all_rows.extend(rows)
        per_set.append({
            "canonicalKey": canonical_key,
            "setId": meta["setId"],
            "setName": meta["setName"],
            "structure": entry.structure,
            "selectionRationale": entry.rationale,
            "packEquivalentCost": meta["packEquivalentCost"],
            "drawablePrintings": len(cards),
            "candidatePoolSize": len(rows),
            "poolProof": pool["proof"],
        })
        print(f"{TAG} {meta['setName']:<28} pool={len(rows):>3} "
              f"of {len(cards):>3} printings  "
              f"cheapestInPool=${pool['proof']['cheapestCardInPool']:.2f} "
              f"dearestExcluded=${(pool['proof']['dearestCardExcluded'] or 0):.2f}")

    out_dir.mkdir(parents=True, exist_ok=True)
    packet_csv = write_packet_csv(all_rows, out_dir / "chase_labeling_packet.csv")
    template_csv = write_label_template_csv(
        all_rows, out_dir / "chase_labels_template.csv")
    review_html = out_dir / "chase_labeling_packet.html"
    review_html.write_text(
        render_html(all_rows, market_date=day, schema_version=CHASE_LABELING_SCHEMA_VERSION),
        encoding="utf-8")

    manifest = {
        "schemaVersion": CHASE_LABELING_SCHEMA_VERSION,
        "codeVersion": code_version(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": day,
        "stage2Artifact": str(stage2_path),
        "cohortSize": len(per_set),
        "candidateCards": len(all_rows),
        "packetColumns": list(PACKET_COLUMNS),
        "blindnessGuarantee":
            "Packet columns are a closed allow-list enforced by "
            "labeling.assert_packet_is_blind. No model output, score, rank, "
            "probability or algorithm selection is present.",
        "sets": per_set,
        "skipped": skipped,
        "files": {
            "packetCsv": packet_csv.name,
            "labelTemplateCsv": template_csv.name,
            "reviewHtml": review_html.name,
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--stage2", default=DEFAULT_STAGE2)
    parser.add_argument("--market-date", default=None)
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from backend.db.clients.supabase_client import create_service_role_client

    manifest = build(create_service_role_client(), out_dir=Path(args.out_dir),
                     stage2_path=Path(args.stage2), market_date=args.market_date)
    print(f"{TAG} wrote {args.out_dir} sets={manifest['cohortSize']} "
          f"cards={manifest['candidateCards']} skipped={len(manifest['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
