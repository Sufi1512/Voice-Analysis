"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Status";
import { api } from "@/lib/api";
import type { Role } from "@/lib/types";
import { PasswordField } from "./PasswordField";

type Accepted = { organization_id: string; role: Role };
type FieldError = "passwordTooShort" | "wrongPassword" | null;
type Blocking = "missing" | "invalid" | "used" | "expired" | "otherAccount" | "locked" | "network" | "unexpected";

const TOKEN = /^[A-Za-z0-9_-]{43,}$/;

// The token travels in the fragment (#...), which browsers never send to servers. Take it once,
// then drop it from the address bar and history so it isn't left behind. Idempotent, so React's
// development double-render reads the same value.
let captured: string | null = null;
function takeToken(): string | null {
  const raw = window.location.hash.slice(1);
  if (raw) {
    captured = TOKEN.test(raw) ? raw : null;
    window.history.replaceState(null, "", window.location.pathname);
  }
  return captured;
}

export function InviteForm() {
  const t = useTranslations();
  const router = useRouter();
  const [token] = useState(takeToken); // rendered only in the browser (see app/(auth)/invite)
  const [busy, setBusy] = useState(false);
  const [blocking, setBlocking] = useState<Blocking | null>(null);
  const [fieldError, setFieldError] = useState<FieldError>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setBlocking(null);
    setFieldError(null);
    const result = await api<Accepted>(`/v1/invitations/${token}/accept`, {
      method: "POST",
      json: { name: String(form.get("name") ?? "").trim() || null, password: String(form.get("password") ?? "") || null },
    });
    if (result.ok) {
      router.replace(`/o/${encodeURIComponent(result.data.organization_id)}`);
      router.refresh();
      return;
    }
    setBusy(false);
    const map: Record<string, () => void> = {
      password_too_short: () => setFieldError("passwordTooShort"),
      invalid_credentials: () => setFieldError("wrongPassword"),
      invitation_invalid: () => setBlocking("invalid"),
      invitation_used: () => setBlocking("used"),
      invitation_expired: () => setBlocking("expired"),
      invitation_for_another_account: () => setBlocking("otherAccount"),
      locked: () => setBlocking("locked"),
      network: () => setBlocking("network"),
    };
    (map[result.error] ?? (() => setBlocking("unexpected")))();
  }

  const heading = <h1 className="m-0 font-display text-[28px] font-semibold">{t("invite.title")}</h1>;
  const dead = token === null ? "missing" : blocking && ["invalid", "used", "expired"].includes(blocking) ? blocking : null;
  if (dead) {
    return (
      <div className="flex flex-col gap-5">
        {heading}
        <Notice tone="critical">{t(`invite.${dead as "missing" | "invalid" | "used" | "expired"}`)}</Notice>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        {heading}
        <p className="m-0 text-sm leading-relaxed text-muted">{t("invite.newAccount")}</p>
        <p className="m-0 text-sm leading-relaxed text-muted">{t("invite.existingAccount")}</p>
      </div>
      {blocking ? (
        <Notice tone="critical">
          {blocking === "otherAccount"
            ? t("invite.otherAccount")
            : blocking === "locked"
              ? t("invite.locked")
              : blocking === "network"
                ? t("common.networkError")
                : t("common.unexpected")}
        </Notice>
      ) : null}
      <Field id="name" name="name" label={t("invite.name")} hint={t("invite.nameHint")} autoComplete="name" maxLength={200} />
      <PasswordField
        id="password"
        name="password"
        label={t("invite.password")}
        hint={t("invite.passwordHint")}
        error={fieldError ? t(`invite.${fieldError}`) : undefined}
        autoComplete="new-password"
        required
        autoFocus
      />
      <Button type="submit" variant="primary" disabled={busy} className="w-full">
        {busy ? t("invite.submitting") : t("invite.submit")}
      </Button>
    </form>
  );
}
