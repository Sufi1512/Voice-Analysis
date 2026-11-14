import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** Ruled, not carded: a panel on hairline rules with 10 px corners and an optional header row. */
export function Panel({
  title,
  titleId,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  titleId?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={title ? titleId : undefined}
      className={cx("overflow-hidden rounded-[var(--radius-panel)] border border-rule bg-panel", className)}
    >
      {title ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-[18px] py-3.5">
          <div className="flex flex-col gap-0.5">
            <h2 id={titleId} className="m-0 text-base font-semibold">
              {title}
            </h2>
            {description ? <p className="m-0 text-[13px] text-muted">{description}</p> : null}
          </div>
          {actions}
        </header>
      ) : null}
      {children}
    </section>
  );
}
