"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorText, MoneyField, NativeSelect, TextField, apiAmount } from "@/components/app/bits";
import { get, post } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { newKey, todayIso } from "@/lib/format";
import { t } from "@/i18n";

export default function Page() {
  const router = useRouter();
  const users = useLoad(() => get<{ id: string; name: string; role: string }[]>("/users"), []);
  const cats = useLoad(() => get<{ id: string; name: string }[]>("/categories"), []);
  const act = useAction();
  const [ref] = useState(newKey());
  const [f, setF] = useState({ user_id: "", supplier_name: "", total: "", expense_date: todayIso(), category_id: "", payment_method: "cash", notes: "" });
  const emps = (users.data ?? []).filter((u) => u.role === "employee");
  const uid = f.user_id || emps[0]?.id || "";
  const cid = f.category_id || cats.data?.[0]?.id || "";
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("expense.create")}</h1>
      <Card><CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <NativeSelect label={t("expense.forEmployee")} value={uid} onChange={(v) => setF({ ...f, user_id: v })} options={emps.map((u) => ({ value: u.id, label: u.name }))} />
        <TextField label={t("common.supplier")} value={f.supplier_name} onChange={(v) => setF({ ...f, supplier_name: v })} />
        <MoneyField label={t("common.total")} value={f.total} onChange={(v) => setF({ ...f, total: v })} />
        <TextField label={t("common.date")} type="date" value={f.expense_date} onChange={(v) => setF({ ...f, expense_date: v })} />
        <NativeSelect label={t("common.category")} value={cid} onChange={(v) => setF({ ...f, category_id: v })} options={(cats.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
        <NativeSelect label={t("add.payment")} value={f.payment_method} onChange={(v) => setF({ ...f, payment_method: v })} options={["cash", "card", "bank_transfer", "personal_funds"].map((m) => ({ value: m, label: t(`pay.${m}`) }))} />
        <div className="sm:col-span-2"><TextField label={t("common.notes")} value={f.notes} onChange={(v) => setF({ ...f, notes: v })} /></div>
        <div className="grid gap-2 sm:col-span-2">
          <ErrorText>{act.error}</ErrorText>
          <Button disabled={act.busy || !f.total || !uid} data-testid="create-expense" onClick={() => void act.run(async () => {
            const e = await post<{ id: string }>("/expenses", { client_ref: ref, ...f, user_id: uid, category_id: cid, total: apiAmount(f.total) });
            await post(`/expenses/${e.id}/submit`, {});
            router.push(`/admin/shpenzimet/${e.id}`);
          })}>{t("expense.create")}</Button>
        </div>
      </CardContent></Card>
    </div>
  );
}
