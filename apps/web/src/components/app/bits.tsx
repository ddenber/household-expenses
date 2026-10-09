"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { formatEur } from "@/lib/format";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export function Money({ v, className }: { v: string | null | undefined; className?: string }) {
  const neg = typeof v === "string" && v.startsWith("-");
  return <span className={cn("tabular-nums", neg && "text-red-600 dark:text-red-400", className)}>{formatEur(v)}</span>;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100",
  uploaded: "bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100",
  processing: "bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100",
  needs_review: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  submitted: "bg-indigo-100 text-indigo-900 dark:bg-indigo-900 dark:text-indigo-100",
  approved: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
  rejected: "bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100",
  posted: "bg-emerald-600 text-white",
  reversed: "bg-zinc-300 text-zinc-800 line-through dark:bg-zinc-700 dark:text-zinc-200",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge data-testid="status-badge" className={cn("border-0", STATUS_STYLE[status])}>
      {t(`status.${status}`)}
    </Badge>
  );
}

export function PageTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{children}</h1>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

export function ErrorText({ children }: { children?: ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" data-testid="error" className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
      {children}
    </p>
  );
}

export function Loading() {
  return <p className="py-8 text-center text-sm text-muted-foreground">{t("common.loading")}</p>;
}

export function Empty({ children }: { children?: ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted-foreground">{children ?? t("common.empty")}</p>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function TextField({ label, value, onChange, type = "text", placeholder, name, hint, required }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; name?: string; hint?: string; required?: boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <Input
        name={name ?? label}
        aria-label={label}
        type={type}
        inputMode={type === "money" ? "decimal" : undefined}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

export function MoneyField(props: Omit<Parameters<typeof TextField>[0], "type">) {
  return <TextField {...props} type="text" placeholder={props.placeholder ?? "0,00"} />;
}

export function NativeSelect({ label, value, onChange, options, name, empty }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; name?: string; empty?: string;
}) {
  return (
    <Field label={label}>
      <select
        aria-label={label}
        name={name ?? label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        {empty !== undefined && <option value="">{empty}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </Field>
  );
}

export function LinkButton({ href, children, variant = "outline", className, testId }: { href: string; children: ReactNode; variant?: "outline" | "default" | "secondary"; className?: string; testId?: string }) {
  return (
    <Link href={href} data-testid={testId} className={cn(buttonVariants({ variant }), className)}>
      {children}
    </Link>
  );
}

/** Normalise "12,50" typed by a user into the API decimal format; validation stays server-side. */
export function apiAmount(s: string): string {
  return s.trim().replace(/\s/g, "").replace(",", ".");
}
