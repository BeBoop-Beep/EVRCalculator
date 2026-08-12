"use client";

const { createContext, useState, useEffect } = require("react");

export const CartContext = createContext({});

/**
 * NOTE ON SERVER RENDERING
 * ------------------------
 * This provider wraps the ENTIRE application in `app/layout.js`, so anything
 * it refuses to render is missing from every page.
 *
 * It used to end with `if (!isClient) return null`, which meant the server
 * emitted no HTML at all for any route — not the nav, not `<main>`, not a
 * single `<h1>` — and the whole document was reconstructed client-side from
 * the React Flight payload. `isClient` is only needed to gate `localStorage`,
 * and every `localStorage` access below already lives in an effect or an event
 * handler, both of which are client-only by construction. Rendering the
 * provider on the server is therefore safe: `cartProducts` starts as `[]` in
 * the server render AND in the first client render (the stored cart is loaded
 * in the effect below, after hydration), so the two renders match.
 *
 * Do not reintroduce a render-time client-only bail-out here.
 */
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

  return (
    <CartContext.Provider value={{ cartProducts, setCartProducts, addItem }}>
      {children}
    </CartContext.Provider>
  );
}
