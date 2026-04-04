import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;

const assertSupabaseEnv = (keyName, keyValue) => {
  if (!supabaseUrl || !keyValue) {
    throw new Error(`Missing Supabase configuration: NEXT_PUBLIC_SUPABASE_URL or ${keyName}`);
  }
};

export const createSupabaseAnonClient = () => {
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  assertSupabaseEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", anonKey);

  return createClient(supabaseUrl, anonKey, {
    auth: { persistSession: false },
  });
};

export const createSupabaseAdminClient = () => {
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  assertSupabaseEnv("SUPABASE_SERVICE_ROLE_KEY", serviceRoleKey);

  return createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false },
  });
};
