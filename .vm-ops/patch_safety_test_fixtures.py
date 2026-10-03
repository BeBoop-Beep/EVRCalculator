"""Keep existing verdict tests focused on their intended stage after fail-closed fix."""
from pathlib import Path
import hashlib
import sys
root=Path(sys.argv[1])
p=root/'backend/tests/unit/db/services/test_post_scrape_publication_trigger.py'
s=p.read_text();b=s.encode()
assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()=='c2bc9736504bf739d10e7d3e570c1cfff9036c78'
for name in ('test_currency_is_stale_when_canonical_passes_but_explorer_v2_is_stale','test_currency_is_current_only_when_canonical_and_explorer_v2_are_current','test_currency_is_unknown_when_explorer_v2_authority_errors'):
    anchor='def '+name+'(monkeypatch):\n'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'    monkeypatch.setattr(trigger, "_global_market_authority_date", lambda client: "2026-09-20")\n',1)
anchor='def test_default_publication_current_returns_unknown_on_audit_exception(monkeypatch):\n    def broken_audit(client, market_date, phase):'
assert s.count(anchor)==1
s=s.replace(anchor,'def test_default_publication_current_returns_unknown_on_audit_exception(monkeypatch):\n    monkeypatch.setattr(trigger, "_global_market_authority_date", lambda client: "2026-09-01")\n    def broken_audit(*, market_date, phase):',1)
anchor='"backend.scripts.audit_pokemon_market_publication.run_market_publication_audit",\n        broken_audit,'
assert s.count(anchor)==1
s=s.replace(anchor,'"backend.scripts.audit_pokemon_market_publication_resilient.run_market_publication_audit",\n        broken_audit,',1)
p.write_text(s)
print('TEST_FIXTURES_PRESERVE_VERDICT_ASSERTIONS=true')
