"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/authStore";

export interface AlertPayload {
  type: "alert";
  watchlist_id: string;
  story_id: string;
  story_title: string;
  risk_level: string;
  channel: string;
}

type SocketMessage = AlertPayload | { type: "connected"; workspace_id: string };

const WS_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_WS_URL ?? "ws://localhost:8000")
    : "ws://localhost:8000";

const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECTS = 5;

export function useAlertSocket(
  onAlert: (alert: AlertPayload) => void,
): { connected: boolean; reconnecting: boolean } {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCount = useRef(0);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  const connect = useCallback(() => {
    if (!accessToken) return;

    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/alerts`);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send token as first message (query params are insecure for JWTs)
      ws.send(accessToken);
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      let msg: SocketMessage;
      try {
        msg = JSON.parse(event.data) as SocketMessage;
      } catch {
        return;
      }
      if (msg.type === "connected") {
        setConnected(true);
        setReconnecting(false);
        reconnectCount.current = 0;
      } else if (msg.type === "alert") {
        onAlertRef.current(msg);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (reconnectCount.current < MAX_RECONNECTS) {
        reconnectCount.current += 1;
        setReconnecting(true);
        setTimeout(connect, RECONNECT_DELAY_MS);
      } else {
        setReconnecting(false);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    connect();
    return () => {
      reconnectCount.current = MAX_RECONNECTS; // prevent reconnect on unmount
      wsRef.current?.close();
    };
  }, [accessToken, connect]);

  return { connected, reconnecting };
}
