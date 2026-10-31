import { useCallback, useState } from "react";

interface GoalGroup {
  goal_id: string;
  category: string;
  evidence_count: number;
  proposal_ids: string[];
  requires_owner_review: boolean;
}
interface GoalTree {
  root_goal?: string;
  groups?: GoalGroup[];
  proposal_count?: number;
  mode: string;
  authorization_granted: boolean;
}

/**
 * AURA HUD has NO approval authority. The OS-owner WebAuthn review surface
 * lives on another origin in an independently started owner control plane.
 */
export default function EvolutionReviewPanel() {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tree, setTree] = useState<GoalTree | null>(null);
  const [message, setMessage] = useState("Evolution incelemesi yalnızca görüntüleme modundadır.");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/evolution/goals", {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Evolution Core etkin değil / yetki gerekiyor (" + response.status + ")");
      const result: GoalTree = await response.json();
      if (result.authorization_granted) {
        throw new Error("Beklenmeyen yetki bildirimi; güvenlik için inceleme kapatıldı.");
      }
      setTree(result);
      setMessage("Kaynak kanıtlı hedefler; yetkilendirme verilmedi.");
    } catch (error) {
      setTree(null);
      setMessage(error instanceof Error ? error.message : "Evolution durumuna erişilemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <section className="mx-auto mt-6 w-full max-w-5xl border border-cyan-900/70 bg-slate-950/80 p-5 text-xs text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold tracking-[.28em] text-cyan-400">
            EVOLUTION / PRIMAL ANCHOR
          </p>
          <p className="mt-2 text-slate-400">Gelişim önerileri · Onay ve çalıştırma bu HUD içinde mümkün değil.</p>
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => {
            setExpanded(!expanded);
            if (!expanded) void refresh();
          }}
          className="rounded border border-cyan-800 px-3 py-2 text-cyan-300 hover:border-cyan-400"
        >
          {expanded ? "İNCELEMEYİ KAPAT" : "HEDEFLERİ İNCELE"}
        </button>
      </div>
      {expanded && (
        <div className="mt-5 space-y-3 border-t border-cyan-950 pt-4">
          <div role="status" className="text-slate-400">{loading ? "Hedefler alınıyor…" : message}</div>
          {tree && (
            <>
              <div className="flex flex-wrap gap-4 text-cyan-300">
                <span>Mod: {tree.mode}</span>
                <span>Öneri: {tree.proposal_count ?? 0}</span>
                <span>Yetki: YOK</span>
              </div>
              {(tree.groups ?? []).map(group => (
                <div key={group.goal_id} className="rounded border border-cyan-950 p-3">
                  <h3 className="text-cyan-200">{group.category} · {group.evidence_count} bulgu</h3>
                  <p className="mt-1 break-all text-[10px] text-slate-500">
                    Proposal IDs: {group.proposal_ids.join(", ")}
                  </p>
                  <p className="mt-2 text-amber-300">
                    {group.requires_owner_review ? "Local Owner incelemesi gerekli" : "İnceleme bekleniyor"}
                  </p>
                </div>
              ))}
            </>
          )}
          <div className="border-t border-cyan-950 pt-3">
            <p className="mb-2 text-[11px] text-slate-400">
              Gerçek passkey doğrulaması ayrı, yerel owner-control-plane origin'inde yapılır.
              Bu bağlantı hiçbir izin veya tool çalıştırma işlemi yapmaz.
            </p>
            <a
              href="http://localhost:8766/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex rounded border border-amber-700 px-4 py-2 text-amber-200 hover:border-amber-400"
            >
              TRUSTED OWNER REVIEW AÇ
            </a>
          </div>
        </div>
      )}
    </section>
  );
}
