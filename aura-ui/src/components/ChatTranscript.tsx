import type { ReactNode } from "react";

export type ChatTurn = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  source?: string;
  approvalId?: string | null;
};

function MarkdownContent({ text }: { text: string }): ReactNode {
  const fence = String.fromCharCode(96).repeat(3);
  const parts = text.split(fence);
  return parts.map((part, index) => {
    if (index % 2 === 1) {
      const code = part.replace(/^[^\n]*\n/, "");
      return <pre key={index} className="my-2 overflow-x-auto rounded border border-cyan-900/70 bg-[#02060b] p-3 text-xs text-cyan-200"><code>{code}</code></pre>;
    }
    return <p key={index} className="whitespace-pre-wrap break-words">{part}</p>;
  });
}

export default function ChatTranscript({ turns }: { turns: ChatTurn[] }) {
  return (
    <section aria-label="Asistan sohbet geçmişi" className="mt-8 w-full max-w-3xl rounded-xl border border-cyan-950/80 bg-slate-950/70 p-4">
      <h2 className="mb-3 text-[10px] font-bold tracking-widest text-cyan-400">AURA · SOHBET</h2>
      <div role="log" aria-live="polite" className="max-h-[42vh] min-h-36 space-y-4 overflow-y-auto pr-2">
        {turns.length === 0 && <p className="py-8 text-center text-xs text-slate-500">Merhaba! Bir mesaj yazabilir veya sesli konuşabilirsin.</p>}
        {turns.map((turn) => (
          <article key={turn.id} className={turn.role === "user"
            ? "ml-6 rounded-lg border border-cyan-900 bg-cyan-950/20 p-4"
            : "mr-6 rounded-lg border border-slate-800 bg-slate-900/40 p-4"}>
            <div className="mb-2 text-[10px] font-bold tracking-widest text-cyan-400">{turn.role === "user" ? "SEN" : "AURA"}</div>
            <div className="text-left text-[13px] leading-6 text-slate-200">
              <MarkdownContent text={turn.content || "Yanıt hazırlanıyor…"} />
            </div>
            {turn.source && <div className="mt-2 break-words text-[10px] text-slate-500">Kaynak / araç: {turn.source}</div>}
            {turn.approvalId && (
              <div className="mt-3 rounded border border-amber-800/70 p-3 text-xs text-amber-200">
                <p>Bekleyen bağımsız Owner onayı: <code>{turn.approvalId}</code></p>
                <button type="button" className="mt-2 rounded border border-amber-700 px-3 py-2"
                  onClick={() => window.open("http://localhost:8766", "_blank", "noopener,noreferrer")}>
                  Owner incelemesini aç
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
