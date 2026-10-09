"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Empty, ErrorText, Loading, Money, NativeSelect, TextField } from "@/components/app/bits";
import { get, post, qs } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";
import { formatDate } from "@/lib/format";
import { t } from "@/i18n";

interface Txn { id: string; type: string; status: string; date: string; description: string; expense_id: string | null; reverses_id: string | null; reason: string | null; lines: { account: string; debit: string; credit: string }[] }
const TYPES = ["funding", "atm_withdrawal", "bank_fee", "cash_return", "employee_transfer", "cash_expense", "card_expense", "transfer_expense", "personal_funds_expense", "refund", "reimbursement", "opening_balance", "cash_difference"];

function Inner() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const [type, setType] = useState(sp.get("type") ?? "");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const accountId = sp.get("account_id") ?? "";
  const expenseId = sp.get("expense_id") ?? "";
  const list = useLoad(() => get<Txn[]>(`/ledger/transactions${qs({ type, date_from: from, date_to: to, account_id: accountId, expense_id: expenseId })}`), [type, from, to, accountId, expenseId]);
  const act = useAction();
  const [reasonFor, setReasonFor] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{t("ledger.title")}</h1>
        <div className="flex gap-3 text-sm">
          <a className="underline" href={`/api/v1/exports/transactions${qs({ type, date_from: from, date_to: to, format: "csv" })}`}>{t("common.csv")}</a>
          <a className="underline" href={`/api/v1/exports/transactions${qs({ type, date_from: from, date_to: to, format: "xlsx" })}`}>{t("common.excel")}</a>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <NativeSelect label={t("ledger.type")} value={type} onChange={setType} empty={t("common.all")} options={TYPES.map((x) => ({ value: x, label: t(`txn.${x}`) }))} />
        <TextField label={t("common.from")} type="date" value={from} onChange={setFrom} />
        <TextField label={t("common.to")} type="date" value={to} onChange={setTo} />
      </div>
      {(accountId || expenseId) && <p className="text-xs text-muted-foreground">Filtër aktiv nga lidhja burimore.</p>}
      <ErrorText>{list.error?.friendly}{act.error}</ErrorText>
      {list.loading && !list.data ? <Loading /> : list.data?.length === 0 ? <Empty /> : (
        <ul className="grid gap-2" data-testid="txn-list">
          {list.data?.map((x) => (
            <li key={x.id} className="rounded-lg border p-3" data-testid="txn-row" data-type={x.type}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-medium">{t(`txn.${x.type}`)}{x.reverses_id ? " (anulim)" : ""}{x.status === "reversed" ? ` · ${t("ledger.reversed")}` : ""}</span>
                <span className="text-muted-foreground">{formatDate(x.date)}</span>
              </div>
              <div className="mt-1 grid gap-0.5 text-xs">
                {x.lines.map((l, i) => <div key={i} className="flex justify-between"><span>{l.account}</span><span className="tabular-nums">{l.debit !== "0.00" ? <>D <Money v={l.debit} /></> : <>K <Money v={l.credit} /></>}</span></div>)}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs">
                {x.expense_id && <a className="underline" href={`/admin/shpenzimet/${x.expense_id}`}>{t("common.openSource")}</a>}
                {canWrite(user?.role) && x.status === "posted" && !x.reverses_id && (reasonFor === x.id ? (
                  <span className="flex items-end gap-2"><TextField label={t("ledger.reverseReason")} value={reason} onChange={setReason} />
                    <Button size="sm" variant="destructive" disabled={!reason || act.busy} onClick={() => void act.run(async () => { await post(`/ledger/transactions/${x.id}/reverse`, { reason }); setReasonFor(null); setReason(""); await list.reload(true); })}>{t("ledger.reverse")}</Button></span>
                ) : <Button size="sm" variant="outline" onClick={() => setReasonFor(x.id)}>{t("ledger.reverse")}</Button>)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Page() {
  return <Suspense><Inner /></Suspense>;
}
