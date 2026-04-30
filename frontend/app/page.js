"use client";

import { useEffect } from "react";
import Featured from "@/components/Featured";
import NewProducts from "@/components/Products/NewProducts/NewProducts";
import Footer from "@/components/Footer";

export default function HomePage() {
  const products = null;

  useEffect(() => {
    // Ensure the fade-in effect happens on refresh too
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  return (
    <div>
      <Featured products={products} />
      <NewProducts products={products} />
      <Footer />
    </div>
  );
}  
