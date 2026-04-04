import { NextResponse } from "next/server";
import { getCurrentUserPortfolioDashboardData } from "@/lib/profile/portfolioDashboardQueries";

export async function GET() {
  const result = await getCurrentUserPortfolioDashboardData();

  if (result.error) {
    return NextResponse.json({ message: result.error.message }, { status: result.error.status });
  }

  return NextResponse.json({ dashboard: result.data }, { status: 200 });
}
