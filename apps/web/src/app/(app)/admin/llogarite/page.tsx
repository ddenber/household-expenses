"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, Loading, Money, MoneyField, NativeSelect, TextField, apiAmount } from "@/components/app/bits";
import { get, post } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";
import { newKey, todayIso } from "@/lib/format";
import { t } from "@/i18n";

interface Account { id: string; name: string; kind: string; balance: string; owner_user_id: string | null }
interface U { id: string; name: string; role: string }
const OPS = ["funding", "atm", "cashReturn", "transfer", "reimbursement", "opening"] as const;
type Op = (typeof OPS)[number];

export default function Page() {
  const { user } = useAuth();
  const write = canWrite(user?.role);
  const accs = useLoad(() => get<Account[]>("/accounts"), []);
  const users = useLoad(() => get<U[]>("/users"), []);
  const act = useAction();
  const [op, setOp] = useState<Op>("funding");
  const [amount, setAmount] = useState("");
  const [fee, setFee] = useState("");
  const [date, setDate] = useState(todayIso());
  const [bank, setBank] = useState("");
  const [emp, setEmp] = useState("");
  const [emp2, setEmp2] = useState("");
  const [target, setTarget] = useState<"bank" | "wallet">("bank");
  const [bankName, setBankName] = useState("");
  const [key, setKey] = useState(newKey());
  const [ok, setOk] = useState(false);

  const banks = (accs.data ?? []).filter((a) => a.kind === "bank");
  const emps = (users.data ?? []).filter((u) => u.role === "employee");
  const bankId = bank || banks[0]?.id || "";
  const empId = emp || emps[0]?.id || "";
  const emp2Id = emp2 || emps[1]?.id || emps[0]?.id || "";

  async function submit() {
    const base = { idempotency_key: key, date, amount: apiAmount(amount) };
    const bodies: Record<Op, [string, object]> = {
      funding: ["/ledger/funding", { ...base, bank_id: bankId }],
      atm: ["/ledger/atm-withdrawal", { ...base, bank_id: bankId, user_id: empId, fee: fee ? apiAmount(fee) : null }],
      cashReturn: ["/ledger/cash-return", { ...base, bank_id: bankId, user_id: empId }],
      transfer: ["/ledger/employee-transfer", { ...base, from_user_id: empId, to_user_id: emp2Id }],
      reimbursement: ["/ledger/reimbursement", { ...base, bank_id: bankId, user_id: empId }],
      opening: ["/ledger/opening-balance", target === "bank" ? { ...base, bank_id: bankId } : { ...base, user_id: empId }],
    };
    const [path, body] = bodies[op];
    const r = await act.run(() => post(path, body));
    if (r) {
      setOk(true);
      setAmount("");
      setFee("");
      setKey(newKey());
      await accs.reload(true);
    }
  }

  const rows = (accs.data ?? []).filter((a) => a.kind !== "expense_category");
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("nav.accounts")}</h1>
      <ErrorText>{accs.error?.friendly}</ErrorText>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("ops.balances")}</CardTitle></CardHeader>
        <CardContent className="grid gap-1" data-testid="balances">
          {accs.loading && !accs.data ? <Loading /> : rows.map((a) => (
            <div key={a.id} className="flex justify-between border-b py-1 text-sm last:border-0" data-testid="balance-row" data-name={a.name}>
              <span>{a.name}</span><Money v={a.balance} className="font-medium" />
            </div>
          ))}
        </CardContent>
      </Card>

      {write && (
        <Card>
          <CardHeader><CardTitle className="text-base">{t("ops.title")}</CardTitle></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <NativeSelect label={t("common.actions")} name="op" value={op} onChange={(v) => { setOp(v as Op); setOk(false); setKey(newKey()); }} options={OPS.map((o) => ({ value: o, label: t(`ops.${o}`) }))} />
            <p className="self-end text-xs text-muted-foreground">{op === "atm" ? `${t("ops.notExpense")} ${t("ops.feeNote")}` : ["funding", "cashReturn", "transfer", "opening"].includes(op) ? t("ops.notExpense") : ""}</p>
            {op === "opening" && <NativeSelect label={t("ops.target")} value={target} onChange={(v) => setTarget(v as "bank" | "wallet")} options={[{ value: "bank", label: t("ops.targetBank") }, { value: "wallet", label: t("ops.targetWallet") }]} />}
            {(op !== "transfer" && !(op === "opening" && target === "wallet")) && <NativeSelect label={t("common.bank")} value={bankId} onChange={setBank} options={banks.map((b) => ({ value: b.id, label: b.name }))} />}
            {(["atm", "cashReturn", "reimbursement"].includes(op) || (op === "opening" && target === "wallet")) && <NativeSelect label={t("common.employee")} value={empId} onChange={setEmp} options={emps.map((u) => ({ value: u.id, label: u.name }))} />}
            {op === "transfer" && <>
              <NativeSelect label={t("ops.from")} value={empId} onChange={setEmp} options={emps.map((u) => ({ value: u.id, label: u.name }))} />
              <NativeSelect label={t("ops.to")} value={emp2Id} onChange={setEmp2} options={emps.map((u) => ({ value: u.id, label: u.name }))} />
            </>}
            <MoneyField label={t("common.amount")} value={amount} onChange={setAmount} name="amount" />
            {op === "atm" && <MoneyField label={t("ops.fee")} value={fee} onChange={setFee} name="fee" />}
            <TextField label={t("common.date")} type="date" value={date} onChange={setDate} />
            <div className="sm:col-span-2 grid gap-2">
              <ErrorText>{act.error}</ErrorText>
              {ok && <p role="status" data-testid="op-done" className="rounded-md bg-emerald-100 p-2 text-sm text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">{t("ops.done")}</p>}
              <Button disabled={act.busy || !amount || !bankId && op !== "transfer"} data-testid="op-submit" onClick={() => void submit()}>{t("ops.submit")}</Button>
            </div>
          </CardContent>
        </Card>
      )}
      {write && (
        <Card><CardContent className="flex flex-wrap items-end gap-2 p-4">
          <TextField label={t("ops.bankName")} value={bankName} onChange={setBankName} />
          <Button variant="outline" disabled={!bankName || act.busy} onClick={() => void act.run(async () => { await post("/bank-accounts", { name: bankName }); setBankName(""); await accs.reload(true); })}>{t("ops.addBank")}</Button>
        </CardContent></Card>
      )}
    </div>
  );
}
