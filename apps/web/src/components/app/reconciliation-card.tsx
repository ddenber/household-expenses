"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorText, Money, MoneyField, TextField, apiAmount } from "@/components/app/bits";
import { post } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { t } from "@/i18n";

export interface Rec {
  user_id: string; user_name: string; year: number; month: number; status: "open" | "closed";
  opening: string; withdrawals: string; transfers_in: string; other_sources: string; refunds: string;
  cash_expenses: string; returns_to_bank: string; transfers_out: string; other_outflows: string;
  expected_closing: string; count_adjustment: string; ledger_closing: string; consistent: boolean;
  declared_count: string | null; difference: string | null;
  pending: { amount: string; count: number }; approved_not_posted: { amount: string; count: number };
  rejected: { amount: string; count: number }; missing_receipts: number; suspense_balance: string; note: string | null;
}

function Row({ label, v, sign, strong, id }: { label: string; v: string; sign?: string; strong?: boolean; id?: string }) {
  return (
    <div className={`flex justify-between py-1 text-sm ${strong ? "border-t font-semibold" : ""}`} data-testid={id}>
      <span>{sign ? `${sign} ` : ""}{label}</span><Money v={v} />
    </div>
  );
}

export function ReconciliationCard({ rec, admin, onChange }: { rec: Rec; admin: boolean; onChange: () => void }) {
  const act = useAction();
  const [count, setCount] = useState(rec.declared_count ?? "");
  const [postDiff, setPostDiff] = useState(true);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const closed = rec.status === "closed";
  const body = { user_id: rec.user_id, year: rec.year, month: rec.month };
  const pdf = `/api/v1/reconciliation/statement.pdf?year=${rec.year}&month=${rec.month}&user_id=${rec.user_id}`;

  return (
    <Card data-testid="rec-card" data-user={rec.user_name}>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-base">{rec.user_name}</CardTitle>
        <span className={`rounded-full px-2 py-0.5 text-xs ${closed ? "bg-zinc-800 text-white" : "bg-emerald-100 text-emerald-900"}`}>{closed ? t("rec.closed") : t("rec.open")}</span>
      </CardHeader>
      <CardContent className="grid gap-3">
        {!rec.consistent && <ErrorText>{t("rec.inconsistent")}</ErrorText>}
        <div>
          <Row label={t("rec.opening")} v={rec.opening} id="rec-opening" />
          <Row label={t("rec.withdrawals")} v={rec.withdrawals} sign="+" id="rec-withdrawals" />
          <Row label={t("rec.transfers_in")} v={rec.transfers_in} sign="+" />
          <Row label={t("rec.other_sources")} v={rec.other_sources} sign="+" />
          <Row label={t("rec.refunds")} v={rec.refunds} sign="+" />
          <Row label={t("rec.cash_expenses")} v={rec.cash_expenses} sign="−" id="rec-cash-expenses" />
          <Row label={t("rec.returns_to_bank")} v={rec.returns_to_bank} sign="−" />
          <Row label={t("rec.transfers_out")} v={rec.transfers_out} sign="−" />
          <Row label={t("rec.other_outflows")} v={rec.other_outflows} sign="−" />
          <Row label={t("rec.expected_closing")} v={rec.expected_closing} sign="=" strong id="rec-expected" />
          {rec.declared_count !== null && <Row label={t("rec.declared")} v={rec.declared_count} id="rec-declared" />}
          {rec.difference !== null && <Row label={t("rec.difference")} v={rec.difference} strong id="rec-difference" />}
          {rec.count_adjustment !== "0.00" && <Row label={t("rec.adjustment")} v={rec.count_adjustment} />}
        </div>
        <div className="rounded-md bg-muted p-3 text-sm">
          <p className="mb-1 text-xs text-muted-foreground">{t("rec.separate")}</p>
          <div className="flex justify-between"><span>{t("rec.pending")} ({rec.pending.count})</span><Money v={rec.pending.amount} /></div>
          <div className="flex justify-between"><span>{t("rec.approved_not_posted")} ({rec.approved_not_posted.count})</span><Money v={rec.approved_not_posted.amount} /></div>
          <div className="flex justify-between"><span>{t("rec.rejected")} ({rec.rejected.count})</span><Money v={rec.rejected.amount} /></div>
          <div className="flex justify-between"><span>{t("rec.missing_receipts")}</span><span>{rec.missing_receipts}</span></div>
          <div className="flex justify-between"><span>{t("rec.suspense")}</span><Money v={rec.suspense_balance} /></div>
        </div>
        <ErrorText>{act.error}</ErrorText>
        {!closed && (admin || true) && (
          <div className="flex flex-wrap items-end gap-2">
            <MoneyField label={t("rec.counted")} value={count} onChange={setCount} name="declared" />
            <Button disabled={act.busy || !count} data-testid="declare" onClick={() => void act.run(async () => { await post("/reconciliation/declare", { ...body, amount: apiAmount(count) }); onChange(); })}>{t("rec.declare")}</Button>
          </div>
        )}
        {admin && !closed && rec.declared_count !== null && (
          <div className="grid gap-2 rounded-md border p-3">
            {rec.difference !== "0.00" && <label className="flex items-center gap-2 text-sm"><Checkbox checked={postDiff} onCheckedChange={(v) => setPostDiff(Boolean(v))} /> {t("rec.postDiff")}</label>}
            <TextField label={t("rec.note")} value={note} onChange={setNote} />
            <Button disabled={act.busy} data-testid="close-period" onClick={() => void act.run(async () => { await post("/reconciliation/close", { ...body, post_difference: postDiff && rec.difference !== "0.00", note: note || null }); onChange(); })}>{t("rec.close")}</Button>
          </div>
        )}
        {admin && closed && (
          <div className="grid gap-2 rounded-md border p-3">
            <TextField label={t("rec.reopenReason")} value={reason} onChange={setReason} />
            <Button variant="outline" disabled={act.busy || !reason} data-testid="reopen-period" onClick={() => void act.run(async () => { await post("/reconciliation/reopen", { ...body, reason }); onChange(); })}>{t("rec.reopen")}</Button>
          </div>
        )}
        <a className="text-sm underline" href={pdf} data-testid="pdf-link">{t("rec.pdf")}</a>
      </CardContent>
    </Card>
  );
}
