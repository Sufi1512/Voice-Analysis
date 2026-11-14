import type messages from "../messages/en.json";
import type { Locale } from "./i18n/config";

// Every translation key used in code must exist in messages/en.json (checked by tsc).
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: typeof messages;
  }
}
