"use client";
import { Empty, ErrorText, Loading } from "@/components/app/bits";
import { get } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

interface Row { id: number; at: string; actor_id: string | null; action: string; entity_type: string; entity_id: string | null }

export default function Page() {
  const l = useLoad(() => get<Row[]>("/audit?limit=300"), []);
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("audit.title")}</h1>
      <p className="text-xs text-muted-foreground">{t("audit.note")}</p>
      <ErrorText>{l.error?.friendly}</ErrorText>
      {l.loading && !l.data ? <Loading /> : l.data?.length === 0 ? <Empty /> : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-xs" data-testid="audit-table">
            <thead className="bg-muted text-left"><tr><th className="p-2">{t("audit.at")}</th><th className="p-2">{t("audit.action")}</th><th className="p-2">{t("audit.entity")}</th></tr></thead>
            <tbody>{l.data?.map((r) => <tr key={r.id} className="border-t"><td className="p-2 whitespace-nowrap">{new Date(r.at).toLocaleString("sq-AL")}</td><td className="p-2" data-testid="audit-action">{r.action}</td><td className="p-2">{r.entity_type} {r.entity_id?.slice(0, 8)}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
