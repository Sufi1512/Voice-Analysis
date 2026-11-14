// Matches Core's rule: 2-63 lowercase letters, digits or hyphens, not starting or ending with "-".
export const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])$/;

/** A suggested short name from an organization name ("Riyadh Health Co." -> "riyadh-health-co"). */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63)
    .replace(/-+$/g, "");
}
