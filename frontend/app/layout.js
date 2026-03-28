import StickyNav from "@/components/StickyNav";
import { CartContextProvider } from "@/components/Cart/CartContext";
import { AuthProvider } from "@/components/AuthContext";
import "./styles/globals.css";

export const metadata = {
  title: "Shiny Finds",
  description: "Your go-to Pokémon TCG store!",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="flex flex-col min-h-screen">
        {/* Sticky Header & Navbar */}
        <CartContextProvider>
          <AuthProvider>
            <StickyNav />

            {/* Main Content Container - Adds space so content doesn't overlap */}
            <div className="flex flex-1 w-full pt-[130px]">
              {/* Main Content */}
              <div className="flex flex-1 p-0 w-full">
                <div className="w-full mt-[30]">{children}</div>
              </div>
            </div>
          </AuthProvider>
        </CartContextProvider>
      </body>
    </html>
  );
}
