import { NextResponse } from "next/server";
import { createSupabaseAdminClient } from "@/lib/supabaseServer";

export async function GET() {
  const adminClient = createSupabaseAdminClient();
  const { data: products, error } = await adminClient
    .from("products")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    console.error("Error fetching products:", error);
    return NextResponse.json({ message: "Failed to fetch products" }, { status: 500 });
  }

  return NextResponse.json(products);
}