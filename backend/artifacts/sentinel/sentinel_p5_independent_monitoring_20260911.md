# inDex Sentinel — Prompt 5 Independent Monitoring

Date: 2026-09-11  
Branch: `feature/sentinel-p5-independent-monitoring-20260911`  
Parent: green P4 head `d6dbca89fee57c06d3dc36dc7d87785f7bbaa057`

## Scope

Prompt 5 adds the watch-the-watcher layer without activating production.

It does **not**:

- create/apply a Supabase migration,
- install or change VM cron,
- change the production VM branch,
- configure a third-party monitor,
- enable alert delivery,
- suppress historical alerts,
- deploy Render/Vercel,
- enable recovery,
- enable AI.

## Why two heartbeat paths exist

A watcher running only on the scraper VM cannot report that the VM itself died.
P5 therefore prepares two independent liveness signals:

1. **Durable internal heartbeat**
   - the existing P2 runner upserts `sentinel_component_heartbeats`, keyed by
     `(component, host)`, when persistence is explicitly activated;
   - P5 adds `watcher.component_heartbeat`, which reads one explicit
     component+host and fails when the heartbeat is missing, invalid, too far in
     the future, or older than the configured threshold;
   - the target host is mandatory so a replacement/test host cannot hide a dead
     production VM;
   - the same component+host is rejected as its own independent observer.

2. **External dead-man completion ping**
   - optional `SENTINEL_DEADMAN_PING_URL`;
   - emitted after a Sentinel cycle reaches completion, whether semantic checks
     passed or failed;
   - therefore a missing external ping means the watcher did not run/complete,
     rather than merely that Market/Rankings/etc. were unhealthy;
   - URL is treated as a secret capability URL and is never returned, rendered,
     or persisted in failure output;
   - HTTPS is required.

The two paths are complementary. The external dead-man monitor is the actual
outside-the-VM observer. The Supabase heartbeat is durable corroboration and a
source for an independent observer in another failure domain.

## New independent profile

Profile: `independent`

Check:

- `watcher.component_heartbeat`

Default stale threshold:

- 900 seconds / 15 minutes

The check itself uses `confirm_after=1` because the 15-minute age threshold is
already the confirmation window. Adding another failed cycle would unnecessarily
extend detection.

`independent` is **deliberately excluded** from `all`. The normal VM may run the
aggregate `all` profile, but that must never be interpreted as independent
proof of the VM's own liveness.

## Persistence activation guard

Persistence is now double-gated:

```text
SENTINEL_STATE_WRITES_ENABLED=true
SENTINEL_PERSISTENCE_SCHEMA_READY=true
```

Both are required before `backend.sentinel.operational` can use a persistent
state store. Supplying a persistent store while writes are disabled also fails
closed.

This prepares the runtime for activation without changing today's default:

```text
SENTINEL_STATE_WRITES_ENABLED=false
SENTINEL_PERSISTENCE_SCHEMA_READY=false
SENTINEL_RECOVERY_ENABLED=false
SENTINEL_AI_ENABLED=false
```

## Configuration prepared by P5

```text
SENTINEL_WATCH_COMPONENT=sentinel_vm
SENTINEL_WATCH_HOST=<explicit production VM host>
SENTINEL_HEARTBEAT_MAX_AGE_SECONDS=900
SENTINEL_DEADMAN_PING_URL=<secret HTTPS capability URL>
SENTINEL_DEADMAN_TIMEOUT_SECONDS=5
```

The dead-man URL is excluded from the `SentinelConfig` repr and never appears in
`DeadmanPingResult`.

## Production schema status

Read-only Supabase inspection on 2026-09-11 confirmed **none** of these proposal
tables currently exist in production:

- `sentinel_incidents`
- `sentinel_check_state`
- `sentinel_recovery_attempts`
- `sentinel_component_heartbeats`

No schema mutation was performed.

The existing proposal remains:

`backend/db/proposals/sentinel_kernel_v1.sql`

Its heartbeat table uses a `(component, host)` primary key, so healthy runs update
one latest-state row instead of appending unbounded heartbeat history.

## External observer activation plan — NOT executed

After an approved production release and persistence-schema activation:

1. Choose/configure one external heartbeat/dead-man monitor.
2. Keep its capability URL secret and set it only as
   `SENTINEL_DEADMAN_PING_URL` on the Sentinel runtime.
3. Configure the external service to expect the Sentinel completion ping on the
   same cadence as the future Sentinel cron (target: every 5 minutes).
4. Configure its alert grace around the Sentinel stale contract (target: alert
   once roughly 15 minutes have elapsed without a valid ping).
5. Separately configure external HTTP availability monitors for the production
   frontend and backend `/health`; public semantic correctness remains Sentinel's
   P4 responsibility rather than a keyword-only external monitor's job.
6. Prove the dead-man path once with an explicit controlled ping, then prove a
   missed-ping alert using a controlled pause before relying on it operationally.

No paid AI or paid cron is required for this architecture.

## VM activation plan — NOT executed

The production VM remains **main-only**. Do not check out `develop` or a Sentinel
feature branch on the VM.

After Sentinel is included in an approved `main` release:

1. inventory/retain the approved VM-only overlay;
2. deploy the dedicated Sentinel persistence migration using the normal Supabase
   migration workflow;
3. verify the four Sentinel tables and their service-role-only/RLS contract;
4. set both persistence activation switches;
5. set `SENTINEL_COMPONENT=sentinel_vm`;
6. set `SENTINEL_RUNNER_HOST` to the explicit production VM host;
7. set `SENTINEL_BACKEND_BASE_URL` to the production backend;
8. configure the external dead-man URL;
9. run a one-shot Sentinel cycle and verify exactly one component-heartbeat row;
10. rerun and verify the same `(component,host)` row advances rather than a new
    row being appended;
11. only then install the bounded nonblocking `flock` Sentinel schedule;
12. verify the external dead-man receives cycles;
13. separately activate the P1 dispatcher/watchdog path only after historical
    alert backlog suppression/review, so 143 historical alerts are not blasted.

## Independent observer activation — NOT executed

If/when the DB heartbeat check is scheduled, it must execute outside the watched
VM failure domain. Required identity rules:

```text
observer component/host != watched component/host
SENTINEL_WATCH_COMPONENT=sentinel_vm
SENTINEL_WATCH_HOST=<production VM host>
```

Do not schedule the `independent` profile on the same VM and call that external
monitoring.

## Tests added/extended

Coverage includes:

- fresh heartbeat healthy,
- exact threshold remains healthy,
- stale heartbeat failure,
- missing heartbeat failure,
- malformed/future heartbeat failure,
- self-observation rejected,
- explicit target host required,
- in-memory latest-state overwrite behavior,
- Supabase conflict upsert on `component,host`,
- dead-man unconfigured inert behavior,
- HTTPS-only dead-man URL,
- dead-man 2xx/non-2xx handling,
- exception-path URL secrecy,
- config repr URL secrecy,
- independent registry isolation,
- `all` profile explicitly excluding independent,
- double-gated persistence activation,
- dead-man completion ping after both healthy and unhealthy semantic cycles,
- dead-man delivery failure degrading an otherwise healthy cycle,
- heartbeat SQL primary-key contract.

## Production mutations

`NONE`

## Next gate

Run the full P1–P5 Sentinel unit suite on the user's Python 3.8 environment.
Do not begin P6 safe self-healing until that suite is green.

Completion target:

`SENTINEL_P5_CODE_COMPLETE_INDEPENDENT_MONITOR_ACTIVATION_PENDING`
