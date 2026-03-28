// app/products/[slug]/page.js
"use client";
import { useSearchParams } from "next/navigation";
import ProductDetails from "@/components/Products/ProductDetails";

export default function ProductDetailsPage() {
  const searchParams = useSearchParams();
  const productData = searchParams.get("data"); // Get the product data from the query parameter

  // Parse the product data
  const product = JSON.parse(decodeURIComponent(productData));

  if (!product) {
    return <div>Product not found.</div>;
  }

  return <ProductDetails product={product} />;
}