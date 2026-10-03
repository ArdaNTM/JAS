import { useEffect, useRef, useState } from "react";

export interface TaskEvent {
  type: string;
  task_id: string;
  payload: Record<string, unknown>;
}

export function useTaskEvents(taskId: string | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return;

    const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
    const websocketUrl = apiUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    const token = "aura-secure-token-123"; // TODO: Move to .env

    const socket = new WebSocket(`${websocketUrl}/ws/tasks/${taskId}?token=${token}`);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as TaskEvent;
      setEvents((current) => [...current, data]);
    };
    socket.onerror = () => console.error("AURA WebSocket error");

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [taskId]);

  return { events };
}
