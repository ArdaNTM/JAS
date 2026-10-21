import { useState } from "react";
import {
  analyzeLocalVision,
  getPrefetchProposals,
  observePrefetchPattern,
  recallVectorMemory,
  synthesizeToolProposal,
  writeVectorMemory,
  type VectorMemoryItem,
} from "../api/client";

type Panel = "memory" | "vision" | "tools" | "prefetch";

const inputClass = "w-full rounded border border-cyan-900/70 bg-slate-950/80 px-3 py-2 text-xs text-cyan-100 outline-none focus:border-cyan-400";
const buttonClass = "rounded border border-cyan-700/80 px-3 py-2 text-[10px] font-bold tracking-widest text-cyan-200 hover:bg-cyan-950/60 disabled:opacity-40";
const labelClass = "mb-1 block text-[9px] tracking-[.18em] text-slate-500";

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Görsel okunamadı."));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const separator = result.indexOf(",");
      if (separator < 0) reject(new Error("Görsel verisi geçersiz."));
      else resolve(result.slice(separator + 1));
    };
    reader.readAsDataURL(file);
  });
}

export default function CapabilityWorkbench() {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>("memory");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [principalId, setPrincipalId] = useState("local_default");

  const [memoryText, setMemoryText] = useState("");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryItems, setMemoryItems] = useState<VectorMemoryItem[]>([]);

  const [imageFile, setImageFile] = useState<File | null>(null);
  const [visionPrompt, setVisionPrompt] = useState("Önemli nesneleri ve görünen metinleri açıkla.");
  const [visionResult, setVisionResult] = useState("");

  const [toolProblem, setToolProblem] = useState("");
  const [toolContext, setToolContext] = useState("");
  const [toolProposal, setToolProposal] = useState<Record<string, unknown> | null>(null);

  const [eventKey, setEventKey] = useState("user_directive");
  const [capabilityId, setCapabilityId] = useState("research");
  const [hourLocal, setHourLocal] = useState(String(new Date().getHours()));
  const [prefetchItems, setPrefetchItems] = useState<Record<string, unknown>[]>([]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Core isteği başarısız oldu.");
    } finally {
      setBusy(false);
    }
  }

  async function saveMemory() {
    await run(async () => {
      const result = await writeVectorMemory({
        principal_id: principalId.trim(),
        content: memoryText.trim(),
        tags: ["arayüz", "kullanıcı-verisi"],
      });
      setMessage(result.stored ? "Güvenilmeyen başvuru verisi olarak kaydedildi." : "Hafıza kaydedilemedi.");
      setMemoryText("");
    });
  }

  async function searchMemory() {
    await run(async () => {
      const result = await recallVectorMemory({
        principal_id: principalId.trim(),
        query: memoryQuery.trim(),
        limit: 8,
      });
      setMemoryItems(result.items);
      setMessage(result.count + " sonuç · " + result.trust);
    });
  }

  async function analyzeImage() {
    await run(async () => {
      if (!imageFile) throw new Error("Önce bir görsel seçin.");
      if (imageFile.size > 8 * 1024 * 1024) throw new Error("8 MiB boyutundan küçük bir görsel seçin.");
      const imageBase64 = await toBase64(imageFile);
      const result = await analyzeLocalVision({ image_base64: imageBase64, prompt: visionPrompt.trim() });
      setVisionResult(result.analysis);
      setMessage("Sağlayıcı: " + result.provider + " · bulut kullanıldı: " + String(result.cloud_used));
    });
  }

  async function createProposal() {
    await run(async () => {
      const result = await synthesizeToolProposal({
        problem: toolProblem.trim(),
        capability_context: toolContext.trim(),
      });
      setToolProposal(result);
      setMessage("Yalnızca öneri oluşturuldu. Hiçbir şey kaydedilmedi veya çalıştırılmadı.");
    });
  }

  async function recordPattern() {
    await run(async () => {
      const result = await observePrefetchPattern({
        principal_id: principalId.trim(),
        event_key: eventKey.trim(),
        capability_id: capabilityId.trim(),
        hour_local: Number(hourLocal),
      });
      setMessage("Gözlem işlendi. Eylem yürütüldü: " + String(result.execution_performed));
      const proposals = await getPrefetchProposals(principalId.trim(), 20);
      setPrefetchItems(proposals.items);
    });
  }

  const tabs: { id: Panel; label: string }[] = [
    { id: "memory", label: "YEREL HAFIZA" },
    { id: "vision", label: "GÖRÜ" },
    { id: "tools", label: "ARAÇ ÖNERİLERİ" },
    { id: "prefetch", label: "ÖN HAZIRLIK" },
  ];

  return (
    <>
      <button
        type="button"
        className="fixed bottom-5 right-5 z-40 rounded border border-cyan-700 bg-slate-950/95 px-4 py-3 text-[10px] font-bold tracking-[.18em] text-cyan-200 shadow-lg shadow-cyan-950/40 hover:border-cyan-300"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="aura-capability-workbench"
      >
        {open ? "ÇALIŞMA ALANINI KAPAT" : "YETENEK ÇALIŞMA ALANI"}
      </button>

      {open && (
        <section
          id="aura-capability-workbench"
          aria-label="AURA yetenek çalışma alanı"
          className="fixed inset-x-3 bottom-20 top-16 z-40 mx-auto flex max-w-4xl flex-col overflow-hidden rounded-lg border border-cyan-900/80 bg-[#030a12]/[.98] shadow-2xl shadow-black"
        >
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-950 p-4">
            <div>
              <div className="text-xs font-bold tracking-[.2em] text-cyan-200">YETENEK ÇALIŞMA ALANI</div>
              <p className="mt-1 text-[9px] text-slate-500">Yalnızca Core API · sağlayıcı yalıtımı · örtük araç çalıştırma yok</p>
            </div>
            <label className="w-48">
              <span className={labelClass}>KULLANICI KAPSAMI</span>
              <input className={inputClass} value={principalId} maxLength={128} onChange={(event) => setPrincipalId(event.target.value)} />
            </label>
          </header>

          <nav className="flex flex-wrap gap-1 border-b border-cyan-950 p-2" aria-label="Yetenek araçları">
            {tabs.map((tab) => (
              <button key={tab.id} type="button" className={panel === tab.id ? buttonClass + " bg-cyan-950/80" : buttonClass + " border-transparent text-slate-500"} onClick={() => { setPanel(tab.id); setMessage(""); }}>
                {tab.label}
              </button>
            ))}
          </nav>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {panel === "memory" && (
              <div className="grid gap-5 md:grid-cols-2">
                <div className="space-y-3">
                  <label className="block"><span className={labelClass}>YEREL BİLGİ EKLE</span><textarea className={inputClass + " min-h-28"} value={memoryText} maxLength={12000} onChange={(event) => setMemoryText(event.target.value)} placeholder="Kapsam dâhilinde anlamsal arama için not ekleyin…" /></label>
                  <button className={buttonClass} disabled={busy || !memoryText.trim() || !principalId.trim()} onClick={() => void saveMemory()}>BAŞVURU BİLGİSİNİ KAYDET</button>
                </div>
                <div className="space-y-3">
                  <label className="block"><span className={labelClass}>ANLAMSAL SORGU</span><input className={inputClass} value={memoryQuery} maxLength={12000} onChange={(event) => setMemoryQuery(event.target.value)} placeholder="Kapsamlı yerel hafızada ara…" /></label>
                  <button className={buttonClass} disabled={busy || !memoryQuery.trim() || !principalId.trim()} onClick={() => void searchMemory()}>HAFIZADA ARA</button>
                  <div className="space-y-2">{memoryItems.map((item, index) => <article key={item.memory_id ?? index} className="rounded border border-cyan-950 p-3 text-xs"><p className="whitespace-pre-wrap text-cyan-100">{item.content ?? JSON.stringify(item)}</p><p className="mt-2 text-[9px] text-slate-500">Güvenilmeyen başvuru verisi · ilgililik {item.relevance_score ?? "yok"}</p></article>)}</div>
                </div>
              </div>
            )}

            {panel === "vision" && (
              <div className="max-w-2xl space-y-3">
                <label className="block"><span className={labelClass}>YEREL GÖRSEL GİRDİSİ (EN FAZLA 8 MİB)</span><input className={inputClass} type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setImageFile(event.target.files?.[0] ?? null)} /></label>
                <label className="block"><span className={labelClass}>ANALİZ İSTEĞİ</span><textarea className={inputClass + " min-h-20"} maxLength={4000} value={visionPrompt} onChange={(event) => setVisionPrompt(event.target.value)} /></label>
                <button className={buttonClass} disabled={busy || !imageFile || !visionPrompt.trim()} onClick={() => void analyzeImage()}>CORE ÜZERİNDEN ANALİZ ET</button>
                {visionResult && <article className="whitespace-pre-wrap rounded border border-cyan-950 p-3 text-xs leading-6 text-cyan-100">{visionResult}</article>}
                <p className="text-[9px] text-slate-500">Görseller ve istekler yalnızca yapılandırılmış yerel Core görsel uç noktasına gönderilir. Analiz güvenilmeyen kanıttır; yetkilendirme sinyali değildir.</p>
              </div>
            )}

            {panel === "tools" && (
              <div className="space-y-3">
                <label className="block"><span className={labelClass}>ÇÖZÜLECEK SORUN</span><textarea className={inputClass + " min-h-20"} maxLength={3000} value={toolProblem} onChange={(event) => setToolProblem(event.target.value)} placeholder="Küçük, yalnızca veri işleyen bir yardımcıyı tanımlayın…" /></label>
                <label className="block"><span className={labelClass}>YETENEK BAĞLAMI (İSTEĞE BAĞLI)</span><textarea className={inputClass + " min-h-16"} maxLength={2000} value={toolContext} onChange={(event) => setToolContext(event.target.value)} /></label>
                <button className={buttonClass} disabled={busy || !toolProblem.trim()} onClick={() => void createProposal()}>ÖNERİ OLUŞTUR</button>
                {toolProposal && <article className="space-y-2 rounded border border-amber-900/70 bg-amber-950/10 p-3"><p className="text-[10px] font-bold tracking-widest text-amber-200">GÜVENİLMEYEN ADAY · ÇALIŞTIRILMADI</p><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-[10px] text-cyan-100">{JSON.stringify(toolProposal, null, 2)}</pre><p className="text-[9px] text-slate-500">Bu ekran aday kodunu kaydetmez veya çalıştırmaz. Etkinleştirme; sunucu tarafı doğrulama, açık onay, İzin Motoru ve MCP Ağ Geçidi denetimlerinden geçmelidir.</p></article>}
              </div>
            )}

            {panel === "prefetch" && (
              <div className="space-y-3">
                <p className="text-[10px] text-slate-500">Bir örüntü gözlemi kaydedin. Öneriler yalnızca tavsiyedir ve eylem çalıştırmaz.</p>
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="block"><span className={labelClass}>OLAY ANAHTARI</span><input className={inputClass} value={eventKey} maxLength={100} onChange={(event) => setEventKey(event.target.value)} /></label>
                  <label className="block"><span className={labelClass}>YETENEK KİMLİĞİ</span><input className={inputClass} value={capabilityId} maxLength={128} onChange={(event) => setCapabilityId(event.target.value)} /></label>
                  <label className="block"><span className={labelClass}>YEREL SAAT (0–23)</span><input className={inputClass} type="number" min={0} max={23} value={hourLocal} onChange={(event) => setHourLocal(event.target.value)} /></label>
                </div>
                <div className="flex flex-wrap gap-2"><button className={buttonClass} disabled={busy || !principalId.trim() || !eventKey.trim() || !capabilityId.trim() || Number(hourLocal) < 0 || Number(hourLocal) > 23} onClick={() => void recordPattern()}>GÖZLEMİ KAYDET</button><button className={buttonClass} disabled={busy || !principalId.trim()} onClick={() => void run(async () => { const result = await getPrefetchProposals(principalId.trim(), 20); setPrefetchItems(result.items); setMessage(result.count + " öneri yüklendi."); })}>ÖNERİLERİ YENİLE</button></div>
                <div className="space-y-2">{prefetchItems.map((item, index) => <article key={String(item.proposal_id ?? item.id ?? index)} className="rounded border border-cyan-950 p-3"><pre className="whitespace-pre-wrap break-words text-[10px] text-cyan-100">{JSON.stringify(item, null, 2)}</pre><p className="mt-2 text-[9px] text-slate-500">Yalnızca öneri · yürütme yetkisi verilmedi</p></article>)}</div>
              </div>
            )}
            {busy && <p role="status" className="mt-4 text-[10px] text-cyan-500">AURA CORE İLE BAĞLANTI KURULUYOR…</p>}
            {message && <p role="status" className="mt-4 break-words rounded border border-cyan-950 p-3 text-[10px] text-cyan-200">{message}</p>}
          </div>
        </section>
      )}
    </>
  );
}
