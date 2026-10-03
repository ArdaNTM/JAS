import React, { useEffect, useState } from 'react';

// Tip ve servis fonksiyonları doğrudan bileşenin içine alındı (api.ts bağımlılığı bitti)
export interface ApprovalRequest {
  id: string;
  task_id: string;
  capability: string;
  operation: string;
  parameters: Record<string, any>;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  timestamp: string;
}

const fetchPendingApprovals = async (): Promise<ApprovalRequest[]> => {
  try {
    const response = await fetch('http://localhost:8000/api/approvals');
    if (!response.ok) return [];
    return await response.json();
  } catch (error) {
    console.error("Onay kuyruğu alınamadı:", error);
    return [];
  }
};

const resolveApproval = async (id: string, approved: boolean): Promise<boolean> => {
  try {
    const response = await fetch(`http://localhost:8000/api/approvals/${id}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved })
    });
    return response.ok;
  } catch (error) {
    console.error("Onay işlemi başarısız:", error);
    return false;
  }
};

export const ApprovalPanel: React.FC = () => {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);

  useEffect(() => {
    const interval = setInterval(async () => {
      const pending = await fetchPendingApprovals();
      if (pending && Array.isArray(pending)) {
        setApprovals(pending);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleResolve = async (id: string, approved: boolean) => {
    const success = await resolveApproval(id, approved);
    if (success) {
      setApprovals((prev) => prev.filter((app) => app.id !== id));
    }
  };

  if (!approvals || approvals.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 w-96 flex flex-col gap-3 z-50">
      {approvals.map((approval) => (
        <div key={approval.id} className="bg-slate-900 border border-orange-500/50 shadow-lg shadow-orange-500/20 rounded-lg p-4 text-slate-200">
          <div className="flex items-center gap-2 mb-2 text-orange-400 font-bold">
            <span className="animate-pulse">⚠️</span>
            <span>AURA Onay Bekliyor</span>
          </div>
          
          <div className="text-sm mb-3">
            <p><span className="text-slate-400">Yetenek:</span> {approval.capability}</p>
            <p><span className="text-slate-400">İşlem:</span> {approval.operation}</p>
            <p className="mt-1"><span className="text-slate-400">Gerekçe:</span> {approval.reason}</p>
          </div>
          
          <div className="bg-slate-950 p-2 rounded text-xs font-mono text-slate-400 mb-4 overflow-x-auto">
            {JSON.stringify(approval.parameters, null, 2)}
          </div>

          <div className="flex justify-end gap-2">
            <button 
              onClick={() => handleResolve(approval.id, false)}
              className="px-4 py-1.5 rounded bg-slate-800 hover:bg-red-900/50 hover:text-red-400 border border-slate-700 hover:border-red-800 transition-colors text-sm"
            >
              DENY (Reddet)
            </button>
            <button 
              onClick={() => handleResolve(approval.id, true)}
              className="px-4 py-1.5 rounded bg-orange-600 hover:bg-orange-500 text-white font-medium transition-colors text-sm shadow-md"
            >
              ALLOW (İzin Ver)
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};