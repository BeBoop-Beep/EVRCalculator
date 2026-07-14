# PostgREST schema-cache recovery

If PostgreSQL is healthy but the Data API persistently returns `PGRST002 Could
not query the database for the schema cache`, an operator may run the standard
Supabase SQL recovery command in the SQL editor:

```sql
notify pgrst, 'reload schema';
```

This is an operational recovery step, not application behavior. Application
code must not execute schema reloads automatically, and no public reload
endpoint should be added. Use the command only after confirming PostgreSQL is
healthy while PostgREST continues returning `PGRST002`. Afterward, verify that
a simple REST table read or RPC request returns HTTP 200.
