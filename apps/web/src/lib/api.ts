import { t } from "@/i18n";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public extra: Record<string, unknown> = {}) {
    super(message);
  }
  get friendly(): string {
    const k = `errors.${this.code}`;
    const msg = t(k);
    return msg === k ? t("errors.generic") : msg;
  }
}

let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}

async function parse(res: Response) {
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
    const { code, message, ...extra } = (err ?? {}) as Record<string, unknown>;
    throw new ApiError(res.status, String(code ?? "generic"), String(message ?? res.statusText), extra);
  }
  return data;
}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "network");
  }
  return (await parse(res)) as T;
}

export const get = <T = unknown>(p: string) => api<T>("GET", p);
export const post = <T = unknown>(p: string, b?: unknown) => api<T>("POST", p, b ?? {});
export const patch = <T = unknown>(p: string, b?: unknown) => api<T>("PATCH", p, b ?? {});
export const del = <T = unknown>(p: string) => api<T>("DELETE", p);

export function qs(params: Record<string, string | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) u.set(k, v);
  const s = u.toString();
  return s ? `?${s}` : "";
}

export function uploadFile<T = unknown>(path: string, file: Blob, filename: string, onProgress?: (pct: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1${path}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new ApiError(0, "network", "network"));
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
      const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
      reject(new ApiError(xhr.status, err?.code ?? "generic", err?.message ?? "error"));
    };
    const fd = new FormData();
    fd.append("file", file, filename);
    xhr.send(fd);
  });
}

export function isRetryable(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 0 || e.status >= 500 || e.status === 429);
}
