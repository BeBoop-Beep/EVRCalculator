# inDex Sentinel — Prompt 7 Auth + Deployment Canaries

Date: 2026-09-11  
Branch: `feature/sentinel-p7-auth-deployment-canaries-20260911`  
Base: accepted P6 head `76bfbec103ba7492e6325b6522a2c1fcd5b23ca3`

## Status

`SENTINEL_P7_CODE_COMPLETE_ACCEPTANCE_PENDING`

Prompt 7 adds detection-only canaries for three failure domains that are not safe self-healing targets:

1. deployed frontend/backend release identity,
2. scraper-VM runtime provenance,
3. authenticated client-side navigation continuity.

No Prompt-7 check is registered for automated recovery.

## 1. Deployment release identity canary

New Sentinel profile: `deploy`

Check key:

- `deployment.release_identity`

The check requires explicit operator authority:

- `SENTINEL_BACKEND_BASE_URL`
- `SENTINEL_FRONTEND_BASE_URL`
- `SENTINEL_EXPECTED_RELEASE_SHA`
- optional `SENTINEL_EXPECTED_RELEASE_BRANCH` (default `main`)
- optional `SENTINEL_EXPECTED_FRONTEND_ENVIRONMENT` (default `production`)

It reads only:

- backend `/health`
- frontend `/api/sentinel/build`

It validates:

- both endpoints are reachable,
- both return their narrow identity contract,
- backend build matches the explicitly expected release SHA,
- frontend build matches the explicitly expected release SHA,
- frontend and backend identify the same build,
- frontend branch matches the expected release branch,
- frontend environment matches the expected environment.

Sentinel never guesses what should be deployed. A release SHA must be supplied by the release process/operator.

The new frontend endpoint exposes only:

```json
{
  "status": "ok",
  "build": "<deployment build identity>",
  "ref": "<git ref or null>",
  "environment": "<deployment environment>",
  "provider": "vercel|local"
}
```

It does not return arbitrary environment variables or secrets and is explicitly `no-store`.

## 2. VM runtime provenance canary

New Sentinel profile: `runtime`

Check key:

- `runtime.vm_provenance`

This implements the production rule established during P1 verification:

> The scraper VM remains on `main`, is based on an approved `main` release, and may carry only a small explicitly approved VM-only overlay.

Raw equality between VM HEAD and remote `main` is intentionally **not** required.

The profile requires:

- `SENTINEL_RUNTIME_REPO_PATH`
- `SENTINEL_RUNTIME_OVERLAY_MANIFEST`

Manifest contract:

```json
{
  "schemaVersion": 1,
  "expectedBranch": "main",
  "approvedMainSha": "<full 40-character approved main SHA>",
  "allowedPaths": [
    "explicit/file",
    "explicit/allowed/directory/"
  ]
}
```

The check reads only Git state:

- current branch,
- current HEAD,
- whether approved main SHA is an ancestor of HEAD,
- committed paths since the approved main SHA,
- current tracked/untracked worktree paths.

It fails on:

- non-`main` branch,
- approved release not being an ancestor,
- malformed observed HEAD,
- any committed/worktree path outside the explicit overlay manifest,
- unavailable Git contract.

The manifest parser rejects parent traversal and requires a full approved-main SHA.

### Activation note

No production VM-overlay manifest is created by P7. The intentional VM-only files must first be inventoried and reviewed; only then should the approved manifest be created on the VM/release side.

## 3. Authenticated navigation browser canary

New explicit command:

```text
npm run sentinel:auth-canary
```

Required runtime-only credentials/configuration:

- `SENTINEL_AUTH_CANARY_BASE_URL`
- `SENTINEL_AUTH_CANARY_EMAIL`
- `SENTINEL_AUTH_CANARY_PASSWORD`
- optional `SENTINEL_AUTH_CANARY_TIMEOUT_MS`

Production URL must be HTTPS. Plain HTTP is accepted only for localhost/loopback local QA.

The canary:

1. logs in through `/api/auth/login` using a dedicated test account,
2. loads Home,
3. establishes an opaque SHA-256-derived identity fingerprint,
4. navigates with real header links through:
   - Market,
   - Rankings,
   - TCGs,
   - Account Settings,
5. waits for the route-triggered `/api/auth/me` reconciliation after each client navigation,
6. verifies `/api/auth/me` still represents the same identity,
7. verifies the rendered header did not regress to a visible `Login` state,
8. verifies the authenticated account menu remains present.

This is designed specifically to detect the reported failure mode where the cookie/backend session can remain valid while route navigation makes the UI appear semi-logged-out.

The command outputs only:

- pass/fail,
- controlled failure code,
- navigation stage,
- opaque identity fingerprint,
- visited routes,
- auth-sync HTTP status codes,
- page-error type names.

It never prints the canary email/password or arbitrary exception messages.

### Activation note

P7 does **not** create a production canary user and does **not** run this synthetic against production. Those are later activation decisions after the P7 code has been released.

## Isolation / recovery boundary

Special profiles are deliberately separate:

- `independent`
- `deploy`
- `runtime`

They are not included in aggregate `all` because each requires a distinct failure-domain or explicit authority contract.

P6 recovery remains supported only for `fast` / `all` and is rejected for P7 detection profiles.

The browser auth canary is also detection-only; it has no recovery path.

## Expected acceptance

Backend Sentinel suite:

- previously accepted through P6: **118 tests**
- P7 additions: **20 tests**
- expected backend total: **138 tests**

P7 backend coverage adds:

- deployment identity success and mismatch classes,
- short operator SHA prefixes,
- backend/frontend reachability and exception redaction,
- branch/environment mismatch,
- approved-main ancestry,
- intentional VM overlay acceptance,
- unapproved committed/worktree drift,
- manifest traversal/full-SHA validation,
- invalid observed HEAD,
- deploy/runtime profile separation,
- explicit configuration guards,
- recovery exclusion for P7 profiles.

Frontend Sentinel contract tests:

- `authCanary.test.mjs`: 7
- `deploymentIdentity.test.mjs`: 3
- expected total: **10 tests**

Additionally require:

- `node --check scripts/sentinel-auth-canary.mjs`
- frontend production build pass

The live authenticated browser canary is **not** part of pre-release acceptance because it requires a deployed endpoint and dedicated canary credentials.

## Production mutation

`NONE`

P7 does not:

- modify Supabase,
- deploy the Sentinel schema,
- modify VM cron,
- switch the VM away from `main`,
- create/modify a canary account,
- execute a production login synthetic,
- change Render settings,
- change Vercel settings,
- deploy Render/Vercel,
- merge or push `main`,
- enable recovery,
- enable AI.

## Next phase after acceptance

Prompt 8 should add the disabled AI escalation adapter/budget guard and whole-system acceptance/activation plan. It must keep the deterministic Sentinel useful with AI completely disabled.

Completion target after local acceptance:

`SENTINEL_P7_CANARIES_ACCEPTED_NOT_DEPLOYED`
