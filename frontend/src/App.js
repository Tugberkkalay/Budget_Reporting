import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Payables from "@/pages/Payables";
import Receivables from "@/pages/Receivables";
import Payments from "@/pages/Payments";
import CashAndBank from "@/pages/CashAndBank";
import CurrentAccounts from "@/pages/CurrentAccounts";
import Reports from "@/pages/Reports";
import Reminders from "@/pages/Reminders";
import MasterData from "@/pages/MasterData";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import Assistant from "@/pages/Assistant";
import { Loader2 } from "lucide-react";

const Protected = ({ children, adminOnly = false }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-[#FBFBFD]">
        <Loader2 className="w-6 h-6 animate-spin text-[#86868B]" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return children;
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Protected><Layout /></Protected>}>
              <Route index element={<Dashboard />} />
              <Route path="payables" element={<Payables />} />
              <Route path="receivables" element={<Receivables />} />
              <Route path="payments" element={<Payments />} />
              <Route path="cash-bank" element={<CashAndBank />} />
              <Route path="current-accounts" element={<CurrentAccounts />} />
              <Route path="reports" element={<Reports />} />
              <Route path="assistant" element={<Assistant />} />
              <Route path="reminders" element={<Reminders />} />
              <Route path="master-data" element={<MasterData />} />
              <Route path="users" element={<Protected adminOnly><Users /></Protected>} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Routes>
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
