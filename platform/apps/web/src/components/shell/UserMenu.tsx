"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { api } from "@/lib/api";
import { initials } from "@/lib/initials";
import { THEME_COOKIE, type Theme } from "@/lib/theme";
import type { User } from "@/lib/types";


function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  const secure = window.location.protocol === "https:" ? "; Secure" : ""; // plain http only in local dev
  document.cookie = `${THEME_COOKIE}=${theme}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}

export function UserMenu({ user, theme: initialTheme }: { user: User; theme: Theme }) {
  const t = useTranslations("user");
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [busy, setBusy] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const display = user.name || user.email;
  const router = useRouter();

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

  async function signOut(everywhere: boolean) {
    setBusy(true);
    await api(everywhere ? "/v1/auth/logout-all" : "/v1/auth/logout", { method: "POST" });
    router.replace("/sign-in?signedOut=1");
    router.refresh();
  }

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  }

  const item =
    "flex h-9 w-full items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 text-start text-sm text-muted hover:bg-raised hover:text-text disabled:opacity-60";

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={t("menu", { name: display })}
        onClick={() => setOpen((v) => !v)}
        className="flex size-10 items-center justify-center rounded-full bg-avatar text-[13px] font-semibold text-avatar-text hover:brightness-110"
      >
        {initials(user.name, user.email)}
      </button>
      {open ? (
        <div
          id={menuId}
          className="nx-rise absolute end-0 top-12 z-30 flex w-64 flex-col gap-0.5 rounded-[var(--radius-panel)] border border-rule bg-panel p-1.5 shadow-lg shadow-black/30"
        >
          <div className="border-b border-rule-soft px-2.5 pt-1.5 pb-2.5">
            <div className="text-xs text-faint">{t("signedInAs")}</div>
            <div className="truncate text-sm text-text">{display}</div>
            {user.name ? <div className="truncate text-xs text-muted">{user.email}</div> : null}
          </div>
          <button type="button" className={item} onClick={toggleTheme}>
            <Icon name={theme === "dark" ? "sun" : "moon"} />
            {theme === "dark" ? t("switchToLight") : t("switchToDark")}
          </button>
          <button type="button" className={item} disabled={busy} onClick={() => signOut(false)}>
            <Icon name="signOut" />
            {t("signOut")}
          </button>
          <button type="button" className={item} disabled={busy} onClick={() => signOut(true)}>
            <Icon name="devices" />
            {t("signOutEverywhere")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
