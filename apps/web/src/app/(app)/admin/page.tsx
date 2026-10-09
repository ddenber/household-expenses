"use client";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, ErrorText, Loading, Money } from "@/components/app/bits";
import { get, qs } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

interface Kpi { key: string; value: string; count?: number; link: { path: string; params?: Record<string, string> } }
interface Dash { month: string; kpis: Kpi[]; wallets: { user_id: string; name: string; balance: string; account_id: string }[]; negative_balances: string[] }

export default function Page() {
  const d = useLoad(() => get<Dash>("/dashboard/admin"), []);
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("admin.dashboard")}</h1>
      <ErrorText>{d.error?.friendly}</ErrorText>
      {d.loading && !d.data ? <Loading /> : d.data && (
        <>
          {d.data.negative_balances.length > 0 && <ErrorText>{t("admin.negative")} {d.data.negative_balances.join(", ")}</ErrorText>}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            {d.data.kpis.map((k) => (
              <Link key={k.key} href={`${k.link.path}${qs(k.link.params ?? {})}`} data-testid={`kpi-${k.key}`} className="rounded-xl border bg-card p-4 transition hover:bg-muted">
                <div className="text-xs text-muted-foreground">{t(`kpi.${k.key}`)}</div>
                <div className="mt-1 text-xl font-semibold" data-testid="kpi-value"><Money v={k.value} /></div>
                {k.count !== undefined && <div className="text-xs text-muted-foreground">{k.count}</div>}
              </Link>
            ))}
          </div>
          <h2 className="text-sm font-medium text-muted-foreground">{t("admin.wallets")}</h2>
          {d.data.wallets.length === 0 ? <Empty>{t("admin.noWallets")}</Empty> : (
            <div className="grid gap-2 sm:grid-cols-2">
              {d.data.wallets.map((w) => (
                <Link key={w.user_id} href={`/admin/librat?account_id=${w.account_id}`} className="flex justify-between rounded-lg border p-3 hover:bg-muted" data-testid="wallet-row">
                  <span>{w.name}</span><Money v={w.balance} className="font-medium" />
                </Link>
              ))}
            </div>
          )}
          <Card><CardContent className="flex flex-wrap gap-3 p-3 text-sm">
            <a className="underline" href="/api/v1/exports/transactions?format=xlsx">{t("common.export")} {t("nav.ledger")} ({t("common.excel")})</a>
            <a className="underline" href="/api/v1/exports/transactions?format=csv">{t("common.export")} {t("nav.ledger")} ({t("common.csv")})</a>
          </CardContent></Card>
        </>
      )}
    </div>
  );
}
