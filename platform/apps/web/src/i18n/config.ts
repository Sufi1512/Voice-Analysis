// English only in P1; the portal is built so Arabic is a messages file plus a locale here.
export const locales = ["en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

const RTL = new Set(["ar", "he", "fa", "ur"]);

export function direction(locale: string): "ltr" | "rtl" {
  return RTL.has(locale.split("-")[0] ?? "") ? "rtl" : "ltr";
}
