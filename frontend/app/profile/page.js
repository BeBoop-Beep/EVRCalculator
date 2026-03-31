"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUserProfile } from "@/lib/profile/profileClient";

export default function ProfilePage() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let mounted = true;

    const resolveProfileRoute = async () => {
      try {
        const data = await getCurrentUserProfile();
        if (!mounted) return;

        const username = data?.profile?.username;
        if (username) {
          router.replace(`/u/${encodeURIComponent(username)}`);
          return;
        }

        router.replace("/my-collection");
      } catch (error) {
        if (!mounted) return;

        if (error?.status === 401) {
          router.replace("/login");
          return;
        }

        setErrorMessage(error?.message || "Unable to resolve your profile route right now.");
      }
    };

    resolveProfileRoute();

    return () => {
      mounted = false;
    };
  }, [router]);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Profile</p>
        <p className="mt-3 text-base text-[var(--text-primary)]">Routing to your public showcase...</p>
        {errorMessage ? (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
            <p className="text-sm text-red-200">{errorMessage}</p>
            <Link href="/my-collection" className="mt-3 inline-block text-sm font-semibold text-[var(--text-primary)] underline">
              Go to My Collection
            </Link>
          </div>
        ) : null}
      </div>
    </main>
  );
}
