import { mongooseConnect } from "@/lib/mongoose"; 
import RipAndShipItems from "@/models/RipAndShipItems";
import { NextResponse } from "next/server";

export async function GET() {
  await mongooseConnect();
  const ripAndShip = await RipAndShipItems.find().sort({ createdAt: -1 }); // Fetch all RipAndShip sorted by newest
  return NextResponse.json(ripAndShip);
}
