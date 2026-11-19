import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AuraApiError, getCapabilityCenter, invokeCapabilityTool,
  type CapabilityCenterResponse, type CenterTool,
} from "../api/client";

const phaseTitles: Record<number, string> = {
  1: "Bellek ve Güvenlik", 2: "Ses", 3: "Masaüstü ve Sistem",
  4: "Araştırma", 5: "Kodlama ve Ajanlar", 6: "Görüntü ve HUD",
  7: "Bilim", 8: "Akıllı Ev ve Robotik", 9: "Kişisel Araçlar",
};

function errorText(cause: unknown): string {
  if (cause instanceof AuraApiError) {
    return cause.code + " (HTTP " + cause.status + "): " + cause.message +
      (cause.requestId ? " · İstek: " + cause.requestId : "");
  }
  return cause instanceof Error ? cause.message : "İstek tamamlanamadı.";
}

export default function CapabilityAndToolCenter({
  onInsertDirective,
}: { onInsertDirective: (text: string) => void }) {
  const [data, setData] = useState<CapabilityCenterResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [featureId, setFeatureId] = useState<number | null>(null);
  const [toolId, setToolId] = useState("");
  const [scope, setScope] = useState("local_default");
  const [args, setArgs] = useState("{}");
  const [approvalId, setApprovalId] = useState("");
  const [confirmRisk, setConfirmRisk] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const next = await getCapabilityCenter();
      if (next.feature_count !== 117 || next.features.length !== 117) {
        throw new Error("Çekirdek beklenen 117 özellik kaydını döndürmedi.");
      }
      setData(next);
      setError("");
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const features = useMemo(() => {
    const text = search.trim().toLocaleLowerCase("tr-TR");
    return (data?.features ?? []).filter((item) =>
      (filter === null || item.phase === filter) &&
      (!text || (String(item.id) + " " + item.name).toLocaleLowerCase("tr-TR").includes(text)),
    );
  }, [data, filter, search]);

  const selected = data?.features.find((item) => item.id === featureId);
  const linked = new Set(selected?.mcp_capability_ids ?? []);
  const tools = (data?.tools ?? []).filter((item) =>
    !selected || linked.has(item.capability_id));
  const tool = data?.tools.find((item) => item.capability_id === toolId);

  function selectTool(value: CenterTool) {
    setToolId(value.capability_id);
    setResult(null);
    setError("");
    setArgs("{}");
    setApprovalId("");
    setScope("local_default");
    setConfirmRisk(false);
  }

  async function runTool() {
    if (!tool || !tool.gateway_registered || running) return;
    if ((tool.risk_level === "high" || tool.risk_level === "critical") && !confirmRisk) {
      setError("Riskli aracı çağırmak için manuel onay kutusunu seçin. Bu işlem Owner izni vermez.");
      return;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(args); } catch {
      setError("Geçerli bir JSON nesnesi gerekli.");
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setError("Araç girdisi JSON nesnesi olmalı.");
      return;
    }
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const reply = await invokeCapabilityTool({
        capability_id: tool.capability_id,
        resource_scope: scope,
        arguments: parsed as Record<string, unknown>,
        ...(approvalId.trim() ? { approval_id: approvalId.trim() } : {}),
      });
      setResult(reply);
      if (reply.status !== "executed") {
        setError(reply.status === "approval_required"
          ? "Gateway bağımsız Owner onayı gerektiriyor. UI bu onayı veremez."
          : "PermissionEngine/Gateway işlemi reddetti.");
      }
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setRunning(false);
    }
  }

  return (
    <section aria-label="Yetenek ve Araç Merkezi"
      className="flex-1 min-h-0 overflow-y-auto py-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4 border-b border-cyan-900/50 pb-5">
        <div>
          <h2 className="text-xl font-bold tracking-[.15em] text-cyan-100">YETENEK VE ARAÇ MERKEZİ</h2>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-400">
            117 bounded-v1 kaynak özelliği. Gerçek MCP araçları ayrı bir listede görünür.
            Kayıtlı araç, PermissionEngine yetkisi değildir.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={busy}
          className="rounded border border-cyan-800 px-4 py-2 text-xs text-cyan-200 disabled:opacity-40">
          {busy ? "YÜKLENİYOR…" : "KAYITLARI YENİLE"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mb-4 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
          {error}
        </p>
      )}
      <div className="mb-4 flex flex-wrap gap-2 text-[11px]">
        <span className="rounded border border-slate-800 px-3 py-2 text-slate-300">
          Özellik: {data?.feature_count ?? "—"}
        </span>
        <span className="rounded border border-slate-800 px-3 py-2 text-slate-300">
          MCP kaydı: {data?.tools.length ?? "—"}
        </span>
        <span className="rounded border border-amber-900/50 px-3 py-2 text-amber-300">
          Gerçek yetki yalnız Gateway'de değerlendirilir
        </span>
      </div>
      <div className="grid min-h-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(340px,.8fr)]">
        <div className="min-w-0 rounded-xl border border-cyan-950 bg-[#06111c] p-4">
          <input aria-label="Özellik ara" type="search" value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="117 özellikte ara…"
            className="mb-3 w-full rounded border border-cyan-900 bg-slate-950 p-3 text-xs text-cyan-100" />
          <div className="mb-4 flex flex-wrap gap-2">
            <button type="button" onClick={() => setFilter(null)} aria-pressed={filter === null}
              className="rounded border border-cyan-900 px-2 py-1.5 text-[10px] text-cyan-300">TÜMÜ</button>
            {Object.entries(phaseTitles).map(([key, label]) => (
              <button type="button" key={key} onClick={() => setFilter(Number(key))}
                aria-pressed={filter === Number(key)}
                className={filter === Number(key)
                  ? "rounded bg-cyan-900 px-2 py-1.5 text-[10px] text-cyan-100"
                  : "rounded border border-slate-800 px-2 py-1.5 text-[10px] text-slate-400"}>
                {label}
              </button>
            ))}
          </div>
          <div className="max-h-[46vh] space-y-2 overflow-y-auto pr-1">
            {features.map((feature) => (
              <button type="button" key={feature.id}
                onClick={() => {
                  setFeatureId(featureId === feature.id ? null : feature.id);
                  setToolId("");
                  setResult(null);
                }}
                aria-pressed={featureId === feature.id}
                className={featureId === feature.id
                  ? "flex w-full items-center justify-between gap-3 rounded-lg border border-cyan-500 bg-cyan-950/40 p-3 text-left"
                  : "flex w-full items-center justify-between gap-3 rounded-lg border border-slate-800 p-3 text-left hover:border-cyan-900"}>
                <span className="min-w-0 text-xs text-cyan-100">
                  <span className="mr-2 text-slate-500">#{feature.id}</span>
                  {feature.name}
                  <span className="mt-1 block text-[10px] text-slate-500">{feature.category}</span>
                </span>
                <span className={feature.runtime_status === "mcp_registered"
                  ? "shrink-0 text-[10px] text-cyan-300"
                  : "shrink-0 text-[10px] text-amber-400"}>
                  {feature.runtime_status === "mcp_registered" ? "MCP BAĞLI" : "KOD KAYDI"}
                </span>
              </button>
            ))}
          </div>
          {selected && (
            <div className="mt-4 rounded border border-cyan-900/50 p-3 text-xs">
              <div className="text-cyan-200">{selected.name}</div>
              <p className="my-2 text-slate-400">
                {selected.runtime_status === "metadata_only"
                  ? "Kaynak kaydı mevcut; bu özellik için doğrudan MCP yürütücüsü bağlanmamış."
                  : "Bu özelliğin canlı MCP kaydı var; kullanım için ayrı Gateway izni gerekir."}
              </p>
              <button type="button" onClick={() => onInsertDirective(selected.name)}
                className="rounded border border-cyan-800 px-3 py-2 text-cyan-300">
                KOMUT ALANINA EKLE — ÇALIŞTIRMAZ
              </button>
            </div>
          )}
        </div>
        <div className="min-w-0 rounded-xl border border-cyan-950 bg-[#06111c] p-4">
          <h3 className="mb-2 text-sm font-bold tracking-[.1em] text-cyan-200">GATEWAY ARAÇLARI</h3>
          <p className="mb-4 text-[11px] leading-5 text-slate-400">
            Gerçek Kernel ProviderRegistry ve CapabilityRegistry'den gelir.
            Araç listesi PermissionEngine'i atlamaz.
          </p>
          <div className="mb-4 max-h-52 space-y-2 overflow-y-auto">
            {tools.map((item) => (
              <button type="button" key={item.capability_id} onClick={() => selectTool(item)}
                className={toolId === item.capability_id
                  ? "w-full rounded border border-cyan-500 bg-cyan-950/30 p-3 text-left text-xs"
                  : "w-full rounded border border-slate-800 p-3 text-left text-xs hover:border-cyan-900"}>
                <span className="block break-all font-semibold text-cyan-100">{item.capability_id}</span>
                <span className="mt-1 block text-[10px] text-slate-500">
                  {item.tool_name} · {item.risk_level} ·
                  {item.gateway_registered ? " kayıtlı" : " erişilemiyor"}
                </span>
              </button>
            ))}
            {!tools.length && <p className="text-xs text-amber-300">Bağlı MCP aracı yok.</p>}
          </div>
          {tool && (
            <div className="space-y-3 border-t border-cyan-900/50 pt-4">
              <p className="break-all text-xs text-cyan-200">{tool.provider_id} / {tool.tool_name}</p>
              <label className="block text-[11px] text-slate-400">
                Kaynak kapsamı
                <input value={scope} onChange={(event) => setScope(event.target.value)}
                  className="mt-1 w-full rounded border border-cyan-900 bg-slate-950 p-2 text-xs text-cyan-100" />
              </label>
              <label className="block text-[11px] text-slate-400">
                JSON araç girdisi
                <textarea value={args} onChange={(event) => setArgs(event.target.value)}
                  rows={5} spellCheck={false}
                  className="mt-1 w-full rounded border border-cyan-900 bg-slate-950 p-2 font-mono text-xs text-cyan-100" />
              </label>
              <label className="block text-[11px] text-slate-400">
                Bağımsız Owner onay kimliği (varsa)
                <input value={approvalId} onChange={(event) => setApprovalId(event.target.value)}
                  className="mt-1 w-full rounded border border-cyan-900 bg-slate-950 p-2 text-xs text-cyan-100" />
              </label>
              {(tool.risk_level === "high" || tool.risk_level === "critical") && (
                <label className="flex gap-2 text-[11px] text-amber-300">
                  <input type="checkbox" checked={confirmRisk} onChange={(event) => setConfirmRisk(event.target.checked)} />
                  Riskli çağrıyı manuel başlatıyorum; bu Owner izni yerine geçmez.
                </label>
              )}
              <button type="button" onClick={() => void runTool()}
                disabled={!tool.gateway_registered || running}
                className="w-full rounded border border-cyan-600 px-4 py-3 text-xs font-bold text-cyan-200 disabled:opacity-40">
                {running ? "GATEWAY ÇALIŞIYOR…" : "MCP GATEWAY İLE ÇALIŞTIR"}
              </button>
            </div>
          )}
          {result !== null && (
            <div className="mt-4 rounded border border-slate-800 bg-slate-950/80 p-3">
              <p className="mb-2 text-[10px] text-slate-500">YANIT — DIŞ ARAÇ ÇIKTISI GÜVENİLMEZDİR</p>
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] text-slate-200">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
