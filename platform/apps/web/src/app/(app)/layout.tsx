import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { getMe } from "@/lib/core";

const SESSION_COOKIE = "__Host-nexora_session";

/** Every page in here needs a session; the shell is rendered by each section's own layout. */
export default async function SignedInLayout({ children }: { children: ReactNode }) {
  const [me, jar] = await Promise.all([getMe(), cookies()]);
  // "Your session ended" only for someone who had one; a first visit just shows sign-in.
  if (!me) redirect(jar.has(SESSION_COOKIE) ? "/sign-in?expired=1" : "/sign-in");
  return children;
}
