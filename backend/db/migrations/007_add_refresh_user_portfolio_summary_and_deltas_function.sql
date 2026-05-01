BEGIN;

CREATE OR REPLACE FUNCTION public.refresh_user_portfolio_summary_and_deltas(
    p_user_id uuid,
    p_snapshot_date date DEFAULT (now() AT TIME ZONE 'America/Phoenix')::date
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM public.refresh_user_collection_summary_live(p_user_id);

    INSERT INTO public.user_portfolio_value_history (
        user_id,
        snapshot_date,
        portfolio_value
    )
    SELECT
        user_id,
        p_snapshot_date,
        portfolio_value
    FROM public.user_collection_summary
    WHERE user_id = p_user_id
    ON CONFLICT (user_id, snapshot_date)
    DO UPDATE SET
        portfolio_value = EXCLUDED.portfolio_value;

    PERFORM public.refresh_user_collection_deltas(p_user_id);
END;
$$;

COMMIT;
