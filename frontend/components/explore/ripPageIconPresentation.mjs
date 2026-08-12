import { RANK_CONFIG } from "../../constants/rankConfig.mjs";

const PRESENTATIONS = {
  neutral: { iconClassName: "", containerClassName: "", style: { color: "rgba(148,163,184,0.82)", borderColor: "rgba(148,163,184,0.14)", backgroundColor: "rgba(148,163,184,0.05)" } },
  verdict: { iconClassName: "", containerClassName: "", style: { color: "rgba(94,234,212,0.9)", borderColor: "rgba(94,234,212,0.2)", backgroundColor: "rgba(94,234,212,0.07)" } },
  financial: { iconClassName: "", containerClassName: "", style: { color: "rgba(94,234,212,0.82)" } },
  collector: { iconClassName: "", containerClassName: "", style: { color: "rgba(196,181,253,0.86)" } },
  odds: { iconClassName: "", containerClassName: "", style: { color: "rgba(103,232,249,0.82)" } },
  takeaway: { iconClassName: "", containerClassName: "", style: { color: "rgba(252,211,77,0.84)" } },
};

export function getRipPageIconPresentation(role = "neutral", tier = null) {
  if (role !== "overall") return PRESENTATIONS[role] || PRESENTATIONS.neutral;
  const color = RANK_CONFIG[String(tier || "").toUpperCase()]?.color || "rgba(148,163,184,0.82)";
  return {
    iconClassName: "",
    containerClassName: "border-slate-400/10 bg-slate-400/[0.04]",
    style: { color },
  };
}
