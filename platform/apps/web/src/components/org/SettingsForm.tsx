"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Status";
import { api } from "@/lib/api";

export function SettingsForm({ orgId, name, slug, canEdit }: { orgId: string; name: string; slug: string; canEdit: boolean }) {
  const t = useTranslations();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<"saved" | "error" | "network" | null>(null);
  const [nameError, setNameError] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    setResult(null);
    if (!value) return setNameError(true);
    setNameError(false);
    setBusy(true);
    const r = await api(`/v1/organizations/${encodeURIComponent(orgId)}`, { method: "PATCH", json: { name: value } });
    setBusy(false);
    setResult(r.ok ? "saved" : r.status === 0 ? "network" : "error");
    if (r.ok) router.refresh(); // the switcher and titles show the new name
  }

  return (
    <form onSubmit={submit} className="flex max-w-xl flex-col gap-5 px-[18px] py-5">
      {!canEdit ? <Notice tone="neutral">{t("settings.readOnly")}</Notice> : null}
      {result === "saved" ? <Notice tone="good">{t("common.saved")}</Notice> : null}
      {result === "error" ? <Notice tone="critical">{t("common.unexpected")}</Notice> : null}
      {result === "network" ? <Notice tone="critical">{t("common.networkError")}</Notice> : null}
      <Field
        id="org-name"
        name="name"
        label={t("settings.name")}
        hint={t("settings.nameHint")}
        error={nameError ? t("settings.nameRequired") : undefined}
        defaultValue={name}
        maxLength={200}
        readOnly={!canEdit}
        required
      />
      <Field id="org-slug" label={t("settings.slug")} hint={t("settings.slugHint")} defaultValue={slug} readOnly />
      <Field id="org-region" label={t("settings.region")} defaultValue={t("settings.regionValue")} readOnly />
      {canEdit ? (
        <div>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      ) : null}
    </form>
  );
}
