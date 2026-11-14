import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { AppShell } from "@/components/shell/AppShell";
import { ButtonLink } from "@/components/ui/Button";
import { getMe, getMyOrganizations } from "@/lib/core";

/** Home: the first organization, the platform page for an owner with none, or how to get in. */
export default async function Home() {
  const [me, orgs, t] = await Promise.all([getMe(), getMyOrganizations(), getTranslations("home")]);
  if (!me) redirect("/sign-in");
  const first = orgs[0];
  if (first) redirect(`/o/${encodeURIComponent(first.id)}`);
  if (me.is_platform_owner) redirect("/platform");
  return (
    <AppShell me={me} orgs={orgs} org={null}>
      <div className="mx-auto mt-16 flex max-w-lg flex-col gap-3 text-center">
        <h1 className="m-0 font-display text-[28px] font-semibold">{t("noOrgTitle")}</h1>
        <p className="m-0 text-sm leading-relaxed text-muted">{t("noOrgBody")}</p>
        {me.is_platform_owner ? (
          <div className="mt-2">
            <ButtonLink href="/platform" variant="primary">
              {t("goToPlatform")}
            </ButtonLink>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
