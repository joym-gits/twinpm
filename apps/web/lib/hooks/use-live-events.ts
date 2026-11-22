"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

/** Subscribe to /events/stream and invalidate server state when the program changes. */
export function useLiveEvents(): boolean {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      es = new EventSource("/api/v1/events/stream", { withCredentials: true });
      es.addEventListener("ready", () => setConnected(true));
      es.addEventListener("domain", (e) => {
        const kind = (() => {
          try {
            return (JSON.parse((e as MessageEvent<string>).data) as { kind?: string }).kind ?? "";
          } catch {
            return "";
          }
        })();
        // Coalesce bursts (a rebalance approves several suggestions at once).
        clearTimeout(timer);
        timer = setTimeout(() => {
          if (kind.startsWith("chat.")) void qc.invalidateQueries({ queryKey: ["conversation"] });
          else void qc.invalidateQueries();
        }, 300);
      });
      es.onerror = () => {
        setConnected(false);
        es?.close();
        retry = setTimeout(connect, 5000);
      };
    };
    connect();
    return () => {
      clearTimeout(retry);
      clearTimeout(timer);
      es?.close();
    };
  }, [qc]);
  return connected;
}
