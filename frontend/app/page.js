"use client";

import { useEffect, useState } from "react";
import Featured from "@/components/Featured";
import NewProducts from "@/components/Products/NewProducts/NewProducts";
import NewMerchandise from "@/components/Merchandise/NewMerchandise/NewMerchandise";
import NewRipAndShip from "@/components/RipAndShip/NewRipAndShip/NewRipAndShip";

export default function HomePage() {
  const [products, setProducts] = useState(null);
  const [merchandise, setMerchandise] = useState(null);
  const [ripAndShipItems, setRipAndShipItems] = useState(null);

  useEffect(() => {
    async function fetchProducts() {
      const res = await fetch("/api/product");
      const data = await res.json();
      
      setProducts(data);
    }
    fetchProducts();
  }, []);

  useEffect(() => {
    async function fetchMerchandise() {
      const res = await fetch("/api/merchandise");
      const data = await res.json();
      
      setMerchandise(data);
    }
    fetchMerchandise();
  }, []);

  useEffect(() => {
    async function fetchRipAndShipItems() {
      const res = await fetch("/api/ripAndShip");
      const data = await res.json();
      
      setRipAndShipItems(data);
    }
    fetchRipAndShipItems();
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
      <NewMerchandise merchandise={merchandise} />
      <NewRipAndShip products={ripAndShipItems} />
    </div>
  );
}  
