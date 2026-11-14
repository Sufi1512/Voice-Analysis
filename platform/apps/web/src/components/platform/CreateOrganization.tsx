"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Notice } from "@/components/ui/Status";
import { api } from "@/lib/api";
import { SLUG, slugify } from "@/lib/slug";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
type Errors = Partial<Record<"name" | "slug" | "ownerEmail", "required" | "slugInvalid" | "slugTaken" | "emailInvalid">>;

export function CreateOrganization() {
  const t = useTranslations();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const slugEdited = useRef(false);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<"emailFailed" | "unexpected" | "network" | null>(null);
  const [created, setCreated] = useState<{ name: string; email: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = {
      name: String(data.get("name") ?? "").trim(),
      slug: String(data.get("slug") ?? "").trim(),
      owner_email: String(data.get("owner_email") ?? "").trim(),
    };
    const next: Errors = {};
    if (!body.name) next.name = "required";
    if (!SLUG.test(body.slug)) next.slug = "slugInvalid";
    if (!EMAIL.test(body.owner_email)) next.ownerEmail = "emailInvalid";
    setErrors(next);
    setFailure(null);
    if (Object.keys(next).length) {
      form.querySelector<HTMLInputElement>("[aria-invalid=true]")?.focus();
      return;
    }
    setBusy(true);
    const r = await api("/v1/platform/organizations", { method: "POST", json: body });
    setBusy(false);
    if (r.ok) {
      setCreated({ name: body.name, email: body.owner_email });
      setOpen(false);
      setSlug("");
      slugEdited.current = false;
      router.refresh();
      return;
    }
    if (r.error === "slug_taken") setErrors({ slug: "slugTaken" });
    else setFailure(r.error === "email_failed" ? "emailFailed" : r.status === 0 ? "network" : "unexpected");
  }

  const message = (e: Errors[keyof Errors]) =>
    e === "required" ? t("common.required") : e ? t(`platform.${e}`) : undefined;

  return (
    <div className="flex flex-col gap-4">
      {created ? <Notice tone="good">{t("platform.created", created)}</Notice> : null}
      {open ? (
        <section aria-labelledby="new-org" className="nx-rise rounded-[var(--radius-panel)] border border-rule bg-panel">
          <header className="flex items-start justify-between gap-3 border-b border-rule px-[18px] py-3.5">
            <div>
              <h2 id="new-org" className="m-0 text-base font-semibold">
                {t("platform.createTitle")}
              </h2>
              <p className="m-0 mt-0.5 text-[13px] text-muted">{t("platform.createIntro")}</p>
            </div>
            <Button variant="ghost" onClick={() => setOpen(false)} aria-label={t("common.close")}>
              <Icon name="close" />
            </Button>
          </header>
          <form onSubmit={submit} noValidate className="grid max-w-3xl gap-5 px-[18px] py-5 md:grid-cols-2">
            {failure ? (
              <div className="md:col-span-2">
                <Notice tone="critical">
                  {failure === "emailFailed"
                    ? t("platform.emailFailed")
                    : failure === "network"
                      ? t("common.networkError")
                      : t("common.unexpected")}
                </Notice>
              </div>
            ) : null}
            <Field
              ref={firstField}
              id="org-name"
              name="name"
              label={t("platform.name")}
              error={message(errors.name)}
              maxLength={200}
              autoFocus
              onChange={(e) => {
                if (!slugEdited.current) setSlug(slugify(e.target.value));
              }}
            />
            <Field
              id="org-slug"
              name="slug"
              label={t("platform.slug")}
              hint={t("platform.slugHint")}
              error={message(errors.slug)}
              value={slug}
              onChange={(e) => {
                slugEdited.current = true;
                setSlug(e.target.value.toLowerCase());
              }}
              autoCapitalize="none"
              spellCheck={false}
              maxLength={63}
            />
            <Field
              id="org-owner"
              name="owner_email"
              type="email"
              label={t("platform.ownerEmail")}
              hint={t("platform.ownerEmailHint")}
              error={message(errors.ownerEmail)}
              autoComplete="off"
              className="md:col-span-2"
            />
            <div className="flex gap-2.5 md:col-span-2">
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? t("platform.submitting") : t("platform.submit")}
              </Button>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                {t("common.cancel")}
              </Button>
            </div>
          </form>
        </section>
      ) : (
        <div>
          <Button
            variant="primary"
            onClick={() => {
              setCreated(null);
              setErrors({});
              setFailure(null);
              setOpen(true);
            }}
          >
            <Icon name="plus" />
            {t("platform.create")}
          </Button>
        </div>
      )}
    </div>
  );
}
