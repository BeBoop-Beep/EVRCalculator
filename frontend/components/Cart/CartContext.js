"use client";

const { createContext, useState, useEffect } = require("react");

export const CartContext = createContext({});

export function CartContextProvider({ children }) {
  const [cartProducts, setCartProducts] = useState([]);
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true); // Ensures code only runs on the client
    const ls = typeof window !== "undefined" ? window.localStorage : null;
    if (ls && ls.getItem("cart")) {
      setCartProducts(JSON.parse(ls.getItem("cart")));
    }
  }, []);

  useEffect(() => {
    if (isClient && cartProducts.length > 0) {
      localStorage.setItem("cart", JSON.stringify(cartProducts));
    } else if (isClient) {
      localStorage.removeItem("cart");
    }
  }, [cartProducts, isClient]);

  function addItem(product_id) {
    if (!product_id) {
      console.warn("Invalid product_id added to cart:", product_id);
      return;
    }

    setCartProducts((prev) => {
      const updatedCart = [...prev, product_id];
      if (isClient) localStorage.setItem("cart", JSON.stringify(updatedCart)); 
      return updatedCart;
    });
  }

  if (!isClient) return null; // Prevent rendering until client-side

  return (
    <CartContext.Provider value={{ cartProducts, setCartProducts, addItem }}>
      {children}
    </CartContext.Provider>
  );
}
