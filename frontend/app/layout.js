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
        {/* Header */}
        <CartContextProvider>
          <AuthProvider>
            <StickyNav />
            <main className="flex-1 w-full">{children}</main>
          </AuthProvider>
        </CartContextProvider>
      </body>
    </html>
  );
}
