import { mongooseConnect } from "@/lib/mongoose"; 
import Merchandise from "@/models/Merchandise";
import { NextResponse } from "next/server";

export async function GET() {
  await mongooseConnect();
  const merchandise = await Merchandise.find().sort({ createdAt: -1 }); // Fetch all merchandise sorted by newest
  return NextResponse.json(merchandise);
}

