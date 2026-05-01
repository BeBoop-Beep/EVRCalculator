"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { verifyWaitlistSignupToken } from "@/lib/waitlist/waitlistSignupServer";

export default function WaitlistVerifyPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const statusParam = searchParams.get("status") || "";
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Verifying your link...");
  const hasVerifiedRef = useRef(false);
  const successLockedRef = useRef(false);

  useEffect(() => {
    if (statusParam === "success") {
      successLockedRef.current = true;
      hasVerifiedRef.current = true;
      setStatus("success");
      setMessage("You're on the list.");
      return;
    }

    async function runVerification() {
      if (hasVerifiedRef.current) {
        return;
      }

      const trimmedToken = token.trim();

      if (process.env.NODE_ENV !== "production") {
        console.log("[waitlist-verify] verification_start", {
          tokenLength: trimmedToken.length,
        });
      }

      if (!trimmedToken) {
        setStatus("error");
        setMessage("This verification link is invalid or expired. Submit your email again to get a new link.");
        return;
      }

      hasVerifiedRef.current = true;

      const result = await verifyWaitlistSignupToken(trimmedToken);

      if (process.env.NODE_ENV !== "production") {
        console.log("[waitlist-verify] verification_result", {
          status: result.status,
        });
      }

      if (successLockedRef.current) {
        return;
      }

      if (result.status === "verified" || result.status === "already_verified") {
        successLockedRef.current = true;
        setStatus("success");
        setMessage("You're on the list.");
        router.replace("/waitlist/verify?status=success");
        return;
      }

      if (result.status === "invalid_or_expired") {
        if (successLockedRef.current) {
          return;
        }
        setStatus("error");
        setMessage("This verification link is invalid or expired. Submit your email again to get a new link.");
        return;
      }

      if (successLockedRef.current) {
        return;
      }

      setStatus("error");
      setMessage(result.message || "Verification failed. Please try again.");
    }

    runVerification();
  }, [token, statusParam, router]);

  const textClass =
    status === "success"
      ? "text-green-300"
      : status === "loading"
      ? "text-yellow-200"
      : "text-red-300";

  return (
    <main className="min-h-[60vh] bg-[#020817] text-white px-4 py-16">
      <div className="mx-auto max-w-xl rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
        <h1 className="text-3xl font-bold">Waitlist Verification</h1>
        <p className={`mt-4 text-base ${textClass}`}>{message}</p>
        {status === "error" && (
          <div className="mt-5">
            <Link
              href="/#waitlist"
              className="text-sm text-white/80 underline underline-offset-2 hover:text-white"
            >
              Request a new verification email
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
