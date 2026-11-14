import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Icon, type IconName } from "./Icon";

export type Tone = "good" | "warn" | "critical" | "running" | "neutral";

const TONE: Record<Tone, { icon: IconName; className: string }> = {
  good: { icon: "check", className: "text-good" },
  warn: { icon: "warning", className: "text-warn" },
  critical: { icon: "error", className: "text-critical" },
  running: { icon: "running", className: "text-running" },
  neutral: { icon: "info", className: "text-muted" },
};

/** Meaning, never colour alone: every status has an icon and words. */
export function Status({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  const t = TONE[tone];
  return (
    <span className={cx("inline-flex items-center gap-2 text-[13px]", t.className, className)}>
      <Icon name={t.icon} size={14} strokeWidth={2.2} />
      <span>{children}</span>
    </span>
  );
}

/** An inline message above a form or list. Errors are announced immediately. */
export function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  const t = TONE[tone];
  return (
    <div
      role={tone === "critical" ? "alert" : "status"}
      className={cx(
        "flex items-start gap-2.5 rounded-[var(--radius-control)] border px-3 py-2.5 text-sm",
        tone === "critical" ? "border-critical/40 bg-critical/10" : "border-rule bg-raised",
      )}
    >
      <Icon name={t.icon} size={16} className={cx("mt-0.5 shrink-0", t.className)} />
      <div className="text-text">{children}</div>
    </div>
  );
}
