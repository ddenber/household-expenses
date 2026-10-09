"use client";
import { NativeSelect } from "@/components/app/bits";
import { months, t } from "@/i18n";

export function MonthPicker({ year, month, onChange }: { year: number; month: number; onChange: (y: number, m: number) => void }) {
  const now = new Date().getFullYear();
  return (
    <div className="grid max-w-sm grid-cols-2 gap-3">
      <NativeSelect label={t("common.month")} value={String(month)} onChange={(v) => onChange(year, Number(v))} options={months.map((m, i) => ({ value: String(i + 1), label: m }))} />
      <NativeSelect label={t("common.year")} value={String(year)} onChange={(v) => onChange(Number(v), month)} options={[now - 2, now - 1, now].map((y) => ({ value: String(y), label: String(y) }))} />
    </div>
  );
}
