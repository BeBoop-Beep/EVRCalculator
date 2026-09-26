# Edition-exact market foundation: executed increment 1

Project: `zwxzxuuawalvwioadhmf`. Execution date: 2026-09-26, America/Phoenix. This is a database deployment receipt, NOT a claim that the public Raw Market chart is fixed.

## Applied migrations
- 20260926173743 market_edition_identity_and_baskets_v3
- 20260926173956 market_basket_guards_v3
- 20260926174201 market_basket_stage_and_approval_v3

Both repository migration directories contain the same blobs. Source files are formatted equivalents of the SQL applied through the Supabase migration connector. The actual version IDs above were read from supabase_migrations.schema_migrations; they were not invented.

## What exists in production now
Four new candidate-only tables: pokemon_market_registry_v3, pokemon_market_basket_versions_v3, pokemon_market_basket_members_v3, pokemon_market_basket_bindings_v3.

Registry seed: 167 independent markets over 156 active roots: Standard 146, First Edition 10, Unlimited 10, Shadowless 1. Zero generic vintage registry rows. Condition is Near Mint; price source is TCGPlayer; currency is USD. Root membership comes from active authority, scope profile from the explicit edition registry, never price availability.

Bindings are selected by reviewed catalog identity and a named printing policy, without reading prices or observation ordering. Equal-priority multiple candidates remain unresolved. All intended canonical slots and counted subset members are retained. Approved definitions become immutable; every insert/update receives edition and physical-identity checks. Approval verifies full intended membership, reviewed fingerprints, and unchanged catalog evidence.

Service role has SELECT/inspect access, but no direct DML on these new tables and no execution grant to definition staging or approval. Anonymous/authenticated access is revoked. Operator-only SECURITY DEFINER helpers use pg_catalog,pg_temp and fully qualified persistent objects. No legacy ACL or function was changed.

## Pilot definitions
All are basket_version=1, effective_from=2026-09-26, definition_basis=current_catalog_staged_v1. These are current catalog definitions, NOT retrospectively proven historical identities.

| Market | Expected slots | Bound | State |
|---|---:|---:|---|
| Fossil First Edition | 62 | 62 | APPROVED |
| Fossil Unlimited | 62 | 62 | APPROVED |
| Hidden Fates Standard | 163 | 163 | APPROVED |
| Neo Destiny Unlimited | 113 | 113 | APPROVED |
| Cosmic Eclipse Standard | 271 | 271 | APPROVED |
| Neo Destiny First Edition | 113 | 112 | DRAFT |
| Base First Edition | 102 | 1 | DRAFT |
| Base Unlimited | 102 | 0 | DRAFT |
| Base Shadowless | 102 | 0 | DRAFT |

The five approved definitions were compared to the existing explicit canonical resolver: all 671 physical variant identities agree exactly. Hidden Fates includes 69 parent + 94 Shiny Vault cards. Cosmic Eclipse's 271 is the current set-value-eligible roster, not a fabricated adjustment to match the page's total catalog count.

Unresolved does NOT mean a quote never exists. Base's inspected root metadata contains 101 unlabeled editions plus one explicitly linked First Edition variant. A separate catalog-only Base Set (Shadowless) record exists. No null edition was guessed to mean Unlimited, no cross-root links were fabricated, and no shared catalog metadata was relabeled. Neo Destiny's unresolved First Edition slot is Shining Noctowl; inspected canonical metadata only linked its Unlimited variant.

## Tests actually executed
22 distinct live PostgreSQL guard checks passed in two rollback-only batches. The first 11-check group was rerun successfully after committing pilot approvals. Tests used the new candidate tables; all test mutations were rolled back. Not mocked pytest and not a GitHub Actions certification run.

Identity checks: complete 62-card First Edition resolution; request replay; independent staging equality; true Unlimited substitution rejected; forged edition label rejected; generic vintage insert rejected; unknown Standard fallback rejected; wrong review fingerprint rejected; complete approval; immutable approved binding; immutable approved header.

Membership/ACL checks: Hidden Fates 69+94 membership; entire omitted subset rejected; single missing slot rejected; shrinking expected denominator rejected; silent backdating rejected; unresolved First Edition approval rejected; actual service-role direct DML denied; service-role definition approval denied; anonymous inspector denied; service-role inspector allowed; rejected test changes preserved original bindings.

The first test handles either a fresh current-day approval or idempotent replay of an already approved current-day definition. The second test intentionally assumes the recorded unresolved Neo Destiny First Edition pilot still needs review; if that input is repaired later, update that negative fixture instead of treating its old absence as a permanent rule.

## Load and serving receipt
Preflight at 17:32:07 UTC: Postgres 17.6, zero other active sessions, zero lock waiters. At 17:49:58 UTC: zero other active sessions, zero lock waiters, four new tables plus indexes allocated 884736 bytes (864 KiB). Batch limits were 6-15 seconds with one-second lock waits and one sequential executor. No query/migration timeout occurred in this increment; negative tests deliberately raised bounded validation errors.

No historical price rows, legacy Set Value rows, existing index rows, application code, VM jobs, or serving pointers were changed. The observed public snapshot remained market_date=2026-09-25, updated_at=2026-09-25T23:34:57.604172+00:00, 156 roots/167 displayed markets.

No cross-session concurrency experiment, full-cohort certification, historical reconstruction, app deployment, or public promotion has been performed. Advisory/per-definition row locking is installed but not represented as a completed concurrency stress test.

## Next increment
1. Audit Base's unlabeled/cross-record edition identities and the missing Neo Destiny First Edition identity against actual source evidence. Do not turn null into Unlimited or borrow editions.
2. Expand staging and human/operator review in bounded market batches; incomplete/ambiguous markets remain unapproved. Registry presence is not valuation coverage.
3. Add scope-aware daily valuation/constituent publications referencing approved immutable bindings, with source/freshness/observation checks and bounded exact-variant reads. Restrict direct writes and test insert/update, atomicity, replay, and metadata drift.
4. Wire global tracked value and performance to the same scoped leaves, including distinct editions and deduplicated parent/subset leaves. Do not sum normalized indexes.
5. Reconstruct a versioned historical candidate with explicit restatement assumptions and real observations; current definitions cannot silently serve as point-in-time historical evidence.
6. Validate a complete generation, API contracts, daily automation and runtime SHA before guarded cutover. Until then the legacy public pipeline still has its previously identified defects.

Do not delete or overwrite existing legacy data as a shortcut. Do not directly reapply an already-recorded migration. Resume from live schema/version inspection and these receipts.
