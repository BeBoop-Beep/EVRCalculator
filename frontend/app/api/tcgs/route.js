import { NextResponse } from "next/server";
import { getTcgOptions } from "@/lib/profile/profileQueries";

export async function GET() {
  const result = await getTcgOptions();

  if (result.error) {
    return NextResponse.json({ message: result.error.message }, { status: result.error.status });
  }

  return NextResponse.json({ tcgs: result.data }, { status: 200 });
}
