# Pokémon analytics production-schema reconciliation

Production contains the four Pokémon analytics tables and publication function,
but migration history lacks `20260818032645` and `20260818032648`. The tables
currently contain zero rows. This means dashboard SQL changed production schema
without registering migration history; it does not mean either analytical
snapshot was published.

Do not rerun the migrations, push the database, recreate objects, or edit
`supabase_migrations.schema_migrations` manually.

The exact read-only inventory query is checked in at
`backend/scripts/assets/pokemon_level_schema_inventory.sql`. It reads column
types/nullability/defaults, normalized catalog constraint/index definitions,
RLS, policies, grants, the Market trigger, function body/security/grants, and
migration history. Run it with SELECT-only `db query` and save the JSON value:

```powershell
npx.cmd --yes supabase@latest db query --linked --file backend/scripts/assets/pokemon_level_schema_inventory.sql
```

Also inspect the ordinary migration list with:

```powershell
npx.cmd --yes supabase@latest migration list --linked
```

Run the offline comparison:

```powershell
python backend/scripts/audit_pokemon_level_schema_parity.py inventory.json
```

The tool exits nonzero and prints exact differences if columns, constraints,
indexes, RLS, policies, grants, function security/body, or execution grants
differ. It prints repair commands only when schema parity is exact. The CLI's
current help establishes the repair form as:

```powershell
npx.cmd --yes supabase@latest migration repair 20260818032645 20260818032648 --status applied --linked
```

That command is an operator recommendation only. This hardening task must not
execute it.

## Foreign-key index review

V1 constituent reads are led by `snapshot_id`. The primary key covers
`(snapshot_id, set_id)`, and the unique constraint covers
`(snapshot_id, calculation_run_id)`. Current publication and audit paths do not
filter directly by `set_id` or `calculation_run_id`, so standalone covering
indexes would add write cost without serving a current query. They are deferred
until a set-led or run-led history query exists and its plan demonstrates need.
