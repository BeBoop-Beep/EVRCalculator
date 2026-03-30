"use client";

import { useContext, useState } from "react";
import { CartContext } from "@/components/Cart/CartContext";
import { useRouter } from "next/navigation";
import { loadStripe } from "@stripe/stripe-js";

export default function Checkout() {
  const { cartProducts } = useContext(CartContext);
  const [step, setStep] = useState(1);
  const [shippingInfo, setShippingInfo] = useState({
    name: "",
    email: "",
    address: "",
    city: "",
    zip: "",
  });

  // console.log(cartProducts);
  const [paymentInfo, setPaymentInfo] = useState({
    method: "card", // "card" or "paypal"
    cardNumber: "",
    expiry: "",
    cvv: "",
  });
  const [shippingCost, setShippingCost] = useState(0);
  const [tax, setTax] = useState(0);
  const router = useRouter();

  const subtotal = cartProducts.reduce((total, item) => total + item.price, 0);
  const total = subtotal + shippingCost + tax;

  const handleShippingChange = (e) => {
    setShippingInfo({ ...shippingInfo, [e.target.name]: e.target.value });
  };

  const handlePaymentChange = (e) => {
    setPaymentInfo({ ...paymentInfo, [e.target.name]: e.target.value });
  };

  const handleNextStep = () => {
    if (step === 1) {
      setShippingCost(5); // Placeholder shipping calculation
      setTax(subtotal * 0.08); // 8% estimated tax
    }
    setStep(step + 1);
  };

  const handleSubmitOrder = async () => {
    // console.log("Order placed:", { shippingInfo, paymentInfo, total });
    router.push("/order-confirmation");
  };

//   console.log("Subtotal:", subtotal);
// console.log("Shipping Cost:", shippingCost);
// console.log("Tax:", tax);
// console.log("Total:", total);

  return (
    <div className="max-w-4xl mx-auto p-6 py-10 grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Left Section: Form Steps */}
      <div className="md:col-span-2">
        {/* Step 1: Shipping Details */}
        {step === 1 && (
          <div>
            <h2 className="text-xl font-semibold mb-4">Shipping Information</h2>
            <input
              name="name"
              type="text"
              placeholder="Full Name"
              onChange={handleShippingChange}
              required
              className="w-full border p-2 rounded mb-3"
            />
            <input
              name="email"
              type="email"
              placeholder="Email"
              onChange={handleShippingChange}
              required
              className="w-full border p-2 rounded mb-3"
            />
            <input
              name="address"
              type="text"
              placeholder="Address"
              onChange={handleShippingChange}
              required
              className="w-full border p-2 rounded mb-3"
            />
            <div className="flex gap-3">
              <input
                name="city"
                type="text"
                placeholder="City"
                onChange={handleShippingChange}
                required
                className="w-full border p-2 rounded"
              />
              <input
                name="zip"
                type="text"
                placeholder="ZIP Code"
                onChange={handleShippingChange}
                required
                className="w-full border p-2 rounded"
              />
            </div>
            <button
              onClick={handleNextStep}
              className="w-full bg-black text-white py-2 rounded-lg mt-4"
            >
              Next: Payment
            </button>
          </div>
        )}

        {/* Step 2: Payment Info */}
        {step === 2 && (
          <div>
            <h2 className="text-xl font-semibold mb-4">Payment Information</h2>
            <select
              name="method"
              onChange={handlePaymentChange}
              className="w-full border p-2 rounded mb-3"
            >
              <option value="card">Credit/Debit Card</option>
              <option value="paypal">PayPal</option>
            </select>
            {paymentInfo.method === "card" && (
              <>
                <input
                  name="cardNumber"
                  type="text"
                  placeholder="Card Number"
                  onChange={handlePaymentChange}
                  required
                  className="w-full border p-2 rounded mb-3"
                />
                <div className="flex gap-3">
                  <input
                    name="expiry"
                    type="text"
                    placeholder="MM/YY"
                    onChange={handlePaymentChange}
                    required
                    className="w-full border p-2 rounded"
                  />
                  <input
                    name="cvv"
                    type="text"
                    placeholder="CVV"
                    onChange={handlePaymentChange}
                    required
                    className="w-full border p-2 rounded"
                  />
                </div>
              </>
            )}
            <button
              onClick={handleNextStep}
              className="w-full bg-black text-white py-2 rounded-lg mt-4"
            >
              Next: Review Order
            </button>
          </div>
        )}

        {/* Step 3: Order Review */}
        {step === 3 && (
          <div>
            <h2 className="text-xl font-semibold mb-4">Order Review</h2>
            <p>
              <strong>Shipping To:</strong> {shippingInfo.name},{" "}
              {shippingInfo.address}, {shippingInfo.city}, {shippingInfo.zip}
            </p>
            <p>
              <strong>Payment Method:</strong>{" "}
              {paymentInfo.method === "card" ? "Credit/Debit Card" : "PayPal"}
            </p>
            <button
              onClick={handleSubmitOrder}
              className="w-full bg-black text-white py-2 rounded-lg mt-4"
            >
              Place Order
            </button>
          </div>
        )}
      </div>

      {/* Right Section: Order Summary */}
      <div className="bg-[var(--surface-panel)] border border-[var(--border-subtle)] p-6 rounded-lg h-fit">
        <h2 className="text-lg font-semibold mb-3">Order Summary</h2>
        {cartProducts.map((product, index) => (
          <div key={index} className="flex justify-between mb-2">
            <span>{product.name}</span>
            <span>${product.price.toFixed(2)}</span>
          </div>
        ))}
        <hr className="my-2" />
        <div className="flex justify-between">
          <span>Subtotal</span>
          <span>${Number(subtotal).toFixed(2)}</span>
        </div>
        <div className="flex justify-between">
          <span>Shipping</span>
          <span>${Number(shippingCost).toFixed(2)}</span>
        </div>
        <div className="flex justify-between">
          <span>Estimated Tax</span>
          <span>${Number(tax).toFixed(2)}</span>
        </div>
        <div className="flex justify-between font-semibold text-lg mt-2">
          <span>Total</span>
          <span>${Number(total).toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
