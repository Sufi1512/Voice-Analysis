import { getTranslations } from "next-intl/server";

/** The NEXORA mark: a voice signal (amber) on a panel tile, and the wordmark. */
export async function Logo({ size = 28 }: { size?: number }) {
  const t = await getTranslations("brand");
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
        <rect x="1" y="1" width="32" height="32" rx="8" fill="var(--nx-panel)" stroke="var(--nx-rule)" />
        <path
          d="M8 20 L12 14 L16 22 L20 10 L24 18 L27 15"
          fill="none"
          stroke="var(--nx-voice)"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-display text-lg font-semibold tracking-[0.04em] text-text">{t("name")}</span>
    </span>
  );
}
