"use client";

import { useTranslations } from "next-intl";
import { type InputHTMLAttributes, type ReactNode, type Ref, useState } from "react";
import { Field } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";

type Props = InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement>; id: string; label: ReactNode; hint?: ReactNode; error?: ReactNode };

export function PasswordField(props: Props) {
  const t = useTranslations("common");
  const [visible, setVisible] = useState(false);
  return (
    <Field
      {...props}
      type={visible ? "text" : "password"}
      trailing={
        <button
          type="button"
          aria-pressed={visible}
          aria-label={visible ? t("hidePassword") : t("showPassword")}
          onClick={() => setVisible((v) => !v)}
          className="flex size-8 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-raised hover:text-text"
        >
          <Icon name={visible ? "eyeOff" : "eye"} />
        </button>
      }
    />
  );
}
