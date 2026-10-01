const API_BASE = "http://127.0.0.1:8000/api";

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
    return response.json();
  }
};