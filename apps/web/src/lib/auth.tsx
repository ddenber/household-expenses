"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { get, post, setCsrf } from "@/lib/api";

export interface User {
  id: string;
  email: string;
  name: string;
  role: "super_admin" | "financial_admin" | "employee" | "auditor";
  household_name: string;
  is_demo: boolean;
}

interface Ctx {
  user: User | null;
  loading: boolean;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);
export const isAdminRole = (r?: string) => r === "super_admin" || r === "financial_admin";
export const canWrite = (r?: string) => isAdminRole(r);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    get<{ user: User; csrf_token: string }>("/auth/me")
      .then((r) => {
        setCsrf(r.csrf_token);
        setUser(r.user);
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await post<{ user: User; csrf_token: string }>("/auth/login", { email, password });
    setCsrf(r.csrf_token);
    setUser(r.user);
  }, []);

  const logout = useCallback(async () => {
    await post("/auth/logout").catch(() => undefined);
    setUser(null);
  }, []);

  return <AuthCtx.Provider value={{ user, loading, login, logout }}>{children}</AuthCtx.Provider>;
}
