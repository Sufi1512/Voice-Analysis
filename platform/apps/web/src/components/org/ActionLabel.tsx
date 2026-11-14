import { getTranslations } from "next-intl/server";
import { actionKey, isKnownAction } from "./actions";

/** Plain words for an audit action (server). */
export async function actionLabel(action: string): Promise<string> {
  const t = await getTranslations("audit.actions");
  return isKnownAction(action) ? t(actionKey(action)) : t("other", { action });
}
