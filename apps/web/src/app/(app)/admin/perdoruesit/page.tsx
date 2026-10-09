"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, Loading, NativeSelect, TextField } from "@/components/app/bits";
import { get, patch, post } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

interface U { id: string; name: string; email: string; role: string; is_active: boolean }

export default function Page() {
  const { user } = useAuth();
  const list = useLoad(() => get<U[]>("/users"), []);
  const act = useAction();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "employee" });
  const roles = user?.role === "super_admin" ? ["employee", "auditor", "financial_admin", "super_admin"] : ["employee"];
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("users.title")}</h1>
      <ErrorText>{list.error?.friendly}{act.error}</ErrorText>
      {list.loading && !list.data ? <Loading /> : (
        <ul className="grid gap-2" data-testid="user-list">
          {list.data?.map((u) => (
            <li key={u.id} className="flex items-center justify-between rounded-lg border p-3 text-sm" data-testid="user-row">
              <div><div className="font-medium">{u.name}</div><div className="text-xs text-muted-foreground">{u.email} · {t(`users.role.${u.role}`)}</div></div>
              {canWrite(user?.role) && u.id !== user?.id && (
                <Button size="sm" variant="outline" onClick={() => void act.run(async () => { await patch(`/users/${u.id}`, { is_active: !u.is_active }); await list.reload(true); })}>{u.is_active ? t("users.deactivate") : t("users.activate")}</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canWrite(user?.role) && (
        <Card>
          <CardHeader><CardTitle className="text-base">{t("users.add")}</CardTitle></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <TextField label={t("common.name")} value={f.name} onChange={(v) => setF({ ...f, name: v })} />
            <TextField label={t("common.email")} type="email" value={f.email} onChange={(v) => setF({ ...f, email: v })} />
            <TextField label={t("common.password")} type="password" value={f.password} onChange={(v) => setF({ ...f, password: v })} hint={t("users.minPw")} />
            <NativeSelect label={t("common.role")} value={f.role} onChange={(v) => setF({ ...f, role: v })} options={roles.map((r) => ({ value: r, label: t(`users.role.${r}`) }))} />
            <Button className="sm:col-span-2" disabled={act.busy || !f.name || !f.email || f.password.length < 10} data-testid="create-user" onClick={() => void act.run(async () => { await post("/users", f); setF({ name: "", email: "", password: "", role: "employee" }); await list.reload(true); })}>{t("common.create")}</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
