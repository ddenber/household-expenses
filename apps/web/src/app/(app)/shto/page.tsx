/* eslint-disable @next/next/no-img-element */
"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Camera, FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ErrorText, NativeSelect, TextField, MoneyField, apiAmount } from "@/components/app/bits";
import { get } from "@/lib/api";
import { prepareFile, type Prepared } from "@/lib/image";
import * as queue from "@/lib/offline-queue";
import { useSync } from "@/lib/sync";
import { useLoad } from "@/lib/hooks";
import { newKey } from "@/lib/format";
import { t } from "@/i18n";

type Item = Prepared & { id: string; preview?: string };

export default function AddReceipt() {
  const router = useRouter();
  const { syncNow, progress, lastCreated, online } = useSync();
  const input = useRef<HTMLInputElement>(null);
  const lock = useRef(false);
  const [items, setItems] = useState<Item[]>([]);
  const [method, setMethod] = useState("cash");
  const [supplier, setSupplier] = useState("");
  const [total, setTotal] = useState("");
  const [date, setDate] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offlineSaved, setOfflineSaved] = useState(false);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const cats = useLoad(() => get<{ id: string; name: string }[]>("/categories"), []);

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    setPreparing(true);
    const next: Item[] = [];
    for (const f of Array.from(files)) {
      const p = await prepareFile(f);
      next.push({ ...p, id: newKey(), preview: p.mime.startsWith("image/") && p.mime !== "image/heic" ? URL.createObjectURL(p.blob) : undefined });
    }
    setItems((cur) => [...cur, ...next]);
    setPreparing(false);
    if (input.current) input.current.value = "";
  }

  async function submit() {
    if (lock.current) return; // duplicate-tap protection
    if (!items.length) return setError(t("add.noFiles"));
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      let id = captureId;
      if (!id) {
        id = newKey();
        setCaptureId(id);
        await queue.enqueue({
          id,
          fields: {
            payment_method: method,
            ...(supplier && { supplier_name: supplier }),
            ...(total && { total: apiAmount(total) }),
            ...(date && { expense_date: date }),
            ...(category && { category_id: category }),
          },
          files: items.map((i) => ({ name: i.name, blob: i.blob })),
        });
      }
      if (!navigator.onLine) {
        setOfflineSaved(true);
        return;
      }
      await syncNow();
      let left = (await queue.list()).find((c) => c.id === id);
      for (let i = 0; left?.status === "syncing" && i < 120; i++) {
        await new Promise((r) => setTimeout(r, 500));
        left = (await queue.list()).find((c) => c.id === id);
      }
      if (left) {
        setError(left.status === "error" ? (left.error ?? t("errors.generic")) : t("errors.network"));
        return;
      }
      const eid = lastCreated.current[id];
      router.push(eid ? `/shpenzimet/${eid}` : "/shpenzimet");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  const pct = captureId ? (progress[captureId] ?? 0) : 0;

  if (offlineSaved) {
    return (
      <div className="grid gap-4 py-8 text-center">
        <p data-testid="offline-saved" className="rounded-md bg-amber-100 p-4 text-amber-900 dark:bg-amber-900 dark:text-amber-100">{t("add.savedOffline")}</p>
        <Button onClick={() => router.push("/")}>{t("nav.home")}</Button>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{t("add.title")}</h1>
      <input ref={input} data-testid="file-input" type="file" accept="image/jpeg,image/png,image/heic,image/heif,application/pdf" capture="environment" multiple hidden onChange={(e) => void onFiles(e.target.files)} />
      <Button type="button" className="h-20 text-lg" data-testid="pick-file" onClick={() => input.current?.click()} disabled={busy}>
        <Camera className="size-6" /> {items.length ? t("add.addPage") : t("add.takePhoto")}
      </Button>
      <p className="text-xs text-muted-foreground">{t("add.hint")}</p>
      {preparing && <p className="text-sm">{t("add.compress")}</p>}
      {items.length > 0 && (
        <ul className="grid grid-cols-3 gap-2" aria-label={t("add.pages")}>
          {items.map((i, idx) => (
            <li key={i.id} className="relative overflow-hidden rounded-lg border bg-muted" data-testid="page-thumb">
              {i.preview ? <img src={i.preview} alt={`${t("add.pages")} ${idx + 1}`} className="aspect-square w-full object-cover" /> : (
                <div className="flex aspect-square flex-col items-center justify-center gap-1 text-xs"><FileText className="size-8" />{i.name.slice(0, 14)}</div>
              )}
              {!busy && <button type="button" aria-label={t("add.remove")} className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white" onClick={() => setItems((c) => c.filter((x) => x.id !== i.id))}><X className="size-3" /></button>}
            </li>
          ))}
        </ul>
      )}
      <NativeSelect label={t("add.payment")} value={method} onChange={setMethod} options={["cash", "card", "bank_transfer", "personal_funds"].map((m) => ({ value: m, label: t(`pay.${m}`) }))} />
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("add.optionalDetails")}</summary>
        <div className="mt-3 grid gap-3">
          <TextField label={t("common.supplier")} value={supplier} onChange={setSupplier} />
          <MoneyField label={t("common.total")} value={total} onChange={setTotal} />
          <TextField label={t("common.date")} type="date" value={date} onChange={setDate} />
          <NativeSelect label={t("common.category")} value={category} onChange={setCategory} empty="–" options={(cats.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
        </div>
      </details>
      <ErrorText>{error}</ErrorText>
      {busy && (
        <div className="grid gap-1" data-testid="upload-progress"><Progress value={pct} /><p className="text-xs text-muted-foreground">{t("add.uploading")} {pct}%</p></div>
      )}
      {!online && <p className="text-xs text-amber-700 dark:text-amber-300">{t("sync.offline")}</p>}
      <Button className="h-12 text-base" data-testid="submit-receipt" disabled={busy || preparing || items.length === 0} onClick={() => void submit()}>
        {busy ? t("add.saving") : error ? t("common.retry") : t("add.submit")}
      </Button>
    </div>
  );
}
