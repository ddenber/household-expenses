"use client";
import { useState } from "react";
import { ErrorText, Loading } from "@/components/app/bits";
import { MonthPicker } from "@/components/app/month-picker";
import { ReconciliationCard, type Rec } from "@/components/app/reconciliation-card";
import { get } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

export default function Page() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const r = useLoad(() => get<Rec>(`/reconciliation?year=${ym.y}&month=${ym.m}`), [ym.y, ym.m]);
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("rec.title")}</h1>
      <MonthPicker year={ym.y} month={ym.m} onChange={(y, m) => setYm({ y, m })} />
      <ErrorText>{r.error?.friendly}</ErrorText>
      {r.loading && !r.data ? <Loading /> : r.data && <ReconciliationCard rec={r.data} admin={false} onChange={() => void r.reload(true)} />}
    </div>
  );
}
