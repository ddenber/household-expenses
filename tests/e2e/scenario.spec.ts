import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "http://localhost:8431";
const FIX = path.join(__dirname, ".fixtures");
const SUFFIX = Date.now().toString(36);
const ADMIN = { email: `admin-${SUFFIX}@e2e.test`, password: "E2e-admin-password-1" };
const A = { name: `Ana ${SUFFIX}`, email: `ana-${SUFFIX}@e2e.test`, password: "E2e-employee-pw-1" };
const B = { name: `Bela ${SUFFIX}`, email: `bela-${SUFFIX}@e2e.test`, password: "E2e-employee-pw-2" };
const SUPER = { email: process.env.E2E_SUPER_EMAIL ?? "admin@hem.local", password: process.env.E2E_SUPER_PASSWORD ?? "Admin-local-pass-1" };

test.describe.configure({ mode: "serial" });

let browser: Browser;
let admin: Page, ana: Page, bela: Page;
let ctxs: BrowserContext[] = [];
let anaExpenseId = "";

async function newPage(viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport, baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3417" });
  ctxs.push(ctx);
  return ctx.newPage();
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Fjalëkalimi").fill(password);
  await page.getByTestId("login-submit").click();
}

async function csrfFetch(page: Page, method: string, url: string, body?: unknown) {
  return page.evaluate(async ({ method, url, body }) => {
    const me = await (await fetch("/api/v1/auth/me")).json();
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, body: await r.text() };
  }, { method, url, body });
}

async function adminOp(page: Page, op: string, fields: Record<string, string>) {
  await page.goto("/admin/llogarite");
  await page.getByLabel("Veprime", { exact: true }).selectOption({ label: op });
  for (const [label, value] of Object.entries(fields)) {
    const el = page.getByLabel(label, { exact: true });
    if ((await el.evaluate((n) => n.tagName)) === "SELECT") await el.selectOption({ label: value });
    else await el.fill(value);
  }
  await page.getByTestId("op-submit").click();
  await expect(page.getByTestId("op-done")).toBeVisible();
}

async function balanceOf(page: Page, name: string) {
  await page.goto("/admin/llogarite");
  const row = page.locator(`[data-testid="balance-row"][data-name^="${name}"]`);
  await expect(row).toBeVisible();
  return (await row.innerText()).replace(/\s+/g, " ");
}

test.beforeAll(async ({ browser: b, request }) => {
  browser = b;
  execFileSync(path.join(__dirname, "../../apps/api/.venv/bin/python"), [path.join(__dirname, "make_receipts.py"), FIX]);
  // Fresh isolated household for this run, created through the real API by the super admin.
  const loginRes = await request.post(`${API}/api/v1/auth/login`, { data: SUPER });
  expect(loginRes.ok()).toBeTruthy();
  const { csrf_token } = await loginRes.json();
  const res = await request.post(`${API}/api/v1/households`, {
    headers: { "X-CSRF-Token": csrf_token },
    data: { name: `E2E ${SUFFIX}`, admin_email: ADMIN.email, admin_name: "Admin E2E", admin_password: ADMIN.password },
  });
  expect(res.status()).toBe(201);
  admin = await newPage();
  ana = await newPage({ width: 390, height: 844 });
  bela = await newPage({ width: 390, height: 844 });
});

test.afterAll(async () => {
  for (const c of ctxs) await c.close();
});

test("1. admin creates two employees, a bank account and opening balances", async () => {
  await login(admin, ADMIN.email, ADMIN.password);
  await expect(admin.getByTestId("whoami")).toContainText("Admin E2E");
  await admin.goto("/admin/perdoruesit");
  for (const u of [A, B]) {
    await admin.getByLabel("Emri", { exact: true }).fill(u.name);
    await admin.getByLabel("Email").fill(u.email);
    await admin.getByLabel("Fjalëkalimi").fill(u.password);
    await admin.getByTestId("create-user").click();
    await expect(admin.getByTestId("user-row").filter({ hasText: u.email })).toBeVisible();
  }
  await admin.goto("/admin/llogarite");
  await admin.getByLabel("Emri i llogarisë").fill("Banka Kryesore E2E");
  await admin.getByRole("button", { name: "Shto llogari bankare" }).click();
  await expect(admin.locator('[data-testid="balance-row"][data-name="Banka Kryesore E2E"]')).toBeVisible();
  await adminOp(admin, "Gjendje fillestare", { "Objektivi": "Arka e punonjësit", "Punonjësi": A.name, "Shuma": "10" });
  await adminOp(admin, "Gjendje fillestare", { "Objektivi": "Arka e punonjësit", "Punonjësi": B.name, "Shuma": "5" });
});

test("2. admin funds EUR 2000; A withdraws 500, B withdraws 400 (not expenses)", async () => {
  await adminOp(admin, "Financim i llogarisë", { "Shuma": "2000" });
  await adminOp(admin, "Tërheqje ATM", { "Punonjësi": A.name, "Shuma": "500" });
  await adminOp(admin, "Tërheqje ATM", { "Punonjësi": B.name, "Shuma": "400" });
  expect(await balanceOf(admin, "Banka Kryesore")).toContain("1.100,00");
  expect(await balanceOf(admin, `Arka cash – ${A.name}`)).toContain("510,00");
  expect(await balanceOf(admin, `Arka cash – ${B.name}`)).toContain("405,00");
  await admin.goto("/admin");
  await expect(admin.getByTestId("kpi-month_expenses")).toContainText("0,00");
});

test("3. A photographs a EUR 85 grocery receipt; real OCR runs async; A confirms and submits", async () => {
  await login(ana, A.email, A.password);
  await expect(ana.getByTestId("cash-balance")).toContainText("510,00");
  await ana.getByTestId("add-receipt").click();
  await ana.getByTestId("file-input").setInputFiles(path.join(FIX, "receipt-grocery.png"));
  await expect(ana.getByTestId("page-thumb")).toHaveCount(1);
  await ana.getByTestId("submit-receipt").click();
  await ana.waitForURL(/\/shpenzimet\/[0-9a-f-]{36}/);
  anaExpenseId = ana.url().split("/").pop()!;
  await expect(ana.getByTestId("ocr-card")).toBeVisible({ timeout: 60_000 });
  await expect(ana.getByTestId("ocr-provider")).toContainText("Real (Tesseract lokal)");
  await expect(ana.getByLabel("Totali")).toHaveValue("85.00");
  await ana.getByLabel("Kategoria").selectOption({ label: "Ushqimore" });
  await ana.getByLabel("Furnitori").fill("Conad");
  if (await ana.getByTestId("confirm-low").isVisible()) await ana.getByTestId("confirm-low").click();
  await ana.getByTestId("submit-expense").click();
  await expect(ana.getByTestId("status-badge").first()).toHaveText("Dërguar");
});

test("4. admin approves and posts A's expense; wallet decreases only after posting", async () => {
  await admin.goto(`/admin/shpenzimet/${anaExpenseId}`);
  await admin.getByTestId("approve").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Miratuar");
  expect(await balanceOf(admin, `Arka cash – ${A.name}`)).toContain("510,00");
  await admin.goto(`/admin/shpenzimet/${anaExpenseId}`);
  await admin.getByTestId("post").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Postuar");
  expect(await balanceOf(admin, `Arka cash – ${A.name}`)).toContain("425,00");
});

test("5. B submits a EUR 120 card purchase; posting hits the bank, not B's wallet", async () => {
  await login(bela, B.email, B.password);
  await bela.getByTestId("add-receipt").click();
  await bela.getByTestId("file-input").setInputFiles(path.join(FIX, "receipt-card.png"));
  await bela.getByLabel("Mënyra e pagesës").selectOption({ label: "Kartë bankare" });
  await bela.getByTestId("submit-receipt").click();
  await bela.waitForURL(/\/shpenzimet\/[0-9a-f-]{36}/);
  const id = bela.url().split("/").pop()!;
  await expect(bela.getByTestId("ocr-card")).toBeVisible({ timeout: 60_000 });
  await bela.getByLabel("Furnitori").fill("Elektro Shop");
  await bela.getByLabel("Totali").fill("120.00");
  await bela.getByLabel("Kategoria").selectOption({ label: "Elektronikë" });
  if (await bela.getByTestId("confirm-low").isVisible()) await bela.getByTestId("confirm-low").click();
  await bela.getByTestId("submit-expense").click();
  await expect(bela.getByTestId("status-badge").first()).toHaveText("Dërguar");
  // an employee has no approve button for their own expense
  await expect(bela.getByTestId("approve")).toHaveCount(0);
  await admin.goto(`/admin/shpenzimet/${id}`);
  await admin.getByTestId("approve").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Miratuar");
  await admin.getByTestId("post").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Postuar");
  expect(await balanceOf(admin, "Banka Kryesore")).toContain("980,00");
  expect(await balanceOf(admin, `Arka cash – ${B.name}`)).toContain("405,00");
});

test("6. admin records a EUR 100 cash expense on behalf of A", async () => {
  await admin.goto("/admin/shpenzimet/nou");
  await admin.getByLabel("Për punonjësin").selectOption({ label: A.name });
  await admin.getByLabel("Furnitori").fill("Pastrim Shtepie");
  await admin.getByLabel("Totali").fill("100");
  await admin.getByLabel("Kategoria").selectOption({ label: "Shërbime" });
  await admin.getByTestId("create-expense").click();
  await admin.waitForURL(/\/admin\/shpenzimet\/[0-9a-f-]{36}/);
  await admin.getByTestId("approve").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Miratuar");
  await admin.getByTestId("post").click();
  await expect(admin.getByTestId("status-badge").first()).toHaveText("Postuar");
  expect(await balanceOf(admin, `Arka cash – ${A.name}`)).toContain("325,00");
});

test("7. employees declare counts; reconciliation shows expected cash and discrepancies", async () => {
  await ana.goto("/pajtimi");
  await expect(ana.getByTestId("rec-expected")).toContainText("325,00");
  await ana.getByLabel("Sa para ke fizikisht?").fill("320");
  await ana.getByTestId("declare").click();
  await expect(ana.getByTestId("rec-difference")).toContainText("-5,00");
  await bela.goto("/pajtimi");
  await bela.getByLabel("Sa para ke fizikisht?").fill("405");
  await bela.getByTestId("declare").click();
  await expect(bela.getByTestId("rec-difference")).toContainText("0,00");
  await admin.goto("/admin/pajtimi");
  const cardA = admin.locator(`[data-testid="rec-card"][data-user="${A.name}"]`);
  await expect(cardA.getByTestId("rec-expected")).toContainText("325,00");
  await expect(cardA.getByTestId("rec-cash-expenses")).toContainText("185,00");
  await expect(cardA.getByTestId("rec-difference")).toContainText("-5,00");
  const cardB = admin.locator(`[data-testid="rec-card"][data-user="${B.name}"]`);
  await expect(cardB.getByTestId("rec-cash-expenses")).toContainText("0,00");
  await expect(cardB.getByTestId("rec-difference")).toContainText("0,00");
});

test("8. export, traceable KPI links and analytics by supplier and category", async () => {
  await admin.goto("/admin/shpenzimet");
  const [dl] = await Promise.all([admin.waitForEvent("download"), admin.getByTestId("export-csv").click()]);
  const text = await (await import("node:fs/promises")).readFile((await dl.path())!, "utf8");
  expect(text).toContain("Conad");
  expect(text).toContain("Elektro Shop");
  const [dlx] = await Promise.all([admin.waitForEvent("download"), admin.getByTestId("export-xlsx").click()]);
  expect(dlx.suggestedFilename()).toMatch(/\.xlsx$/);

  await admin.goto("/admin");
  await admin.getByTestId("kpi-month_expenses").click();
  await expect(admin).toHaveURL(/status=posted/);
  await expect(admin.getByTestId("expense-row")).toHaveCount(3);

  await admin.goto("/admin/analitika");
  await expect(admin.locator('#x, [data-testid="by-supplier"] [data-name="Conad"]')).toContainText("85,00");
  await expect(admin.locator('[data-testid="by-supplier"] [data-name="Elektro Shop"]')).toContainText("120,00");
  await expect(admin.locator('[data-testid="by-category"] [data-name="Ushqimore"]')).toContainText("85,00");
  await expect(admin.locator('[data-testid="by-category"] [data-name="Elektronikë"]')).toContainText("120,00");
  await expect(admin.locator('[data-testid="by-category"] [data-name="Shërbime"]')).toContainText("100,00");

  await admin.goto("/admin/auditimi");
  await expect(admin.getByTestId("audit-action").filter({ hasText: "expense.post" }).first()).toBeVisible();
});

test("9. unauthorized cross-employee receipt access is denied", async () => {
  const docs = await csrfFetch(admin, "GET", `/api/v1/expenses/${anaExpenseId}`);
  const docId = JSON.parse(docs.body).documents[0].id as string;
  expect((await csrfFetch(ana, "GET", `/api/v1/documents/${docId}/url`)).status).toBe(200);
  expect((await csrfFetch(bela, "GET", `/api/v1/documents/${docId}/url`)).status).toBe(404);
  expect((await csrfFetch(bela, "GET", `/api/v1/expenses/${anaExpenseId}`)).status).toBe(404);
  await bela.goto(`/shpenzimet/${anaExpenseId}`);
  await expect(bela.getByTestId("expense-detail")).toHaveCount(0);
  await bela.goto("/admin");
  await expect(bela).not.toHaveURL(/\/admin$/);
});
