-- Supabase/PostgREST can expose the JWT role through either the legacy
-- request.jwt.claim.role setting or the request.jwt.claims JSON payload.
-- auth.role() normalizes both representations, so use it for the trusted
-- service-role bypass instead of reading only the legacy setting directly.

CREATE OR REPLACE FUNCTION public.block_public_users_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  IF auth.role() = 'service_role' THEN
    RETURN NEW;
  END IF;

  IF current_setting('app.allow_user_insert', true) IS DISTINCT FROM 'on' THEN
    RAISE EXCEPTION 'Account creation is currently invite-only.'
      USING ERRCODE = '42501';
  END IF;

  RETURN NEW;
END;
$function$;

COMMENT ON FUNCTION public.block_public_users_insert() IS
  'Blocks direct public.users inserts while allowing verified backend service-role profile provisioning.';
