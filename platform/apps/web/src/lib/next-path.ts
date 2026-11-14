/** Where to go after signing in: only a path on this site (no //evil.example or /\evil.example). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}
