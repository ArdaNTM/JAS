import { useState, useEffect } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { AuraAPI } from "./services/api";

function App() {
  const { events, isConnected } = useWebSocket("ws://127.0.0.1:8000/api/ws/events");
  const [intent, setIntent] = useState("");
  const [isPlanning, setIsPlanning] = useState(false);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [resultData, setResultData] = useState<any>(null);
  
  // Kalıcı Bellek (Memory) State'leri
  const [history, setHistory] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    const fetchApprovals = async () => {
      try {
        const data = await AuraAPI.getApprovals();
        setApprovals(data);
      } catch (e) {}
    };
    const interval = setInterval(fetchApprovals, 2000);
    fetchApprovals();
    return () => clearInterval(interval);
  }, []);

  const loadHistory = async () => {
    try {
      const data = await AuraAPI.getHistory();
      setHistory(data);
    } catch (error) {
      console.error("Geçmiş yüklenemedi:", error);
    }
  };

  const toggleHistory = () => {
    if (!showHistory) loadHistory();
    setShowHistory(!showHistory);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!intent.trim() || isPlanning) return;

    setIsPlanning(true);
    setResultData(null);
    try {
      const result = await AuraAPI.planIntent(intent);
      setResultData(result);
      setIntent("");
      if (showHistory) loadHistory();
    } catch (error) {
      console.error("Planlama hatası:", error);
      setResultData({ error: "İşlem sırasında bir hata oluştu." });
    } finally {
      setIsPlanning(false);
    }
  };

  const handleApprove = async (reqId: string) => {
    try {
      const result = await AuraAPI.approveAction(reqId);
      setResultData(result);
      const data = await AuraAPI.getApprovals();
      setApprovals(data);
      if (showHistory) loadHistory();
    } catch (error) {
      console.error("Onay hatası:", error);
    }
  };

  return (
    <div className="min-h-screen p-8 flex flex-col items-center font-sans">
      <header className="mb-8 text-center w-full max-w-4xl border-b border-slate-800 pb-6 relative">
        <h1 className="text-4xl font-bold text-blue-500 tracking-wider mb-2">
          AURA <span className="text-slate-200">UI</span>
        </h1>
        <div className="flex items-center justify-center gap-2 mt-4">
          <div className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`}></div>
          <span className="text-sm font-medium text-slate-400 uppercase tracking-widest">
            {isConnected ? "EventBus Aktif (Senkronize)" : "Çekirdek Bağlantısı Bekleniyor..."}
          </span>
        </div>
        
        {/* SİSTEM GEÇMİŞİ BUTONU */}
        <button 
          onClick={toggleHistory}
          className={`absolute right-0 top-0 mt-4 px-4 py-2 rounded text-sm font-bold shadow-md transition-colors ${showHistory ? "bg-purple-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"}`}
        >
          {showHistory ? "Geçmişi Kapat" : "🧠 Sistem Geçmişi (Memory)"}
        </button>
      </header>

      <main className="w-full max-w-4xl bg-slate-800/50 p-6 rounded-xl shadow-2xl border border-slate-700 backdrop-blur-sm flex flex-col gap-6">

        {/* ONAY KUYRUĞU */}
        {approvals.length > 0 && (
          <div className="bg-orange-950/30 border border-orange-500/50 rounded-lg p-4 shadow-lg shadow-orange-900/20">
            <h2 className="text-lg font-bold text-orange-400 flex items-center gap-2 mb-3">
              <span className="animate-pulse">⚠️</span> Onay Bekleyen İşlemler ({approvals.length})
            </h2>
            <div className="flex flex-col gap-3">
              {approvals.map((app: any) => (
                <div key={app.id} className="bg-slate-900 border border-orange-900/50 p-3 rounded flex justify-between items-center">
                  <div>
                    <div className="font-mono text-sm text-slate-300">
                      <span className="text-blue-400 font-bold">{app.capability_name}</span> ➔ {app.operation}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      Parametreler: {JSON.stringify(app.parameters)}
                    </div>
                  </div>
                  <button
                    onClick={() => handleApprove(app.id)}
                    className="bg-orange-600 hover:bg-orange-500 text-white px-4 py-1.5 rounded text-sm font-bold shadow-md transition-colors"
                  >
                    İzin Ver
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {/* SİSTEM GEÇMİŞİ (MEMORY) PANELİ */}
        {showHistory && (
          <div className="bg-purple-950/20 border border-purple-500/30 rounded-lg p-4 shadow-lg shadow-purple-900/10 animate-fade-in-down">
            <h2 className="text-lg font-bold text-purple-400 mb-3 flex items-center gap-2">
              <span>🧠</span> AURA Belleği (Son İşlemler)
            </h2>
            <div className="flex flex-col gap-3 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
              {history.length === 0 ? (
                <p className="text-slate-500 italic text-sm">Geçmişte kayıtlı bir işlem bulunmuyor.</p>
              ) : (
                history.map((item) => (
                  <div key={item.id} className="bg-slate-900 border border-slate-700/50 p-3 rounded flex flex-col gap-2">
                    <div className="flex justify-between items-start">
                      <span className="text-blue-400 font-semibold text-sm">"{item.intent}"</span>
                      <span className="text-slate-500 text-xs">{new Date(item.timestamp).toLocaleString('tr-TR')}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-800">
                      <div>
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">Planlanan Eylem</span>
                        <pre className="text-xs text-slate-300 bg-slate-950 p-2 rounded overflow-x-auto border border-slate-800">{JSON.stringify(item.plan, null, 2)}</pre>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">Eylem Çıktısı</span>
                        <pre className="text-xs text-emerald-400/80 bg-slate-950 p-2 rounded overflow-x-auto border border-slate-800">{JSON.stringify(item.result, null, 2)}</pre>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* CANLI SİSTEM AKIŞI (Geçmiş Kapalıyken Göster) */}
        {!showHistory && (
          <div>
            <h2 className="text-lg font-semibold mb-4 text-slate-300 border-b border-slate-700/50 pb-2">
              Canlı Sistem Akışı
            </h2>
            <div className="h-64 overflow-y-auto bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-sm shadow-inner flex flex-col">
              {events.length === 0 ? (
                <p className="text-slate-600 italic m-auto flex items-center gap-2">
                  <span className="animate-spin text-xl">⚙️</span> Sistem olayları bekleniyor...
                </p>
              ) : (
                events.map((ev, idx) => (
                  <div key={idx} className="mb-3 flex items-start gap-3">
                    <span className="text-blue-400 font-bold whitespace-nowrap">
                      [{new Date().toLocaleTimeString('tr-TR', { hour12: false })}]
                    </span>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                      ev.event === 'system_status' ? 'bg-green-500/20 text-green-400' :
                      ev.event === 'agent_progress' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-slate-700 text-slate-300'
                    }`}>
                      {ev.event}
                    </span>
                    <span className="text-slate-300 leading-relaxed break-all">
                      {ev.message || JSON.stringify(ev.data)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* NİHAİ VERİ ÇIKTISI PANELİ */}
        {resultData && !showHistory && (
          <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-lg p-4 shadow-lg shadow-emerald-900/10 mt-2">
            <h3 className="text-emerald-400 font-bold mb-3 flex items-center gap-2">
              <span>✓</span> Görev Çıktısı (Sonuç)
            </h3>
            <pre className="text-slate-300 font-mono text-sm whitespace-pre-wrap overflow-x-auto p-3 bg-slate-950/80 rounded border border-slate-800">
              {typeof resultData === 'object' ? JSON.stringify(resultData, null, 2) : resultData}
            </pre>
          </div>
        )}

        {/* KOMUT GİRİŞ FORMU */}
        <form onSubmit={handleSubmit} className="flex gap-4 items-center bg-slate-900 p-2 rounded-lg border border-slate-700 mt-auto">
          <span className="text-blue-500 pl-4 font-bold h-full flex items-center text-xl">❯</span>
          <input
            type="text"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            disabled={isPlanning || !isConnected}
            placeholder="AURA'ya bir komut verin..."
            className="flex-1 bg-transparent border-none text-slate-200 focus:outline-none focus:ring-0 placeholder-slate-600 px-2 py-3"
          />
          <button
            type="submit"
            disabled={isPlanning || !isConnected || !intent.trim()}
            className={`px-6 py-2 rounded font-semibold transition-all ${
              isPlanning || !isConnected || !intent.trim()
                ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/50"
            }`}
          >
            {isPlanning ? "İşleniyor..." : "Gönder"}
          </button>
        </form>

      </main>
    </div>
  );
}

export default App;