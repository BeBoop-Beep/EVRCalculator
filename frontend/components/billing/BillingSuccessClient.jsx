"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import { getBillingStatus } from "@/lib/billing/billingClient.mjs";
import { pollBillingConfirmation } from "@/lib/billing/billingSuccessPolling.mjs";
import { planLabel } from "@/lib/billing/billingPresentation.mjs";

export default function BillingSuccessClient(){
  const {refreshUser}=useAuth(); const [state,setState]=useState({phase:"checking",status:null});
  useEffect(()=>{ let active=true; pollBillingConfirmation({getStatus,onStatus:status=>{if(active)setState({phase:"checking",status});}}).then(async result=>{
    if(!active)return; if(result.confirmed){await refreshUser(); if(active)setState({phase:"confirmed",status:result.status});} else setState({phase:"pending",status:result.status});
  }); return()=>{active=false;};},[refreshUser]);
  return <main className="mx-auto w-full max-w-2xl px-4 py-16 sm:px-6"><section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8 text-center" aria-live="polite">
    <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Membership</p>
    {state.phase==="confirmed"?<><h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Your membership is active</h1><p className="mt-3 text-[var(--text-secondary)]">Current access: {planLabel(state.status?.effectivePlan)}.</p></>:state.phase==="pending"?<><h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Confirmation is still processing</h1><p className="mt-3 text-[var(--text-secondary)]">Your subscription is still being confirmed. Refresh your account shortly.</p></>:<><h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Confirming your membership</h1><p className="mt-3 text-[var(--text-secondary)]">Checkout is complete. We’re waiting for secure billing confirmation.</p></>}
    <Link href="/account-settings#billing" className="mt-6 inline-flex rounded-lg bg-brand px-5 py-2 font-semibold text-white hover:bg-brand-dark">Membership &amp; Billing</Link>
  </section></main>;
}
