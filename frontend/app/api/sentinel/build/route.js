import { NextResponse } from "next/server";

import { buildDeploymentIdentity } from "@/lib/sentinel/deploymentIdentity.mjs";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(buildDeploymentIdentity(), {
    status: 200,
    headers: {
      "cache-control": "no-store, max-age=0",
    },
  });
}
