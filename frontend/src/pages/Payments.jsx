import { useEffect, useMemo, useState } from "react";
import { api, fmtUSD, fmtDate, formatApiError } from "@/lib/api";
import { Page, Card, StatusBadge, EmptyState } from "@/components/Primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search, CreditCard, Trash2, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { toast } from "sonner";

export default function Payments() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [bankFilter, setBankFilter] = useState("all");
  const [masters, setMasters] = useState({ banks: [], vendors: [], ships: [], companies: [], currencies: [], paymentMethods: [] });

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (typeFilter !== "all") params.append("type", typeFilter);
      if (bankFilter !== "all") params.append("bank", bankFilter);
      if (search) params.append("search", search);
      const { data } = await api.get(`/payments?${params.toString()}`);
      setItems(data);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [typeFilter, bankFilter]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [search]);

  useEffect(() => {
    (async () => {
      const [banks, vendors, ships, companies, currencies, methods] = await Promise.all([
        api.get("/master/banks"), api.get("/master/vendors"), api.get("/master/ships"),
        api.get("/master/companies"), api.get("/master/currencies"), api.get("/master/payment_methods"),
      ]);
      setMasters({ banks: banks.data, vendors: vendors.data, ships: ships.data, companies: companies.data, currencies: currencies.data, paymentMethods: methods.data });
    })();
  }, []);

  const summary = useMemo(() => {
    const tediye = items.filter(i => i.type === "TEDİYE").reduce((s, i) => s + (i.usd_amount || 0), 0);
    const tahsil = items.filter(i => i.type === "TAHSİL").reduce((s, i) => s + (i.usd_amount || 0), 0);
    return { tediye, tahsil, count: items.length };
  }, [items]);

  const openCreate = () => {
    setEditing({ type: "TEDİYE", date: new Date().toISOString().slice(0, 10), currency: "USD", fx_rate: 1, amount: 0, usd_amount: 0 });
    setOpen(true);
  };
  const openEdit = (item) => { setEditing(item); setOpen(true); };

  const save = async () => {
    try {
      if (editing.id) {
        await api.put(`/payments/${editing.id}`, editing);
        toast.success("Güncellendi");
      } else {
        await api.post("/payments", editing);
        toast.success("Kaydedildi");
      }
      setOpen(false); setEditing(null); load();
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Bu hareket silinsin mi?")) return;
    await api.delete(`/payments/${id}`);
    toast.success("Silindi"); load();
  };

  return (
    <Page
      title="Ödemeler"
      subtitle={`${summary.count} hareket · Tediye ${fmtUSD(summary.tediye)} · Tahsil ${fmtUSD(summary.tahsil)}`}
      actions={
        <Button data-testid="btn-new-payment" onClick={openCreate} className="bg-[#111111] hover:bg-[#2C2C2E] text-white gap-1.5 rounded-lg h-9">
          <Plus className="w-4 h-4"/> Yeni Hareket
        </Button>
      }
    >
      <Card className="p-4 mb-4 flex gap-3 items-center flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#86868B]"/>
          <Input data-testid="input-search" placeholder="Açıklama, firma…" value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 pl-9 bg-[#F5F5F7] border-0 rounded-lg"/>
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger data-testid="filter-type" className="w-[160px] h-9 bg-[#F5F5F7] border-0 rounded-lg"><SelectValue/></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm tipler</SelectItem>
            <SelectItem value="TEDİYE">Tediye (Ödeme)</SelectItem>
            <SelectItem value="TAHSİL">Tahsil</SelectItem>
          </SelectContent>
        </Select>
        <Select value={bankFilter} onValueChange={setBankFilter}>
          <SelectTrigger data-testid="filter-bank" className="w-[180px] h-9 bg-[#F5F5F7] border-0 rounded-lg"><SelectValue/></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm hesaplar</SelectItem>
            {masters.banks.map(b => <SelectItem key={b.id} value={b.name}>{b.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </Card>

      <Card className="overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-3">{[...Array(6)].map((_, i) => <div key={i} className="skeleton h-10 w-full"/>)}</div>
        ) : items.length === 0 ? (
          <EmptyState icon={CreditCard} title="Henüz hareket yok" message="Tediye veya tahsil hareketi ekleyebilirsiniz."/>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] border-b border-[#E5E5EA]">
                <tr className="text-left">
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Tarih</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Tip</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Firma / Açıklama</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Şirket</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold">Hesap</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold text-right">Tutar</th>
                  <th className="px-4 py-3 text-[11px] uppercase tracking-wider text-[#86868B] font-semibold text-right">USD</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id} data-testid={`row-payment-${p.id}`} onClick={() => openEdit(p)} className="border-b border-[#F5F5F7] hover:bg-[#FAFAFA] cursor-pointer transition">
                    <td className="px-4 py-3 tabular-nums">{fmtDate(p.date)}</td>
                    <td className="px-4 py-3"><StatusBadge value={p.type}/></td>
                    <td className="px-4 py-3 text-[#1D1D1F] max-w-xs">
                      <div className="font-medium truncate">{p.vendor || "—"}</div>
                      <div className="text-xs text-[#86868B] truncate">{p.description || ""}</div>
                    </td>
                    <td className="px-4 py-3 text-[#3A3A3C]">{p.paying_company || "—"}</td>
                    <td className="px-4 py-3 text-[#3A3A3C] text-xs">{p.payment_method || "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{p.amount?.toLocaleString("tr-TR")} <span className="text-[#86868B]">{p.currency}</span></td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium">{fmtUSD(p.usd_amount)}</td>
                    <td className="px-4 py-3 text-right">
                      <button data-testid={`btn-delete-${p.id}`} onClick={(e) => { e.stopPropagation(); remove(p.id); }} className="p-1.5 rounded-md hover:bg-[#FFEBEA] text-[#86868B] hover:text-[#D92D20] transition">
                        <Trash2 className="w-4 h-4"/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="sm:max-w-xl overflow-y-auto rounded-l-3xl">
          <SheetHeader>
            <SheetTitle>{editing?.id ? "Hareketi Düzenle" : "Yeni Hareket"}</SheetTitle>
            <SheetDescription>Tediye (ödeme) veya Tahsil hareketini kaydedin.</SheetDescription>
          </SheetHeader>
          {editing && (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <FieldL label="Tip *"><SelectF value={editing.type} onChange={(v) => setEditing({...editing, type: v})} options={["TEDİYE", "TAHSİL"]}/></FieldL>
                <FieldL label="Tarih *"><Input type="date" value={editing.date?.slice(0,10) || ""} onChange={(e) => setEditing({...editing, date: e.target.value})}/></FieldL>
              </div>
              <FieldL label="Firma">
                <SelectF value={editing.vendor} onChange={(v) => setEditing({...editing, vendor: v})} options={masters.vendors.map(v => v.name)}/>
              </FieldL>
              <FieldL label="Açıklama">
                <Textarea value={editing.description || ""} onChange={(e) => setEditing({...editing, description: e.target.value})} rows={2} className="bg-[#F5F5F7] border-0 rounded-lg"/>
              </FieldL>
              <div className="grid grid-cols-2 gap-3">
                <FieldL label="Şirket"><SelectF value={editing.paying_company} onChange={(v) => setEditing({...editing, paying_company: v})} options={masters.companies.map(c => c.name)}/></FieldL>
                <FieldL label="Hesap / Banka"><SelectF value={editing.payment_method} onChange={(v) => setEditing({...editing, payment_method: v})} options={masters.banks.map(b => b.name)}/></FieldL>
              </div>
              <FieldL label="Gemi / Birim"><SelectF value={editing.ship} onChange={(v) => setEditing({...editing, ship: v})} options={masters.ships.map(s => s.name)}/></FieldL>
              <div className="grid grid-cols-3 gap-3">
                <FieldL label="Tutar *"><Input type="number" step="0.01" value={editing.amount || ""} onChange={(e) => setEditing({...editing, amount: parseFloat(e.target.value) || 0})}/></FieldL>
                <FieldL label="Döviz"><SelectF value={editing.currency} onChange={(v) => setEditing({...editing, currency: v})} options={masters.currencies.map(c => c.code)}/></FieldL>
                <FieldL label="Kur"><Input type="number" step="0.0001" value={editing.fx_rate || ""} onChange={(e) => setEditing({...editing, fx_rate: parseFloat(e.target.value) || 0})}/></FieldL>
              </div>
              <FieldL label="USD Karşılığı"><Input type="number" step="0.01" value={editing.usd_amount || ""} onChange={(e) => setEditing({...editing, usd_amount: parseFloat(e.target.value) || 0})}/></FieldL>
              <div className="flex gap-2 pt-4 border-t border-[#E5E5EA]">
                <Button data-testid="btn-save-payment" onClick={save} className="bg-[#111111] hover:bg-[#2C2C2E] text-white rounded-lg flex-1">{editing.id ? "Güncelle" : "Kaydet"}</Button>
                <Button variant="outline" onClick={() => setOpen(false)} className="rounded-lg">İptal</Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </Page>
  );
}

const FieldL = ({ label, children }) => (
  <div className="space-y-1.5">
    <Label className="text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">{label}</Label>
    {children}
  </div>
);
const SelectF = ({ value, onChange, options }) => (
  <Select value={value || ""} onValueChange={onChange}>
    <SelectTrigger className="bg-[#F5F5F7] border-0 rounded-lg"><SelectValue placeholder="Seçin"/></SelectTrigger>
    <SelectContent className="max-h-80">
      {options.filter(Boolean).map((o, i) => <SelectItem key={i} value={o}>{o}</SelectItem>)}
    </SelectContent>
  </Select>
);
