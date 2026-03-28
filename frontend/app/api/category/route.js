import { mongooseConnect } from "@/lib/mongoose"; 
import Category from "@/models/Category";
import { NextResponse } from "next/server";

export async function GET() {
  await mongooseConnect();
  const categories = await Category.find().sort({ createdAt: -1 }); // Fetch all products sorted by newest
  return NextResponse.json(categories);
}
