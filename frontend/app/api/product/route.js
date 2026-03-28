import { mongooseConnect } from "@/lib/mongoose"; 
import Product from "@/models/Product";
import { NextResponse } from "next/server";

export async function GET() {
  await mongooseConnect();
  const products = await Product.find().sort({ createdAt: -1 }); // Fetch all products sorted by newest
  return NextResponse.json(products);
}

  // const featuredProductId = "679c226955387359de7ff2e0";