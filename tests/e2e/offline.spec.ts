import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8431";
const FIX = path.join(__dirname, ".fixtures");
const S = Date.now().toString(36);
const ADMIN = { email: `off-admin-${S}@e2e.test`, password: "E2e-admin-password-1" };
const EMP = { name: `Offline ${S}`, email: `off-emp-${S}@e2e.test`, password: "E2e-employee-pw-1" };
const SUPER = { email: process.env.E2E_SUPER_EMAIL ?? "admin@hem.local", password: process.env.E2E_SUPER_PASSWORD ?? "Admin-local-pass-1" };

test("offline capture is queued in IndexedDB and synced exactly once when back online; double tap creates one expense", async ({ browser, request }) => {
  execFileSync(path.join(__dirname, "../../apps/api/.venv/bin/python"), [path.join(__dirname, "make_receipts.py"), FIX]);
  const sup = await (await request.post(`${API}/api/v1/auth/login`, { data: SUPER })).json();
  expect((await request.post(`${API}/api/v1/households`, { headers: { "X-CSRF-Token": sup.csrf_token }, data: { name: `OFF ${S}`, admin_email: ADMIN.email, admin_name: "Admin Off", admin_password: ADMIN.password } })).status()).toBe(201);
  const ctxA = await browser.newContext();
  const aa = await ctxA.request.post(`${API}/api/v1/auth/login`, { data: ADMIN });
  const { csrf_token } = await aa.json();
  expect((await ctxA.request.post(`${API}/api/v1/users`, { headers: { "X-CSRF-Token": csrf_token }, data: { ...EMP, role: "employee" } })).status()).toBe(201);

  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3417" });
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMP.email);
  await page.getByLabel("Fjalëkalimi").fill(EMP.password);
  await page.getByTestId("login-submit").click();
  await page.getByTestId("add-receipt").click();
  await page.getByTestId("file-input").setInputFiles(path.join(FIX, "receipt-grocery.png"));
  await expect(page.getByTestId("page-thumb")).toHaveCount(1);

  await ctx.setOffline(true);
  await page.getByTestId("submit-receipt").dblclick(); // double tap
  await expect(page.getByTestId("offline-saved")).toBeVisible();
  await expect(page.getByTestId("sync-status")).toContainText("Pa internet");

  await ctx.setOffline(false);
  await expect(page.getByTestId("sync-status")).not.toContainText("në pritje", { timeout: 30_000 });
  await page.goto("/shpenzimet");
  await expect(page.getByTestId("expense-row")).toHaveCount(1, { timeout: 30_000 });
  await page.getByTestId("expense-row").click();
  await expect(page.getByTestId("view-doc")).toHaveCount(1);
});
