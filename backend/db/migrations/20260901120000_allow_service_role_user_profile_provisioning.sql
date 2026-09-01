-- OAuth identities are verified by the backend before an application profile
-- is provisioned. Those inserts use the Supabase service-role credential and
-- must be allowed through the invite-only public.users trigger.
--
-- Browser/anon/authenticated Data API inserts remain blocked unless an
-- explicitly trusted database operation enables app.allow_user_insert.

CREATE OR REPLACE FUNCTION public.block_public_users_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  IF current_setting('request.jwt.claim.role', true) = 'service_role' THEN
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
