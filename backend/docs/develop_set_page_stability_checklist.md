# Develop Set Page Stability Checklist

1. Kill all dev servers.
2. Clear Next cache:
   - `cd frontend && rm -rf .next`
3. Start backend:
   - `d:/EVRCalculator/backend/.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload`
4. Start frontend:
   - `cd frontend && npm run dev`
5. Open these routes:
   - `/TCGs/Pokemon/Sets/white-flare?tab=overview`
   - `/TCGs/Pokemon/Sets/white-flare?tab=insights&section=simulation-cards`
   - `/TCGs/Pokemon/Sets/ascended-heroes?tab=insights&section=rip-score`
   - `/Explore`
6. Network expectations:
   - No page request stuck longer than 8s.
   - No `/cards` 504 responses.
   - No `/market/value-history` requests longer than 15s.
   - No route-killing `RIP_STATISTICS_TARGETS_SNAPSHOT_FAILED` failures.
   - No indefinite logo spinner.
7. UI expectations:
   - Header loads.
   - Overview tab loads.
   - Insights tab loads.
   - Simulation Drivers render when `top_hits` exists.
   - Stale data renders with info bubble timestamp and does not show unavailable messaging for transport fallback.
