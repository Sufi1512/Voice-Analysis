"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Status";
import { api } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { actionKey, isKnownAction } from "./actions";

type Page = { items: AuditEntry[]; next_before: number | null };

export function AuditTable({ orgId, me, initial }: { orgId: string; me: string; initial: Page }) {
  const t = useTranslations("audit");
  const common = useTranslations("common");
  const format = useFormatter();
  const [items, setItems] = useState(initial.items);
  const [before, setBefore] = useState(initial.next_before);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function more() {
    if (before === null) return;
    setBusy(true);
    setFailed(false);
    const r = await api<Page>(`/v1/organizations/${encodeURIComponent(orgId)}/audit-logs?before=${before}`);
    setBusy(false);
    if (!r.ok) return setFailed(true);
    setItems((prev) => [...prev, ...r.data.items]);
    setBefore(r.data.next_before);
  }

  if (items.length === 0) return <p className="m-0 px-[18px] py-8 text-sm text-muted">{t("empty")}</p>;

  const th = "px-[18px] py-2.5 text-start text-xs font-medium text-faint";
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-rule">
              <th scope="col" className={th}>{t("when")}</th>
              <th scope="col" className={th}>{t("actor")}</th>
              <th scope="col" className={th}>{t("action")}</th>
              <th scope="col" className={th}>{t("target")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="nx-rise border-b border-rule-soft last:border-b-0">
                <td className="px-[18px] py-3 align-top whitespace-nowrap">
                  <time dateTime={e.occurred_at} className="font-mono text-xs text-muted tabular">
                    {format.dateTime(new Date(e.occurred_at), { dateStyle: "medium", timeStyle: "medium" })}
                  </time>
                </td>
                <td className="px-[18px] py-3 align-top">
                  {e.actor_type === "system" ? (
                    <span className="text-muted">{t("system")}</span>
                  ) : e.actor_id === me ? (
                    t("you")
                  ) : (
                    <span className="font-mono text-xs text-muted">{e.actor_id}</span>
                  )}
                </td>
                <td className="px-[18px] py-3 align-top">
                  {isKnownAction(e.action) ? t(`actions.${actionKey(e.action)}`) : t("actions.other", { action: e.action })}
                </td>
                <td className="px-[18px] py-3 align-top">
                  {e.target_id ? <span className="font-mono text-xs text-muted">{e.target_id}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {failed || before !== null ? (
        <div className="flex flex-col items-start gap-3 border-t border-rule px-[18px] py-3.5">
          {failed ? <Notice tone="critical">{common("networkError")}</Notice> : null}
          {before !== null ? (
            <Button onClick={more} disabled={busy}>
              {busy ? common("loading") : t("loadMore")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
