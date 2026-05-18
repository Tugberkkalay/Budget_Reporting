/* Page-level reusable components */
import { cn } from "@/lib/utils";

export const Page = ({ title, subtitle, actions, children }) => (
  <div className="max-w-[1400px] mx-auto">
    <div className="flex items-start justify-between mb-8 gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-[#1D1D1F]" data-testid="page-title">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[#86868B]">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
    {children}
  </div>
);

export const StatusBadge = ({ value }) => {
  const map = {
    "ÖDENDİ": { bg: "#E3F8E9", text: "#1F8942", border: "#B9EAC8" },
    "ONAYLANDI": { bg: "#E6F2FF", text: "#0062CC", border: "#B3D7FF" },
    "ONAY BEKLİYOR": { bg: "#FFF4CE", text: "#B26205", border: "#FCE088" },
    "VADESİ GELDİ": { bg: "#FFF4CE", text: "#B26205", border: "#FCE088" },
    "VADESİ GEÇTİ": { bg: "#FFEBEA", text: "#D92D20", border: "#FECDCB" },
    "ÖDENMEDİ": { bg: "#FFEBEA", text: "#D92D20", border: "#FECDCB" },
    "İPTAL": { bg: "#F2F2F7", text: "#636366", border: "#E5E5EA" },
    "TASLAK": { bg: "#F2F2F7", text: "#636366", border: "#E5E5EA" },
    "KISMİ ÖDEME": { bg: "#E6F2FF", text: "#0062CC", border: "#B3D7FF" },
    "SİPARİŞ": { bg: "#F2F2F7", text: "#636366", border: "#E5E5EA" },
    "TEDİYE": { bg: "#FFEBEA", text: "#D92D20", border: "#FECDCB" },
    "TAHSİL": { bg: "#E3F8E9", text: "#1F8942", border: "#B9EAC8" },
  };
  const v = value || "—";
  const c = map[v] || { bg: "#F2F2F7", text: "#636366", border: "#E5E5EA" };
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold border tabular-nums"
      style={{ background: c.bg, color: c.text, borderColor: c.border }}
    >
      {v}
    </span>
  );
};

export const Card = ({ children, className = "", ...rest }) => (
  <div
    className={cn("bg-white border border-[#E5E5EA] rounded-2xl shadow-card hover:shadow-card-hover transition-all", className)}
    {...rest}
  >
    {children}
  </div>
);

export const EmptyState = ({ icon: Icon, title, message, action }) => (
  <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
    {Icon && <Icon className="w-12 h-12 text-[#A1A1A6] mb-4" strokeWidth={1} />}
    <h3 className="text-base font-medium text-[#1D1D1F]">{title}</h3>
    {message && <p className="mt-1 text-sm text-[#86868B] max-w-md">{message}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export const Skeleton = ({ className = "" }) => (
  <div className={cn("skeleton h-4 w-full", className)} />
);
