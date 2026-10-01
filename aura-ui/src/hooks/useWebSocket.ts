import { useEffect, useState, useRef } from 'react';

export interface AuraEvent {
  event: string;
  message?: string;
  status?: string;
  step?: string;
  data?: any;
}

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<AuraEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setEvents((prev) => [...prev, parsed]);
      } catch (e) {
        console.error("WebSocket Ayrıştırma Hatası", e);
      }
    };

    ws.onclose = () => setIsConnected(false);

    return () => ws.close();
  }, [url]);

  return { events, isConnected };
}