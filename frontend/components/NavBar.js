import Link from "next/link";

export default function NavBar() {
  return (
    <div className="bg-neutral-light py-4">
      <div className="container mx-auto flex justify-between items-center px-4">
        <nav className="flex space-x-8">
          <Link href="/priceCheck" className="text-primary hover:text-accent">
            Price Check
          </Link>
        </nav>
      </div>
    </div>
  );
}
