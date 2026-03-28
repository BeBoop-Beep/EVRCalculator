"use client";
import { useContext, useEffect, useState } from "react";
import { CartContext } from "@/components/Cart/CartContext";
import { useRouter } from "next/navigation";

export default function Cart() {
  const { cartProducts, setCartProducts } = useContext(CartContext);
  const [products, setProducts] = useState([]);
  const [merchandise, setMerchandise] = useState([]);
  const [ripAndShipItems, setRipAndShipItems] = useState([]);
  const [cartTimestamp, setCartTimestamp] = useState(null); // Track timestamp
  const [showPriceReview, setShowPriceReview] = useState(false); // Track price review prompt
  const [shippingCost, setShippingCost] = useState(null); // For shipping cost
  const [salesTax, setSalesTax] = useState(null); // For sales tax
  const router = useRouter();

  useEffect(() => {
    // Check if cart has a stored timestamp in localStorage
    const storedTimestamp = localStorage.getItem("cartTimestamp");
    if (storedTimestamp) {
      setCartTimestamp(Number(storedTimestamp)); // Load the timestamp from localStorage
    }

    // Fetch cart products
    async function fetchCartItems() {
      if (cartProducts.length === 0) {
        setProducts([]);
        setMerchandise([]);
        setRipAndShipItems([]);
        return;
      }

      try {
        // Fetch products
        const productRes = await fetch("/api/product");
        if (!productRes.ok) throw new Error("Failed to fetch products");
        const productData = await productRes.json();

        // Fetch merchandise
        const merchandiseRes = await fetch("/api/merchandise");
        if (!merchandiseRes.ok) throw new Error("Failed to fetch merchandise");
        const merchandiseData = await merchandiseRes.json();

        // Fetch ripAndShipItems
        const ripAndShipRes = await fetch("/api/ripAndShip");
        if (!ripAndShipRes.ok)
          throw new Error("Failed to fetch ripAndShip items");
        const ripAndShipData = await ripAndShipRes.json();

        // Filter items that are in the cart
        const filteredProducts = productData.filter((p) =>
          cartProducts.includes(String(p._id))
        );
        const filteredMerchandise = merchandiseData.filter((m) =>
          cartProducts.includes(String(m._id))
        );
        const filteredRipAndShipItems = ripAndShipData.filter((r) =>
          cartProducts.includes(String(r._id))
        );

        setProducts(filteredProducts);
        setMerchandise(filteredMerchandise);
        setRipAndShipItems(filteredRipAndShipItems);
      } catch (error) {
        console.error("Error fetching cart items:", error);
      }
    }

    fetchCartItems();
  }, [cartProducts]);

  useEffect(() => {
    // If cartProducts are empty, clear the timestamp and products
    if (cartProducts.length === 0) {
      localStorage.removeItem("cart");
      localStorage.removeItem("cartTimestamp"); // Clear timestamp when cart is emptied
      setProducts([]); // Ensure UI updates correctly when cart is emptied
      setCartTimestamp(null); // Reset the timestamp
    } else {
      // Store timestamp only if cart is not empty
      if (!cartTimestamp) {
        const timestamp = Date.now();
        localStorage.setItem("cartTimestamp", timestamp.toString());
        setCartTimestamp(timestamp);
      }
    }
  }, [cartProducts, cartTimestamp]);

  useEffect(() => {
    if (cartTimestamp && Date.now() - cartTimestamp > 24 * 60 * 60 * 1000) {
      setShowPriceReview(true); // If 24 hours passed, prompt to review price changes
    }
  }, [cartTimestamp]);

  function removeItem(product_id) {
    setCartProducts((prev) => prev.filter((id) => id !== product_id));
  }

  function updateQuantity(product_id, amount) {
    setCartProducts((prev) => {
      const updatedCart = [...prev];
      const currentCount = prev.filter((id) => id === product_id).length;

      if (amount > 0) {
        updatedCart.push(product_id);
      } else if (amount < 0 && currentCount > 1) {
        updatedCart.splice(updatedCart.indexOf(product_id), 1);
      } else if (amount < 0 && currentCount === 1) {
        // Remove item completely if last one is being decreased
        return prev.filter((id) => id !== product_id);
      }

      return updatedCart;
    });
  }

  // Handle price review
  function handlePriceReview() {
    // Fetch updated prices from the backend
    async function updatePrices() {
      try {
        const res = await fetch("/api/product");
        if (!res.ok) throw new Error("Failed to fetch products");

        const data = await res.json();
        const updatedProducts = data.filter((p) =>
          cartProducts.includes(String(p._id))
        );

        setProducts(updatedProducts);
        setShowPriceReview(false); // Close review prompt after updating prices
        setCartTimestamp(Date.now()); // Reset the timestamp to now
        localStorage.setItem("cartTimestamp", Date.now().toString());
      } catch (error) {
        console.error("Error fetching updated prices:", error);
      }
    }

    updatePrices();
  }

  const totalPrice = [...products, ...merchandise, ...ripAndShipItems].reduce(
    (sum, item) => {
      const quantity = cartProducts.filter((id) => id === item._id).length;
      return sum + item.price * quantity;
    },
    0
  );

  return (
    <div className="container mx-auto p-6 py-10">
      <h2 className="text-3xl font-bold text-primary mb-6 flex items-center gap-2">
        Cart{" "}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="size-8 text-primary"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 0 0-16.536-1.84M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z"
          />
        </svg>
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-lg shadow-md">
          {cartProducts.length === 0 ? (
            <p className="text-gray-500 text-lg">Your cart is empty.</p>
          ) : (
            <ul>
              {[...products, ...merchandise, ...ripAndShipItems].map(
                (item, index) => {
                  const quantity = cartProducts.filter(
                    (id) => id === item._id
                  ).length;
                  return (
                    <li
                      key={`${item._id}-${index}`}
                      className="flex items-center border-b py-4"
                    >
                      <img
                        src={item.images?.[0] || "/fallback-image.jpg"}
                        alt={item.title}
                        className="w-24 h-24 object-cover rounded-lg"
                      />
                      <div className="ml-4 flex-grow flex justify-between items-center">
                        <div>
                          <h3 className="text-lg font-semibold">
                            {item.title}
                          </h3>
                          <p className="">${item.price.toFixed(2)}</p>
                          <div className="flex items-center mt-2">
                            <button
                              className={`w-8 h-8 flex items-center justify-center rounded-md ${
                                quantity === 1
                                  ? "bg-transparent"
                                  : "bg-gray-200"
                              }`}
                              onClick={() =>
                                quantity === 1
                                  ? removeItem(item._id)
                                  : updateQuantity(item._id, -1)
                              }
                            >
                              {quantity === 1 ? (
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  strokeWidth={1.5}
                                  stroke="currentColor"
                                  className="size-6 text-red-500"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M6 18L18 6M6 6l12 12"
                                  />
                                </svg>
                              ) : (
                                "-"
                              )}
                            </button>
                            <span className="mx-2">{quantity}</span>
                            <button
                              className="w-8 h-8 flex items-center justify-center rounded-md bg-gray-200"
                              onClick={() => updateQuantity(item._id, 1)}
                            >
                              +
                            </button>
                            
                          </div>
                          
                        </div>
                        <p className="font-semibold">
                        ${(item.price * quantity).toFixed(2)}
                      </p>
                      </div>
                    </li>
                  );
                }
              )}
            </ul>
          )}
          
        </div>

        <div className="bg-white p-6 rounded-lg shadow-md">
          <h3 className="text-xl font-semibold mb-4">Summary</h3>

          <div className="flex justify-between items-center border-b pb-2 mb-2">
            <div>Subtotal</div>
            <div className="font-semibold">${totalPrice.toFixed(2)}</div>
          </div>

          <div className="flex justify-between items-center border-b pb-2 mb-2">
            <div>Estimated Shipping Cost</div>
            <div className="font-semibold text-gray-400">--</div>
          </div>

          <div className="flex justify-between items-center border-b pb-2 mb-2">
            <div>Estimated Sales Tax</div>
            <div className="font-semibold text-gray-400">--</div>
          </div>

          <div className="flex justify-between items-center font-semibold text-lg mt-4">
            <div>Estimated Total</div>
            <div>${totalPrice.toFixed(2)}</div>
          </div>

          {showPriceReview && (
            <button
              onClick={handlePriceReview}
              className="w-full bg-blue-500 text-white py-2 mt-4 rounded-md"
            >
              Review Prices
            </button>
          )}

          <button
            onClick={() => router.push("/checkout")}
            className="w-full font-semibold bg-primary text-xl text-neutral-light py-2 mt-4 rounded-md hover:bg-neutral-dark"
          >
            Checkout
          </button>
        </div>
      </div>
    </div>
  );
}
