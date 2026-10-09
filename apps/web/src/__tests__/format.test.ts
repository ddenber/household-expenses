import { describe, expect, it } from "vitest";
import { formatDate, formatEur } from "@/lib/format";
import { t } from "@/i18n";
import { sq } from "@/i18n/sq";
import { scaleDims } from "@/lib/image";
import { apiAmount } from "@/components/app/bits";

describe("formatEur", () => {
  it("formats decimal strings without floating point", () => {
    expect(formatEur("1234.5")).toBe("1.234,50\u00a0€");
    expect(formatEur("0.10")).toBe("0,10\u00a0€");
    expect(formatEur("-5.00")).toBe("-5,00\u00a0€");
    expect(formatEur("1000000.01")).toBe("1.000.000,01\u00a0€");
    expect(formatEur("99999999999999.99")).toBe("99.999.999.999.999,99\u00a0€");
  });
  it("handles empty values", () => {
    expect(formatEur(null)).toBe("–");
    expect(formatEur("")).toBe("–");
  });
});

describe("i18n", () => {
  it("resolves keys and interpolates", () => {
    expect(t("home.addReceipt")).toBe("Shto Faturë");
    expect(t("sync.pending", { n: 3 })).toBe("3 në pritje për sinkronizim");
    expect(t("does.not.exist")).toBe("does.not.exist");
  });
  it("has the 20 seeded-category-related statuses translated", () => {
    for (const s of ["draft", "uploaded", "processing", "needs_review", "submitted", "approved", "rejected", "posted", "reversed"]) {
      expect(sq.status[s as keyof typeof sq.status]).toBeTruthy();
    }
  });
});

describe("helpers", () => {
  it("formats dates dd.mm.yyyy", () => expect(formatDate("2026-03-05")).toBe("05.03.2026"));
  it("scales images down but never up", () => {
    expect(scaleDims(4000, 3000)).toEqual({ w: 2000, h: 1500 });
    expect(scaleDims(800, 600)).toEqual({ w: 800, h: 600 });
  });
  it("normalises decimal commas for the API only", () => {
    expect(apiAmount("12,50")).toBe("12.50");
    expect(apiAmount(" 1 200,00 ")).toBe("1200.00");
  });
});
