"""Restore exact applied migration statements, retaining original version IDs.

Read-only against Postgres; never applies, repairs, renumbers, or fabricates SQL.
Defaults to a dry-run filesystem plan. All collisions fail before any file write.
psql is needed only with --database-url-env; --export-json is fully offline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

FIRST = "20260905235956"
LAST = "20260906233651"
EXPECTED_COUNT = 89
EXPECTED_MANIFEST = "d988d2e6e877d3373f613d2351e86339"
EXPORT_SQL = f"""BEGIN READ ONLY;
SET LOCAL statement_timeout='20s';
SELECT coalesce(jsonb_agg(jsonb_build_object('version',version,'name',name,
 'statements',statements,'md5',md5(array_to_string(statements,E'\\n')))
 ORDER BY version),'[]'::jsonb)
FROM supabase_migrations.schema_migrations
WHERE version BETWEEN '{FIRST}' AND '{LAST}';
COMMIT;
"""


def validate_export(records: Any, *, verify_checkpoint: bool = True) -> list[dict[str, str]]:
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty migration export list required")
    verified = []
    seen: set[str] = set()
    for row in records:
        version, name = row.get("version"), row.get("name")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]{14}", version):
            raise ValueError("invalid version")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("unsafe migration name; manual reconciliation required")
        if version in seen:
            raise ValueError("duplicate migration version")
        seen.add(version)
        statements = row.get("statements")
        if not isinstance(statements, list) or not statements or not all(isinstance(s, str) for s in statements):
            raise ValueError("original statements missing; placeholders are forbidden")
        content = "\n".join(statements)
        checksum = hashlib.md5(content.encode("utf-8")).hexdigest()
        if checksum != row.get("md5"):
            raise ValueError(f"statement checksum failed for {version}")
        verified.append({"version": version, "name": name, "content": content, "md5": checksum})
    verified.sort(key=lambda row: row["version"])
    signature = hashlib.md5("\n".join(f"{r['version']}:{r['md5']}" for r in verified).encode()).hexdigest()
    if verify_checkpoint and (len(verified) != EXPECTED_COUNT or signature != EXPECTED_MANIFEST):
        raise ValueError("live migration export differs from the inspected 89-record checkpoint")
    return verified


def plan_files(records: list[dict[str, str]], repo: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    pending: list[tuple[Path, str]] = []
    conflicts: list[str] = []
    for folder in (repo / "supabase/migrations", repo / "backend/db/migrations"):
        existing = list(folder.glob("*.sql")) if folder.exists() else []
        for row in records:
            target = folder / f"{row['version']}_{row['name']}.sql"
            by_version = [p for p in existing if p.name.startswith(row["version"] + "_")]
            by_name = [p for p in existing if p.name.endswith("_" + row["name"] + ".sql")]
            if len(by_version) > 1 or any(p != target for p in by_version + by_name):
                conflicts.append(f"{folder.name}: version/name collision for {target.name}")
            elif target.exists():
                if target.read_bytes() != row["content"].encode("utf-8"):
                    conflicts.append(f"{folder.name}: content differs for {target.name}")
            else:
                pending.append((target, row["content"]))
    return pending, conflicts


def write_plan(pending: list[tuple[Path, str]], conflicts: list[str], *, write: bool) -> int:
    if conflicts:
        raise ValueError("; ".join(conflicts))
    if not write:
        return 0
    # Exclusively create files: concurrent work is never overwritten.
    written = []
    try:
        for path, content in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content.encode("utf-8"))
            written.append(path)
    except Exception:
        # Only files successfully created by this invocation are rolled back.
        for path in written:
            path.unlink()
        raise
    return len(written)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--export-json", type=Path)
    source.add_argument("--database-url-env", help="Name of env var containing DB URL; never put a URL on the command line")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--write-files", action="store_true")
    args = parser.parse_args()
    try:
        if args.export_json:
            records = json.loads(args.export_json.read_text(encoding="utf-8"))
        else:
            url = os.environ.get(args.database_url_env)
            if not url:
                raise ValueError("database URL environment variable is unset")
            env = dict(os.environ, PGDATABASE=url, PGOPTIONS="-c default_transaction_read_only=on")
            result = subprocess.run(["psql", "--no-psqlrc", "-qAt", "--set=ON_ERROR_STOP=1"],
                                    input=EXPORT_SQL, text=True, capture_output=True, env=env,
                                    check=True, timeout=30)
            records = json.loads(result.stdout)
        verified = validate_export(records)
        pending, conflicts = plan_files(verified, args.repo)
        written = write_plan(pending, conflicts, write=args.write_files)
        print(json.dumps({"records_verified": len(verified), "files_to_add": len(pending),
                          "files_written": written, "database_writes": 0,
                          "paths": [str(p.relative_to(args.repo)) for p, _ in pending]}, indent=2))
    except Exception as exc:
        # Do not print psql stderr / DSNs. File collisions contain only safe names.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__, "database_writes": 0}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
