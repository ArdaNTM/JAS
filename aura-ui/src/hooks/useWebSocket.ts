import {
  useEffect,
  useRef,
  useState,
} from "react";

export interface AuraEvent {
  event?: string;
  type?: string;
  message?: string;
  status?: string;
  step?: string;
  data?: Record<string, unknown>;
}

export function useWebSocket(
  url: string,
) {
  const [events, setEvents] =
    useState<AuraEvent[]>([]);

  const [isConnected, setIsConnected] =
    useState(false);

  const wsRef =
    useRef<WebSocket | null>(null);

  useEffect(() => {
    let active = true;

    const connect = () => {
      if (!active) {
        return;
      }

      const ws =
        new WebSocket(url);

      wsRef.current = ws;

      ws.onopen = () => {
        if (active) {
          setIsConnected(true);
        }
      };

      ws.onmessage = (event) => {
        try {
          const parsed =
            JSON.parse(
              event.data,
            ) as AuraEvent;

          if (active) {
            setEvents(
              (current) => [
                ...current.slice(-199),
                parsed,
              ],
            );
          }
        } catch {
          // Ignore malformed event.
        }
      };

      ws.onclose = () => {
        if (!active) {
          return;
        }

        setIsConnected(false);
      };
    };

    connect();

    return () => {
      active = false;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [url]);

  return {
    events,
    isConnected,
  };
}