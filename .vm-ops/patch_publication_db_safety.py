"""Apply the reviewed publication fixes only to exact inspected source blobs."""
from pathlib import Path
import hashlib
import shutil
import sys


def git_blob(text):
    b=text.encode();return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()


def replace_once(text, old, new):
    if text.count(old)!=1:
        raise RuntimeError('source anchor changed; refusing patch')
    return text.replace(old,new,1)

root=Path(sys.argv[1]); bundle=Path(__file__).parent
path=root/'backend/db/services/post_scrape_publication_trigger.py'
s=path.read_text()
assert git_blob(s)=='5af2da4f8c8ab6d50ce81bd34b75b095ce80ed03','trigger source changed'
s=replace_once(s,'logger = logging.getLogger(__name__)',
'''from backend.db.services.production_db_safety import (
    maintenance_hold_active,
    require_maintenance_allowed,
)

logger = logging.getLogger(__name__)''')
s=replace_once(s,'''    target = str(market_date)[:10]
    try:
        global_market_date = _global_market_authority_date(client)''',
'''    if maintenance_hold_active():
        return PublicationCurrencyStatus.UNKNOWN
    target = str(market_date)[:10]
    try:
        global_market_date = _global_market_authority_date(client)''')
s=replace_once(s,'''            "falling back to full audit: %s: %s",''',
'''            "refusing heavier fallback audit: %s: %s",''')
s=replace_once(s,'''            type(exc).__name__,
            exc,
        )
    else:
        if global_market_date is None or global_market_date < target:''',
'''            type(exc).__name__,
            exc,
        )
        return PublicationCurrencyStatus.UNKNOWN
    else:
        if global_market_date is None or global_market_date < target:''')
s=replace_once(s,'''        if audit_runner is None:
            from backend.scripts.audit_pokemon_market_publication import (
                PHASE_POST_SCRAPE,
                run_market_publication_audit,
            )
            audit_runner = run_market_publication_audit
        else:
            from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE

        report = audit_runner(client, market_date=market_date, phase=PHASE_POST_SCRAPE)''',
'''        from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE
        if audit_runner is None:
            # The CLI already uses this adapter. Use the same compact reads and
            # current publication contracts for the pre-launch check as well.
            from backend.scripts.audit_pokemon_market_publication_resilient import (
                run_market_publication_audit,
            )
            report = run_market_publication_audit(
                market_date=market_date, phase=PHASE_POST_SCRAPE,
            )
        else:
            # Preserve the injected test/operator callable contract.
            report = audit_runner(client, market_date=market_date, phase=PHASE_POST_SCRAPE)''')
s=replace_once(s,'''def _default_popen(args: list, *, cwd: str, log_path: Path) -> subprocess.Popen:
    log_file = open(log_path, "a", encoding="utf-8")''',
'''def _default_popen(args: list, *, cwd: str, log_path: Path) -> subprocess.Popen:
    require_maintenance_allowed()
    log_file = open(log_path, "a", encoding="utf-8")''')
s=replace_once(s,'''    market_date = str(market_date)
    logger.info("%s batch complete market_date=%s", TRIGGER_TAG, market_date)''',
'''    if maintenance_hold_active():
        result["status"] = "skipped_database_safety_hold"
        return result

    market_date = str(market_date)
    logger.info("%s batch complete market_date=%s", TRIGGER_TAG, market_date)''')
path.write_text(s)
path=root/'backend/scripts/rebuild_snapshots_after_scrape.sh'
s=path.read_text()
assert git_blob(s)=='4db32c73cbe653857680bda6af134e1e582a5e48','wrapper source changed'
s=replace_once(s,'set -euo pipefail\n', '''set -euo pipefail

# This state is outside Git and is intentionally not removed by deployment or
# cron restoration. Also fences a direct manual launch of this wrapper.
if [[ -e /home/ubuntu/state/db-safety/hold.json || -L /home/ubuntu/state/db-safety/hold.json ]]; then
  printf '[post-scrape-publication] production_database_safety_hold_active; no database work launched\\n'
  exit 75
fi
''')
path.write_text(s)
shutil.copyfile(bundle/'production_db_safety.py',root/'backend/db/services/production_db_safety.py')
shutil.copyfile(bundle/'test_publication_db_safety.py',root/'backend/tests/unit/db/services/test_publication_db_safety.py')
print('PATCH_SOURCE_ANCHORS_VERIFIED=true')
