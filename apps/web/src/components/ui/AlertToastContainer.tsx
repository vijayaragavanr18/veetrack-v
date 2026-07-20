"use client";

import { useCallback, useState } from "react";
import AlertToast from "./AlertToast";
import { useAlertSocket } from "@/features/watchlists/hooks/useAlertSocket";
import type { AlertPayload } from "@/features/watchlists/hooks/useAlertSocket";

interface ToastEntry {
  id: string;
  alert: AlertPayload;
}

let _seq = 0;
function nextId() {
  return `alert-${++_seq}`;
}

export default function AlertToastContainer() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  const handleAlert = useCallback((alert: AlertPayload) => {
    setToasts((prev) => [...prev, { id: nextId(), alert }]);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useAlertSocket(handleAlert);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-label="Alert notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
    >
      {toasts.map((t) => (
        <AlertToast
          key={t.id}
          alert={t.alert}
          onDismiss={() => dismiss(t.id)}
        />
      ))}
    </div>
  );
}
