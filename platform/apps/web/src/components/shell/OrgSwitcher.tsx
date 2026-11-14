"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { cx } from "@/lib/cx";
import type { MyOrganization } from "@/lib/types";

export function OrgSwitcher({ orgs, currentId }: { orgs: MyOrganization[]; currentId: string | null }) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const current = orgs.find((o) => o.id === currentId) ?? null;

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (orgs.length === 0) return null;
  const label = current ? current.name : t("orgSwitcher.none");

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={t("orgSwitcher.change", { name: label })}
        onClick={() => setOpen((v) => !v)}
        className="flex h-11 w-full items-center justify-between gap-2 rounded-[var(--radius-control)] border border-rule bg-panel px-2.5 text-start text-sm font-medium text-text hover:border-control"
      >
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="truncate">{label}</span>
          {current ? <span className="truncate text-xs font-normal text-muted">{t(`roles.${current.role}`)}</span> : null}
        </span>
        <Icon name="chevrons" className="shrink-0 text-muted" />
      </button>
      {open ? (
        <ul
          id={menuId}
          className="nx-rise absolute inset-x-0 top-12 z-20 m-0 flex list-none flex-col gap-0.5 rounded-[var(--radius-panel)] border border-rule bg-panel p-1.5 shadow-lg shadow-black/30"
        >
          {orgs.map((org) => (
            <li key={org.id}>
              <Link
                href={`/o/${encodeURIComponent(org.id)}`}
                onClick={() => setOpen(false)}
                aria-current={org.id === currentId ? "true" : undefined}
                className={cx(
                  "flex items-center justify-between gap-2 rounded-[var(--radius-control)] px-2.5 py-2 text-sm",
                  org.id === currentId ? "bg-raised text-text" : "text-muted hover:bg-raised hover:text-text",
                )}
              >
                <span className="flex min-w-0 flex-col leading-tight">
                  <span className="truncate">{org.name}</span>
                  <span className="truncate text-xs text-faint">{t(`roles.${org.role}`)}</span>
                </span>
                {org.id === currentId ? <Icon name="check" className="shrink-0 text-link" /> : null}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
