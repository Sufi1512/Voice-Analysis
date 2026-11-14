import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SignInForm } from "@/components/auth/SignInForm";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("signIn"))("title") };
}

export default async function SignInPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const banner = params.signedOut ? "signedOut" : params.expired ? "sessionEnded" : null;
  return <SignInForm next={params.next ?? null} banner={banner} />;
}
