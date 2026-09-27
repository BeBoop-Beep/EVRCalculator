"""Align repository history to the version returned by apply_migration.

This changes filenames/references only, never SQL contents or a database.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
old='20260927014000_add_dated_edition_history_refresh.sql'
new='20260927014248_add_dated_edition_history_refresh.sql'
for directory in ('supabase/migrations','backend/db/migrations'):
    src=ROOT/directory/old; dest=ROOT/directory/new
    if src.exists():
        if dest.exists():
            assert dest.read_bytes()==src.read_bytes()
            src.unlink()
        else:
            src.rename(dest)
    assert dest.is_file()
for relative in ('.vm-ops/prepare_vintage_history_fix.py','backend/tests/integration/test_edition_history_dated_repair.py'):
    path=ROOT/relative
    text=path.read_text()
    path.write_text(text.replace(old,new))
print('APPLIED_MIGRATION_VERSION_ALIGNED=20260927014248')
