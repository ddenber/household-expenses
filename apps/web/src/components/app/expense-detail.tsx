"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorText, Loading, Money, MoneyField, NativeSelect, StatusBadge, TextField, apiAmount } from "@/components/app/bits";
import { get, post, patch } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";
import { formatDate } from "@/lib/format";
import { t } from "@/i18n";

interface OcrField { value: string | null; confidence: number }
interface Detail {
  id: string; user_id: string; status: string; supplier_name: string | null; expense_date: string | null; total: string | null;
  category_id: string | null; payment_method: string; notes: string | null; rejection_reason: string | null;
  ocr_needs_confirmation: boolean; is_refund: boolean; refund_of_id: string | null; posted_txn_id: string | null; refunded_total: string | null;
  bank_account_id: string | null;
  documents: { id: string; page_no: number; mime: string; ocr_status: string }[];
  ocr: { document_id: string; provider: string; provider_real: boolean; status: string; error: string | null; extraction: Record<string, OcrField> | null }[];
  history: { from: string | null; to: string; at: string; note: string | null }[];
}

export function ExpenseDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const admin = canWrite(user?.role);
  const [poll, setPoll] = useState<number | undefined>(undefined);
  const d = useLoad(() => get<Detail>(`/expenses/${id}`), [id], poll);
  const cats = useLoad(() => get<{ id: string; name: string }[]>("/categories"), []);
  const banks = useLoad(() => (admin ? get<{ id: string; name: string; kind: string }[]>("/accounts") : Promise.resolve([])), [admin]);
  const act = useAction();
  const [form, setForm] = useState({ supplier_name: "", expense_date: "", total: "", category_id: "", payment_method: "cash", notes: "", bank_account_id: "" });
  const [confirmLow, setConfirmLow] = useState(false);
  const [reason, setReason] = useState("");
  const [refundAmt, setRefundAmt] = useState("");

  const e = d.data;
  useEffect(() => {
    if (!e) return;
    setForm({ supplier_name: e.supplier_name ?? "", expense_date: e.expense_date ?? "", total: e.total ?? "", category_id: e.category_id ?? "", payment_method: e.payment_method, notes: e.notes ?? "", bank_account_id: e.bank_account_id ?? "" });
    setPoll(e.status === "uploaded" || e.status === "processing" ? 2000 : undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e?.status, e?.supplier_name, e?.total, e?.expense_date, e?.category_id]);

  if (d.loading && !e) return <Loading />;
  if (!e) return <ErrorText>{d.error?.status === 404 ? t("common.empty") : d.error?.friendly}</ErrorText>;

  const own = e.user_id === user?.id;
  const editable = ["draft", "uploaded", "processing", "needs_review"].includes(e.status);
  const canEdit = editable && (own || admin) && user?.role !== "auditor";
  const lowFields = e.ocr.flatMap((o) => Object.entries(o.extraction ?? {}).filter(([k, v]) => typeof v === "object" && v && ["supplier", "date", "total"].includes(k) && v.value !== null && v.confidence < 0.8).map(([k]) => k));
  const call = (path: string, body?: unknown) => act.run(async () => { await post(`/expenses/${id}${path}`, body); await d.reload(true); });
  const bankOptions = (banks.data ?? []).filter((a) => a.kind === "bank").map((a) => ({ value: a.id, label: a.name }));

  async function save() {
    await act.run(async () => {
      await patch(`/expenses/${id}`, {
        supplier_name: form.supplier_name || null, expense_date: form.expense_date || null, total: form.total ? apiAmount(form.total) : null,
        category_id: form.category_id || null, payment_method: form.payment_method, notes: form.notes || null, bank_account_id: form.bank_account_id || null,
      });
      await d.reload(true);
    });
  }

  async function openDoc(docId: string) {
    const r = await act.run(() => get<{ url: string }>(`/documents/${docId}/url`));
    if (r) window.open(r.url, "_blank", "noopener");
  }

  return (
    <div className="grid gap-4" data-testid="expense-detail">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{e.is_refund ? t("expense.refundOf") : t("expense.detail")}</h1>
        <StatusBadge status={e.status} />
      </div>
      {e.rejection_reason && <ErrorText>{t("status.rejected")}: {e.rejection_reason}</ErrorText>}
      <ErrorText>{act.error}</ErrorText>

      {(e.status === "uploaded" || e.status === "processing") && <p className="text-sm text-muted-foreground" data-testid="ocr-pending">{t("expense.ocrPending")}</p>}

      <Card>
        <CardHeader><CardTitle className="text-base">{t("expense.detail")}</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <TextField label={t("common.supplier")} value={form.supplier_name} onChange={(v) => setForm({ ...form, supplier_name: v })} />
          <MoneyField label={t("common.total")} value={form.total} onChange={(v) => setForm({ ...form, total: v })} />
          <TextField label={t("common.date")} type="date" value={form.expense_date} onChange={(v) => setForm({ ...form, expense_date: v })} />
          <NativeSelect label={t("common.category")} value={form.category_id} onChange={(v) => setForm({ ...form, category_id: v })} empty="–" options={(cats.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
          <NativeSelect label={t("add.payment")} value={form.payment_method} onChange={(v) => setForm({ ...form, payment_method: v })} options={["cash", "card", "bank_transfer", "personal_funds"].map((m) => ({ value: m, label: t(`pay.${m}`) }))} />
          {["card", "bank_transfer"].includes(form.payment_method) && admin && <NativeSelect label={t("common.bank")} value={form.bank_account_id} onChange={(v) => setForm({ ...form, bank_account_id: v })} empty="–" options={bankOptions} />}
          <div className="sm:col-span-2"><TextField label={t("common.notes")} value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} /></div>
          {!canEdit && <p className="text-sm text-muted-foreground sm:col-span-2">{formatDate(e.expense_date)} · {e.supplier_name} · <Money v={e.total} /></p>}
          {canEdit && <Button variant="secondary" disabled={act.busy} onClick={() => void save()} data-testid="save-expense">{t("expense.saveChanges")}</Button>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">{t("expense.pages")}</CardTitle></CardHeader>
        <CardContent className="grid gap-2">
          {e.documents.length === 0 && <p className="text-sm text-muted-foreground">{t("expense.noDocs")}</p>}
          {e.documents.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between rounded-md border p-2 text-sm">
              <span>{t("add.pages")} {doc.page_no} · {doc.mime} · OCR: {doc.ocr_status}</span>
              <Button size="sm" variant="outline" data-testid="view-doc" onClick={() => void openDoc(doc.id)}>{t("expense.viewDoc")}</Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {e.ocr.length > 0 && (
        <Card data-testid="ocr-card">
          <CardHeader><CardTitle className="text-base">{t("expense.ocr")}</CardTitle></CardHeader>
          <CardContent className="grid gap-2 text-sm">
            {e.ocr.map((o, i) => (
              <div key={i} className="rounded-md border p-2">
                <div data-testid="ocr-provider" className={o.provider_real ? "" : "font-medium text-amber-700 dark:text-amber-300"}>{t("expense.ocrProvider")}: {o.provider} — {o.provider_real ? t("expense.ocrReal") : t("expense.ocrSimulated")}</div>
                {o.status === "failed" && <p className="text-red-600">{t("expense.ocrFailed")}</p>}
                {o.extraction && (["supplier", "date", "total"] as const).map((k) => (
                  <div key={k} className="flex justify-between"><span>{t("expense.ocrSuggested")}: {k}</span><span>{o.extraction?.[k]?.value ?? "–"} ({Math.round((o.extraction?.[k]?.confidence ?? 0) * 100)}%)</span></div>
                ))}
              </div>
            ))}
            {canEdit && e.ocr.some((o) => o.status === "failed") && <Button size="sm" variant="outline" onClick={() => void call("/ocr/retry")}>{t("expense.ocrRetry")}</Button>}
          </CardContent>
        </Card>
      )}

      {canEdit && e.ocr_needs_confirmation && (
        <div className="rounded-md border border-amber-400 bg-amber-50 p-3 text-sm dark:bg-amber-950" data-testid="low-confidence">
          <p>{t("expense.lowConfidence")} {lowFields.length > 0 && `(${lowFields.join(", ")})`}</p>
          <label className="mt-2 flex items-center gap-2"><Checkbox checked={confirmLow} onCheckedChange={(v) => setConfirmLow(Boolean(v))} data-testid="confirm-low" /> {t("expense.confirmLow")}</label>
        </div>
      )}

      <div className="flex flex-wrap gap-2" data-testid="actions">
        {canEdit && <Button disabled={act.busy} data-testid="submit-expense" onClick={() => void act.run(async () => { await patch(`/expenses/${id}`, { supplier_name: form.supplier_name || null, expense_date: form.expense_date || null, total: form.total ? apiAmount(form.total) : null, category_id: form.category_id || null, payment_method: form.payment_method, notes: form.notes || null, bank_account_id: form.bank_account_id || null }); await post(`/expenses/${id}/submit`, { confirm_low_confidence: confirmLow }); await d.reload(true); })}>{t("expense.submit")}</Button>}
        {e.status === "rejected" && (own || admin) && <Button variant="outline" onClick={() => void call("/reopen")}>{t("expense.reopen")}</Button>}
        {admin && e.status === "submitted" && !own && <Button disabled={act.busy} data-testid="approve" onClick={() => void call("/approve")}>{t("expense.approve")}</Button>}
        {admin && e.status === "submitted" && own && <span className="text-sm text-muted-foreground">{t("expense.selfApprove")}</span>}
        {admin && e.status === "approved" && !own && <Button disabled={act.busy} data-testid="post" onClick={() => void call("/post")}>{t("expense.post")}</Button>}
      </div>

      {admin && ["submitted", "approved", "posted"].includes(e.status) && !own && (
        <Card><CardContent className="grid gap-3 p-4">
          {(e.status === "submitted" || e.status === "approved") && <>
            <TextField label={t("expense.rejectReason")} value={reason} onChange={setReason} />
            <div className="flex flex-wrap gap-2">
              <Button variant="destructive" disabled={act.busy || !reason} data-testid="reject" onClick={() => void call("/reject", { reason })}>{t("expense.reject")}</Button>
              {e.status === "submitted" && <Button variant="outline" disabled={act.busy || !reason} onClick={() => void call("/return", { reason })}>{t("expense.returnForFix")}</Button>}
            </div>
          </>}
          {e.status === "posted" && <>
            {e.posted_txn_id && <Link className="text-sm underline" href={`/admin/librat?expense_id=${e.id}`}>{t("expense.linkedTxn")}</Link>}
            {!e.is_refund && <div className="flex flex-wrap items-end gap-2"><MoneyField label={t("expense.refundAmount")} value={refundAmt} onChange={setRefundAmt} /><Button variant="outline" disabled={act.busy || !refundAmt} data-testid="create-refund" onClick={() => void act.run(async () => { const r = await post<{ id: string }>(`/expenses/${id}/refund`, { amount: apiAmount(refundAmt) }); router.push(`/admin/shpenzimet/${r.id}`); })}>{t("expense.refund")}</Button></div>}
            <TextField label={t("expense.reverseReason")} value={reason} onChange={setReason} />
            <Button variant="destructive" disabled={act.busy || !reason} data-testid="reverse" onClick={() => void call("/reverse", { reason })}>{t("expense.reverse")}</Button>
          </>}
        </CardContent></Card>
      )}

      {e.refund_of_id && <Link className="text-sm underline" href={`${admin ? "/admin" : ""}/shpenzimet/${e.refund_of_id}`}>{t("expense.refundOf")}</Link>}
      {e.refunded_total && e.refunded_total !== "0.00" && <p className="text-sm">{t("expense.refund")}: <Money v={e.refunded_total} /></p>}

      <Card><CardHeader><CardTitle className="text-base">{t("expense.history")}</CardTitle></CardHeader>
        <CardContent className="grid gap-1 text-xs text-muted-foreground">
          {e.history.map((h, i) => <div key={i}>{formatDate(h.at)} · {h.from ? t(`status.${h.from}`) : "∅"} → {t(`status.${h.to}`)}{h.note ? ` · ${h.note}` : ""}</div>)}
        </CardContent></Card>
    </div>
  );
}
