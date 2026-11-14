import { describe, expect, it } from "vitest";
import { SLUG, slugify } from "./slug";

describe("slugify", () => {
  it.each([
    ["Riyadh Health Co.", "riyadh-health-co"],
    ["  Jeddah   Bank  ", "jeddah-bank"],
    ["Café Résumé", "cafe-resume"],
    ["A".repeat(80), "a".repeat(63)],
  ])("%s -> %s", (input, out) => expect(slugify(input)).toBe(out));

  it("returns something Core accepts, or nothing (Arabic names need a typed short name)", () => {
    expect(SLUG.test(slugify("Dammam Energy"))).toBe(true);
    expect(slugify("شركة")).toBe("");
  });
});

describe("SLUG", () => {
  it.each(["ab", "a1-b2", "x".repeat(63)])("accepts %s", (s) => expect(SLUG.test(s)).toBe(true));
  it.each(["a", "-ab", "ab-", "Ab", "a b", "x".repeat(64)])("refuses %s", (s) => expect(SLUG.test(s)).toBe(false));
});
