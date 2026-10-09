import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import * as q from "@/lib/offline-queue";

const blob = (s: string) => new Blob([s]);

function fakeApi(opts: { failUploadsAfter?: number; retryable?: boolean } = {}) {
  const calls = { create: 0, upload: [] as string[] };
  let uploads = 0;
  const api: q.SyncApi = {
    async createExpense(c) {
      calls.create += 1;
      return { id: `exp-${c.id}` };
    },
    async uploadPage(_id, f) {
      uploads += 1;
      if (opts.failUploadsAfter !== undefined && uploads > opts.failUploadsAfter) throw new Error("boom");
      calls.upload.push(f.name);
    },
    isRetryable: () => opts.retryable ?? true,
  };
  return { api, calls };
}

beforeEach(async () => {
  for (const c of await q.list()) await q.remove(c.id);
});

describe("offline queue", () => {
  it("replays queued captures once and clears them", async () => {
    await q.enqueue({ id: "c1", fields: { payment_method: "cash" }, files: [{ name: "a.jpg", blob: blob("a") }, { name: "b.jpg", blob: blob("b") }] });
    const { api, calls } = fakeApi();
    const res = await q.syncAll(api);
    expect(res).toEqual({ synced: 1, failed: 0 });
    expect(calls.create).toBe(1);
    expect(calls.upload).toEqual(["a.jpg", "b.jpg"]);
    expect(await q.list()).toHaveLength(0);
  });

  it("resumes mid-capture without re-creating the expense or re-uploading finished pages", async () => {
    await q.enqueue({ id: "c2", fields: { payment_method: "cash" }, files: [{ name: "p1", blob: blob("1") }, { name: "p2", blob: blob("2") }] });
    const first = fakeApi({ failUploadsAfter: 1, retryable: true });
    const r1 = await q.syncAll(first.api);
    expect(r1.failed).toBe(1);
    const [left] = await q.list();
    expect(left.uploaded).toBe(1);
    expect(left.status).toBe("pending");
    const second = fakeApi();
    await q.syncAll(second.api);
    expect(second.calls.create).toBe(0);
    expect(second.calls.upload).toEqual(["p2"]);
    expect(await q.list()).toHaveLength(0);
  });

  it("marks non-retryable failures as error and keeps the data", async () => {
    await q.enqueue({ id: "c3", fields: { payment_method: "cash" }, files: [{ name: "x", blob: blob("x") }] });
    const { api } = fakeApi({ failUploadsAfter: 0, retryable: false });
    await q.syncAll(api);
    const [c] = await q.list();
    expect(c.status).toBe("error");
    expect(c.files).toHaveLength(1);
  });

  it("does not run two syncs concurrently (duplicate protection)", async () => {
    await q.enqueue({ id: "c4", fields: { payment_method: "cash" }, files: [{ name: "x", blob: blob("x") }] });
    const { api, calls } = fakeApi();
    const [a, b] = await Promise.all([q.syncAll(api), q.syncAll(api)]);
    expect(a.synced + b.synced).toBe(1);
    expect(calls.create).toBe(1);
  });
});
