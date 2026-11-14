import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { Logo } from "@/components/brand/Logo";

/** Sign-in and invitation pages: one ruled panel, the signal mark above it. */
export default async function AuthLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("brand");
  return (
    <main id="content" className="flex min-h-dvh flex-col items-center justify-center gap-8 px-4 py-12">
      <div className="flex flex-col items-center gap-3 text-center">
        <Logo size={34} />
        <p className="m-0 max-w-xs text-sm text-muted">{t("tagline")}</p>
      </div>
      <div className="w-full max-w-[420px] rounded-[var(--radius-panel)] border border-rule bg-panel p-6 sm:p-8">{children}</div>
    </main>
  );
}
