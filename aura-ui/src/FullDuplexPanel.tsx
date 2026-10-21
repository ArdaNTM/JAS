import { useState } from "react";
import type { useFullDuplexAura } from "./voice/useFullDuplexAura";

type FullDuplexController = ReturnType<typeof useFullDuplexAura>;

export default function FullDuplexPanel({ voice, goal }: { voice: FullDuplexController; goal: string }) {
  const [testText, setTestText] = useState("Merhaba. AURA full-duplex ses hattı hazır.");
  const [visionConsent, setVisionConsent] = useState(false);

  async function readScreen() {
    if (!visionConsent) return;
    const approved = window.confirm(
      "AURA mevcut masaüstü ekranının görüntüsünü yerel görsel sağlayıcıya gönderecek. Ekranda hassas bilgi bulunabilir. Devam edilsin mi?",
    );
    if (!approved) return;
    setVisionConsent(false);
    const result = await voice.describeScreen();
    if (result && voice.active) await voice.speak(result.slice(0, 1500));
  }

  return (
    <section className="mx-auto mt-6 w-full max-w-5xl rounded border border-cyan-950/80 bg-slate-950/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[9px] font-bold tracking-[.25em] text-cyan-500">FULL-DUPLEX / ALGILAMA</div>
          <div className="mt-1 text-xs text-cyan-100">
            {voice.active ? (voice.speaking ? "AURA KONUŞUYOR — ARAYA GİREBİLİRSİN" : "MİKROFON DİNLİYOR") : "OTURUM KAPALI"}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[8px] tracking-wider ${voice.eventConnected ? "text-emerald-300" : "text-amber-300"}`}>
            SSE {voice.eventConnected ? "BAĞLI" : "BAĞLANIYOR"}
          </span>
          {voice.active ? (
            <>
              <button type="button" onClick={() => void voice.interrupt()} className="border border-amber-700 px-3 py-2 text-[9px] tracking-wider text-amber-200 hover:border-amber-300">
                SESİ KES
              </button>
              <button type="button" onClick={() => void voice.stop()} className="border border-red-900 px-3 py-2 text-[9px] tracking-wider text-red-300 hover:border-red-500">
                OTURUMU KAPAT
              </button>
            </>
          ) : (
            <button type="button" onClick={() => void voice.start()} className="border border-cyan-700 px-3 py-2 text-[9px] font-bold tracking-wider text-cyan-200 hover:border-cyan-300">
              MİKROFON + SESİ BAŞLAT
            </button>
          )}
        </div>
      </div>

      <div role="status" aria-live="polite" className="mt-3 border-l border-cyan-800 pl-3 text-[10px] leading-5 text-slate-400">
        {voice.message}
      </div>
      {voice.transcript && (
        <div className="mt-3 rounded border border-cyan-950 p-3">
          <div className="text-[8px] tracking-[.2em] text-slate-500">SON STT TRANSKRİPSİYONU</div>
          <p className="mt-1 whitespace-pre-wrap text-xs text-cyan-100">{voice.transcript}</p>
          <p className="mt-2 text-[8px] text-slate-500">Metin komut alanına aktarılır; görev yürütmesi için kullanıcı onayı gerekir.</p>
        </div>
      )}

      <div className="mt-4 rounded border border-cyan-900/70 bg-black/20 p-3">
        <div className="text-[9px] font-bold tracking-[.2em] text-cyan-500">GOVERNED AUTONOMOUS RUN</div>
        <p className="mt-1 text-[10px] leading-5 text-slate-400">Bu düğme komutu yalnızca açık kullanıcı tıklamasıyla backend Governor'a gönderir. Çalıştırma devre dışıysa veya izin listesi yoksa backend isteği reddeder; UI hiçbir aracı doğrudan çağırmaz.</p>
        <button
          type="button"
          disabled={!goal.trim() || voice.busy || voice.autonomyState === "running" || voice.autonomyState === "starting"}
          onClick={() => {
            const approved = window.confirm("Bu direktifi AURA'nın yönetilen otonom döngüsünde çalıştırmak istiyor musunuz? Yürütme yalnızca Kernel Permission Engine ve MCP Gateway yetkileri dahilinde yapılır.");
            if (approved) void voice.runGovernedGoal(goal);
          }}
          className="mt-2 border border-amber-800 px-3 py-2 text-[9px] font-bold tracking-wider text-amber-200 disabled:opacity-30"
        >
          {voice.autonomyState === "running" || voice.autonomyState === "starting" ? "GOVERNOR ÇALIŞIYOR…" : "GOVERNOR İLE ÇALIŞTIR"}
        </button>
        {voice.autonomyResult && <p className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-5 text-cyan-100">{voice.autonomyResult}</p>}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded border border-cyan-950/70 p-3">
          <div className="text-[9px] font-bold tracking-[.2em] text-cyan-600">GATEWAY TTS TESTİ</div>
          <textarea
            value={testText}
            onChange={(event) => setTestText(event.target.value)}
            maxLength={8000}
            rows={3}
            className="mt-2 w-full resize-y rounded border border-cyan-950 bg-black/40 p-2 text-xs text-cyan-100 outline-none focus:border-cyan-700"
            aria-label="Seslendirme test metni"
          />
          <button
            type="button"
            disabled={!voice.active || !testText.trim() || voice.busy}
            onClick={() => void voice.speak(testText).catch((error: unknown) => window.alert(error instanceof Error ? error.message : "Gateway TTS başarısız"))}
            className="mt-2 border border-cyan-800 px-3 py-2 text-[9px] tracking-wider text-cyan-200 disabled:opacity-30"
          >
            METNİ GATEWAY ÜZERİNDEN SESLENDİR
          </button>
        </div>

        <div className="rounded border border-cyan-950/70 p-3">
          <div className="text-[9px] font-bold tracking-[.2em] text-cyan-600">KONTROLLÜ EKRAN ALGILAMA</div>
          <label className="mt-2 flex items-start gap-2 text-[10px] leading-5 text-slate-400">
            <input type="checkbox" checked={visionConsent} onChange={(event) => setVisionConsent(event.target.checked)} className="mt-1 accent-cyan-500" />
            Bu istekte masaüstü ekran görüntüsünün yerel görsel sağlayıcı tarafından analiz edilmesine izin veriyorum.
          </label>
          <button type="button" disabled={!visionConsent} onClick={() => void readScreen()} className="mt-2 border border-cyan-800 px-3 py-2 text-[9px] tracking-wider text-cyan-200 disabled:opacity-30">
            EKRANI OKU
          </button>
          {voice.vision && (
            <div className="mt-3 max-h-40 overflow-auto rounded bg-black/30 p-2">
              <div className="text-[8px] tracking-wider text-slate-500">GÖRSEL SAĞLAYICI ÇIKTISI · GÜVENİLMEYEN BAĞLAM</div>
              <p className="mt-1 whitespace-pre-wrap text-[10px] leading-5 text-cyan-100">{voice.vision.description}</p>
              <button type="button" disabled={!voice.active} onClick={() => void voice.speak(voice.vision!.description.slice(0, 1500))} className="mt-2 text-[9px] text-cyan-500 hover:text-cyan-200 disabled:opacity-30">
                SONUCU SESLENDİR
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4">
        <div className="text-[9px] font-bold tracking-[.2em] text-cyan-600">PROAKTİF BİLDİRİMLER</div>
        {voice.notices.length === 0 ? (
          <p className="mt-2 text-[10px] text-slate-600">Henüz yeni bildirim yok. Backend sessiz saat ve bütçe kurallarını uygular.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {voice.notices.map((notice) => (
              <li key={notice.id} className="flex flex-wrap items-start justify-between gap-3 rounded border border-cyan-950/70 bg-black/20 p-3">
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap text-xs text-cyan-100">{notice.message}</p>
                  <time className="mt-1 block text-[8px] text-slate-600" dateTime={notice.timestamp}>{new Date(notice.timestamp).toLocaleString()}</time>
                </div>
                <button type="button" disabled={!voice.active} onClick={() => void voice.speakNotice(notice.message)} className="text-[9px] tracking-wider text-cyan-500 hover:text-cyan-200 disabled:opacity-30">
                  SESLENDİR
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
