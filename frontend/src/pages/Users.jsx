import { useEffect, useState } from "react";
import { api, fmtDate, formatApiError } from "@/lib/api";
import { Page, Card, EmptyState } from "@/components/Primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ShieldCheck, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

const ROLES = [
  { v: "admin", label: "Süper Admin" },
  { v: "manager", label: "Yönetici" },
  { v: "accountant", label: "Muhasebe" },
  { v: "finance", label: "Finans" },
  { v: "operations", label: "Operasyon" },
  { v: "viewer", label: "İzleyici" },
];

export default function Users() {
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [u, l] = await Promise.all([api.get("/users"), api.get("/audit-logs?limit=50")]);
      setUsers(u.data); setLogs(l.data);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openCreate = () => { setEditing({ role: "viewer", password: "" }); setOpen(true); };
  const openEdit = (u) => { setEditing({...u, password: ""}); setOpen(true); };

  const save = async () => {
    try {
      if (editing.id) {
        const body = { name: editing.name, role: editing.role, active: editing.active };
        if (editing.password) body.new_password = editing.password;
        await api.put(`/users/${editing.id}`, body);
        toast.success("Güncellendi");
      } else {
        await api.post("/users", { email: editing.email, name: editing.name, password: editing.password, role: editing.role });
        toast.success("Eklendi");
      }
      setOpen(false); load();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Silinsin mi?")) return;
    await api.delete(`/users/${id}`);
    toast.success("Silindi"); load();
  };

  return (
    <Page
      title="Kullanıcılar & Yetkiler"
      subtitle={`${users.length} kullanıcı`}
      actions={<Button data-testid="btn-new-user" onClick={openCreate} className="bg-[#111111] hover:bg-[#2C2C2E] text-white gap-1.5 rounded-lg h-9"><Plus className="w-4 h-4"/>Yeni Kullanıcı</Button>}
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <Card className="lg:col-span-7 overflow-hidden">
          <div className="px-4 sm:px-6 py-4 border-b border-[#E5E5EA]/50">
            <h3 className="text-base font-medium text-[#1D1D1F]">Kullanıcılar</h3>
          </div>
          {loading ? (
            <div className="p-6 space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="skeleton h-10 w-full"/>)}</div>
          ) : users.length === 0 ? (
            <EmptyState icon={ShieldCheck} title="Kullanıcı yok"/>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA]">
                <tr className="text-left">
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Ad</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Email</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Rol</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} data-testid={`user-row-${u.id}`} onClick={() => openEdit(u)} className="border-b border-[#F5F5F7] hover:bg-[#FAFAFA] cursor-pointer transition">
                    <td className="px-4 py-2.5 font-medium text-[#1D1D1F]">{u.name || "—"}</td>
                    <td className="px-4 py-2.5 text-[#3A3A3C]">{u.email}</td>
                    <td className="px-4 py-2.5"><span className="px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider rounded-full bg-[#F2F2F7] text-[#636366] border border-[#E5E5EA]">{u.role}</span></td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={(e) => { e.stopPropagation(); remove(u.id); }} className="p-1.5 rounded-md hover:bg-[#FFEBEA] text-[#86868B] hover:text-[#D92D20] transition">
                        <Trash2 className="w-4 h-4"/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="lg:col-span-5 overflow-hidden">
          <div className="px-4 sm:px-6 py-4 border-b border-[#E5E5EA]/50">
            <h3 className="text-base font-medium text-[#1D1D1F]">Aktivite Logu</h3>
            <p className="text-xs text-[#86868B] mt-0.5">Son işlemler</p>
          </div>
          <div className="divide-y divide-[#F5F5F7] max-h-[60vh] overflow-y-auto">
            {logs.map((l, i) => (
              <div key={i} className="px-5 py-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[#1D1D1F]">{l.user_email}</span>
                  <span className="text-[10px] text-[#86868B]">{fmtDate(l.ts)}</span>
                </div>
                <div className="text-[#86868B] mt-0.5">{l.action} · {l.resource}</div>
              </div>
            ))}
            {logs.length === 0 && <div className="px-5 py-12 text-center text-sm text-[#86868B]">Henüz log yok</div>}
          </div>
        </Card>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto rounded-l-3xl">
          <SheetHeader>
            <SheetTitle>{editing?.id ? "Kullanıcıyı Düzenle" : "Yeni Kullanıcı"}</SheetTitle>
            <SheetDescription>Email, ad ve rol bilgilerini girin.</SheetDescription>
          </SheetHeader>
          {editing && (
            <div className="mt-6 space-y-4">
              <div className="space-y-1.5">
                <Label className="text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">Email *</Label>
                <Input data-testid="input-user-email" type="email" value={editing.email || ""} disabled={!!editing.id} onChange={(e) => setEditing({...editing, email: e.target.value})} className="bg-[#F5F5F7] border-0 rounded-lg"/>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">Ad Soyad *</Label>
                <Input data-testid="input-user-name" value={editing.name || ""} onChange={(e) => setEditing({...editing, name: e.target.value})} className="bg-[#F5F5F7] border-0 rounded-lg"/>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">{editing.id ? "Yeni Şifre (opsiyonel)" : "Şifre *"}</Label>
                <Input data-testid="input-user-password" type="password" value={editing.password || ""} onChange={(e) => setEditing({...editing, password: e.target.value})} className="bg-[#F5F5F7] border-0 rounded-lg"/>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">Rol *</Label>
                <Select value={editing.role || "viewer"} onValueChange={(v) => setEditing({...editing, role: v})}>
                  <SelectTrigger data-testid="select-role" className="bg-[#F5F5F7] border-0 rounded-lg"><SelectValue/></SelectTrigger>
                  <SelectContent>
                    {ROLES.map(r => <SelectItem key={r.v} value={r.v}>{r.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2 pt-4 border-t border-[#E5E5EA]">
                <Button data-testid="btn-save-user" onClick={save} className="bg-[#111111] hover:bg-[#2C2C2E] text-white rounded-lg flex-1">{editing.id ? "Güncelle" : "Kaydet"}</Button>
                <Button variant="outline" onClick={() => setOpen(false)} className="rounded-lg">İptal</Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </Page>
  );
}
