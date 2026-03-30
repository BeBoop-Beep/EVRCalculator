import Image from "next/image";

export default function CartLayout({
    cartProducts,
    products,
    merchandise,
    removeItem,
    updateQuantity,
    totalPrice,
}) {
    return(
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
          <div className="lg:col-span-2 bg-[var(--surface-panel)] p-6 rounded-lg border border-[var(--border-subtle)]">
            {cartProducts.length === 0 ? (
              <p className="text-[var(--text-secondary)] text-lg">Your cart is empty.</p>
            ) : (
              <ul>
                {[...products, ...merchandise].map((item, index) => {
                  const quantity = cartProducts.filter(
                    (id) => id === item._id
                  ).length;
                  return (
                    <li
                      key={`${item._id}-${index}`}
                      className="flex items-center border-b py-4"
                    >
                      <Image
                        unoptimized
                        src={item.images?.[0] || "/fallback-image.jpg"}
                        alt={item.title}
                        width={96}
                        height={96}
                        className="w-24 h-24 object-cover rounded-lg"
                      />
                      <div className="ml-4 flex-grow flex justify-between items-center">
                        <div>
                          <h3 className="text-lg font-semibold">{item.title}</h3>
                          <div className="flex items-center mt-2">
                            <button
                              className={`w-8 h-8 flex items-center justify-center rounded-md ${
                                quantity === 1 ? "bg-transparent" : "bg-[var(--surface-hover)]"
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
                              className="w-8 h-8 flex items-center justify-center bg-[var(--surface-hover)] rounded-md"
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
                })}
              </ul>
            )}
          </div>
  
          <div className="bg-[var(--surface-panel)] p-6 rounded-lg border border-[var(--border-subtle)]">
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