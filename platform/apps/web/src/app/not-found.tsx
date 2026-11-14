import { getTranslations } from "next-intl/server";
import { ButtonLink } from "@/components/ui/Button";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <main id="content" className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="m-0 font-display text-[28px] font-semibold">{t("notFoundTitle")}</h1>
      <p className="m-0 text-sm text-muted">{t("notFoundBody")}</p>
      <div className="mt-2">
        <ButtonLink href="/">{t("backHome")}</ButtonLink>
      </div>
    </main>
  );
}
