// Shared by server (layouts) and client (the theme switch). Must not live in a "use client"
// module: a server component importing a value from one gets a client reference, not the value.
export const THEME_COOKIE = "nexora_theme";
export type Theme = "dark" | "light";

export function themeFrom(value: string | undefined): Theme {
  return value === "light" ? "light" : "dark"; // dark is the default
}
