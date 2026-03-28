import Link from "next/link";
import { CartContext } from "./Cart/CartContext";
import { useContext } from "react";

export default function NavBar() {
  const { cartProducts } = useContext(CartContext);
  return (
    <div className="bg-neutral-light py-4">
      <div className="container mx-auto flex justify-between items-center px-4">
        <nav className="flex space-x-8">
          <Link href="/products" className="text-primary hover:text-accent">
            Product Store
          </Link>
          <Link href="/merchandise" className="text-primary hover:text-accent">
            Merchandise
          </Link>
          <Link href="/ripAndShip" className="text-primary hover:text-accent">
            Rip &amp; Ship
          </Link>
          <Link href="/priceCheck" className="text-primary hover:text-accent">
            Price Check
          </Link>
        </nav>
        <Link href="/cart" className="text-primary hover:text-accent flex">
          <span className="flex gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="size-6 flex"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 0 0-16.536-1.84M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z"
              />
            </svg>
            ({cartProducts?.length ?? 0})
          </span>
        </Link>
      </div>
    </div>
  );
}
