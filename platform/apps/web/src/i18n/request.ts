import { getRequestConfig } from "next-intl/server";
import { defaultLocale } from "./config";

export default getRequestConfig(async () => {
  const locale = defaultLocale;
  return {
    locale,
    // Data and customers are in Saudi Arabia; per-person time zones can come later.
    timeZone: "Asia/Riyadh",
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
