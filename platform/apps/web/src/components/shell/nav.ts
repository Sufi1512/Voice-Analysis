import type { IconName } from "@/components/ui/Icon";
import type { Permission } from "@/lib/types";

export type NavItem = { key: "overview" | "auditLog" | "settings" | "organizations"; href: string; icon: IconName };
export type NavGroup = { key: "operate" | "govern" | "platform"; items: NavItem[] };

/** Only pages that exist in this release; items appear only when the role can open them. */
export function navigation(org: { id: string; permissions: Permission[] } | null, isPlatformOwner: boolean): NavGroup[] {
  const groups: NavGroup[] = [];
  if (org) {
    const base = `/o/${encodeURIComponent(org.id)}`;
    groups.push({ key: "operate", items: [{ key: "overview", href: base, icon: "overview" }] });
    const govern: NavItem[] = [];
    if (org.permissions.includes("audit:read")) govern.push({ key: "auditLog", href: `${base}/audit`, icon: "audit" });
    govern.push({ key: "settings", href: `${base}/settings`, icon: "settings" });
    groups.push({ key: "govern", items: govern });
  }
  if (isPlatformOwner) {
    groups.push({ key: "platform", items: [{ key: "organizations", href: "/platform", icon: "building" }] });
  }
  return groups;
}
