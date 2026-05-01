# Backend API Deployment

This file documents the deployable web API runtime under [backend/api/main.py](backend/api/main.py).

## Install

Use only the API runtime requirements:

```bash
pip install -r backend/requirements.txt
```

## Start Command

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
```

## Required Environment Variables

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`
- `JWT_SECRET`
- `ALLOWED_ORIGINS`
- `FRONTEND_BASE_URL`

## Optional Environment Variables

- `WAITLIST_TOKEN_HASH_SECRET` when waitlist verification is enabled
- `RESEND_API_KEY` when waitlist email delivery is enabled
- `WAITLIST_EMAIL_PROVIDER` when waitlist email delivery is enabled
- `APP_ENV` or `ENVIRONMENT` or `NODE_ENV` to signal production runtime behavior

## Allowed Origins Format

Set `ALLOWED_ORIGINS` as a comma-separated list, for example:

```text
https://inthedex.io,https://www.inthedex.io,http://localhost:3000
```

## Scope

This start command is for the public FastAPI service only.

Do not use scraper or simulation commands for the web API process. In particular, these remain separate worker/local flows:

- `backend/scripts/run_pokemon_set_scrape.py`
- `backend/scripts/run_all_v2_sets.py`
- `backend/jobs/evr_runner.py`
- `infra/local/run_simulations.sh`