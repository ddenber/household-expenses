import { sq } from "./sq";

type Dict = Record<string, unknown>;
const dict: Dict = sq;

export function t(key: string, vars?: Record<string, string | number>): string {
  let cur: unknown = dict;
  for (const part of key.split(".")) {
    if (cur && typeof cur === "object") cur = (cur as Dict)[part];
    else return key;
  }
  if (typeof cur !== "string") return key;
  return vars ? cur.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "")) : cur;
}

export const months = sq.months;
