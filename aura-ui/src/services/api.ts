const API_BASE = "http://127.0.0.1:8000/api";

// Onay nesnesi için arayüz
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

export const AuraAPI = {
  planIntent: async (intent: string) => {
    const response = await fetch(`${API_BASE}/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ intent })
    });
    return response.json();
  },
  
  getApprovals: async () => {
    const response = await fetch(`${API_BASE}/approvals`);
    if (!response.ok) return [];
    return response.json();
  },

  approveAction: async (reqId: string) => {
    const response = await fetch(`${API_BASE}/approve/${reqId}`, {
      method: "POST"
    });
    return response.json();
  },

  getHistory: async () => {
    const response = await fetch(`${API_BASE}/history`);
    if (!response.ok) return [];
    return response.json();
  },

  // Bekleyen onayları getiren fonksiyon
  fetchPendingApprovals: async (): Promise<ApprovalRequest[]> => {
    try {
      const response = await fetch(`${API_BASE}/approvals`);
      if (!response.ok) return [];
      return await response.json();
    } catch (error) {
      console.error("Onay kuyruğu alınamadı:", error);
      return [];
    }
  },

  // Onay durumunu çözümleyen (Kabul/Red) fonksiyon
  resolveApproval: async (id: string, approved: boolean): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/approvals/${id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved })
      });
      return response.ok;
    } catch (error) {
      console.error("Onay işlemi başarısız:", error);
      return false;
    }
  }
};

// Geriye dönük uyumluluk için bağımsız exportlar
export const fetchPendingApprovals = AuraAPI.fetchPendingApprovals;
export const resolveApproval = AuraAPI.resolveApproval;