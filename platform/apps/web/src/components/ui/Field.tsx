import type { InputHTMLAttributes, ReactNode, Ref } from "react";
import { cx } from "@/lib/cx";
import { Icon } from "./Icon";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  ref?: Ref<HTMLInputElement>;
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  trailing?: ReactNode;
};

export const inputClass =
  "h-10 w-full min-w-0 rounded-[var(--radius-control)] border border-control bg-canvas px-3 text-sm text-text " +
  "placeholder:text-faint transition-colors duration-[120ms] hover:border-faint " +
  "aria-[invalid=true]:border-critical read-only:bg-raised read-only:text-muted";

/** A labelled input with its hint and error right below it (errors next to the field). */
export function Field({ id, label, hint, error, trailing, className, ...input }: Props) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-text">
        {label}
      </label>
      <div className="relative flex items-center">
        <input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={[errorId, hintId].filter(Boolean).join(" ") || undefined}
          className={cx(inputClass, trailing ? "pe-11" : undefined)}
          {...input}
        />
        {trailing ? <div className="absolute end-1 flex">{trailing}</div> : null}
      </div>
      {error ? (
        <p id={errorId} className="flex items-start gap-1.5 text-[13px] text-critical">
          <Icon name="error" size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </p>
      ) : null}
      {hint ? (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
