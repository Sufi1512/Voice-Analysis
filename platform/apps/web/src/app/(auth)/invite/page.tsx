import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { InviteClient } from "@/components/auth/InviteClient";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("invite"))("title"), referrer: "no-referrer" };
}

export default function InvitePage() {
  return <InviteClient />;
}
