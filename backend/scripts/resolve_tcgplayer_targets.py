import argparse
import json
from pathlib import Path


DEFAULT_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_bootstrap_report.json")


def resolve_tcgplayer_target_placeholder(set_row: dict) -> dict:
    """
    Placeholder hook for future TCGplayer target discovery.

    This intentionally does not attempt network scraping or advanced matching.
    It marks unresolved sets so bootstrap propagation is not blocked.
    """
    if set_row.get("ready_for_daily_scrape"):
        set_row["target_resolution_note"] = "Already has at least one scrape target."
    else:
        set_row["target_resolution_note"] = "TODO: Resolve CARD_DETAILS_URL and/or SEALED_DETAILS_URL from TCGplayer."
    return set_row


def main() -> int:
    parser = argparse.ArgumentParser(description="Placeholder TCGplayer target resolution hook")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Path to pokemon bootstrap report JSON")
    parser.add_argument("--apply", action="store_true", help="Write updates back to report file")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sets = payload.get("sets", [])

    updated_sets = [resolve_tcgplayer_target_placeholder(dict(row)) for row in sets]
    payload["sets"] = updated_sets

    unresolved = [row for row in updated_sets if not row.get("ready_for_daily_scrape")]
    print(f"[TCGPLAYER-HOOK] unresolved_target_count={len(unresolved)}")

    if args.apply:
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
        print(f"[TCGPLAYER-HOOK] updated report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
