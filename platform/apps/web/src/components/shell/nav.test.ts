import { describe, expect, it } from "vitest";
import { navigation } from "./nav";

describe("navigation", () => {
  it("shows the audit log only to roles that can read it", () => {
    const viewer = navigation({ id: "org_a", permissions: ["organization:read"] }, false);
    expect(viewer.flatMap((g) => g.items.map((i) => i.key))).toEqual(["overview", "settings"]);
    const admin = navigation({ id: "org_a", permissions: ["organization:read", "audit:read"] }, false);
    expect(admin.flatMap((g) => g.items.map((i) => i.href))).toEqual(["/o/org_a", "/o/org_a/audit", "/o/org_a/settings"]);
  });
  it("adds Platform only for the platform owner", () => {
    expect(navigation(null, false)).toEqual([]);
    expect(navigation(null, true)).toEqual([{ key: "platform", items: [{ key: "organizations", href: "/platform", icon: "building" }] }]);
  });
});
