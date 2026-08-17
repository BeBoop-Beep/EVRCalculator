# Follow-up: `create_public_read_client()` is not a public/anon client

Status: OPEN. Recorded 2026-08-16. **Deliberately not fixed** as part of the
half-booster-box `simulation_result_unavailable` patch.

## What was observed

`backend/db/clients/supabase_client.py:161`:

```python
def create_public_read_client():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(postgrest_client_timeout=_PUBLIC_READ_TIMEOUT_SECONDS),
    )
```

`SUPABASE_KEY` is the **service-role** key. The only thing "public" about this
client is its read timeout. It is a full service-role client that bypasses RLS.

## Why this is not a publication blocker

It is a naming and test-hygiene problem, not an exposure one:

* The anon-key verification run against the chase-economics table was done with
  a **real anon key**, and it correctly **denied** access. Public/anon exposure
  of `pokemon_set_chase_economics_snapshot_latest` was therefore genuinely
  tested and genuinely negative.
* No new surface was granted by the Entertainment Cost / chase work.

## The actual risk

A future security test that reaches for `create_public_read_client()` because
of its name will read through RLS with service-role privileges, see the rows,
and conclude either "the data is public" (false alarm) or - far worse in the
other direction - use it as the *proof of denial* and conclude "anon cannot
read this" when the check never exercised the anon path at all. The name makes
the wrong test look like the right one.

## What the follow-up should do

1. Enumerate every caller of `create_public_read_client()` and classify each as
   (a) genuinely wanting service-role reads with a shorter timeout, or
   (b) actually wanting an anon/public-key client.
2. Rename the (a) callers' helper to something that says what it is, e.g.
   `create_short_timeout_service_client()`.
3. If any (b) caller exists, add a real anon-key client built from the
   publishable/anon key and move those callers onto it.
4. Add a test asserting that any helper whose name contains `public` or `anon`
   is NOT constructed from `SUPABASE_KEY`, so the confusion cannot come back.

## Out of scope

Changing which key any current caller uses. This ticket is an audit first; the
behavioural change (if any) follows from step 1.
