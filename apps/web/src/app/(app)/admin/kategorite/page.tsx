"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorText, Loading, TextField } from "@/components/app/bits";
import { del, get, post } from "@/lib/api";
import { canWrite, useAuth } from "@/lib/auth";
import { useAction, useLoad } from "@/lib/hooks";
import { t } from "@/i18n";

export default function Page() {
  const { user } = useAuth();
  const list = useLoad(() => get<{ id: string; name: string }[]>("/categories"), []);
  const act = useAction();
  const [name, setName] = useState("");
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("categories.title")}</h1>
      <ErrorText>{act.error}</ErrorText>
      {canWrite(user?.role) && (
        <div className="flex items-end gap-2">
          <TextField label={t("common.name")} value={name} onChange={setName} />
          <Button disabled={!name || act.busy} data-testid="add-category" onClick={() => void act.run(async () => { await post("/categories", { name }); setName(""); await list.reload(true); })}>{t("categories.add")}</Button>
        </div>
      )}
      {list.loading && !list.data ? <Loading /> : (
        <ul className="grid gap-2 sm:grid-cols-2" data-testid="category-list">
          {list.data?.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded-lg border p-3 text-sm"><span>{c.name}</span>
              {canWrite(user?.role) && <Button size="sm" variant="ghost" onClick={() => void act.run(async () => { await del(`/categories/${c.id}`); await list.reload(true); })}>{t("categories.archive")}</Button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
