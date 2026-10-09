"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "generic", String(e)));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(() => void reload(true), pollMs);
    return () => clearInterval(id);
  }, [pollMs, reload]);
  return { data, error, loading, reload };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (lock.current) return undefined; // duplicate-tap protection
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.friendly : "Gabim");
      return undefined;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }, []);
  return { busy, error, run, setError };
}
