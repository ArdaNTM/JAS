import { getWebSocketTicket } from "../api/client";

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

    const connect = async () => {
      if (!active) {
        return;
      }

      let ticketResponse: {
        ticket: string;
        expires_at: number;
      };

      try {
        ticketResponse = await getWebSocketTicket();
      } catch {
        if (active) {
          setIsConnected(false);
        }
        return;
      }

      if (!active) {
        return;
      }

      const socketUrl = new URL(url, window.location.href);

      if (socketUrl.protocol === "http:") {
        socketUrl.protocol = "ws:";
      } else if (socketUrl.protocol === "https:") {
        socketUrl.protocol = "wss:";
      }

      socketUrl.searchParams.set("ticket", ticketResponse.ticket);

      const ws = new WebSocket(socketUrl.toString());

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