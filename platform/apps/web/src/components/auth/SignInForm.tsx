"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Status";
import { api } from "@/lib/api";
import { safeNext } from "@/lib/next-path";
import { PasswordField } from "./PasswordField";

type Problem = { kind: "invalid" } | { kind: "locked"; minutes: number } | { kind: "network" } | { kind: "unexpected" };

export function SignInForm({ next, banner }: { next: string | null; banner: "signedOut" | "sessionEnded" | null }) {
  const t = useTranslations();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const password = useRef<HTMLInputElement>(null);
  const router = useRouter();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setProblem(null);
    const result = await api("/v1/auth/login", {
      method: "POST",
      json: { email: String(form.get("email") ?? "").trim(), password: String(form.get("password") ?? "") },
    });
    if (result.ok) {
      router.replace(safeNext(next));
      router.refresh(); // server layouts render again with the new session
      return;
    }
    setBusy(false);
    if (result.status === 401) {
      setProblem({ kind: "invalid" });
      if (password.current) {
        password.current.value = "";
        password.current.focus();
      }
    } else if (result.status === 429) {
      const seconds = Number(result.headers?.get("retry-after") ?? 900);
      setProblem({ kind: "locked", minutes: Math.max(1, Math.ceil(seconds / 60)) });
    } else {
      setProblem({ kind: result.status === 0 ? "network" : "unexpected" });
    }
  }

  return (
    <form onSubmit={submit} noValidate={false} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h1 className="m-0 font-display text-[28px] font-semibold">{t("signIn.title")}</h1>
        <p className="m-0 text-sm text-muted">{t("signIn.intro")}</p>
      </div>
      {banner && !problem ? <Notice tone="neutral">{t(`signIn.${banner}`)}</Notice> : null}
      {problem ? (
        <Notice tone="critical">
          {problem.kind === "invalid"
            ? t("signIn.invalid")
            : problem.kind === "locked"
              ? t("signIn.locked", { minutes: problem.minutes })
              : problem.kind === "network"
                ? t("common.networkError")
                : t("common.unexpected")}
        </Notice>
      ) : null}
      <Field id="email" name="email" type="email" label={t("signIn.email")} autoComplete="username" required autoFocus />
      <PasswordField
        ref={password}
        id="password"
        name="password"
        label={t("signIn.password")}
        autoComplete="current-password"
        required
      />
      <Button type="submit" variant="primary" disabled={busy} className="w-full">
        {busy ? t("signIn.submitting") : t("signIn.submit")}
      </Button>
      <p className="m-0 border-t border-rule-soft pt-4 text-[13px] leading-relaxed text-muted">{t("signIn.inviteOnly")}</p>
    </form>
  );
}
