"use client";

import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import type { MyOrganization } from "@/lib/types";
import type { NavGroup } from "./nav";
import { NavLinks } from "./NavLinks";
import { OrgSwitcher } from "./OrgSwitcher";

/** Below the large breakpoint the sidebar folds into a drawer behind a menu button. */
export function MobileNav({ groups, orgs, currentId }: { groups: NavGroup[]; orgs: MyOrganization[]; currentId: string | null }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  // Open on the page it was opened on: following any link (nav or organization) closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (value: boolean | ((v: boolean) => boolean)) =>
    setOpenOn((typeof value === "function" ? value(open) : value) ? pathname : null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenOn(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? t("closeMenu") : t("openMenu")}
        onClick={() => setOpen((v) => !v)}
        className="flex size-10 items-center justify-center rounded-[var(--radius-control)] border border-rule bg-panel text-muted"
      >
        <Icon name={open ? "close" : "menu"} size={18} />
      </button>
      {open ? (
        <nav
          aria-label={t("main")}
          className="nx-rise fixed inset-x-0 top-16 bottom-0 z-40 flex flex-col gap-4 overflow-y-auto border-t border-rule bg-sidebar p-4"
        >
          <OrgSwitcher orgs={orgs} currentId={currentId} />
          <NavLinks groups={groups} onNavigate={() => setOpen(false)} />
        </nav>
      ) : null}
    </div>
  );
}
