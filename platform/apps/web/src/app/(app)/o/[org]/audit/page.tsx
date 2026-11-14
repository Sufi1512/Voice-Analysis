import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { AuditTable } from "@/components/org/AuditTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Notice } from "@/components/ui/Status";
import { core, getMe, getOrganization } from "@/lib/core";
import type { AuditEntry } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("audit"))("title") };
}

export default async function AuditLog({ params }: { params: Promise<{ org: string }> }) {
  const { org: orgId } = await params;
  const [org, me, t] = await Promise.all([getOrganization(orgId), getMe(), getTranslations("audit")]);
  if (!org || !me) notFound();
  if (!org.permissions.includes("audit:read")) {
    return (
      <>
        <PageHeader title={t("title")} />
        <Notice tone="neutral">{t("forbidden")}</Notice>
      </>
    );
  }
  const page = await core<{ items: AuditEntry[]; next_before: number | null }>(
    `/v1/organizations/${encodeURIComponent(org.id)}/audit-logs`,
  );
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("intro", { organization: org.name })} />
      <Panel>
        <AuditTable orgId={org.id} me={me.user.id} initial={page} />
      </Panel>
    </>
  );
}
