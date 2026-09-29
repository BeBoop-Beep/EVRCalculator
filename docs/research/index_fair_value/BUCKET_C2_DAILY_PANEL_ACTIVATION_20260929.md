# Bucket C2 — daily panel activation

## Reviewed runtime

The full-panel collector accepts only the frozen 207-card Core Panel V1,
fingerprint `9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`,
at exactly 19 listings/card and a 4,500-credit hard cap. It reuses a provider ID
only when canonical card, TCGplayer product and English-language identity all
match. Unresolved identities are looked up once and persisted through the
existing conflict-checked identity store.

Seller identity requires the dedicated persistent
`ACTIVE_SUPPLY_SELLER_HASH_KEY`. It has no provider-key fallback. The installer
generates a 256-bit key only on an explicit first-install command, persists it in
the VM's mode-600 `backend/.env`, never prints it, and never rotates or replaces
an existing assignment. Runs retain only its one-way fingerprint for continuity
diagnostics.

The VM schedule uses `CRON_TZ=America/Phoenix`: primary 21:10, one retry at
21:40, and missing-run health materialization at 22:10. The runtime holds the
dedicated panel lock, shared `/tmp/pkmnprices-api.lock`, and heavy post-scrape
publication lock. It refuses the database safety hold and refuses any checkout
whose HEAD differs from the installer-written release SHA.

No page 2 is requested. Truncation remains bounded-depth/lower-bound evidence.
Turnover and Market Scarcity remain disabled.

## Full dry run

The production REST/schema dry run represented all 207 frozen variants and made
zero provider calls, spent zero credits and wrote zero rows. Ten exact identities
were reusable and 197 were unresolved, producing a conservative first-day ceiling
of `207 * 19 + 197 = 4,130` credits. No cached identity mismatches were found.
The typed snapshot/listing columns were reachable.

## Activation state

VM deployment is fail-closed pending host authentication. Direct SSH correctly
refused because the stored host key differs from the key currently presented by
`129.146.189.32` (`SHA256:2lXV6C9Ul5Lo3Vc3kmpxYIYl7DcS0cqbK1RaST4hOpQ`).
That key was not bypassed or trusted without independent verification. Therefore
the dedicated VM credential, direct PostgreSQL index proof, cron conflict audit,
release pin, cron installation and first live daily observation were not run.

After independent host-key verification and PR review, activation order is:

1. deploy the reviewed commit to the VM checkout;
2. run `infra/oracle/install_active_supply_credentials.sh --apply --generate-if-missing`;
3. run `infra/oracle/install_active_supply_panel_cron.sh` (verify-only);
4. run `infra/oracle/install_active_supply_panel_cron.sh --apply`;
5. invoke `infra/oracle/run_active_supply_panel.sh` once for the first Phoenix date;
6. audit 207 snapshot states, exact-identity failures, seller privacy, typed row
   counts, credits under 4,500, and database health/advisors.

Current terminal state: `BUCKET_C2_BLOCKED`. The code is ready for the remaining
activation preflights, but VM identity must be independently verified first. It
is not yet `BUCKET_C2_DAILY_PANEL_ACTIVE`.
