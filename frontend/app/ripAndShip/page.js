"use client";
import { CartContext } from "@/components/Cart/CartContext";
import Spinner from "@/utils/Spinner";
import { useContext, useEffect, useState } from "react";

export default function RipAndShip() {
  const [ripAndShipItems, setRipAndShipItems] = useState([]);
  const {addItem} = useContext(CartContext);

  useEffect(() => {
    async function fetchRipAndShipItems() {
      try {
        const res = await fetch("/api/ripAndShip");
        if (!res.ok) {
          throw new Error("Failed to fetch ripAndShipItems");
        }
        const data = await res.json();
        setRipAndShipItems(data);
      } catch (error) {
        console.error("Error fetching ripAndShipItems:", error);
      }
    }
    fetchRipAndShipItems();
  }, []);

  useEffect(() => {
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  if (ripAndShipItems.length === 0) {
    return <Spinner />;
  }

  function addProductToCart(ripAndShipItem) {
    if (ripAndShipItem && ripAndShipItem._id) {
        addItem(ripAndShipItem._id);
    } else {
        console.error("Product object or _id is missing!");
    }
}


  return (
    <div className="container mx-auto px-6 py-10">
      {/* Flex container to hold the title and make sure it centers in the remaining space */}
      <div className="flex w-full mb-6">
        {/* Title container with flex-grow to take up remaining space */}
        <div className="flex-grow flex justify-center">
          <h2 className="text-3xl font-bold text-gray-900 text-center">
            Rip And Ship
          </h2>
        </div>
      </div>

      {/* Flexbox layout for sidebar and ripAndShipItems */}
      <div className="flex space-x-8">
        {/* RipAndShipItems Grid - using flex-grow to take remaining space */}
        <div className="flex-grow ml-4">
          {/* 3-Column Grid for RipAndShipItems */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {ripAndShipItems.map((ripAndShipItem, index) => (
              <div
                key={index}
                className="group relative bg-white p-4 rounded-2xl shadow-lg hover:shadow-xl transition-all hover:cursor-pointer"
              >
                {/* Make the image and ripAndShipItems title clickable */}
                <a
                  href={ripAndShipItem.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full block"
                >
                  <div className="w-full h-72 bg-gray-100 rounded-lg overflow-hidden flex justify-center items-center ">
                    <img
                      src={ripAndShipItem.images?.[0] || "/fallback-image.jpg"}
                      alt={ripAndShipItem.title}
                      className="h-full object-cover group-hover:scale-105 transition-transform"
                    />
                  </div>
                  <div className="mt-4 text-center">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {ripAndShipItem.title}
                    </h3>
                    <p className="text-gray-600 mt-1">${ripAndShipItem.price}</p>
                  </div>
                </a>

                {/* Add To Cart button below the image */}
                <div className="mt-3 text-center">
                  <a
                    href={ripAndShipItem.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block bg-black text-white px-4 py-2 rounded-lg hover:bg-gray-800 transition-transform duration-100 transform active:scale-90 active:shadow-lg"
                    onClick={() => addProductToCart(ripAndShipItem)}
                  >
                    Add To Cart
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
