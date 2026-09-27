"""Bucket 2A: read-only source audit or offline request preparation; never publish.

Usage:
  python -m backend.scripts.run_rip_benchmark_v1 audit-sources
  python -m backend.scripts.run_rip_benchmark_v1 prepare --input candidate.json

This intentionally has no --commit flag. An approved calibration, full semantic
source certification and the coordinated publisher are later gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError, fingerprint, wire
from backend.db.services.rip_benchmark_preview_v1 import candidate_request


def _one(query: Any, name: str) -> dict[str, Any]:
    rows = list(query.limit(2).execute().data or [])
    if len(rows) != 1:
        raise BenchmarkError(f"missing or ambiguous {name}")
    return dict(rows[0])


def audit_sources(client: Any, resolve_bundle: Callable[[str], Any]) -> dict[str, Any]:
    """Seven narrow metadata reads, no simulation artifacts and no writes.

    This proves observed metadata, not full source completeness or effective
    Collector intervals. It does not turn a fresh timestamp into score authority.
    """
    pointer_fields = 'publication_run_id,rankings_generation_id,set_page_generation_id'
    def pointer():
        return _one(client.table('pokemon_overall_rip_current_publication').select(pointer_fields)
                    .eq('scope','pokemon'), 'active release pointer')
    before = pointer()
    release = _one(client.table('pokemon_overall_rip_publication_runs')
        .select('id,model_version,status,market_date,financial_version,chase_version,collector_version,collector_run_id')
        .eq('id',before['publication_run_id']), 'active release header')
    if release['status'] != 'published':
        raise BenchmarkError('active release is not published')
    bundle = resolve_bundle(release['model_version'])  # unknown release raises, no fallback
    opening = _one(client.table('pokemon_rip_stats_snapshot_latest')
        .select('market_date,source_run_fingerprint,updated_at').eq('tcg','pokemon').eq('scope','rip-stats'),
        'Opening Economics publication')
    rankings = _one(client.table('pokemon_explore_rankings_snapshot_latest')
        .select('meta:ranking_payload_json->meta,updated_at').eq('tcg','pokemon').eq('scope','rip-statistics'),
        'Rankings publication')
    collector = _one(client.table('pokemon_collector_appeal_current')
        .select('model_run_id,model_version,as_of_date,promoted_at').eq('scope','pokemon'), 'Collector pointer')
    after = pointer()
    opening_after = _one(client.table('pokemon_rip_stats_snapshot_latest')
        .select('market_date,source_run_fingerprint,updated_at').eq('tcg','pokemon').eq('scope','rip-stats'),
        'Opening Economics recheck')
    if before != after or opening != opening_after:
        raise BenchmarkError('source publication changed during audit; restart')
    snapshot = (rankings.get('meta') or {}).get('snapshot') or {}
    selected_day = opening.get('market_date')
    source_day = snapshot.get('simulationSourceMarketDate')
    return {
        'status': 'source_metadata_audited_not_publish_certified', 'mode': 'read_only',
        'production_publish_enabled': False,
        'observed_release': {'pointer':before, 'header':release,
                            'score_source_policy':bundle.overall_source},
        'opening_economics': opening, 'rankings_snapshot': snapshot,
        'rankings_source_matches_economics': bool(source_day and source_day == selected_day),
        'standalone_collector': collector,
        'embedded_collector_version':release.get('collector_version'),
        'collector_versions_match':collector.get('model_version') == release.get('collector_version'),
        'remaining_proofs': [
            'exact coherent source rows and model raw-score/rank contracts',
            'Collector effective intervals; distinct embedded and standalone lineage',
            'registered era model aggregation; no invented averages',
            'approved benchmark reference policy and calibration',
            'typed global return reference for history chart',
        ],
        'audit_fingerprint':fingerprint({'pointer':before,'opening':opening,'rankings':snapshot,'collector':collector}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('audit-sources', help='Read current source metadata without publishing')
    prepare = sub.add_parser('prepare', help='Validate already assembled offline candidate request')
    prepare.add_argument('--input', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'audit-sources':
            from backend.db.clients.supabase_client import create_short_timeout_service_client
            from backend.db.services.rip_release import bundle_for_model
            result = audit_sources(create_short_timeout_service_client(), bundle_for_model)
        else:
            if args.input.stat().st_size > 9 * 1024 * 1024:
                raise BenchmarkError('candidate input exceeds 9 MiB')
            payload = json.loads(args.input.read_text(encoding='utf-8'))
            result = candidate_request(payload['header'],payload['rows'],
                expected_previous_id=payload.get('expected_previous_id'))
        print(json.dumps(wire(result), indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (BenchmarkError, KeyError, OSError, ValueError) as exc:
        print(json.dumps({'status':'blocked','mode':'read_only','error':str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
