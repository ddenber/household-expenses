"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Camera } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, ErrorText, LinkButton, Loading, Money, StatusBadge } from "@/components/app/bits";
import { get } from "@/lib/api";
import { isAdminRole, useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/hooks";
import { useSync } from "@/lib/sync";
import { formatDate } from "@/lib/format";
import { t } from "@/i18n";

interface Dash {
  cash_balance: string | null;
  pending: { amount: string; count: number };
  month_total: { amount: string; count: number };
  recent: { id: string; supplier_name: string | null; total: string | null; status: string; expense_date: string | null }[];
}

export default function Home() {
  const { user } = useAuth();
  const router = useRouter();
  const admin = isAdminRole(user?.role) || user?.role === "auditor";
  useEffect(() => { if (admin) router.replace("/admin"); }, [admin, router]);
  const { data, error, loading } = useLoad(() => get<Dash>("/dashboard/employee"), [admin]);
  const { pending } = useSync();
  if (admin) return <Loading />;
  return (
    <div className="grid gap-4">
      <h1 className="text-lg font-medium">{t("home.greeting")}, {user?.name}</h1>
      <ErrorText>{error?.friendly}</ErrorText>
      {loading && !data ? <Loading /> : data && (
        <>
          <Card><CardContent className="p-5">
            <div className="text-sm text-muted-foreground">{t("home.cash")}</div>
            <div className="mt-1 text-4xl font-bold" data-testid="cash-balance"><Money v={data.cash_balance} /></div>
          </CardContent></Card>
          <div className="grid grid-cols-2 gap-3">
            <Card><CardContent className="p-4">
              <div className="text-xs text-muted-foreground">{t("home.pending")}</div>
              <div className="text-xl font-semibold" data-testid="pending-count">{data.pending.count}</div>
              <div className="text-xs text-muted-foreground"><Money v={data.pending.amount} /></div>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <div className="text-xs text-muted-foreground">{t("home.monthTotal")}</div>
              <div className="text-xl font-semibold" data-testid="month-total"><Money v={data.month_total.amount} /></div>
            </CardContent></Card>
          </div>
          <Link href="/shto" data-testid="add-receipt" className="flex h-20 items-center justify-center gap-3 rounded-2xl bg-emerald-600 text-xl font-semibold text-white shadow-lg active:scale-[0.99] hover:bg-emerald-700">
            <Camera className="size-7" /> {t("home.addReceipt")}
          </Link>
          <LinkButton href="/shpenzimet" testId="view-expenses" className="h-12">{t("home.viewExpenses")}</LinkButton>
          {pending.length > 0 && (
            <p className="rounded-md bg-amber-100 p-3 text-sm text-amber-900 dark:bg-amber-900 dark:text-amber-100">{t("home.offlineQueue")}: {pending.length}</p>
          )}
          <section>
            <h2 className="mb-2 text-sm font-medium text-muted-foreground">{t("home.recent")}</h2>
            {data.recent.length === 0 ? <Empty>{t("home.noRecent")}</Empty> : (
              <ul className="grid gap-2">
                {data.recent.map((e) => (
                  <li key={e.id}>
                    <Link href={`/shpenzimet/${e.id}`} className="flex items-center justify-between rounded-lg border p-3 hover:bg-muted">
                      <div className="min-w-0"><div className="truncate font-medium">{e.supplier_name ?? "–"}</div><div className="text-xs text-muted-foreground">{formatDate(e.expense_date)}</div></div>
                      <div className="flex flex-col items-end gap-1"><Money v={e.total} /><StatusBadge status={e.status} /></div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
