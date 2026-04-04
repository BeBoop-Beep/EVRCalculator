import { NextResponse } from "next/server";
import {
  getCurrentAuthenticatedUserProfile,
  updateCurrentUserProfile,
} from "@/lib/profile/profileQueries";

export async function GET() {
  const result = await getCurrentAuthenticatedUserProfile();

  if (result.error) {
    return NextResponse.json({ message: result.error.message }, { status: result.error.status });
  }

  return NextResponse.json({ profile: result.data }, { status: 200 });
}

export async function PUT(req) {
  let payload;

  try {
    payload = await req.json();
  } catch (error) {
    return NextResponse.json({ message: "Invalid JSON body" }, { status: 400 });
  }

  const result = await updateCurrentUserProfile(payload);

  if (result.error) {
    return NextResponse.json({ message: result.error.message }, { status: result.error.status });
  }

  return NextResponse.json({ profile: result.data }, { status: 200 });
}
