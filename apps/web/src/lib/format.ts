// Presentation only: amounts arrive from the API as decimal strings and are never parsed to floats.
export function formatEur(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "–";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!m) return value;
  const [, sign, whole, frac = ""] = m;
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped},${(frac + "00").slice(0, 2)}\u00a0€`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, mo, d] = iso.slice(0, 10).split("-");
  return `${d}.${mo}.${y}`;
}

export function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function newKey(): string {
  return crypto.randomUUID();
}
