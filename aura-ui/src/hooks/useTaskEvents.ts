import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  getWebSocketTicket,
} from "../api/client";

export interface TaskEvent {
  id?: string;
  event?: string;
  type?: string;
  task_id?: string;
  timestamp?: string;
  source?: string;
  payload?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

interface EventConnectionState {
  connected: boolean;
  reconnecting: boolean;
}

function websocketBaseUrl(): string {
  const apiBase =
    import.meta.env.VITE_API_BASE_URL ??
    "http://127.0.0.1:8000";

  return apiBase
    .replace(/^http:/, "ws:")
    .replace(/^https:/, "wss:");
}

export function useTaskEvents(
  taskId: string | null,
) {
  const [events, setEvents] =
    useState<TaskEvent[]>([]);

  const [connection, setConnection] =
    useState<EventConnectionState>({
      connected: false,
      reconnecting: false,
    });

  const socketRef =
    useRef<WebSocket | null>(null);

  const retryTimerRef =
    useRef<number | null>(null);

  const stoppedRef =
    useRef(false);

  useEffect(() => {
    stoppedRef.current = false;

    if (!taskId) {
      setEvents([]);

      setConnection({
        connected: false,
        reconnecting: false,
      });

      return () => {
        stoppedRef.current = true;
      };
    }

    let retry = 0;

    const connect = async (): Promise<void> => {
      if (stoppedRef.current) {
        return;
      }

      setConnection({
        connected: false,
        reconnecting: retry > 0,
      });

      try {
        const ticket =
          await getWebSocketTicket();

        if (stoppedRef.current) {
          return;
        }

        const socket =
          new WebSocket(
            `${websocketBaseUrl()}/ws/tasks/${encodeURIComponent(taskId)}?ticket=${encodeURIComponent(ticket.ticket)}`,
          );

        socketRef.current = socket;

        socket.onopen = () => {
          retry = 0;

          setConnection({
            connected: true,
            reconnecting: false,
          });
        };

        socket.onmessage = (
          message,
        ) => {
          try {
            const event =
              JSON.parse(
                message.data,
              ) as TaskEvent;

            setEvents(
              (current) => [
                ...current.slice(-199),
                event,
              ],
            );
          } catch {
            // Ignore malformed event frames.
          }
        };

        socket.onerror = () => {
          socket.close();
        };

        socket.onclose = () => {
          socketRef.current = null;

          if (stoppedRef.current) {
            return;
          }

          retry += 1;

          setConnection({
            connected: false,
            reconnecting: true,
          });

          const delay = Math.min(
            1000 *
              2 **
                Math.min(
                  retry - 1,
                  5,
                ),
            15000,
          );

          retryTimerRef.current =
            window.setTimeout(
              () => {
                void connect();
              },
              delay,
            );
        };
      } catch {
        if (stoppedRef.current) {
          return;
        }

        retry += 1;

        setConnection({
          connected: false,
          reconnecting: true,
        });

        const delay = Math.min(
          1000 *
            2 **
              Math.min(
                retry - 1,
                5,
              ),
          15000,
        );

        retryTimerRef.current =
          window.setTimeout(
            () => {
              void connect();
            },
            delay,
          );
      }
    };

    void connect();

    return () => {
      stoppedRef.current = true;

      if (
        retryTimerRef.current !== null
      ) {
        window.clearTimeout(
          retryTimerRef.current,
        );

        retryTimerRef.current = null;
      }

      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [taskId]);

  return {
    events,
    connected:
      connection.connected,
    reconnecting:
      connection.reconnecting,
  };
}