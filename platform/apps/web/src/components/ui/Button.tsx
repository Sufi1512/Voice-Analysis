import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";
import { cx } from "@/lib/cx";

type Variant = "primary" | "secondary" | "ghost";

const BASE =
  "inline-flex h-10 items-center justify-center gap-2 rounded-[var(--radius-control)] px-4 text-sm font-medium whitespace-nowrap " +
  "transition-colors duration-[120ms] ease-[var(--ease-signal)] disabled:cursor-not-allowed disabled:opacity-60";

// One action colour: ion blue only for the main action of a screen.
const VARIANTS: Record<Variant, string> = {
  primary: "bg-action text-on-action hover:brightness-110",
  secondary: "border border-control bg-raised text-text hover:border-faint",
  ghost: "bg-transparent px-3 text-muted hover:bg-raised hover:text-text",
};

export function buttonClass(variant: Variant = "secondary", extra?: string) {
  return cx(BASE, VARIANTS[variant], extra);
}

export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button type={type} className={buttonClass(variant, className)} {...props} />;
}

export function ButtonLink({ variant = "secondary", className, ...props }: ComponentProps<typeof Link> & { variant?: Variant }) {
  return <Link className={buttonClass(variant, cx("hover:text-current", className))} {...props} />;
}
