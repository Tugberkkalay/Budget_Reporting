import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, ArrowRight } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@eyfinans.com");
  const [password, setPassword] = useState("Admin1234!");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await login(email, password);
    setLoading(false);
    if (res.ok) navigate("/");
    else setError(res.error);
  };

  return (
    <div className="min-h-screen bg-[#FBFBFD] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-6">
            <div className="w-10 h-10 rounded-xl bg-[#111111] grid place-items-center text-white font-semibold text-sm">M</div>
            <span className="text-xl font-semibold tracking-tight text-[#1D1D1F]">MARTI Finans</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#1D1D1F]">Hoş geldiniz</h1>
          <p className="mt-2 text-sm text-[#86868B]">Hesabınıza giriş yapın</p>
        </div>

        <form onSubmit={submit} className="bg-white border border-[#E5E5EA] rounded-2xl p-8 shadow-card space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="email" className="text-xs font-medium text-[#3A3A3C]">EMAIL</Label>
            <Input
              data-testid="input-email"
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              className="h-11 rounded-lg bg-[#F5F5F7] border-0 focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-[#007AFF]/20"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password" className="text-xs font-medium text-[#3A3A3C]">ŞİFRE</Label>
            <Input
              data-testid="input-password"
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="h-11 rounded-lg bg-[#F5F5F7] border-0 focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-[#007AFF]/20"
              required
            />
          </div>
          {error && (
            <div className="text-sm text-[#D92D20] bg-[#FFEBEA] border border-[#FECDCB] rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          <Button
            data-testid="btn-login"
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-lg bg-[#111111] hover:bg-[#2C2C2E] text-white font-medium gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Giriş yap <ArrowRight className="w-4 h-4" /></>}
          </Button>
        </form>

        <p className="mt-8 text-center text-xs text-[#86868B]">
          © MARTI Denizcilik Finans · Borç ve alacak yönetimi
        </p>
      </div>
    </div>
  );
}
