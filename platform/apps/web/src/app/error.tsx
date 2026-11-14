"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations();
  return (
    <main id="content" className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="m-0 font-display text-[28px] font-semibold">{t("errors.errorTitle")}</h1>
      <p className="m-0 text-sm text-muted">{t("errors.errorBody")}</p>
      <div className="mt-2">
        <Button onClick={reset}>{t("common.tryAgain")}</Button>
      </div>
    </main>
  );
}
