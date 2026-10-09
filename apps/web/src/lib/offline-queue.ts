import { openDB, type IDBPDatabase } from "idb";

export interface CaptureFields {
  payment_method: string;
  supplier_name?: string;
  total?: string;
  expense_date?: string;
  category_id?: string;
  notes?: string;
}

export interface Capture {
  id: string; // doubles as the server-side client_ref -> create is idempotent
  createdAt: number;
  fields: CaptureFields;
  files: { name: string; blob: Blob }[];
  uploaded: number; // number of pages already confirmed by the server
  expenseId?: string;
  status: "pending" | "syncing" | "error";
  error?: string;
  attempts: number;
}

export interface SyncApi {
  createExpense(c: Capture): Promise<{ id: string }>;
  uploadPage(expenseId: string, file: { name: string; blob: Blob }, onProgress?: (p: number) => void): Promise<void>;
  isRetryable(e: unknown): boolean;
}

const DB = "hem-offline";
const STORE = "captures";
let dbp: Promise<IDBPDatabase> | null = null;

function db() {
  dbp ??= openDB(DB, 1, { upgrade: (d) => void d.createObjectStore(STORE, { keyPath: "id" }) });
  return dbp;
}

export async function resetDbForTests() {
  dbp = null;
}

export async function enqueue(c: Omit<Capture, "uploaded" | "status" | "attempts" | "createdAt">): Promise<Capture> {
  const full: Capture = { ...c, createdAt: Date.now(), uploaded: 0, status: "pending", attempts: 0 };
  await (await db()).put(STORE, full);
  return full;
}

export async function list(): Promise<Capture[]> {
  return ((await (await db()).getAll(STORE)) as Capture[]).sort((a, b) => a.createdAt - b.createdAt);
}

export async function remove(id: string) {
  await (await db()).delete(STORE, id);
}

async function put(c: Capture) {
  await (await db()).put(STORE, c);
}

let running = false;

/** Replays the queue in order. Safe to call repeatedly: a re-entrancy guard + server-side idempotency make duplicates impossible. */
export async function syncAll(api: SyncApi, onChange?: () => void, onProgress?: (id: string, pct: number) => void): Promise<{ synced: number; failed: number }> {
  if (running) return { synced: 0, failed: 0 };
  running = true;
  let synced = 0;
  let failed = 0;
  try {
    for (const c of await list()) {
      c.status = "syncing";
      c.error = undefined;
      await put(c);
      onChange?.();
      try {
        if (!c.expenseId) {
          c.expenseId = (await api.createExpense(c)).id;
          await put(c);
        }
        while (c.uploaded < c.files.length) {
          await api.uploadPage(c.expenseId, c.files[c.uploaded], (p) => onProgress?.(c.id, p));
          c.uploaded += 1;
          await put(c);
        }
        await remove(c.id);
        synced += 1;
      } catch (e) {
        failed += 1;
        c.attempts += 1;
        c.status = api.isRetryable(e) ? "pending" : "error";
        c.error = e instanceof Error ? e.message : "error";
        await put(c);
        if (api.isRetryable(e)) break; // still offline/server down: stop and retry later
      }
      onChange?.();
    }
  } finally {
    running = false;
    onChange?.();
  }
  return { synced, failed };
}
