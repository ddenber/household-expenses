"use client";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorText, Loading, Money, TextField } from "@/components/app/bits";
import { get, qs } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

interface Row { id: string; name: string; total: string }

function Table({ title, rows, id }: { title: string; rows: Row[]; id: string }) {
  // Bar widths use the integer cents only to scale the visual; no money is calculated here.
  const cents = (s: string) => Number(s.replace(".", ""));
  const max = Math.max(1, ...rows.map((r) => cents(r.total)));
  return (
    <Card data-testid={id}>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent className="grid gap-2">
        {rows.length === 0 ? <Empty /> : rows.map((r) => (
          <div key={r.id} data-testid="analytics-row" data-name={r.name}>
            <div className="flex justify-between text-sm"><span>{r.name}</span><Money v={r.total} className="font-medium" /></div>
            <div className="h-1.5 rounded bg-muted"><div className="h-1.5 rounded bg-emerald-600" style={{ width: `${Math.max(2, (cents(r.total) / max) * 100)}%` }} /></div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function Page() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const sup = useLoad(() => get<Row[]>(`/analytics/spend${qs({ group: "supplier", date_from: from, date_to: to })}`), [from, to]);
  const cat = useLoad(() => get<Row[]>(`/analytics/spend${qs({ group: "category", date_from: from, date_to: to })}`), [from, to]);
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("analytics.title")}</h1>
      <p className="text-xs text-muted-foreground">{t("analytics.note")}</p>
      <div className="grid max-w-md grid-cols-2 gap-3"><TextField label={t("common.from")} type="date" value={from} onChange={setFrom} /><TextField label={t("common.to")} type="date" value={to} onChange={setTo} /></div>
      <ErrorText>{sup.error?.friendly}</ErrorText>
      {(sup.loading && !sup.data) || (cat.loading && !cat.data) ? <Loading /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Table id="by-supplier" title={t("analytics.bySupplier")} rows={sup.data ?? []} />
          <Table id="by-category" title={t("analytics.byCategory")} rows={cat.data ?? []} />
        </div>
      )}
    </div>
  );
}
