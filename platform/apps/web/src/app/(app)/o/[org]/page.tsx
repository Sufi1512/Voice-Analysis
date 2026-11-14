import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";
import { actionLabel } from "@/components/org/ActionLabel";
import { ButtonLink } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Status, type Tone } from "@/components/ui/Status";
import { core, getMyOrganizations, getOrganization, getReadiness } from "@/lib/core";
import type { AuditEntry, Permission } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("overview"))("title") };
}

type Health = "good" | "down" | "unknown";
const PERMISSION_ORDER: Permission[] = [
  "organization:read",
  "organization:update",
  "workspace:read",
  "workspace:create",
  "member:read",
  "member:invite",
  "member:manage",
  "audit:read",
];
const TONE: Record<Health, Tone> = { good: "good", down: "critical", unknown: "neutral" };

export default async function Overview({ params }: { params: Promise<{ org: string }> }) {
  const { org: orgId } = await params;
  const org = await getOrganization(orgId);
  if (!org) notFound();
  const canAudit = org.permissions.includes("audit:read");
  const [t, status, roles, format, readiness, orgs, recent] = await Promise.all([
    getTranslations("overview"),
    getTranslations("status"),
    getTranslations("roles"),
    getFormatter(),
    getReadiness(),
    getMyOrganizations(),
    canAudit
      ? core<{ items: AuditEntry[] }>(`/v1/organizations/${encodeURIComponent(org.id)}/audit-logs?limit=5`).then(
          (r) => r.items,
        )
      : Promise.resolve(null),
  ]);
  const role = orgs.find((o) => o.id === org.id)?.role;
  const labels = recent ? await Promise.all(recent.map((e) => actionLabel(e.action))) : [];
  const health: Array<{ key: "coreService" | "database"; state: Health }> = [
    { key: "coreService", state: readiness.reachable ? "good" : "down" },
    {
      key: "database",
      state: readiness.database === "up" ? "good" : readiness.database === "down" ? "down" : "unknown",
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle", { organization: org.name })} />

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Panel
          title={t("health")}
          titleId="health"
          description={t("checkedAt", { time: format.dateTime(new Date(readiness.checkedAt), { timeStyle: "medium" }) })}
        >
          <dl className="m-0 divide-y divide-rule-soft">
            {health.map((row) => (
              <div key={row.key} className="flex items-center justify-between gap-4 px-[18px] py-3.5">
                <dt className="text-sm">{t(row.key)}</dt>
                <dd className="m-0">
                  <Status tone={TONE[row.state]}>{status(row.state)}</Status>
                </dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title={t("yourAccess")} titleId="access" description={role ? roles(role) : undefined}>
          <ul className="m-0 flex list-none flex-col gap-2 px-[18px] py-4">
            {PERMISSION_ORDER.filter((p) => org.permissions.includes(p)).map((p) => (
              <li key={p} className="flex items-center gap-2.5 text-sm">
                <Icon name="check" size={14} className="shrink-0 text-good" />
                {t(`permission.${p}`)}
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      {recent ? (
        <Panel
          title={t("recentActivity")}
          titleId="recent"
          actions={
            <ButtonLink href={`/o/${encodeURIComponent(org.id)}/audit`} variant="ghost">
              {t("viewAuditLog")}
            </ButtonLink>
          }
        >
          {recent.length === 0 ? (
            <p className="m-0 px-[18px] py-6 text-sm text-muted">{t("noActivity")}</p>
          ) : (
            <ol className="m-0 list-none divide-y divide-rule-soft p-0">
              {recent.map((entry, i) => (
                <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-[18px] py-3">
                  <span className="text-sm">{labels[i]}</span>
                  <time dateTime={entry.occurred_at} className="font-mono text-xs text-muted tabular">
                    {format.dateTime(new Date(entry.occurred_at), { dateStyle: "medium", timeStyle: "short" })}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      ) : null}
    </>
  );
}
