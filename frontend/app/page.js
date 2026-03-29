"use client";

import { useEffect, useState } from "react";
import Featured from "@/components/Featured";
import NewProducts from "@/components/Products/NewProducts/NewProducts";

export default function HomePage() {
  const [products, setProducts] = useState(null);

  useEffect(() => {
    async function fetchProducts() {
      const res = await fetch("/api/product");
      const data = await res.json();
      
      setProducts(data);
    }
    fetchProducts();
  }, []);

  useEffect(() => {
    // Ensure the fade-in effect happens on refresh too
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  return (
    <div className="">
      <Featured products={products} />
      <NewProducts products={products} />
    </div>
  );
}  
