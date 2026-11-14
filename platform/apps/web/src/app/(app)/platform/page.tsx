import type { Metadata } from "next";
import { getFormatter, getTranslations } from "next-intl/server";
import { CreateOrganization } from "@/components/platform/CreateOrganization";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Status } from "@/components/ui/Status";
import { core } from "@/lib/core";
import type { PlatformOrganization } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("platform"))("title") };
}

export default async function PlatformOrganizations() {
  const [t, format, { items }] = await Promise.all([
    getTranslations("platform"),
    getFormatter(),
    core<{ items: PlatformOrganization[] }>("/v1/platform/organizations"),
  ]);
  const th = (align: "start" | "end" = "start") =>
    `px-[18px] py-2.5 text-xs font-medium text-faint ${align === "end" ? "text-end" : "text-start"}`;
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("intro")} />
      <CreateOrganization />
      <Panel>
        {items.length === 0 ? (
          <p className="m-0 px-[18px] py-8 text-sm text-muted">{t("empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-rule">
                  <th scope="col" className={th()}>{t("columns.name")}</th>
                  <th scope="col" className={th()}>{t("columns.slug")}</th>
                  <th scope="col" className={th("end")}>{t("columns.members")}</th>
                  <th scope="col" className={th()}>{t("columns.status")}</th>
                  <th scope="col" className={th()}>{t("columns.created")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((o) => (
                  <tr key={o.id} className="border-b border-rule-soft last:border-b-0">
                    <td className="px-[18px] py-3 font-medium">{o.name}</td>
                    <td className="px-[18px] py-3 font-mono text-xs text-muted">{o.slug}</td>
                    <td className="px-[18px] py-3 text-end tabular">{format.number(o.members)}</td>
                    <td className="px-[18px] py-3">
                      <Status tone={o.status === "active" ? "good" : "warn"}>{t(`statusValue.${o.status}`)}</Status>
                    </td>
                    <td className="px-[18px] py-3 text-muted">
                      <time dateTime={o.created_at}>{format.dateTime(new Date(o.created_at), { dateStyle: "medium" })}</time>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
