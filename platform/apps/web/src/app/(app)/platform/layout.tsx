import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { getMe, getMyOrganizations } from "@/lib/core";

export default async function PlatformLayout({ children }: { children: ReactNode }) {
  const [me, orgs] = await Promise.all([getMe(), getMyOrganizations()]);
  if (!me?.is_platform_owner) notFound(); // the page doesn't exist for anyone else
  return (
    <AppShell me={me} orgs={orgs} org={null}>
      {children}
    </AppShell>
  );
}
