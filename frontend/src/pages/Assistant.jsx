import { useEffect, useRef, useState } from "react";
import { api, fmtDate, formatApiError } from "@/lib/api";
import { Page, Card, EmptyState } from "@/components/Primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Send, Trash2, Plus, MessageSquare, Loader2, User as UserIcon, Bot } from "lucide-react";
import { toast } from "sonner";

const SUGGESTIONS = [
  "Bu ay vadesi gelen toplam borç ne kadar?",
  "En çok ödeme yapılan ilk 5 tedarikçi kim?",
  "Vadesi geçmiş borçların toplamı ve sayısı?",
  "Hangi gemi en yüksek açık borca sahip?",
  "Son 12 ay nakit akışı nasıl?",
  "VALENTINA1 gemisinin masraf dağılımı?",
];

export default function Assistant() {
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages]);

  const loadSessions = async () => {
    try { const { data } = await api.get("/ai/sessions"); setSessions(data); } catch {}
  };

  const openSession = async (sid) => {
    setCurrentSession(sid);
    try {
      const { data } = await api.get(`/ai/sessions/${sid}/messages`);
      setMessages(data);
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const newSession = () => { setCurrentSession(null); setMessages([]); setInput(""); };

  const send = async (text = null) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setSending(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg, _temp: true }]);
    try {
      const { data } = await api.post("/ai/chat", { session_id: currentSession, message: msg });
      setCurrentSession(data.session_id);
      setMessages((m) => [
        ...m.filter(x => !x._temp),
        { role: "user", content: msg, created_at: new Date().toISOString() },
        { role: "assistant", content: data.response, created_at: new Date().toISOString() }
      ]);
      loadSessions();
    } catch (e) {
      toast.error(formatApiError(e));
      setMessages((m) => m.filter(x => !x._temp));
    } finally { setSending(false); }
  };

  const removeSession = async (sid) => {
    if (!window.confirm("Bu konuşma silinsin mi?")) return;
    await api.delete(`/ai/sessions/${sid}`);
    if (sid === currentSession) newSession();
    loadSessions();
  };

  return (
    <Page title="AI Asistan" subtitle="Tüm finansal verinize hakim — Türkçe doğal dilde sorgu yapın">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-180px)]">
        {/* Sessions sidebar */}
        <Card className="lg:col-span-3 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-[#E5E5EA]/50">
            <Button data-testid="btn-new-chat" onClick={newSession} className="w-full bg-[#111111] hover:bg-[#2C2C2E] text-white rounded-lg gap-1.5 h-9">
              <Plus className="w-4 h-4"/> Yeni Konuşma
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto py-2">
            {sessions.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-[#86868B]">Henüz konuşma yok</div>
            ) : (
              sessions.map((s) => (
                <div key={s.id} className={`group flex items-start gap-2 px-3 py-2 mx-2 rounded-lg cursor-pointer transition ${currentSession === s.id ? "bg-[#FAFAFA]" : "hover:bg-[#FAFAFA]"}`}>
                  <button
                    data-testid={`session-${s.id}`}
                    onClick={() => openSession(s.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="text-sm font-medium text-[#1D1D1F] truncate">{s.title || "Yeni Konuşma"}</div>
                    <div className="text-[10px] text-[#86868B] truncate">{s.last_message}</div>
                  </button>
                  <button
                    onClick={() => removeSession(s.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-[#86868B] hover:text-[#D92D20] hover:bg-white"
                  ><Trash2 className="w-3.5 h-3.5"/></button>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Chat area */}
        <Card className="lg:col-span-9 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-6 py-4 border-b border-[#E5E5EA]/50 flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#111111] to-[#2C2C2E] grid place-items-center">
              <Sparkles className="w-4 h-4 text-white" strokeWidth={1.5}/>
            </div>
            <div>
              <h3 className="text-base font-semibold text-[#1D1D1F]">Finans Asistanı</h3>
              <p className="text-xs text-[#86868B]">GPT-5.2 ile çalışır · Gerçek verinizden cevap verir</p>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#111111] to-[#2C2C2E] grid place-items-center mb-4">
                  <Sparkles className="w-6 h-6 text-white" strokeWidth={1.5}/>
                </div>
                <h2 className="text-2xl font-semibold tracking-tight text-[#1D1D1F]">Nasıl yardımcı olabilirim?</h2>
                <p className="mt-2 text-sm text-[#86868B]">Borçlar, ödemeler, geminizin finansal durumu hakkında sorabilirsiniz.</p>
                <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-2 w-full">
                  {SUGGESTIONS.map((q, i) => (
                    <button
                      key={i}
                      data-testid={`suggestion-${i}`}
                      onClick={() => send(q)}
                      className="text-left text-sm px-4 py-3 rounded-xl border border-[#E5E5EA] hover:border-[#1D1D1F]/30 hover:bg-[#FAFAFA] transition text-[#3A3A3C]"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <Message key={i} role={m.role} content={m.content}/>
              ))
            )}
            {sending && (
              <div className="flex items-start gap-3 animate-fade-in-up">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#111111] to-[#2C2C2E] grid place-items-center shrink-0">
                  <Sparkles className="w-4 h-4 text-white" strokeWidth={1.5}/>
                </div>
                <div className="flex items-center gap-2 text-sm text-[#86868B] py-2">
                  <Loader2 className="w-4 h-4 animate-spin"/> Yazıyor…
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="px-6 py-4 border-t border-[#E5E5EA]/50 bg-white">
            <div className="flex gap-2 items-end">
              <textarea
                data-testid="input-chat"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={1}
                placeholder="Sorunuzu yazın… (Enter göndermek için, Shift+Enter yeni satır)"
                className="flex-1 px-4 py-2.5 bg-[#F5F5F7] border-0 rounded-xl text-sm placeholder:text-[#86868B] focus:bg-white focus:ring-2 focus:ring-[#007AFF]/20 resize-none"
                style={{ minHeight: 44, maxHeight: 160 }}
              />
              <Button
                data-testid="btn-send"
                onClick={() => send()}
                disabled={!input.trim() || sending}
                className="bg-[#111111] hover:bg-[#2C2C2E] text-white rounded-xl h-11 px-4"
              >
                {sending ? <Loader2 className="w-4 h-4 animate-spin"/> : <Send className="w-4 h-4"/>}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </Page>
  );
}

const Message = ({ role, content }) => {
  const isUser = role === "user";
  return (
    <div className={`flex items-start gap-3 animate-fade-in-up ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-8 h-8 rounded-lg grid place-items-center shrink-0 ${isUser ? "bg-[#F5F5F7]" : "bg-gradient-to-br from-[#111111] to-[#2C2C2E]"}`}>
        {isUser ? <UserIcon className="w-4 h-4 text-[#1D1D1F]" strokeWidth={1.5}/> : <Sparkles className="w-4 h-4 text-white" strokeWidth={1.5}/>}
      </div>
      <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${isUser ? "bg-[#111111] text-white rounded-tr-md" : "bg-[#F5F5F7] text-[#1D1D1F] rounded-tl-md"}`}>
        <pre className="font-sans whitespace-pre-wrap break-words">{content}</pre>
      </div>
    </div>
  );
};
