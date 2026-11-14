"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { Icon } from "@/components/ui/Icon";
import { cx } from "@/lib/cx";
import type { NavGroup } from "./nav";

export function NavLinks({ groups, onNavigate }: { groups: NavGroup[]; onNavigate?: () => void }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => (
        <div key={group.key} className="flex flex-col gap-0.5">
          <div className="px-2.5 pt-1.5 pb-1 text-xs text-faint">{t(group.key)}</div>
          {group.items.map((item) => {
            // Overview is the organization root; its sub-pages are their own items.
            const active = item.key === "overview" ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link
                key={item.key}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex h-9 items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 text-sm transition-colors duration-[120ms]",
                  active ? "bg-raised text-text" : "text-muted hover:bg-raised/60 hover:text-text",
                )}
              >
                <Icon name={item.icon} />
                {t(item.key)}
              </Link>
            );
          })}
        </div>
      ))}
    </div>
  );
}
