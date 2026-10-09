"use client";
import { useEffect, type ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import { SyncProvider } from "@/lib/sync";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);
  return (
    <AuthProvider>
      <SyncProvider>{children}</SyncProvider>
    </AuthProvider>
  );
}
