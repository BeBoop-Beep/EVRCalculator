import StickyNav from "@/components/StickyNav";
import { CartContextProvider } from "@/components/Cart/CartContext";
import { AuthProvider } from "@/components/AuthContext";
import { Manrope } from "next/font/google";
import "./styles/globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata = {
  title: "inDex",
  description: "Your go-to Pokémon TCG store!",
  manifest: "/manifest.json",
  icons: {
    icon: [{ url: "/inDex.png", type: "image/png" }],
    shortcut: ["/inDex.png"],
    apple: [{ url: "/inDex.png", type: "image/png" }]
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} flex flex-col min-h-screen`}>
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
