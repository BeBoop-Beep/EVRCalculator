from .supabase_client import supabase

def get_set_by_name(name: str):
    return supabase.table("sets").select("*").eq("name", name).single().execute()

def get_set_id_by_name(name: str):
    res = get_set_by_name(name)
    return res.data["id"] if res.data else None
