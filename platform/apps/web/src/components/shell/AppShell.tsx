import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { THEME_COOKIE, themeFrom } from "@/lib/theme";
import { Logo } from "@/components/brand/Logo";
import type { Me, MyOrganization, Organization } from "@/lib/types";
import { MobileNav } from "./MobileNav";
import { NavLinks } from "./NavLinks";
import { navigation } from "./nav";
import { OrgSwitcher } from "./OrgSwitcher";
import { UserMenu } from "./UserMenu";

export async function AppShell({
  me,
  orgs,
  org,
  children,
}: {
  me: Me;
  orgs: MyOrganization[];
  org: Organization | null;
  children: ReactNode;
}) {
  const [t, jar] = await Promise.all([getTranslations("nav"), cookies()]);
  const theme = themeFrom(jar.get(THEME_COOKIE)?.value);
  const groups = navigation(org, me.is_platform_owner);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#content"
        className="absolute start-2 top-2 z-50 -translate-y-20 rounded-[var(--radius-control)] bg-action px-3 py-2 text-sm text-on-action focus:translate-y-0"
      >
        {t("skipToContent")}
      </a>
      <nav
        aria-label={t("main")}
        className="hidden w-[232px] shrink-0 flex-col gap-[18px] border-e border-rule-soft bg-sidebar px-3.5 py-5 lg:flex"
      >
        <div className="px-2">
          <Logo />
        </div>
        <OrgSwitcher orgs={orgs} currentId={org?.id ?? null} />
        <NavLinks groups={groups} />
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between gap-3 border-b border-rule-soft px-4 sm:px-6 lg:justify-end lg:border-b-0 lg:px-9">
          <div className="flex items-center gap-3 lg:hidden">
            <MobileNav groups={groups} orgs={orgs} currentId={org?.id ?? null} />
            <Logo size={24} />
          </div>
          <UserMenu user={me.user} theme={theme} />
        </header>
        <main id="content" tabIndex={-1} className="flex min-w-0 flex-1 flex-col gap-7 px-4 pt-2 pb-12 outline-none sm:px-6 lg:px-9">
          {children}
        </main>
      </div>
    </div>
  );
}
