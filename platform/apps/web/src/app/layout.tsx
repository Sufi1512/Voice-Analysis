import type { Metadata } from "next";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { THEME_COOKIE, themeFrom } from "@/lib/theme";
import { direction } from "@/i18n/config";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: { default: t("title"), template: t("titleTemplate", { page: "%s" }) } };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const [locale, jar] = await Promise.all([getLocale(), cookies()]);
  // Dark is the default; light only when the person chose it (no flash: set on the server).
  const theme = themeFrom(jar.get(THEME_COOKIE)?.value);
  return (
    <html lang={locale} dir={direction(locale)} data-theme={theme}>
      <body>
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
