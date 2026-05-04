import StickyNav from "@/components/StickyNav";
import GlobalMobileBottomNav from "@/components/GlobalMobileBottomNav";
import { CartContextProvider } from "@/components/Cart/CartContext";
import { AuthProvider } from "@/components/AuthContext";
import { getAuthenticatedUserFromCookiesWithTimeout } from "@/lib/authServer";
import { Manrope } from "next/font/google";
import "./styles/globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata = {
  title: "inDex — Collectible Intelligence",
  description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
  openGraph: {
    title: "inDex — Collectible Intelligence",
    description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
    siteName: "inDex",
    type: "website",
    url: "https://www.inthedex.io/",
  },
  twitter: {
    card: "summary_large_image",
    title: "inDex — Collectible Intelligence",
    description: "Your collectible intelligence platform for pack simulations, EV insights, market signals, and collection analytics.",
  },
  manifest: "/manifest.json",
  icons: {
    icon: [{ url: "/inDex.png", type: "image/png" }],
    shortcut: ["/inDex.png"],
    apple: [{ url: "/inDex.png", type: "image/png" }]
  },
};

export default async function RootLayout({ children }) {
  const authResult = await getAuthenticatedUserFromCookiesWithTimeout(150);
  const initialUser = authResult?.user || null;

  return (
    <html lang="en">
      <body className={`${manrope.variable} flex flex-col min-h-screen`}>
        {/* Header */}
        <CartContextProvider>
          <AuthProvider initialUser={initialUser}>
            <StickyNav />
            <main className="flex-1 w-full pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0">{children}</main>
            <GlobalMobileBottomNav />
          </AuthProvider>
        </CartContextProvider>
      </body>
    </html>
  );
}
