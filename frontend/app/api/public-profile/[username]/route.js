import { NextResponse } from "next/server";
import { getPublicProfileByUsername } from "@/lib/profile/profileQueries";

export async function GET(req, { params }) {
  const { username } = await params;
  const result = await getPublicProfileByUsername(username || "");

  if (result.error) {
    return NextResponse.json({ message: result.error.message }, { status: result.error.status });
  }

  return NextResponse.json({ profile: result.data }, { status: 200 });
}
