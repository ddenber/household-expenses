"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { isRetryable, post, uploadFile } from "@/lib/api";
import * as queue from "@/lib/offline-queue";
import { useAuth } from "@/lib/auth";

interface Ctx {
  online: boolean;
  pending: queue.Capture[];
  syncing: boolean;
  progress: Record<string, number>;
  syncNow(): Promise<{ synced: number; failed: number }>;
  refresh(): Promise<void>;
  lastCreated: React.MutableRefObject<Record<string, string>>;
}

const SyncCtx = createContext<Ctx>(null as unknown as Ctx);
export const useSync = () => useContext(SyncCtx);

export const adapter: queue.SyncApi = {
  async createExpense(c) {
    return post<{ id: string }>("/expenses", { client_ref: c.id, ...c.fields });
  },
  async uploadPage(expenseId, file, onProgress) {
    await uploadFile(`/expenses/${expenseId}/documents`, file.blob, file.name, onProgress);
  },
  isRetryable,
};

export function SyncProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState<queue.Capture[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const lastCreated = useRef<Record<string, string>>({});

  const refresh = useCallback(async () => setPending(await queue.list()), []);
  const syncNow = useCallback(async () => {
    setSyncing(true);
    try {
      const res = await queue.syncAll(
        {
          ...adapter,
          createExpense: async (c) => {
            const r = await adapter.createExpense(c);
            lastCreated.current[c.id] = r.id;
            return r;
          },
        },
        () => void refresh(),
        (id, p) => setProgress((s) => ({ ...s, [id]: p })),
      );
      return res;
    } finally {
      setSyncing(false);
      await refresh();
    }
  }, [refresh]);

  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => {
      setOnline(true);
      void syncNow();
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [syncNow]);

  useEffect(() => {
    if (!user) return;
    void refresh().then(() => navigator.onLine && void syncNow());
  }, [user, refresh, syncNow]);

  return (
    <SyncCtx.Provider value={{ online, pending, syncing, progress, syncNow, refresh, lastCreated }}>{children}</SyncCtx.Provider>
  );
}
