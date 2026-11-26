import { useEffect, useState, type ReactNode } from "react";
import { getCapabilityCenter, getContinuousEvolutionStatus, getSelfPatches, getPendingApprovals,
  type CapabilityCenterResponse, type ContinuousEvolutionStatus, type SelfPatchReview, type PendingApproval } from "../api/client";

export default function SystemDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const [center, setCenter] = useState<CapabilityCenterResponse | null>(null);
  const [evolution, setEvolution] = useState<ContinuousEvolutionStatus | null>(null);
  const [patches, setPatches] = useState<SelfPatchReview[] | null>(null);
  const [approvals, setApprovals] = useState<PendingApproval[] | null>(null);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const refresh = () => {
      void getCapabilityCenter().then(value => { if (alive) setCenter(value); }).catch(() => { if (alive) setCenter(null); });
      void getContinuousEvolutionStatus().then(value => { if (alive) setEvolution(value); }).catch(() => { if (alive) setEvolution(null); });
      void getSelfPatches().then(value => { if (alive) setPatches(value.items); }).catch(() => { if (alive) setPatches(null); });
      void getPendingApprovals().then(value => { if (alive) setApprovals(Array.isArray(value) ? value : null); }).catch(() => { if (alive) setApprovals(null); });
    };
    refresh();
    const timer = window.setInterval(refresh, 10000);
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", escape);
    return () => { alive = false; clearInterval(timer); window.removeEventListener("keydown", escape); };
  }, [open, onClose]);
  if (!open) return null;
  const providers = new Map<string, number>();
  center?.tools.filter(t => t.gateway_registered).forEach(t => providers.set(t.provider_id, (providers.get(t.provider_id) ?? 0) + 1));
  return <>
    <button type="button" aria-label="Sistem panelini kapat" className="astral-backdrop" onClick={onClose} />
    <aside className="astral-drawer" aria-label="Sistem Çekirdeği ve Evrim">
      <div className="astral-drawer-heading"><div><small>AURA // CONTROL PLANE</small><h2>Sistem Çekirdeği &amp; Evrim</h2></div><button onClick={onClose} type="button" aria-label="Kapat">×</button></div>
      <div className="astral-drawer-body">
        <section className="astral-card"><h3>BAĞIMSIZ ATTESTOR</h3><p>{evolution?.attestor_health?.state ?? "BİLİNMİYOR"}</p>
          {evolution?.attestor_health?.last_success ? <small>Son başarılı tarama: {new Date(evolution.attestor_health.last_success * 1000).toLocaleString("tr-TR")}</small> : null}
          {evolution?.attestor_health?.last_error && <p role="status">{evolution.attestor_health.last_error}</p>}
          <p>{evolution ? evolution.active_count + " aktif evrim yeteneği · " + evolution.queued_packages + " kuyrukta" : "Evrim durumu alınamadı"}</p>
        </section>
        <section className="astral-card"><h3>AKTİF EVRİM SAĞLAYICILARI</h3>{evolution?.active_providers ? (evolution.active_providers.length ? evolution.active_providers.map(p => <p key={p.repository}>{p.repository} · {p.tool_count} araç</p>) : <p>Aktif evrim sağlayıcısı yok.</p>) : <p>Durum alınamadı.</p>}</section>
        <section className="astral-card"><h3>PERMISSION ENGINE · ONAYLAR</h3>{approvals === null ? <p>Onay kuyruğu alınamadı.</p> : approvals.length === 0 ? <p>Bekleyen onay yok.</p> : approvals.map(a => <article key={a.approval_id}><strong>{a.capability_id}</strong><p>{a.operation_id} · {a.resource_scope}</p><small>{a.status} · {a.approval_id}</small></article>)}<a href="http://localhost:8766/" target="_blank" rel="noopener noreferrer">Bağımsız Owner incelemesini aç</a></section>
        <section className="astral-card"><h3>GATEWAY KAYITLARI</h3>{center ? (providers.size ? Array.from(providers, ([id, count]) => <p key={id}>{id} · {count} araç</p>) : <p>Kayıtlı araç yok.</p>) : <p>Kayıtlar alınamadı.</p>}<small>Kayıtlı olmak yürütme izni anlamına gelmez.</small></section>
        <section className="astral-card"><h3>SELF-PATCH İNCELEME</h3>{patches === null ? <p>İnceleme kuyruğu alınamadı.</p> : patches.length === 0 ? <p>Bekleyen taslak yok.</p> : patches.map(p => <article key={p.draft_id}><strong>{p.path}</strong><p>{p.summary}</p><small>{p.state} · {p.draft_id.slice(0, 12)}</small><p>{p.test_plan}</p></article>)}
        <small>Salt okunur · Bağımsız Owner incelemesi ve release kapısı gerekli.</small></section>
        {children}
      </div>
    </aside>
  </>;
}
