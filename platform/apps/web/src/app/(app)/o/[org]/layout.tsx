import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { getMe, getMyOrganizations, getOrganization } from "@/lib/core";

export default async function OrganizationLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ org: string }>;
}) {
  const { org: orgId } = await params;
  const [me, orgs, org] = await Promise.all([getMe(), getMyOrganizations(), getOrganization(orgId)]);
  // Core answers 404 for organizations the person isn't in, whether or not they exist.
  if (!me || !org) notFound();
  return (
    <AppShell me={me} orgs={orgs} org={org}>
      {children}
    </AppShell>
  );
}
