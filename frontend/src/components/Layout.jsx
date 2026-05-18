import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ArrowDownToLine, ArrowUpFromLine, CreditCard, Wallet,
  Users, FileBarChart2, BellRing, Database, ShieldCheck, Settings,
  LogOut, Search, ChevronLeft, ChevronRight, Sparkles,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/payables", label: "Borçlar", icon: ArrowDownToLine },
  { to: "/receivables", label: "Alacaklar", icon: ArrowUpFromLine },
  { to: "/payments", label: "Ödemeler", icon: CreditCard },
  { to: "/cash-bank", label: "Kasa & Banka", icon: Wallet },
  { to: "/current-accounts", label: "Cari Hesaplar", icon: Users },
  { to: "/reports", label: "Raporlar", icon: FileBarChart2 },
  { to: "/assistant", label: "AI Asistan", icon: Sparkles },
  { to: "/reminders", label: "Hatırlatmalar", icon: BellRing },
  { to: "/master-data", label: "Tanımlamalar", icon: Database },
];

const NAV_ADMIN = [
  { to: "/users", label: "Kullanıcılar", icon: ShieldCheck },
  { to: "/settings", label: "Ayarlar", icon: Settings },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [notifCount, setNotifCount] = useState(0);

  useEffect(() => {
    const fetchUnread = async () => {
      try {
        const { data } = await api.get("/notifications?unread_only=true");
        setNotifCount(data.length);
      } catch {}
    };
    fetchUnread();
    const t = setInterval(fetchUnread, 60000);
    return () => clearInterval(t);
  }, []);

  const initials = (user?.name || user?.email || "U").slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-screen bg-[#FBFBFD]">
      {/* Sidebar */}
      <aside
        data-testid="sidebar"
        className={`${collapsed ? "w-16" : "w-64"} shrink-0 bg-[#F5F5F7] border-r border-[#E5E5EA]/50 transition-all duration-300 flex flex-col`}
      >
        <div className={`h-14 flex items-center ${collapsed ? "justify-center" : "px-5 justify-between"} border-b border-[#E5E5EA]/50`}>
          {!collapsed && (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#111111] grid place-items-center text-white text-xs font-semibold">EY</div>
              <span className="text-sm font-semibold tracking-tight text-[#1D1D1F]">Finans</span>
            </div>
          )}
          <button
            data-testid="btn-toggle-sidebar"
            onClick={() => setCollapsed((c) => !c)}
            className="p-1.5 rounded-md hover:bg-white/80 text-[#86868B] hover:text-[#1D1D1F] transition"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              data-testid={`nav-${item.to.replace(/\//g, "") || "dashboard"}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                  isActive
                    ? "bg-white text-[#1D1D1F] shadow-[0_1px_3px_rgba(0,0,0,0.05)] font-medium"
                    : "text-[#3A3A3C] hover:bg-white/60 font-normal"
                }`
              }
            >
              <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={1.75} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          ))}

          {user?.role === "admin" && (
            <>
              <div className={`mt-6 mb-2 px-3 text-[10px] uppercase tracking-wider text-[#86868B] font-semibold ${collapsed ? "hidden" : ""}`}>
                Yönetim
              </div>
              {NAV_ADMIN.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={`nav-${item.to.replace(/\//g, "")}`}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                      isActive
                        ? "bg-white text-[#1D1D1F] shadow-[0_1px_3px_rgba(0,0,0,0.05)] font-medium"
                        : "text-[#3A3A3C] hover:bg-white/60"
                    }`
                  }
                >
                  <item.icon className="w-[18px] h-[18px] shrink-0" strokeWidth={1.75} />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </NavLink>
              ))}
            </>
          )}
        </nav>

        <div className="p-3 border-t border-[#E5E5EA]/50">
          <button
            data-testid="btn-logout"
            onClick={async () => { await logout(); navigate("/login"); }}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[#3A3A3C] hover:bg-white/80 transition"
          >
            <LogOut className="w-[18px] h-[18px]" strokeWidth={1.75} />
            {!collapsed && <span>Çıkış</span>}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-30 h-14 bg-[#FBFBFD]/80 backdrop-blur-xl border-b border-[#E5E5EA]/50 flex items-center px-6 gap-4">
          <div className="flex-1 max-w-md relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#86868B]" />
            <input
              data-testid="input-global-search"
              type="text"
              placeholder="Ara… (⌘K)"
              className="w-full h-9 pl-9 pr-3 bg-[#F5F5F7] border-0 rounded-lg text-sm placeholder:text-[#86868B] focus:bg-white focus:ring-2 focus:ring-[#007AFF]/20 transition"
            />
          </div>

          <button
            data-testid="btn-notifications"
            onClick={() => navigate("/reminders")}
            className="relative p-2 rounded-lg hover:bg-[#F5F5F7] transition"
          >
            <BellRing className="w-5 h-5 text-[#3A3A3C]" strokeWidth={1.5} />
            {notifCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 grid place-items-center text-[10px] font-semibold bg-[#D92D20] text-white rounded-full">
                {notifCount > 99 ? "99+" : notifCount}
              </span>
            )}
          </button>

          <div className="flex items-center gap-2 pl-3 border-l border-[#E5E5EA]/50">
            <div className="w-8 h-8 rounded-full bg-[#111111] text-white grid place-items-center text-xs font-semibold">
              {initials}
            </div>
            <div className="text-xs leading-tight">
              <div className="font-medium text-[#1D1D1F]">{user?.name || "Kullanıcı"}</div>
              <div className="text-[#86868B]">{user?.role}</div>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8 animate-fade-in-up">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
