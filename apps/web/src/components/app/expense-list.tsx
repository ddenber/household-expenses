"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, ErrorText, Loading, Money, NativeSelect, StatusBadge, TextField } from "@/components/app/bits";
import { get, qs } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { useSync } from "@/lib/sync";
import { formatDate } from "@/lib/format";
import { t } from "@/i18n";

export interface ExpenseRow {
  id: string; user_id: string; supplier_name: string | null; total: string | null; status: string; expense_date: string | null;
  payment_method: string; category_id: string | null; is_refund: boolean; document_count: number;
}
const STATUSES = ["draft", "uploaded", "processing", "needs_review", "submitted", "approved", "rejected", "posted", "reversed"];

export function ExpenseList({ admin }: { admin: boolean }) {
  const sp = useSearchParams();
  const [status, setStatus] = useState(sp.get("status") ?? "");
  const [userId, setUserId] = useState(sp.get("user_id") ?? "");
  const [category, setCategory] = useState(sp.get("category_id") ?? "");
  const [from, setFrom] = useState(sp.get("date_from") ?? "");
  const [to, setTo] = useState(sp.get("date_to") ?? "");
  const [q, setQ] = useState("");
  const { pending } = useSync();
  const filters = { status, user_id: userId, category_id: category, date_from: from, date_to: to, q };
  const list = useLoad(() => get<{ total: number; items: ExpenseRow[] }>(`/expenses${qs({ ...filters, limit: "200" })}`), [status, userId, category, from, to, q]);
  const users = useLoad(() => (admin ? get<{ id: string; name: string; role: string }[]>("/users") : Promise.resolve([])), [admin]);
  const cats = useLoad(() => get<{ id: string; name: string }[]>("/categories"), []);
  const catName = (id: string | null) => cats.data?.find((c) => c.id === id)?.name ?? "–";
  const userName = (id: string) => users.data?.find((u) => u.id === id)?.name ?? "";
  const base = admin ? "/admin/shpenzimet" : "/shpenzimet";
  const exportQs = qs({ status, user_id: userId, date_from: from, date_to: to });

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{admin ? t("expense.queue") : t("expense.mine")}</h1>
        {admin && (
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/admin/shpenzimet/nou" data-testid="new-expense" className="text-sm font-medium underline">{t("expense.create")}</Link>
            <a className="text-sm underline" data-testid="export-csv" href={`/api/v1/exports/expenses${exportQs}${exportQs ? "&" : "?"}format=csv`}>{t("common.export")} {t("common.csv")}</a>
            <a className="text-sm underline" data-testid="export-xlsx" href={`/api/v1/exports/expenses${exportQs}${exportQs ? "&" : "?"}format=xlsx`}>{t("common.export")} {t("common.excel")}</a>
          </div>
        )}
      </div>
      {!admin && pending.length > 0 && (
        <Card><CardContent className="p-3 text-sm">
          <div className="mb-1 font-medium">{t("home.offlineQueue")}</div>
          {pending.map((p) => <div key={p.id} className="flex justify-between text-muted-foreground"><span>{p.files.length} {t("add.pages").toLowerCase()}</span><span>{p.status}</span></div>)}
        </CardContent></Card>
      )}
      <Card><CardContent className="grid gap-3 p-3 sm:grid-cols-3 lg:grid-cols-6">
        <NativeSelect label={t("common.status")} value={status} onChange={setStatus} empty={t("common.all")} options={STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
        {admin && <NativeSelect label={t("common.employee")} value={userId} onChange={setUserId} empty={t("common.all")} options={(users.data ?? []).filter((u) => u.role === "employee").map((u) => ({ value: u.id, label: u.name }))} />}
        <NativeSelect label={t("common.category")} value={category} onChange={setCategory} empty={t("common.all")} options={(cats.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
        <TextField label={t("common.from")} type="date" value={from} onChange={setFrom} />
        <TextField label={t("common.to")} type="date" value={to} onChange={setTo} />
        <TextField label={t("common.search")} value={q} onChange={setQ} />
      </CardContent></Card>
      <ErrorText>{list.error?.friendly}</ErrorText>
      {list.loading && !list.data ? <Loading /> : list.data && list.data.items.length === 0 ? <Empty /> : (
        <ul className="grid gap-2" data-testid="expense-list">
          {list.data?.items.map((e) => (
            <li key={e.id}>
              <Link href={`${base}/${e.id}`} data-testid="expense-row" className="flex items-center justify-between gap-3 rounded-lg border p-3 hover:bg-muted">
                <div className="min-w-0">
                  <div className="truncate font-medium">{e.is_refund ? `↩ ${t("expense.refundOf")} · ` : ""}{e.supplier_name ?? "–"}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {formatDate(e.expense_date)} · {catName(e.category_id)} · {t(`pay.${e.payment_method}`)}{admin && userName(e.user_id) ? ` · ${userName(e.user_id)}` : ""}{e.document_count === 0 ? ` · ${t("expense.noDocs")}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1"><Money v={e.total} className="font-medium" /><StatusBadge status={e.status} /></div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {list.data && <p className="text-xs text-muted-foreground">{list.data.total}</p>}
      <Button className="hidden" onClick={() => void list.reload()}>{t("common.retry")}</Button>
    </div>
  );
}
