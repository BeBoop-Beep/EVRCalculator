const CONFIRMED = new Set(["trialing", "active", "past_due"]);
export function isBillingConfirmed(status) { return Boolean(status?.billingManaged && CONFIRMED.has(status?.subscriptionStatus)); }
export async function pollBillingConfirmation({ getStatus, onStatus=()=>{}, sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms)), delays=[0,1000,2000,3000,5000] }) {
  let latest=null;
  for (const delay of delays) {
    if (delay) await sleep(delay);
    try { latest=await getStatus(); onStatus(latest); if(isBillingConfirmed(latest)) return { confirmed:true,status:latest }; }
    catch { /* A temporary status failure is not payment failure. */ }
  }
  return { confirmed:false,status:latest };
}
