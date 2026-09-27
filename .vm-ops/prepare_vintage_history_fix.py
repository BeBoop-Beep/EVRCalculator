"""Apply exact-source integration edits in an isolated worktree, before tests.

Used once by the controlled preparation workflow. It never touches production.
"""
from pathlib import Path
import hashlib
import shutil

ROOT=Path(__file__).resolve().parents[1]
def blob(text):
    data=text.encode();return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def once(text,old,new):
    if text.count(old)!=1:raise RuntimeError('source anchor changed; refusing edit')
    return text.replace(old,new,1)

path=ROOT/'backend/scripts/build_pokemon_explore_set_value_snapshot.py'
s=path.read_text()
if 'from backend.db.services.pokemon_edition_history import' not in s:
    if blob(s)!='5ab57567ed0d63ea62c57462493d6f8546c054b7':raise RuntimeError('publisher source changed')
    s=once(s,'MARKET_READY_VIEW = ','''from backend.db.services.pokemon_edition_history import (
    read_edition_history_batch,
    refresh_edition_history_for_markets,
)

MARKET_READY_VIEW = ''')
    a=s.index('def _load_scoped_certified_histories(');b=s.index('\ndef _load_canonical_histories(',a)
    part=s[a:b]
    old='''        response = client.rpc(
            CANONICAL_HISTORY_RPC,
            {
                "p_root_set_ids": batch,
                "p_start_date": CANONICAL_HISTORY_START,
                "p_end_date": limit_date,
            },
        ).execute()
        for row in list(response.data or []):'''
    new='''        rows = read_edition_history_batch(
            client, batch, start_date=CANONICAL_HISTORY_START, end_date=limit_date,
        )
        for row in rows:'''
    part=once(part,old,new);s=s[:a]+part+s[b:]
    s=once(s,'''    histories = _load_canonical_histories(
        client,
        sets,
        through_date=market_date,
    )''','''    # Never depend on the separately paused legacy maintenance cron to make
    # edition aggregate histories current. One root/date per transaction, under
    # the canonical publication admission lock. Dry runs remain read-only.
    edition_receipts = []
    if commit and str(market_date)[:10] >= "2026-09-25":
        edition_receipts = refresh_edition_history_for_markets(
            client, sets, market_date=str(market_date)[:10],
        )

    histories = _load_canonical_histories(
        client,
        sets,
        through_date=market_date,
    )
    if commit and str(market_date)[:10] >= "2026-09-25":
        for market in sets:
            if (market.get("market_scope") in ("first_edition", "unlimited", "shadowless")
                    and market.get("market_current_certification_status") == "CERTIFIED"):
                points = histories.get(market["market_key"]) or []
                if not points or str(points[-1].get("snapshot_date"))[:10] != str(market_date)[:10]:
                    raise RuntimeError("edition_history_not_current:" + market["market_key"])
''')
    s=once(s,'''    _attach_initial_selected_set_movers(client, row)
    if commit:''','''    if edition_receipts:
        row["payload_json"].setdefault("meta", {}).setdefault("publicationDiagnostics", {})["editionHistory"] = {
            "targetDate": str(market_date)[:10],
            "verifiedRoots": len(edition_receipts),
            "rawV2Parity": all(r["raw_v2_equal"] for r in edition_receipts),
            "perMarketDateValidated": True,
        }
        row["payload_size_bytes"] = len(json.dumps(row["payload_json"], separators=(",", ":")).encode())
    _attach_initial_selected_set_movers(client, row)
    if commit:''')
    path.write_text(s)

path=ROOT/'backend/tests/unit/scripts/test_market_vintage_scope_override.py'
s=path.read_text()
if 'class _HistoryRPCQuery' not in s:
    if blob(s)!='7c4780e15559b03648627df22a4cca200aefd610':raise RuntimeError('vintage fixtures changed')
    s=once(s,'class _Client:', '''class _HistoryRPCQuery:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: (r["set_id"], r["market_scope"], r["market_date"]))
        self.bounds = None
    def order(self, *_args):
        return self
    def range(self, start, end):
        self.bounds = (start, end)
        return self
    def execute(self):
        rows = self.rows if self.bounds is None else self.rows[self.bounds[0]:self.bounds[1]+1]
        return SimpleNamespace(data=rows, count=len(self.rows))


class _Client:''')
    s=once(s,'    def rpc(self, name, params):','    def rpc(self, name, params, **kwargs):')
    s=once(s,'        return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))','        return _HistoryRPCQuery(rows)')
    path.write_text(s)

migration='20260927014000_add_dated_edition_history_refresh.sql'
shutil.copyfile(ROOT/'supabase/migrations'/migration,ROOT/'backend/db/migrations'/migration)
print('INTEGRATION_EDITS_AND_MIGRATION_MIRROR_PREPARED=true')
