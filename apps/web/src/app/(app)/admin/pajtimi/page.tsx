"use client";
import { useState } from "react";
import { Empty, ErrorText, Loading } from "@/components/app/bits";
import { MonthPicker } from "@/components/app/month-picker";
import { ReconciliationCard, type Rec } from "@/components/app/reconciliation-card";
import { get } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

export default function Page() {
  const { user } = useAuth();
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const r = useLoad(() => get<Rec[]>(`/reconciliation/overview?year=${ym.y}&month=${ym.m}`), [ym.y, ym.m]);
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("rec.overview")}</h1>
      <MonthPicker year={ym.y} month={ym.m} onChange={(y, m) => setYm({ y, m })} />
      <ErrorText>{r.error?.friendly}</ErrorText>
      {r.loading && !r.data ? <Loading /> : r.data?.length === 0 ? <Empty>{t("admin.noWallets")}</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {r.data?.map((rec) => <ReconciliationCard key={rec.user_id} rec={rec} admin={canWrite(user?.role)} onChange={() => void r.reload(true)} />)}
        </div>
      )}
    </div>
  );
}
