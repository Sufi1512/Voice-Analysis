import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { SettingsForm } from "@/components/org/SettingsForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { getOrganization } from "@/lib/core";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("settings"))("title") };
}

export default async function Settings({ params }: { params: Promise<{ org: string }> }) {
  const { org: orgId } = await params;
  const [org, t] = await Promise.all([getOrganization(orgId), getTranslations("settings")]);
  if (!org) notFound();
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("intro", { organization: org.name })} />
      <Panel>
        <SettingsForm
          key={org.name}
          orgId={org.id}
          name={org.name}
          slug={org.slug}
          canEdit={org.permissions.includes("organization:update")}
        />
      </Panel>
    </>
  );
}
